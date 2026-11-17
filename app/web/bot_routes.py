"""Money Bot's console (12.0).

  GET  /api/bot          the whole console: tiles, crew, queue, funnel, focus, risk, proof
  GET  /api/bot/log      agent.log lines after a number (tab: orders | risk)
  GET  /api/bot/ledger   the finished trades of today, the week or all time

Read-only. Nothing here trades, arms or changes a limit.
"""
from __future__ import annotations

import logging
import threading
import time

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from app.bot import log as botlog
from app.bot.settings import NeedsConfirm
from app.bot.snapshot import paces_view, proof_of, risk_view, snapshot
from app.web.auth import Auth

log = logging.getLogger(__name__)
BOT_TRIGGERS = {"bot_log", "status", "trade_opened", "trade_closed", "intent", "proposal_resolved", "approval_needed"}


def build_bot_router(engine, repo, events, token) -> APIRouter:
    router = APIRouter(prefix="/api/bot")
    auth = token if isinstance(token, Auth) else Auth(token)
    guarded = [Depends(auth.guard())]
    owner = [Depends(auth.owner("The bot's limits can only be changed on the PC running the bot."))]

    agent_log = getattr(engine, "agent_log", None)
    if agent_log is None:
        agent_log = botlog.AgentLog(botlog.default_path(), events)
        engine.agent_log = agent_log

    def turkish(lang: str | None) -> bool:
        return (lang or getattr(engine, "language", "en")) == "tr"

    # The live "bot" event: something happened -> at most one fresh console a second.
    # The snapshot can ask the broker, so it is made on its own thread, never on the
    # thread that published the event.
    if events is not None and not getattr(engine, "_bot_publisher", None):
        wake = threading.Event()

        def on_event(event: dict) -> None:
            if event.get("type") in BOT_TRIGGERS:
                wake.set()

        def publisher() -> None:
            while True:
                wake.wait()
                wake.clear()
                try:
                    snap = snapshot(engine, agent_log, turkish(None))
                    events.publish("bot", {k: snap[k] for k in ("account", "tiles", "crew", "queue", "focus", "risk", "funnel")})
                except Exception:
                    log.debug("could not make the bot event", exc_info=True)
                time.sleep(1.0)

        events.subscribe(on_event)
        engine._bot_publisher = threading.Thread(target=publisher, name="bot-event", daemon=True)
        engine._bot_publisher.start()

    @router.get("", dependencies=guarded)
    def bot(lang: str | None = Query(default=None)) -> dict:
        return snapshot(engine, agent_log, turkish(lang))

    def settings():
        s = getattr(engine, "bot_settings", None)
        if s is None:
            raise HTTPException(status_code=503, detail="The bot's settings are not ready.")
        return s

    def change(body: dict) -> dict:
        try:
            equity = float(engine.executor.get_balance().total)
        except Exception:
            equity = 0.0
        live = bool(getattr(engine.risk, "is_live", False))
        try:
            values, clamped = settings().update(body, equity, live, confirm=bool(body.get("confirm")))
        except NeedsConfirm as exc:
            raise HTTPException(status_code=409, detail=f"On real money, loosening needs confirm=true: {exc}") from None
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        events.publish("status", engine.status()) if events is not None else None
        return {"ok": True, "values": values, "clamped": clamped}

    @router.post("/risk", dependencies=owner)
    def set_risk(body: dict = Body(default={})) -> dict:
        allowed = {"budget", "per_trade_pct", "daily_loss", "max_positions", "confirm"}
        if not body or set(body) - allowed:
            raise HTTPException(status_code=400, detail="Send budget, per_trade_pct, daily_loss or max_positions (null removes one).")
        done = change(body)
        from app.engine import scalper

        return {**done, "risk": risk_view(engine, scalper.SLOTS if getattr(engine, "ultra", False) else
                                           int(engine.config.risk.max_open_positions), turkish(None))}

    @router.post("/pace", dependencies=owner)
    def set_pace(body: dict = Body(default={})) -> dict:
        if body.get("pace") not in ("calm", "balanced", "aggressive"):
            raise HTTPException(status_code=400, detail="pace must be calm, balanced or aggressive")
        done = change({"pace": body["pace"], "confirm": body.get("confirm")})
        return {**done, "proof": proof_of(engine)}

    @router.post("/planner", dependencies=owner)
    def set_planner(body: dict = Body(default={})) -> dict:
        if not isinstance(body.get("on"), bool):
            raise HTTPException(status_code=400, detail='Send {"on": true} or {"on": false}.')
        return change({"planner": body["on"]})

    @router.get("/paces", dependencies=guarded)
    def paces() -> dict:
        return paces_view(engine)

    @router.get("/log", dependencies=guarded)
    def log_lines(after: int = Query(default=0, ge=0), limit: int = Query(default=200, ge=1, le=500),
                  agent: str | None = Query(default=None), tab: str | None = Query(default=None),
                  before: int | None = Query(default=None, ge=1)) -> dict:
        return {"head": agent_log.head, "lines": agent_log.lines(after, limit, agent, tab, before)}

    @router.get("/ledger", dependencies=guarded)
    def ledger(range: str = Query(default="today", pattern="^(today|week|all)$")) -> dict:
        from app.bot.ledger import ledger as book

        return book(repo, engine.mode, range)

    return router
