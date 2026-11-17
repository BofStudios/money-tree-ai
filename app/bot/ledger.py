"""The ledger (12.0): finished trades of today, the week or all time, with one set of sums.

The console's ledger tab and Telegram's end-of-day message read the same
function, so they always show the same numbers. Times are New York days.
"""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
RANGES = ("today", "week", "all")


def to_ms(raw) -> int | None:
    """An ISO time from the database as epoch ms; a time without a zone is UTC."""
    if not raw:
        return None
    try:
        t = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return int(t.timestamp() * 1000)


def day_start_ms(now: datetime | None = None) -> int:
    now = (now or datetime.now(NY)).astimezone(NY)
    return int(now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)


def _f(v) -> float:
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return 0.0


def ledger(repo, mode: str, range_: str = "today", now: datetime | None = None) -> dict:
    trades = repo.recent_trades(mode, limit=5000)
    day = day_start_ms(now)
    floor = {"today": day, "week": day - 6 * 86_400_000, "all": 0}[range_]
    fills = []
    for i, t in enumerate(trades):
        closed, opened = to_ms(t.get("closed_at")), to_ms(t.get("opened_at"))
        if (closed or 0) < floor:
            continue
        reason = str(t.get("exit_reason") or "")
        fills.append({
            "id": t.get("id", f"{t.get('symbol')}-{closed}"), "symbol": t.get("symbol"), "side": t.get("side") or "long",
            "qty": t.get("qty", t.get("quantity")), "entry": t.get("entry_price"), "exit": t.get("exit_price"),
            "opened_at": opened, "closed_at": closed,
            "minutes": round((closed - opened) / 60000) if closed and opened else None,
            "pnl": _f(t.get("pnl")), "pct": _f(t.get("pnl_pct")), "fees": 0.0, "reason": reason,
            "book": "ultra" if reason.startswith("Scalp: ") else None,
        })
    pnls = [f["pnl"] for f in fills]
    won, lost = sum(p for p in pnls if p > 0), -sum(p for p in pnls if p < 0)
    minutes = [f["minutes"] for f in fills if f["minutes"] is not None]
    curve = []
    if range_ != "all":
        try:
            days = 1 if range_ == "today" else 7
            curve = [[p["time"] * 1000, p["value"]] for p in repo.equity_curve(mode, days=days) if p["time"] * 1000 >= floor]
        except Exception:
            curve = []
    return {"range": range_, "fills": fills,
            "sum": {"count": len(fills), "wins": sum(1 for p in pnls if p > 0), "pnl": round(sum(pnls), 2),
                    "fees": 0.0, "best": max(pnls, default=0.0), "worst": min(pnls, default=0.0),
                    "profit_factor": round(won / lost, 2) if lost else None,
                    "avg_minutes": round(sum(minutes) / len(minutes)) if minutes else None},
            "curve": curve}
