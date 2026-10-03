"""Learning from its own signals, kept honest — the phone app's learner, ported.

Every buy signal is followed "in the head" to its stop, target or sell
signal, bought or not. Each kind of signal (RSI band, news mood, time of day,
daily trend, the five checks, attention, the stock) is scored in R, with the
average pulled toward zero until there is enough evidence. A kind only blocks
buys after ten results averaging −0.25R or worse; learning can block or
shrink a buy, never add one or make it bigger.
"""
from __future__ import annotations

import math
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from app.brain.genome import Genome, Series, signals

PRIOR = 6.0
MIN_EVIDENCE = 10.0
BLOCK_AT = -0.25
CAP = 1200
SHADOW_CAP = 600
MAX_BARS = 40
NY = ZoneInfo("America/New_York")


@dataclass
class Features:
    symbol: str
    quality: str = "UNKNOWN"
    news: float | None = None
    rsi: float | None = None
    stretch: float | None = None          # price above the slow average, in ATRs
    minute: int | None = None             # minutes since the 9:30 New York open
    daily_up: bool | None = None
    attention: float | None = None

    def buckets(self) -> list[tuple[str, str]]:
        out = [("QUALITY", self.quality)]
        if self.news is None:
            out.append(("NEWS", "NONE"))
        else:
            out.append(("NEWS", "BAD" if self.news <= -0.15 else "GOOD" if self.news >= 0.15 else "MIXED"))
        if self.rsi is not None and not math.isnan(self.rsi):
            out.append(("RSI", "<45" if self.rsi < 45 else "45-60" if self.rsi < 60 else "60+"))
        if self.stretch is not None and not math.isnan(self.stretch):
            out.append(("STRETCH", "NEAR" if self.stretch < 1 else "EXTENDED" if self.stretch < 2.5 else "FAR"))
        if self.minute is None:
            out.append(("SESSION", "DAILY"))
        else:
            out.append(("SESSION", "OPEN" if self.minute < 60 else "CLOSE" if self.minute >= 330 else "MIDDAY"))
        if self.daily_up is not None:
            out.append(("DAILY_TREND", "UP" if self.daily_up else "DOWN"))
        if self.attention is not None:
            out.append(("ATTENTION", "NORMAL" if self.attention < 1.5 else "HIGH" if self.attention < 3 else "SPIKE"))
        out.append(("SYMBOL", self.symbol))
        return out


def minute_of_session(ts) -> int | None:
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    ny = t.tz_convert(NY)
    m = ny.hour * 60 + ny.minute - (9 * 60 + 30)
    return m if 0 <= m < 390 else None


@dataclass
class Sample:
    features: Features
    r: float
    real: bool
    at: float


@dataclass
class BucketStats:
    key: str
    value: str
    n: float
    wins: float
    sum_r: float

    @property
    def shrunk(self) -> float:
        return self.sum_r / (self.n + PRIOR)

    @property
    def win_rate(self) -> float:
        return self.wins / self.n if self.n else 0.0

    @property
    def avg_r(self) -> float:
        return self.sum_r / self.n if self.n else 0.0

    def to_dict(self) -> dict:
        return {"key": self.key, "value": self.value, "n": self.n, "wins": self.wins, "sum_r": round(self.sum_r, 3),
                "shrunk": round(self.shrunk, 3), "win_rate": round(self.win_rate, 3), "avg_r": round(self.avg_r, 3)}


@dataclass
class Verdict:
    blocked: bool
    edge: float | None
    evidence: list[BucketStats]
    size: float


