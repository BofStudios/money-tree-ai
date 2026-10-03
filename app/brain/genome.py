"""Strategy settings that evolve, the replay that scores them, and the live strategy they become.

Three families, each long-only, each with an ATR stop and a target at a
multiple of it:

  TREND     the fast average crosses above the slow one, RSI not overheated
  BREAKOUT  the close clears the highest high of the last N bars on above-average volume
  PULLBACK  in an uptrend (above the slow average), RSI dips under a level and hooks back up

The replay and the live strategy compute signals with the same numpy code,
so what the swarm tested is exactly what trades.
"""
from __future__ import annotations

import math
import random
from dataclasses import asdict, dataclass, replace

import numpy as np
import pandas as pd

from app.common.models import Action, Position, Signal
from app.strategy.base import Strategy

FAMILIES = ("TREND", "BREAKOUT", "PULLBACK")
COST_R = 0.03        # spread and slippage, charged on every trade
MAX_HOLD = 200       # bars a replayed trade may stay open


@dataclass(frozen=True)
class Genome:
    family: str = "TREND"
    fast: int = 12
    slow: int = 26
    entry_rsi: float = 70.0
    exit_rsi: float = 70.0
    atr_mult: float = 1.5
    reward_risk: float = 2.0
    lookback: int = 20       # BREAKOUT: the N-bar high to clear
    vol_mult: float = 1.2    # BREAKOUT: volume over its 20-bar average
    dip_rsi: float = 35.0    # PULLBACK: the RSI level to dip under and reclaim

    def clamped(self) -> "Genome":
        family = self.family if self.family in FAMILIES else "TREND"
        fast = int(min(max(self.fast, 5), 20))
        return Genome(
            family=family,
            fast=fast,
            slow=int(min(max(self.slow, max(20, fast + 6)), 60)),
            entry_rsi=float(min(max(self.entry_rsi, 50.0), 80.0)),
            exit_rsi=float(min(max(self.exit_rsi, 60.0), 90.0)),
            atr_mult=float(min(max(self.atr_mult, 0.8), 3.0)),
            reward_risk=float(min(max(self.reward_risk, 1.2), 4.0)),
            lookback=int(min(max(self.lookback, 10), 60)),
            vol_mult=float(min(max(self.vol_mult, 0.8), 2.5)),
            dip_rsi=float(min(max(self.dip_rsi, 25.0), 45.0)),
        )

    @property
    def warmup(self) -> int:
        return max(self.slow, self.lookback, 20) * 3

    @property
    def label(self) -> str:
        tail = f"stop {self.atr_mult:.1f} ATR · {self.reward_risk:.1f}:1"
        if self.family == "BREAKOUT":
            return f"Breakout {self.lookback}-bar high · vol ×{self.vol_mult:.1f} · exit RSI>{self.exit_rsi:.0f} · {tail}"
        if self.family == "PULLBACK":
            return f"Pullback above EMA {self.slow} · RSI dip <{self.dip_rsi:.0f} · exit>{self.exit_rsi:.0f} · {tail}"
        return f"Trend EMA {self.fast}/{self.slow} · RSI<{self.entry_rsi:.0f} · exit>{self.exit_rsi:.0f} · {tail}"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["label"] = self.label
        return d

    @staticmethod
    def from_dict(d: dict) -> "Genome":
        fields = Genome.__dataclass_fields__
        return Genome(**{k: v for k, v in d.items() if k in fields}).clamped()


DEFAULT = Genome()


def random_genome(rng: random.Random, family: str | None = None) -> Genome:
    fast = rng.randint(5, 20)
    return Genome(
        family=family or rng.choice(FAMILIES),
        fast=fast,
        slow=rng.randint(max(20, fast + 6), 60),
        entry_rsi=rng.uniform(50, 80),
        exit_rsi=rng.uniform(60, 90),
        atr_mult=rng.uniform(0.8, 3.0),
        reward_risk=rng.uniform(1.2, 4.0),
        lookback=rng.randint(10, 60),
        vol_mult=rng.uniform(0.8, 2.5),
        dip_rsi=rng.uniform(25, 45),
    ).clamped()


