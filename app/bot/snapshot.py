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


def _iso_ms(raw) -> int | None:
    if not raw:
        return None
    try:
        return int(datetime.fromisoformat(str(raw).replace("Z", "+00:00")).timestamp() * 1000)
    except ValueError:
        return None


def _cash(balance) -> float:
    if isinstance(balance, dict):
        for key in ("cash", "free", "available"):
            if balance.get(key) is not None:
                return _f(balance[key])
        return 0.0
    return _f(balance)


def _day_start_ms() -> int:
    now = datetime.now(NY)
    return int(now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)


def _closed_ms(trade: dict) -> int:
    raw = trade.get("exit_time") or trade.get("closed_at") or ""
    try:
        return int(datetime.fromisoformat(str(raw).replace("Z", "+00:00")).timestamp() * 1000)
    except ValueError:
        return 0


WORK_S, VETO_S = 8, 30


def crew_state(engine, agent_log, cid: str, queue: list[dict], now_ms: int) -> str:
    """off | error | veto | work | wait | idle, from what really happened (docs: A1.2)."""
    if not engine.status_running():
        return "off"
    last = agent_log.last_of(cid) if agent_log else None
    if last and last["verb"] == "error" and now_ms - last["at"] < 5 * 60_000:
        return "error"
    if last and last["verb"] == "veto" and now_ms - last["at"] < VETO_S * 1000:
        return "veto"
    if last and now_ms - last["at"] < WORK_S * 1000:
        return "work"
    if any(q.get("by") == cid for q in queue):
        return "wait"
    return "idle"


def queue_of(engine, turkish: bool) -> list[dict]:
    """What is waiting: approvals, news ideas waiting for the price, and Ultra's best charts."""
    out: list[dict] = []
    try:
        for p in engine.proposals.pending("approval"):
            out.append({"id": f"p_{p.id}", "symbol": p.intent.symbol, "kind": "approval", "score": None, "votes": None,
                        "state": "approval", "why": p.intent.reason[:140], "by": "titan",
                        "since": _ms(p.created_at), "expires_at": _ms(p.expires_at)})
    except Exception:
        pass
    reflex = getattr(engine, "reflex", None)
    for w in list(getattr(reflex, "pending", []) or [])[:5]:
        try:
            out.append({"id": f"n_{w.idea.symbol}_{int(w.published)}", "symbol": w.idea.symbol, "kind": "news",
                        "score": round(float(w.idea.confidence), 2), "votes": None, "state": "waiting",
                        "why": (w.decision.title or w.idea.why)[:140], "by": "titan",
                        "since": int(w.published * 1000), "expires_at": int(w.until * 1000)})
        except Exception:
            continue
    sc = getattr(engine, "scalper", None)
    if sc is not None and getattr(engine, "ultra", False):
        blocked = bool(getattr(sc, "state", ""))
        for r in list(getattr(sc, "radar", []) or [])[:5]:
            out.append({"id": f"u_{r['symbol']}", "symbol": r["symbol"], "kind": r.get("setup") or "dip",
                        "score": r.get("score"), "votes": f"{r.get('vote', 0)}/8",
                        "state": "blocked" if blocked else "waiting",
                        "why": sc.state if blocked else ("Best chart now" if not turkish else "Şu anki en iyi grafik"),
                        "by": "nova" if blocked else "orion", "since": None, "expires_at": None})
    return out


def _owner(engine) -> dict:
    s = getattr(engine, "bot_settings", None)
    return s.all() if s is not None else {"pace": "balanced"}


def risk_view(engine, engine_max: int, turkish: bool) -> dict:
    """The owner's limits as they are, and how much of the day's loss limit is used."""
    v = _owner(engine)
    try:
        realized = float(getattr(engine.risk, "_daily_realized_pnl", 0.0) or 0.0)
    except Exception:
        realized = 0.0
    used = round(max(-realized, 0.0), 2)
    paused = None
    if v.get("daily_loss") is not None and used >= float(v["daily_loss"]):
        paused = "Daily loss limit reached: no new buys today" if not turkish else "Günlük zarar sınırı doldu: bugün yeni alım yok"
    most = v.get("max_positions")
    return {"budget": v.get("budget"), "per_trade_pct": v.get("per_trade_pct"), "daily_loss": v.get("daily_loss"),
            "max_positions": min(engine_max, int(most)) if most and engine_max else (most or engine_max),
            "daily_loss_used": used, "paused": paused, "pace": v.get("pace") or "balanced"}


def paces_view(engine) -> dict:
    """Each pace's thresholds and its own Lab replay (GET /api/bot/paces)."""
    from app.bot import pace as P
    from app.engine.lab import PACE_RULE

    lab = getattr(engine, "lab", None)
    try:
        report = (lab.status() or {}).get("report") or {} if lab is not None else {}
    except Exception:
        report = {}
    out = []
    for pid in P.IDS:
        m = (report.get("rules") or {}).get(PACE_RULE[pid]) or {}
        pf = (m.get("portfolio") or {})
        out.append({**P.get(pid).to_dict(), "proof": _verdict(m, report),
                    "max_drawdown_pct": pf.get("max_drawdown")})
    return {"pace": _owner(engine).get("pace") or "balanced", "paces": out}


