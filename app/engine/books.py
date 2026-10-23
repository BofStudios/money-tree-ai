"""The portfolio: three books, and the bot decides what goes where.

Before 7.0 everything was a short trade: a few dollars in, out again within
hours, so the account moved by cents and sat at the same number for weeks.
Now the money is split into three books, each with its own horizon and its
own rules, and every position is managed only by the rules of the book that
bought it:

  long    months   quality companies and broad funds in a long uptrend
                   (close above the 200-day average, 50-day above 200-day),
                   ranked by the five company checks and six-month momentum,
                   one per sector. Wide stop (15%), trailing 15% from the peak.
                   Sold when the long trend breaks, the checks turn AVOID, or
                   after 30 days it is no longer near the top of the ranking.
                   No new long buys while SPY is under its 200-day average.
  swing    weeks    a pullback in an uptrend on the daily chart: RSI dipped
                   under 42 in the last five days and is turning up. Stop two
                   daily ATRs (3% to 9%), target 2.5 times the stop, a trailing
                   stop from +6%, out after 35 days or under the 50-day line.
  short    hours    the 15-minute strategy and the news reflex, as before.

The split starts at 60 / 25 / 15 and follows results: a book whose recent
trades earned more gets more (at most 1.4x), one that lost gets less (at
least 0.6x); the long book never falls under 40%. Everything is shown on the
Portfolio screen with the reason.

Nothing here skips a gate: every buy still passes Stop, the market clock,
the sector limit, the safety pauses, the risk manager, arming and the
owner's autonomy choice.
"""
from __future__ import annotations

import logging
import math
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np

log = logging.getLogger(__name__)

NY = ZoneInfo("America/New_York")
BOOKS = ("long", "swing", "short")
BASE = {"long": 0.60, "swing": 0.25, "short": 0.15}
LONG_FLOOR = 0.40
PREFIX = {"long": "Long-term: ", "swing": "Swing: "}

# Trailing stops per book: (activate after this % gain, then trail this % behind the peak)
TRAIL = {"long": (15.0, 15.0), "swing": (6.0, 4.0)}
LONG_STOP, SWING_STOP_MIN, SWING_STOP_MAX, SWING_RR = 15.0, 3.0, 9.0, 2.5
LONG_TARGET_RR = 20.0          # +300%: a long holding has no real target
SWING_DAYS, LONG_REVIEW_DAYS = 35, 30
MIN_ORDER = 1.0

# Large, liquid names and funds the long book chooses from (it also looks at
# everything the bot already watches). Chips and energy are here on purpose.
LONG_UNIVERSE = [
    "SPY", "QQQ", "SMH", "XLE", "XLV",
    "MSFT", "AAPL", "NVDA", "GOOGL", "AMZN", "META", "AVGO", "TSM", "ASML",
    "COST", "LLY", "JPM", "V", "CEG", "NEE", "XOM",
]
FUNDS = {"SPY", "QQQ", "SMH", "XLE", "XLV", "IWM", "DIA", "VOO", "VTI", "SOXX", "XLK", "XLF"}


# ------------------------------------------------------------- indicators

def sma(x: np.ndarray, n: int) -> float | None:
    return float(np.mean(x[-n:])) if len(x) >= n else None


def rsi_series(close: np.ndarray, n: int = 14) -> np.ndarray:
    if len(close) <= n:
        return np.full(len(close), np.nan)
    diff = np.diff(close)
    up, down = np.clip(diff, 0, None), np.clip(-diff, 0, None)
    out = np.full(len(close), np.nan)
    avg_up, avg_down = up[:n].mean(), down[:n].mean()
    for i in range(n, len(diff) + 1):
        if i > n:
            avg_up = (avg_up * (n - 1) + up[i - 1]) / n
            avg_down = (avg_down * (n - 1) + down[i - 1]) / n
        out[i] = 100.0 if avg_down == 0 else 100 - 100 / (1 + avg_up / avg_down)
    return out


def atr_pct(high: np.ndarray, low: np.ndarray, close: np.ndarray, n: int = 14) -> float | None:
    if len(close) <= n:
        return None
    prev = close[-n - 1:-1]
    tr = np.maximum(high[-n:] - low[-n:], np.maximum(abs(high[-n:] - prev), abs(low[-n:] - prev)))
    return float(tr.mean() / close[-1] * 100) if close[-1] > 0 else None


def trend(d: dict) -> dict | None:
    """The daily picture of one stock: averages, momentum, RSI, ATR."""
    close = np.asarray(d.get("close", []), dtype=float)
    if len(close) < 200:
        return None
    high = np.asarray(d.get("high", close), dtype=float)
    low = np.asarray(d.get("low", close), dtype=float)
    r = rsi_series(close)
    s50, s200 = sma(close, 50), sma(close, 200)
    return {
        "close": float(close[-1]), "prev": float(close[-2]), "sma50": s50, "sma200": s200,
        "uptrend": bool(close[-1] > s200 and s50 > s200),
        "mom126": float(close[-1] / close[-127] - 1) * 100 if len(close) > 127 and close[-127] > 0 else 0.0,
        "rsi": float(r[-1]) if not math.isnan(r[-1]) else None,
        "rsi_prev": float(r[-2]) if not math.isnan(r[-2]) else None,
        "rsi_min5": float(np.nanmin(r[-5:])) if not np.all(np.isnan(r[-5:])) else None,
        "atr_pct": atr_pct(high, low, close),
    }


