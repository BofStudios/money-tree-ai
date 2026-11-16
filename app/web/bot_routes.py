"""Money Bot's console (12.0).

  GET  /api/bot          the whole console: tiles, crew, queue, funnel, focus, risk, proof
  GET  /api/bot/log      agent.log lines after a number (tab: orders | risk)
  GET  /api/bot/ledger   the finished trades of today, the week or all time

Read-only. Nothing here trades, arms or changes a limit.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.bot import log as botlog
from app.bot.snapshot import _closed_ms, _day_start_ms, _f, snapshot
from app.web.auth import Auth


def build_bot_router(engine, repo, events, token) -> APIRouter:
    router = APIRouter(prefix="/api/bot")
    auth = token if isinstance(token, Auth) else Auth(token)
    guarded = [Depends(auth.guard())]

    agent_log = getattr(engine, "agent_log", None)
    if agent_log is None:
        agent_log = botlog.AgentLog(botlog.default_path(), events)
        engine.agent_log = agent_log

    def turkish(lang: str | None) -> bool:
        return (lang or getattr(engine, "language", "en")) == "tr"

    @router.get("", dependencies=guarded)
    def bot(lang: str | None = Query(default=None)) -> dict:
        return snapshot(engine, agent_log, turkish(lang))

    @router.get("/log", dependencies=guarded)
    def log_lines(after: int = Query(default=0, ge=0), limit: int = Query(default=200, ge=1, le=500),
                  agent: str | None = Query(default=None), tab: str | None = Query(default=None)) -> dict:
        return {"head": agent_log.head, "lines": agent_log.lines(after, limit, agent, tab)}

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