class Learner:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.samples: list[Sample] = []

    def add(self, s: Sample) -> list[BucketStats]:
        """Adds a result; returns the rules that just became active because of it."""
        with self._lock:
            before = {(b.key, b.value) for b in self._rules()}
            self.samples.append(s)
            del self.samples[:-CAP]
            return [b for b in self._rules() if (b.key, b.value) not in before]

    def clear(self) -> None:
        with self._lock:
            self.samples.clear()

    def stats(self) -> list[BucketStats]:
        with self._lock:
            return self._stats()

    def _stats(self) -> list[BucketStats]:
        acc: dict[tuple[str, str], list[float]] = {}
        for s in self.samples:
            w = 2.0 if s.real else 1.0
            for key, value in s.features.buckets():
                a = acc.setdefault((key, value), [0.0, 0.0, 0.0])
                a[0] += w
                a[1] += w if s.r > 0 else 0.0
                a[2] += s.r * w
        return [BucketStats(k, v, a[0], a[1], a[2]) for (k, v), a in acc.items()]

    def _rules(self) -> list[BucketStats]:
        return sorted((b for b in self._stats() if b.n >= MIN_EVIDENCE and b.shrunk <= BLOCK_AT), key=lambda b: b.shrunk)

    def rules(self) -> list[BucketStats]:
        with self._lock:
            return self._rules()

    def verdict(self, f: Features) -> Verdict:
        stats = {(b.key, b.value): b for b in self.stats()}
        mine = [stats[k] for k in f.buckets() if k in stats and stats[k].n >= 3]
        if not mine:
            return Verdict(False, None, [], 1.0)
        edge = sum(b.shrunk for b in mine) / len(mine)
        blockers = [b for b in mine if b.n >= MIN_EVIDENCE and b.shrunk <= BLOCK_AT]
        size = 0.5 if edge <= -0.15 else 0.75 if edge < 0 else 1.0
        return Verdict(bool(blockers) and edge < 0, edge, sorted(mine, key=lambda b: b.shrunk), size)

    def lessons(self) -> list[BucketStats]:
        rows = [b for b in self.stats() if (b.n >= 5 and b.key != "SYMBOL") or b.n >= 8]
        return sorted(rows, key=lambda b: abs(b.shrunk) * math.sqrt(b.n), reverse=True)

    def to_json(self) -> list[dict]:
        with self._lock:
            return [{"f": asdict(s.features), "r": s.r, "real": s.real, "at": s.at} for s in self.samples]

    def load(self, rows: list[dict]) -> None:
        with self._lock:
            self.samples = [Sample(Features(**r["f"]), float(r["r"]), bool(r.get("real")), float(r.get("at", 0))) for r in rows][-CAP:]


@dataclass
class Shadow:
    id: str
    symbol: str
    opened_at: float          # epoch seconds of the signal candle
    entry: float
    stop: float
    target: float
    features: Features
    bought: bool = False
    closed_at: float | None = None
    r: float | None = None
    exit: str | None = None

    def r_at(self, price: float) -> float:
        return (price - self.entry) / (self.entry - self.stop) if self.entry > self.stop else 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


class ShadowBook:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.trades: list[Shadow] = []

    def open(self, t: Shadow) -> bool:
        with self._lock:
            if any(x.symbol == t.symbol and (x.closed_at is None or x.opened_at == t.opened_at) for x in self.trades):
                return False
            self.trades.append(t)
            while len(self.trades) > SHADOW_CAP:
                idx = next((i for i, x in enumerate(self.trades) if x.closed_at is not None), 0)
                self.trades.pop(idx)
            return True

    def mark_bought(self, symbol: str) -> None:
        with self._lock:
            for t in reversed(self.trades):
                if t.symbol == symbol and t.closed_at is None:
                    t.bought = True
                    break

    def resolve(self, frames: dict[str, pd.DataFrame], genome: Genome, reward_risk: float) -> list[Shadow]:
        """Walks each open shadow trade through the candles after it; the stop
        wins when a candle touches both."""
        closed = []
        with self._lock:
            for t in self.trades:
                if t.closed_at is not None or t.symbol not in frames:
                    continue
                df = frames[t.symbol]
                times = np.array([pd.Timestamp(x).timestamp() for x in df.index])
                after = np.flatnonzero(times > t.opened_at)
                if after.size == 0:
                    continue
                s = Series.from_frame(t.symbol, df)
                _, exit_ = signals(genome, s)
                for count, j in enumerate(after, 1):
                    res = None
                    if s.low[j] <= t.stop:
                        res = (-1.0, "stop-loss")
                    elif s.high[j] >= t.target:
                        res = (reward_risk, "take-profit")
                    elif exit_[j]:
                        res = (t.r_at(s.close[j]), "signal")
                    elif count >= MAX_BARS:
                        res = (t.r_at(s.close[j]), "time")
                    if res:
                        t.r, t.exit, t.closed_at = res[0], res[1], float(times[j])
                        closed.append(t)
                        break
        return closed

    def clear(self) -> None:
        with self._lock:
            self.trades.clear()

    def to_json(self) -> list[dict]:
        with self._lock:
            return [t.to_dict() for t in self.trades]

    def load(self, rows: list[dict]) -> None:
        with self._lock:
            out = []
            for r in rows:
                r = dict(r)
                r["features"] = Features(**r["features"])
                out.append(Shadow(**r))
            self.trades = out[-SHADOW_CAP:]