def mutate(g: Genome, rng: random.Random, strength: float = 1.0, family: str | None = None) -> Genome:
    def maybe(p: float = 0.5) -> bool:
        return rng.random() < p
    fam = family or (rng.choice(FAMILIES) if maybe(0.05) else g.family)
    s = strength
    return replace(
        g,
        family=fam,
        fast=g.fast + int(round(rng.gauss(0, 2 * s))) if maybe() else g.fast,
        slow=g.slow + int(round(rng.gauss(0, 4 * s))) if maybe() else g.slow,
        entry_rsi=g.entry_rsi + rng.gauss(0, 4 * s) if maybe() else g.entry_rsi,
        exit_rsi=g.exit_rsi + rng.gauss(0, 4 * s) if maybe() else g.exit_rsi,
        atr_mult=g.atr_mult + rng.gauss(0, 0.25 * s) if maybe() else g.atr_mult,
        reward_risk=g.reward_risk + rng.gauss(0, 0.3 * s) if maybe() else g.reward_risk,
        lookback=g.lookback + int(round(rng.gauss(0, 5 * s))) if maybe() else g.lookback,
        vol_mult=g.vol_mult + rng.gauss(0, 0.2 * s) if maybe() else g.vol_mult,
        dip_rsi=g.dip_rsi + rng.gauss(0, 3 * s) if maybe() else g.dip_rsi,
    ).clamped()


def crossover(a: Genome, b: Genome, rng: random.Random) -> Genome:
    pick = lambda x, y: x if rng.random() < 0.5 else y  # noqa: E731
    return Genome(*(pick(getattr(a, f), getattr(b, f)) for f in Genome.__dataclass_fields__)).clamped()


# ================================================================ indicators

def ema(values: np.ndarray, period: int) -> np.ndarray:
    """pandas ewm(span=period, adjust=False): starts at the first value."""
    out = np.empty_like(values, dtype=float)
    if len(values) == 0:
        return out
    alpha = 2.0 / (period + 1)
    acc = float(values[0])
    out[0] = acc
    for i in range(1, len(values)):
        acc = alpha * values[i] + (1 - alpha) * acc
        out[i] = acc
    return out


def _wilder(values: np.ndarray, period: int) -> np.ndarray:
    out = np.full(len(values), np.nan)
    alpha = 1.0 / period
    mean = math.nan
    seen = 0
    for i, x in enumerate(values):
        if math.isnan(x):
            continue
        mean = x if seen == 0 else alpha * x + (1 - alpha) * mean
        seen += 1
        if seen >= period:
            out[i] = mean
    return out


def rsi(close: np.ndarray, period: int = 14) -> np.ndarray:
    delta = np.diff(close, prepend=np.nan)
    gain = np.where(np.isnan(delta), np.nan, np.clip(delta, 0, None))
    loss = np.where(np.isnan(delta), np.nan, np.clip(-delta, 0, None))
    g, l = _wilder(gain, period), _wilder(loss, period)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = 100.0 - 100.0 / (1.0 + g / l)
    out = np.where((g == 0) & (l == 0), 50.0, out)
    out = np.where((l == 0) & (g > 0), 100.0, out)
    return out


def atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    prev = np.concatenate([[np.nan], close[:-1]])
    tr = np.nanmax(np.vstack([high - low, np.abs(high - prev), np.abs(low - prev)]), axis=0)
    return _wilder(tr, period)


def _prior_max(values: np.ndarray, n: int) -> np.ndarray:
    """Max of the n values before each index (excluding it); NaN until n exist."""
    out = np.full(len(values), np.nan)
    if len(values) <= n:
        return out
    windows = np.lib.stride_tricks.sliding_window_view(values, n)
    out[n:] = windows.max(axis=1)[:-1]
    return out


def _prior_min(values: np.ndarray, n: int) -> np.ndarray:
    out = np.full(len(values), np.nan)
    if len(values) <= n:
        return out
    windows = np.lib.stride_tricks.sliding_window_view(values, n)
    out[n:] = windows.min(axis=1)[:-1]
    return out


def _prior_mean(values: np.ndarray, n: int) -> np.ndarray:
    out = np.full(len(values), np.nan)
    if len(values) <= n:
        return out
    c = np.cumsum(np.concatenate([[0.0], values]))
    out[n:] = (c[n:-1] - c[:-n - 1]) / n
    return out


