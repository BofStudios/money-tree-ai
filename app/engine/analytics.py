"""Analytics (10.0): what the real, finished trades say.

The numbers the serious bots show (Jesse's metrics, Freqtrade's /profit and
per-pair tables), from Money Tree's own trade history and equity snapshots:

  money      net profit, profit factor, expectancy ($ per trade), win rate,
             average win and loss, best and worst
  risk       max drawdown of the equity curve, Sharpe and Sortino of the
             daily returns (none with fewer than three days)
  where      by book (Ultra, long, swing, short, strategy), by New York hour,
             by weekday, by symbol
  streaks    the longest run of wins and of losses, and the current one
  days       profit or loss of each day, for the calendar

Read-only: nothing here changes a rule or a trade.
"""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.engine.lab import max_drawdown, ratios

NY = ZoneInfo("America/New_York")
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def book_of(trade: dict) -> str:
    reason = trade.get("entry_reason") or ""
    if reason.startswith("Scalp: "):
        return "ultra"
    if reason.startswith("Long-term: "):
        return "long"
    if reason.startswith("Swing: "):
        return "swing"
    if (trade.get("side") or "").lower() in ("short", "sell"):
        return "short"
    return "strategy"


def _ny(iso: str) -> datetime | None:
    try:
        t = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)      # the database keeps UTC without a zone
    return t.astimezone(NY)


def _money(pnls: list[float]) -> dict:
    n = len(pnls)
    if not n:
        return {"trades": 0, "net": 0.0, "win_rate": None, "profit_factor": None, "expectancy": None,
                "avg_win": None, "avg_loss": None, "best": None, "worst": None}
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    gross_loss = -sum(losses)
    return {
        "trades": n,
        "net": round(sum(pnls), 2),
        "win_rate": round(100 * len(wins) / n, 1),
        "profit_factor": round(sum(wins) / gross_loss, 2) if gross_loss > 0 else None,
        "expectancy": round(sum(pnls) / n, 3),
        "avg_win": round(sum(wins) / len(wins), 2) if wins else None,
        "avg_loss": round(sum(losses) / len(losses), 2) if losses else None,
        "best": round(max(pnls), 2),
        "worst": round(min(pnls), 2),
    }


def _group(trades: list[dict], key) -> list[dict]:
    groups: dict = {}
    for t in trades:
        k = key(t)
        if k is not None:
            groups.setdefault(k, []).append(t["pnl"])
    rows = []
    for k, p in groups.items():
        m = _money(p)
        rows.append({"key": k, "trades": m["trades"], "net": m["net"], "win_rate": m["win_rate"],
                     "profit_factor": m["profit_factor"]})
    return rows


def streaks(pnls_oldest_first: list[float]) -> dict:
    best_w = best_l = run = 0
    for p in pnls_oldest_first:
        if p > 0:
            run = run + 1 if run > 0 else 1
            best_w = max(best_w, run)
        else:
            run = run - 1 if run < 0 else -1
            best_l = max(best_l, -run)
    return {"longest_wins": best_w, "longest_losses": best_l, "current": run}


def analyse(trades: list[dict], curve: list[dict]) -> dict:
    """trades: repository.recent_trades rows (any order); curve: equity_curve rows."""
    trades = sorted((t for t in trades if t.get("closed_at")), key=lambda t: t["closed_at"])
    pnls = [float(t["pnl"]) for t in trades]

    values = [float(p["value"]) for p in curve]
    day_end: dict[str, float] = {}
    for p in curve:
        t = datetime.fromtimestamp(p["time"], NY) if isinstance(p["time"], (int, float)) else _ny(str(p["time"]))
        if t is not None:
            day_end[t.strftime("%Y-%m-%d")] = float(p["value"])
    daily, prev = [], None
    for d in sorted(day_end):
        if prev:
            daily.append((day_end[d] / prev - 1) * 100)
        prev = day_end[d]

    by_day: dict[str, float] = {}
    for t in trades:
        c = _ny(t["closed_at"])
        if c is not None:
            k = c.strftime("%Y-%m-%d")
            by_day[k] = round(by_day.get(k, 0.0) + float(t["pnl"]), 2)

    def hour(t):
        o = _ny(t.get("opened_at") or "")
        return o.hour if o else None

    def weekday(t):
        o = _ny(t.get("opened_at") or "")
        return WEEKDAYS[o.weekday()] if o else None

    symbols = sorted(_group(trades, lambda t: t["symbol"]), key=lambda r: (-r["trades"], r["key"]))
    return {
        "money": _money(pnls),
        "risk": {"max_drawdown": max_drawdown(values) if values else None,
                 "days": len(day_end), **ratios(daily)},
        "books": sorted(_group(trades, book_of), key=lambda r: -r["trades"]),
        "hours": sorted(_group(trades, hour), key=lambda r: r["key"]),
        "weekdays": sorted(_group(trades, weekday), key=lambda r: WEEKDAYS.index(r["key"])),
        "symbols": symbols[:15],
        "streaks": streaks(pnls),
        "days": [{"day": d, "pnl": v} for d, v in sorted(by_day.items())][-60:],
        "first": trades[0]["closed_at"] if trades else None,
        "last": trades[-1]["closed_at"] if trades else None,
    }