# ------------------------------------------------------------------ books

class Books:
    def __init__(self, engine) -> None:
        self.engine = engine
        self.last_review = ""          # NY day of the last daily review
        self.log: list[dict] = []      # newest first: what each book did and why
        self.regime_up: bool | None = None
        self.weight_why: dict[str, str] = {}

    # ----------------------------------------------------------- money split
    def slots(self, book: str, equity: float) -> int:
        small = equity < 500
        return {"long": 3 if small else 5, "swing": 2 if small else 3, "short": 3}[book]

    def weights(self) -> dict[str, float]:
        """60 / 25 / 15, shifted by each book's recent results."""
        perf = self._recent_results()
        raw, self.weight_why = {}, {}
        for book in BOOKS:
            n, avg = perf.get(book, (0, 0.0))
            mult = 1.0
            if n >= 5:
                mult = min(max(1 + avg / 4.0, 0.6), 1.4)
                self.weight_why[book] = f"{n} recent trades averaged {avg:+.2f}% → x{mult:.2f}"
            else:
                self.weight_why[book] = f"{n} recent trades: too few to adjust"
            raw[book] = BASE[book] * mult
        total = sum(raw.values()) or 1.0
        w = {b: v / total for b, v in raw.items()}
        if w["long"] < LONG_FLOOR:
            rest = sum(v for b, v in w.items() if b != "long") or 1.0
            w = {b: (LONG_FLOOR if b == "long" else v / rest * (1 - LONG_FLOOR)) for b, v in w.items()}
        return w

    def _recent_results(self) -> dict[str, tuple[int, float]]:
        try:
            rows = self.engine.repo.recent_trades(self.engine.mode, limit=120)
        except Exception:
            return {}
        out: dict[str, list[float]] = {b: [] for b in BOOKS}
        for r in rows:
            out[book_of_reason(r.get("entry_reason", ""))].append(float(r.get("pnl_pct") or 0.0))
        return {b: (len(v[:20]), float(np.mean(v[:20])) if v else 0.0) for b, v in out.items()}

    def budgets(self) -> dict[str, dict]:
        eng = self.engine
        try:
            equity = float(eng.executor.get_balance().total)
        except Exception:
            equity = 0.0
        w = self.weights()
        used = {b: 0.0 for b in BOOKS}
        with eng._lock:
            for s, p in eng._positions.items():
                used[eng.book_of(s)] += (p.current_price or p.entry_price) * p.qty
        return {b: {"weight": round(w[b], 3), "budget": round(equity * w[b], 2), "used": round(used[b], 2),
                    "free": round(max(equity * w[b] - used[b], 0.0), 2), "slots": self.slots(b, equity),
                    "why": self.weight_why.get(b, "")} for b in BOOKS}

    # ---------------------------------------------------------- daily review
    def due(self) -> bool:
        now = datetime.now(NY)
        opened = now.replace(hour=9, minute=45, second=0, microsecond=0)
        return now >= opened and self.last_review != now.strftime("%Y-%m-%d")

    def review(self, force: bool = False) -> list[dict]:
        """Once a trading day: sell what broke its book's rules, then fill free room."""
        eng = self.engine
        if not force and not self.due():
            return []
        self.last_review = datetime.now(NY).strftime("%Y-%m-%d")
        brain = eng.brain
        if brain is None:
            return []
        done: list[dict] = []
        daily = dict(brain.daily)
        reports = dict(brain.reports)
        spy = trend(daily["SPY"]) if "SPY" in daily else None
        self.regime_up = None if spy is None else bool(spy["close"] > spy["sma200"])

        # 1. exits by each book's own rules
        with eng._lock:
            held = {s: (eng.book_of(s), p) for s, p in eng._positions.items()}
        long_ranked = self._rank_long(daily, reports)
        top = {s for s, _ in long_ranked[: self.slots("long", 1e9) * 3]}
        for s, (book, p) in held.items():
            t = trend(daily[s]) if s in daily else None
            age = (time.time() - p.opened_at.timestamp()) / 86400
            why = None
            if book == "long" and t:
                rep = reports.get(s)
                if t["close"] < t["sma200"] * 0.97:
                    why = "the long trend broke: under the 200-day average"
                elif rep is not None and rep.decision == "AVOID":
                    why = "the company checks turned AVOID"
                elif age >= LONG_REVIEW_DAYS and s not in top and long_ranked:
                    why = "after 30 days it is no longer near the top; the money moves to a better one"
            elif book == "swing" and t:
                if age >= SWING_DAYS:
                    why = "the swing time limit (35 days) is over"
                elif t["close"] < t["sma50"] * 0.97:
                    why = "it fell under the 50-day average"
            if why:
                result = eng.book_sell(s, f"{PREFIX[book]}{why}")
                done.append(self._note(book, s, "sell" if result == "sold" else "skip", why if result == "sold" else f"{why} ({result})"))

        # 2. buys into the free room of each book
        budgets = self.budgets()
        with eng._lock:
            held_now = {s: eng.book_of(s) for s in eng._positions}
        for book, picks in (("long", self._long_picks(long_ranked, held_now)),
                            ("swing", self._swing_picks(daily, reports, held_now))):
            b = budgets[book]
            count = sum(1 for v in held_now.values() if v == book)
            free_slots = b["slots"] - count
            if free_slots <= 0 or b["free"] < MIN_ORDER:
                continue
            if book == "long" and self.regime_up is False:
                done.append(self._note(book, "SPY", "wait", "SPY is under its 200-day average: no new long buys until it recovers"))
                continue
            per = b["free"] / free_slots
            for s, stop, rr, why in picks[:free_slots]:
                if per < MIN_ORDER:
                    break
                result = eng.book_buy(s, book, f"{PREFIX[book]}{why}", per, stop, rr)
                done.append(self._note(book, s, "buy" if result == "bought" else ("wait" if result == "waiting" else "skip"),
                                       why if result in ("bought", "waiting") else f"{why} ({result})"))
                if result in ("bought", "waiting"):
                    held_now[s] = book
        return done

    def _rank_long(self, daily: dict, reports: dict) -> list[tuple[str, float]]:
        rows = []
        for s in set(LONG_UNIVERSE) | set(self.engine.watched_symbols()):
            if s not in daily:
                continue
            t = trend(daily[s])
            if not t or not t["uptrend"]:
                continue
            rep = reports.get(s)
            if s in FUNDS:
                quality = 3.5
            elif rep is None or rep.decision in ("AVOID", "UNKNOWN"):
                continue
            else:
                quality = float(rep.score)
            rows.append((s, quality, t["mom126"]))
        if not rows:
            return []
        moms = sorted(r[2] for r in rows)
        ranked = [(s, 0.5 * q / 5 + 0.5 * (moms.index(m) / max(len(moms) - 1, 1))) for s, q, m in rows]
        return sorted(ranked, key=lambda r: -r[1])

    def _long_picks(self, ranked: list, held: dict) -> list:
        from app.engine.desk import sector_of

        sectors = {sector_of(s) for s, b in held.items() if b == "long"}
        out = []
        for s, score in ranked:
            if s in held:
                continue
            sec = sector_of(s)
            if sec in sectors and sec != "other":
                continue
            sectors.add(sec)
            kind = "a broad fund" if s in FUNDS else "a quality company"
            out.append((s, LONG_STOP, LONG_TARGET_RR, f"{kind} in a long uptrend (rank score {score:.2f})"))
        return out

    def _swing_picks(self, daily: dict, reports: dict, held: dict) -> list:
        out = []
        for s in set(LONG_UNIVERSE) | set(self.engine.watched_symbols()):
            if s in held or s not in daily:
                continue
            rep = reports.get(s)
            if rep is not None and rep.decision == "AVOID":
                continue
            t = trend(daily[s])
            if not t or not t["uptrend"] or t["rsi"] is None or t["rsi_prev"] is None or t["rsi_min5"] is None:
                continue
            if t["rsi_min5"] < 42 and t["rsi"] > t["rsi_prev"] and t["close"] > t["prev"]:
                stop = min(max(2 * (t["atr_pct"] or 2.0), SWING_STOP_MIN), SWING_STOP_MAX)
                out.append((t["rsi_min5"], s, stop))
        out.sort()
        return [(s, stop, SWING_RR, f"a pullback in an uptrend: RSI dipped to {low:.0f} and turns up") for low, s, stop in out]

    def _note(self, book: str, symbol: str, action: str, why: str) -> dict:
        row = {"at": time.time(), "book": book, "symbol": symbol, "action": action, "why": why}
        self.log.insert(0, row)
        del self.log[60:]
        return row

    # ------------------------------------------------------------------ view
    def snapshot(self) -> dict:
        eng = self.engine
        budgets = self.budgets()
        holdings = {b: [] for b in BOOKS}
        with eng._lock:
            items = list(eng._positions.items())
        for s, p in items:
            price = p.current_price or p.entry_price
            holdings[eng.book_of(s)].append({
                "symbol": s, "value": round(price * p.qty, 2), "pnl_pct": round(p.unrealized_pnl_pct, 2),
                "days": round((time.time() - p.opened_at.timestamp()) / 86400, 1),
                "stop": p.stop_loss, "reason": eng._entry_reasons.get(s, "")})
        return {"books": {b: {**budgets[b], "holdings": holdings[b]} for b in BOOKS},
                "regime_up": self.regime_up, "last_review": self.last_review, "log": self.log[:30],
                "universe": len(set(LONG_UNIVERSE) | set(eng.watched_symbols()))}


def book_of_reason(reason: str) -> str:
    for book, prefix in PREFIX.items():
        if (reason or "").startswith(prefix):
            return book
    return "short"