class Series:
    """One stock's candles, with indicators computed once and cached by period."""

    def __init__(self, symbol: str, open_: np.ndarray, high: np.ndarray, low: np.ndarray,
                 close: np.ndarray, volume: np.ndarray) -> None:
        self.symbol = symbol
        self.open, self.high, self.low = (np.asarray(a, dtype=float) for a in (open_, high, low))
        self.close, self.volume = np.asarray(close, dtype=float), np.asarray(volume, dtype=float)
        self.size = len(self.close)
        self.rsi = rsi(self.close)
        self.atr = atr(self.high, self.low, self.close)
        self._cache: dict[tuple, np.ndarray] = {}

    @staticmethod
    def from_frame(symbol: str, df: pd.DataFrame) -> "Series":
        return Series(symbol, df["open"].to_numpy(), df["high"].to_numpy(), df["low"].to_numpy(),
                      df["close"].to_numpy(), df["volume"].to_numpy() if "volume" in df else np.zeros(len(df)))

    def to_arrays(self) -> dict:
        return {"symbol": self.symbol, "open": self.open, "high": self.high, "low": self.low,
                "close": self.close, "volume": self.volume}

    def _cached(self, key: tuple, make):
        found = self._cache.get(key)
        if found is None:
            found = make()
            self._cache[key] = found
        return found

    def ema(self, p: int) -> np.ndarray:
        return self._cached(("ema", p), lambda: ema(self.close, p))

    def prior_high(self, n: int) -> np.ndarray:
        return self._cached(("hh", n), lambda: _prior_max(self.high, n))

    def prior_low(self, n: int) -> np.ndarray:
        return self._cached(("ll", n), lambda: _prior_min(self.low, n))

    def vol_avg(self, n: int = 20) -> np.ndarray:
        return self._cached(("va", n), lambda: _prior_mean(self.volume, n))