def _verdict(m: dict, report: dict) -> dict:
    out = {"state": "untested", "per_trade_pct": None, "profit_factor": None, "trades": 0,
           "days": len(report.get("days") or []), "ran_at": None}
    if not m:
        return out
    try:
        ran_ms = int(datetime.fromisoformat(report["ran_at"]).timestamp() * 1000)
    except (KeyError, TypeError, ValueError):
        ran_ms = None
    trades, avg, pf = int(m.get("trades") or 0), m.get("avg"), m.get("profit_factor")
    if trades < 60:
        state = "untested"
    elif (pf or 0) >= 1.2 and (avg or 0) >= 0.05:
        state = "passed"
    else:
        state = "lost"
    if ran_ms and time.time() * 1000 - ran_ms > 48 * 3_600_000:
        state = "stale"
    return {**out, "state": state, "per_trade_pct": avg, "profit_factor": pf, "trades": trades, "ran_at": ran_ms}


def proof_of(engine) -> dict:
    """The Lab's last replay of the pace that runs now (balanced is the 9.0 rule)."""
    from app.engine.lab import PACE_RULE

    pace = _owner(engine).get("pace") or "balanced"
    out = {"rule": "ultra-9.0" if pace == "balanced" else f"ultra-{pace}", "state": "untested", "per_trade_pct": None,
           "profit_factor": None, "trades": 0, "days": 0, "ran_at": None}
    lab = getattr(engine, "lab", None)
    try:
        report = (lab.status() or {}).get("report") or {} if lab is not None else {}
    except Exception:
        report = {}
    m = (report.get("rules") or {}).get(PACE_RULE.get(pace, "9.0"))
    v = _verdict(m or {}, report)
    return {**out, **{k: v[k] for k in ("state", "per_trade_pct", "profit_factor", "trades", "ran_at")},
            "days": v["days"] if m else 0}


def day_start_equity(engine, equity: float) -> float | None:
    if not equity:
        return None
    today = datetime.now(NY).strftime("%Y-%m-%d")
    seen = getattr(engine, "_bot_day", None)
    if not seen or seen.get("day") != today:
        seen = {"day": today, "equity": round(equity, 2)}
        engine._bot_day = seen
        path = getattr(getattr(engine, "agent_log", None), "path", None)
        if path is not None:
            try:
                import json

                day_file = path.parent / "day.json"
                old = json.loads(day_file.read_text(encoding="utf-8")) if day_file.exists() else {}
                if old.get("day") == today and old.get("equity"):
                    seen = engine._bot_day = {"day": today, "equity": float(old["equity"])}
                else:
                    day_file.parent.mkdir(parents=True, exist_ok=True)
                    day_file.write_text(json.dumps(seen), encoding="utf-8")
            except (OSError, ValueError):
                pass
    return seen["equity"]


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

    queue = queue_of(engine, turkish)
    now_ms = int(time.time() * 1000)
    crew = []
    for cid, name, role, labels in CREW:
        last = agent_log.last_of(cid) if agent_log else None
        crew.append({"id": cid, "name": name, "role": role, "role_label": labels[1 if turkish else 0],
                     "state": crew_state(engine, agent_log, cid, queue, now_ms),
                     "last": last["text"] if last else None, "last_at": last["at"] if last else None,
                     "today": {"lines": agent_log.count_today(cid, day) if agent_log else 0,
                               "acted": agent_log.count_today(cid, day, acted=True) if agent_log else 0}})

    # The right panel's symbol: an open position, else the head of the queue, else the last trade.
    t = (lambda en, tr: tr if turkish else en)
    focus = None
    if positions:
        p = positions[-1]
        focus = {"kind": "position", "symbol": p.get("symbol"), "why": t("open position", "açık pozisyon"),
                 "entry": _f(p.get("entry_price")), "stop": p.get("stop_loss"), "target": p.get("take_profit"),
                 "qty": p.get("quantity", p.get("qty")), "pnl": _f(p.get("unrealized_pnl")),
                 "pnl_pct": _f(p.get("unrealized_pnl_pct")), "opened_at": _iso_ms(p.get("entry_time") or p.get("opened_at"))}
    elif queue:
        q = queue[0]
        focus = {"kind": "queue", "symbol": q["symbol"], "why": t("next in the queue", "sırada"), "entry": None,
                 "stop": None, "target": None, "qty": None, "pnl": None, "pnl_pct": None, "opened_at": None}
    elif today:
        focus = {"kind": "last", "symbol": today[0].get("symbol"), "why": t("last trade", "son işlem"), "entry": None,
                 "stop": None, "target": None, "qty": None, "pnl": _f(today[0].get("pnl")),
                 "pnl_pct": _f(today[0].get("pnl_pct")), "opened_at": None}

    start_today = day_start_equity(engine, equity)
    funnel = getattr(engine, "funnel", None)

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
            "net": {"today": round(sum(_f(t.get("pnl")) for t in today), 2),
                    "today_pct": round(sum(_f(t.get("pnl")) for t in today) / start_today * 100, 2) if start_today else 0.0,
                    "unrealized": round(unrealized, 2),
                    "week": round(sum(_f(t.get("pnl")) for t in week), 2),
                    "all": round(sum(_f(t.get("pnl")) for t in trades), 2), "fees_today": 0.0, "since": None},
            "capital": {"start_today": start_today, "equity": equity, "cash": _cash(status.get("balance")),
                        "budget": _owner(engine).get("budget")},
        },
        "crew": crew,
        "queue": queue,
        "funnel": funnel.view(turkish) if funnel is not None else
        {"day": datetime.now(NY).strftime("%Y-%m-%d"), "steps": [], "blocked": []},
        "focus": focus,
        "risk": risk_view(engine, max_pos, turkish),
        "proof": proof_of(engine),
        "log_head": agent_log.head if agent_log else 0,
        "at": int(time.time() * 1000),
    }
