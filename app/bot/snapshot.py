"""GET /api/bot: the whole console in one answer (the contract is docs' section 4
and tests/fixtures/bot_snapshot.json; tests/test_bot_contract.py holds them together).

12.0 M0: the shape is final. The queue, the funnel, the pace and the day's
start capital are filled in by M1 and M3; until then they are empty, not invented.
"""
from __future__ import annotations

import time
from datetime import datetime
from zoneinfo import ZoneInfo

from app import __version__
from app.bot.crew import CREW

NY = ZoneInfo("America/New_York")
NAME = "Money Bot"


def _ms(when) -> int | None:
    try:
        return int(when.timestamp() * 1000)
    except Exception:
        return None


def _f(v, default: float = 0.0) -> float:
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return default


def _day_start_ms() -> int:
    now = datetime.now(NY)
    return int(now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)


def _closed_ms(trade: dict) -> int:
    raw = trade.get("exit_time") or trade.get("closed_at") or ""
    try:
        return int(datetime.fromisoformat(str(raw).replace("Z", "+00:00")).timestamp() * 1000)
    except ValueError:
        return 0


def snapshot(engine, agent_log, turkish: bool = False) -> dict:
    status = engine.status()
    ultra = bool(status.get("ultra"))
    risk = status.get("risk") if isinstance(status.get("risk"), dict) else {}
    positions = status.get("positions") or []
    day = _day_start_ms()

    try:
        market = engine.clock.state()
        is_open = bool(market.is_open)
        change = getattr(market, "next_close" if is_open else "next_open", None)
        words = engine.words()
        label = words.market_open(change) if is_open else words.market_closed(change)
    except Exception:
        is_open, change, label = False, None, ""

    try:
        trades = engine.repo.recent_trades(engine.mode, limit=500)
    except Exception:
        trades = []
    today = [t for t in trades if _closed_ms(t) >= day]
    week = [t for t in trades if _closed_ms(t) >= day - 6 * 86_400_000]
    unrealized = sum(_f(p.get("unrealized_pnl")) for p in positions)

    from app.engine import scalper

    max_fills = scalper.MAX_ENTRIES if ultra else 0
    max_pos = scalper.SLOTS if ultra else int(getattr(engine.config.risk, "max_open_positions", 0) or 0)
    equity = _f(status.get("equity"))

    crew = []
    for cid, name, role, labels in CREW:
        last = agent_log.last_of(cid) if agent_log else None
        crew.append({"id": cid, "name": name, "role": role, "role_label": labels[1 if turkish else 0],
                     "state": "idle" if status.get("running") else "off",
                     "last": last["text"] if last else None, "last_at": last["at"] if last else None,
                     "today": {"lines": agent_log.count_today(cid, day) if agent_log else 0, "acted": 0}})

    focus = None
    if positions:
        p = positions[-1]
        focus = {"symbol": p.get("symbol"), "why": "open position", "entry": _f(p.get("entry_price")),
                 "stop": p.get("stop_loss"), "target": p.get("take_profit"),
                 "qty": p.get("quantity", p.get("qty")), "pnl": _f(p.get("unrealized_pnl")),
                 "pnl_pct": _f(p.get("unrealized_pnl_pct")), "opened_at": None}
    elif today:
        focus = {"symbol": today[0].get("symbol"), "why": "last trade", "entry": None, "stop": None, "target": None,
                 "qty": None, "pnl": _f(today[0].get("pnl")), "pnl_pct": _f(today[0].get("pnl_pct")), "opened_at": None}

    lab = getattr(engine, "lab", None)
    proof = {"rule": "ultra-9.0", "state": "untested", "per_trade_pct": None, "profit_factor": None,
             "trades": 0, "days": 0, "ran_at": None}

    return {
        "name": NAME,
        "version": __version__,
        "account": {"mode": "paper" if str(status.get("mode")) == "paper" else "live",
                    "armed": bool(risk.get("armed", False)), "halted": bool(status.get("halted")),
                    "engine": "running" if status.get("running") else "stopped",
                    "book": "ultra" if ultra else "balanced"},
        "market": {"open": is_open, "label": label, "next_change_at": _ms(change)},
        "tiles": {
            "fills": {"closed": len(today), "max": max_fills, "opened": len(today) + len(positions)},
            "positions": {"open": len(positions), "max": max_pos},
            "net": {"today": round(sum(_f(t.get("pnl")) for t in today), 2), "today_pct": 0.0,
                    "unrealized": round(unrealized, 2),
                    "week": round(sum(_f(t.get("pnl")) for t in week), 2),
                    "all": round(sum(_f(t.get("pnl")) for t in trades), 2), "fees_today": 0.0, "since": None},
            "capital": {"start_today": None, "equity": equity, "cash": _f(status.get("balance")), "budget": None},
        },
        "crew": crew,
        "queue": [],
        "funnel": {"day": datetime.now(NY).strftime("%Y-%m-%d"), "steps": [], "blocked": []},
        "focus": focus,
        "risk": {"budget": None, "per_trade_pct": None, "daily_loss": None, "max_positions": max_pos,
                 "daily_loss_used": 0.0, "paused": None, "pace": "balanced"},
        "proof": proof if lab is None else {**proof, "ran_at": None},
        "log_head": agent_log.head if agent_log else 0,
        "at": int(time.time() * 1000),
    }
