"""The Time Machine (12.0): the honest odds of one Ultra buy, before it is placed.

The method comes from the MIT-licensed "trader-timemachine" skill
(github.com/jakeschincariol/day-trader-skill); this is our own code for it,
fitted to Ultra's rules. The skill's scripts are not bundled or run.

How it works:
  1. The pool. Sirius downloads the last 60 days of 5-minute bars for every
     stock Ultra watches, once a trading day, before the open. Only full
     sessions (78 bars, 9:30-16:00 New York) are kept. Each bar becomes four
     ratios to the close before it: open, high, low, close.
  2. One replay. Start at the entry price. For each 5-minute bar until the
     trade must end (Ultra holds at most 30 minutes and is flat at 15:52),
     pick a past bar from the same time of day (plus or minus 2 bars) at
     random and scale it to the price. The stop is checked before the target;
     a bar that touches both counts as the stop.
  3. Many replays give the odds: target first, stop first, neither. R is +RR
     at the target, -1 at the stop, else the move at the end over the risk.
  4. The gate. A target RR times the risk away needs to come first in 1 of
     (1 + RR) decided replays to break even. When the replays lean toward the
     stop by 5 points or more AND the average R is below zero, the buy is
     skipped (gate "odds"). It can only hold a buy back, never start one, and
     a stock without a pool is not held back.

It is a simulation from the stock's own recent bars, not a prediction.
"""
from __future__ import annotations

import logging
import random
import threading
from datetime import datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)

NY = ZoneInfo("America/New_York")
BARS = 78                    # 9:30 to 16:00 in 5-minute bars
WINDOW = 2                   # bars either side of the same time of day
MIN_SESSIONS = 20
REPLAYS = 2000
SEED = 19
LEAN = 0.05                  # 5 points toward the stop before it holds a buy back
HOLD_MIN, FLAT = 30, dtime(15, 52)


def slot_of(t: datetime) -> int:
    """The 5-minute bar of the session a New York time falls in (0 = 9:30)."""
    t = t.astimezone(NY)
    return (t.hour * 60 + t.minute - (9 * 60 + 30)) // 5


def pool_from(bars: list[tuple[datetime, float, float, float, float]]) -> tuple[list[list[tuple]], int]:
    """bars: (time, open, high, low, close), any order. Returns the ratio pool by
    time-of-day slot and the number of full sessions used."""
    days: dict = {}
    for t, o, h, l, c in sorted(bars):
        days.setdefault(t.astimezone(NY).date(), []).append((slot_of(t), o, h, l, c))
    pool: list[list[tuple]] = [[] for _ in range(BARS)]
    sessions, prev_close = 0, None
    for day in sorted(days):
        rows = days[day]
        full = len(rows) == BARS and [r[0] for r in rows] == list(range(BARS))
        if full:
            sessions += 1
            pc = prev_close
            for s, o, h, l, c in rows:
                if pc and pc > 0:
                    pool[s].append((o / pc, h / pc, l / pc, c / pc))
                pc = c
        prev_close = rows[-1][4] if rows else prev_close
    return pool, sessions


def replay(pool: list[list[tuple]], entry: float, stop: float, target: float, first_slot: int, n_bars: int,
           replays: int = REPLAYS, seed: int = SEED) -> dict:
    rng = random.Random(seed)
    risk = entry - stop
    hit_t = hit_s = 0
    total_r = 0.0
    rr = (target - entry) / risk if risk > 0 else 0.0
    slots = []
    for k in range(n_bars):
        s = first_slot + k
        near = [b for j in range(max(0, s - WINDOW), min(BARS, s + WINDOW + 1)) for b in pool[j]]
        if not near:
            break
        slots.append(near)
    for _ in range(replays):
        price, done = entry, None
        for near in slots:
            o, h, l, c = rng.choice(near)
            if price * l <= stop:
                done = "stop"
                break
            if price * h >= target:
                done = "target"
                break
            price *= c
        if done == "stop":
            hit_s += 1
            total_r -= 1.0
        elif done == "target":
            hit_t += 1
            total_r += rr
        else:
            total_r += (price - entry) / risk if risk > 0 else 0.0
    n = max(replays, 1)
    decided = hit_t + hit_s
    return {"target": round(hit_t / n, 3), "stop": round(hit_s / n, 3), "neither": round((n - decided) / n, 3),
            "avg_r": round(total_r / n, 3), "rr": round(rr, 2), "bars": len(slots), "replays": replays, "seed": seed,
            "target_share": round(hit_t / decided, 3) if decided else None,
            "breakeven": round(1 / (1 + rr), 3) if rr > 0 else None}