def signals(g: Genome, s: Series) -> tuple[np.ndarray, np.ndarray]:
    """Entry and exit flags for every bar. NaN indicators never fire."""
    n = s.size
    entry = np.zeros(n, dtype=bool)
    exit_ = np.zeros(n, dtype=bool)
    if n < 3:
        return entry, exit_
    r = s.rsi
    with np.errstate(invalid="ignore"):
        if g.family == "BREAKOUT":
            hh = s.prior_high(g.lookback)
            va = s.vol_avg(20)
            entry = (s.close > hh) & ((va <= 0) | (s.volume >= g.vol_mult * va)) & (r < g.entry_rsi)
            ll = s.prior_low(max(5, g.lookback // 2))
            exit_ = (s.close < ll) | (r > g.exit_rsi)
        elif g.family == "PULLBACK":
            sl = s.ema(g.slow)
            entry[1:] = (s.close[1:] > sl[1:]) & (r[:-1] < g.dip_rsi) & (r[1:] >= g.dip_rsi)
            exit_[1:] = (r[1:] > g.exit_rsi) | ((s.close[:-1] >= sl[:-1]) & (s.close[1:] < sl[1:]))
        else:
            f, sl = s.ema(g.fast), s.ema(g.slow)
            entry[1:] = (f[:-1] <= sl[:-1]) & (f[1:] > sl[1:]) & (r[1:] < g.entry_rsi)
            exit_[1:] = ((f[:-1] >= sl[:-1]) & (f[1:] < sl[1:])) | (r[1:] > g.exit_rsi)
    entry[: min(g.warmup, n)] = False
    return entry, exit_


@dataclass
class Score:
    trades: int = 0
    sum_r: float = 0.0
    wins: int = 0

    @property
    def expectancy(self) -> float:
        return self.sum_r / self.trades if self.trades else 0.0

    @property
    def win_rate(self) -> float:
        return self.wins / self.trades if self.trades else 0.0

    def __add__(self, o: "Score") -> "Score":
        return Score(self.trades + o.trades, self.sum_r + o.sum_r, self.wins + o.wins)

    def to_dict(self) -> dict:
        return {"trades": self.trades, "sum_r": round(self.sum_r, 4), "wins": self.wins,
                "expectancy": round(self.expectancy, 4), "win_rate": round(self.win_rate, 4)}


def replay(g: Genome, s: Series, lo: int, hi: int, min_stop_pct: float, max_stop_pct: float,
           flags: tuple[np.ndarray, np.ndarray] | None = None) -> Score:
    """Trade the genome over bars [lo, hi): enter on the signal candle's close,
    out at stop, target or exit signal — whichever comes first, the stop when a
    candle touches both, a gap through the stop filled at the open."""
    entry, exit_ = flags or signals(g, s)
    hi = min(hi, s.size)
    trades = wins = 0
    total = 0.0
    free = lo
    for i in np.flatnonzero(entry[lo:hi]) + lo:
        if i < free:
            continue
        price, a = s.close[i], s.atr[i]
        if not (a > 0) or price <= 0:
            continue
        pct = min(max(a * g.atr_mult / price * 100, min_stop_pct), max_stop_pct) / 100
        stop, target = price * (1 - pct), price * (1 + pct * g.reward_risk)
        risk = price - stop
        j0, j1 = i + 1, min(hi, i + 1 + MAX_HOLD)
        if j0 >= j1:
            break
        lows, highs = s.low[j0:j1], s.high[j0:j1]
        hit = (lows <= stop) | (highs >= target) | exit_[j0:j1]
        if hit.any():
            k = int(hit.argmax())
            j = j0 + k
            if lows[k] <= stop:
                r = (min(s.open[j], stop) - price) / risk
            elif highs[k] >= target:
                r = (target - price) / risk
            else:
                r = (s.close[j] - price) / risk
            free = j + 1
        else:
            r = (s.close[j1 - 1] - price) / risk
            free = j1
        trades += 1
        total += float(r) - COST_R
        wins += 1 if r > 0 else 0
    return Score(trades, total, wins)


# ============================================================ live strategy

class EvolvedStrategy(Strategy):
    """The champion genome as the engine's live strategy: the same numpy
    signals the swarm replayed, read on the latest candle."""

    def __init__(self, genome: Genome) -> None:
        self.genome = genome
        self.name = f"evolved_{genome.family.lower()}"
        self.warmup_bars = genome.warmup
        # The engine and the screen read these like the EMA/RSI strategy's.
        self.fast_ema, self.slow_ema = genome.fast, genome.slow
        self.rsi_period, self.rsi_overbought, self.rsi_oversold = 14, genome.entry_rsi, 30.0

    def on_bar(self, history: pd.DataFrame, position: Position | None) -> Signal:
        g = self.genome
        if len(history) < g.warmup:
            return Signal(Action.HOLD, "warming up")
        s = Series.from_frame("", history)
        entry, exit_ = signals(g, s)
        r = s.rsi[-1]
        if math.isnan(r):
            return Signal(Action.HOLD, "indicators not ready")
        if position is None:
            if entry[-1]:
                return Signal(Action.BUY, self._why(s))
            return Signal(Action.HOLD, "no entry signal")
        if exit_[-1]:
            return Signal(Action.CLOSE, f"{g.family.lower()} exit rule, RSI {r:.0f}")
        return Signal(Action.HOLD, "holding position")

    def _why(self, s: Series) -> str:
        g = self.genome
        r = s.rsi[-1]
        if g.family == "BREAKOUT":
            return f"broke the {g.lookback}-bar high on volume, RSI {r:.0f}"
        if g.family == "PULLBACK":
            return f"RSI hooked back above {g.dip_rsi:.0f} in an uptrend (EMA{g.slow}), RSI {r:.0f}"
        return f"EMA{g.fast} crossed above EMA{g.slow}, RSI {r:.0f}"

    def indicator_series(self, history: pd.DataFrame) -> dict[str, pd.Series]:
        close = history["close"]
        g = self.genome
        lines = {f"EMA {g.slow}": pd.Series(ema(close.to_numpy(dtype=float), g.slow), index=close.index)}
        if g.family == "TREND":
            lines[f"EMA {g.fast}"] = pd.Series(ema(close.to_numpy(dtype=float), g.fast), index=close.index)
        return lines

    def snapshot(self, history: pd.DataFrame) -> dict:
        g = self.genome
        if len(history) < max(g.slow, 14) + 2:
            return {"ready": False, "bars": len(history)}
        s = Series.from_frame("", history)
        fast, slow = s.ema(g.fast), s.ema(g.slow)
        price = float(s.close[-1])
        r = None if math.isnan(s.rsi[-1]) else float(s.rsi[-1])
        a = None if math.isnan(s.atr[-1]) else float(s.atr[-1])
        above = fast > slow
        since = 0
        for i in range(len(above) - 1, 0, -1):
            if above[i] != above[i - 1]:
                break
            since += 1
        zone = "neutral"
        if r is not None:
            zone = "overbought" if r >= g.entry_rsi else "oversold" if r <= 30 else "neutral"
        first = float(s.close[0])
        return {
            "ready": True, "bars": len(history), "price": price,
            "fast_ema": float(fast[-1]), "slow_ema": float(slow[-1]),
            "fast_period": g.fast, "slow_period": g.slow,
            "spread_pct": (fast[-1] - slow[-1]) / slow[-1] * 100 if slow[-1] else 0.0,
            "trend": "up" if above[-1] else "down", "bars_since_cross": since,
            "rsi": r, "rsi_zone": zone, "rsi_overbought": g.entry_rsi, "rsi_oversold": 30.0,
            "atr": a, "atr_pct": a / price * 100 if a and price else None,
            "window_change_pct": (price / first - 1) * 100 if first else None,
            "family": g.family,
        }
