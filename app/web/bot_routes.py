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
from app.bot.snapshot import _closed_ms, _day_start_ms, _f, paces_view, proof_of, risk_view, snapshot
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
        trades = repo.recent_trades(engine.mode, limit=5000)
        day = _day_start_ms()
        floor = {"today": day, "week": day - 6 * 86_400_000, "all": 0}[range]
        rows = [t for t in trades if _closed_ms(t) >= floor]
        fills = [{"id": t.get("id"), "symbol": t.get("symbol"), "side": "long", "qty": t.get("quantity"),
                  "entry": t.get("entry_price"), "exit": t.get("exit_price"),
                  "opened_at": None, "closed_at": _closed_ms(t) or None, "minutes": None,
                  "pnl": _f(t.get("pnl")), "pct": _f(t.get("pnl_pct")), "fees": 0.0,
                  "reason": t.get("exit_reason"), "book": None} for t in rows]
        pnls = [f["pnl"] for f in fills]
        won, lost = sum(p for p in pnls if p > 0), -sum(p for p in pnls if p < 0)
        return {"range": range, "fills": fills,
                "sum": {"count": len(fills), "wins": sum(1 for p in pnls if p > 0), "pnl": round(sum(pnls), 2),
                        "fees": 0.0, "best": max(pnls, default=0.0), "worst": min(pnls, default=0.0),
                        "profit_factor": round(won / lost, 2) if lost else None, "avg_minutes": None},
                "curve": []}

    return router