def leans_to_stop(odds: dict) -> bool:
    share, be = odds.get("target_share"), odds.get("breakeven")
    if share is None or be is None or odds["target"] + odds["stop"] < 0.2:
        return False
    return share < be - LEAN and odds["avg_r"] < 0


def fetch_5m(symbol: str) -> list[tuple]:
    """60 days of 5-minute bars from Yahoo (the most it keeps at 5 minutes)."""
    import pandas as pd
    import yfinance as yf

    df = yf.download(symbol, period="60d", interval="5m", progress=False, auto_adjust=False,
                     prepost=False, threads=False)
    if df is None or df.empty:
        return []
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns=str.lower).dropna()
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    return [(t.to_pydatetime(), float(r.open), float(r.high), float(r.low), float(r.close)) for t, r in df.iterrows()]


class TimeMachine:
    def __init__(self, engine=None, fetch=fetch_5m, now=None) -> None:
        self.engine = engine
        self._fetch = fetch
        self._now = now or (lambda: datetime.now(NY))
        self._pools: dict[str, tuple[list, int]] = {}
        self._day: str = ""
        self._lock = threading.Lock()
        self.running = False
        self.last: dict[str, dict] = {}        # symbol -> the last odds, for the console

    def ready(self, symbol: str) -> bool:
        p = self._pools.get(symbol.upper())
        return bool(p and p[1] >= MIN_SESSIONS)

    def load(self, symbols: list[str]) -> int:
        """Blocking: download and build the pools. Returns how many stocks are ready."""
        ok = 0
        for s in symbols:
            try:
                pool, n = pool_from(self._fetch(s))
            except Exception:
                log.debug("time machine: no 5-minute bars for %s", s, exc_info=True)
                continue
            with self._lock:
                self._pools[s.upper()] = (pool, n)
            ok += n >= MIN_SESSIONS
        return ok

    def maybe_prefetch(self, symbols: list[str]) -> bool:
        """Once a New York day, in the background: Sirius gets the pools before the open."""
        day = self._now().strftime("%Y-%m-%d")
        if self.running or self._day == day or not symbols:
            return False
        self._day, self.running = day, True

        def work() -> None:
            try:
                ok = self.load(list(symbols))
                self._say(ok, len(symbols))
            finally:
                self.running = False

        threading.Thread(target=work, name="time-machine", daemon=True).start()
        return True

    def _say(self, ok: int, total: int) -> None:
        monitor = getattr(self.engine, "monitor", None)
        if monitor is None:
            return
        tr = getattr(self.engine, "language", "en") == "tr"
        monitor.info("lab", f"Zaman Makinesi: {ok}/{total} hisse için 60 günlük 5 dakikalık mumlar hazır" if tr else
                     f"Time Machine: 60 days of 5-minute bars ready for {ok}/{total} stocks")

    def check(self, symbol: str, entry: float, stop_pct: float, rr: float, now: datetime | None = None) -> dict | None:
        """The odds of one Ultra buy, or None when this stock has no pool yet."""
        symbol = symbol.upper()
        with self._lock:
            p = self._pools.get(symbol)
        if not p or p[1] < MIN_SESSIONS or entry <= 0 or stop_pct <= 0:
            return None
        now = (now or self._now()).astimezone(NY)
        first = slot_of(now) + 1
        end = min(now + timedelta(minutes=HOLD_MIN), now.replace(hour=FLAT.hour, minute=FLAT.minute, second=0, microsecond=0))
        n_bars = max(0, min(BARS - first, int((end - now).total_seconds() // 300)))
        if first < 0 or first >= BARS or n_bars <= 0:
            return None
        stop = entry * (1 - stop_pct / 100)
        target = entry * (1 + stop_pct * rr / 100)
        odds = replay(p[0], entry, stop, target, first, n_bars)
        odds.update(symbol=symbol, sessions=p[1], hold=leans_to_stop(odds), at=int(now.timestamp() * 1000))
        self.last[symbol] = odds
        return odds
