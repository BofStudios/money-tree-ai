"""Confluence (9.0): many indicators vote, one number comes out.

A single indicator is wrong a lot. RSI says "oversold" all the way down a
crash. So before Ultra buys a dip, eight more readings have to agree that
the selling is tiring, and two readings can veto it outright:

  confirmations (each one vote)
    stoch_rsi    Stochastic RSI %K crossed over %D from under 20
    bollinger    price was under the lower Bollinger band (20, 2) and is back up
    macd         the MACD (12, 26, 9) histogram is rising
    mfi          Money Flow Index (14) under 30: volume-weighted oversold
    williams     Williams %R (14) came up from under -80
    cci          CCI (20) under -100 in the last three candles
    climax       volume at least 1.3x normal on the dip (sellers giving up)
    hammer       the last candle has a long lower wick (buyers stepped in)

  vetoes
    knife        ADX (14) over 35 with -DI well over +DI: a strong, still
                 accelerating downtrend, not a dip
    exhausted    the stock already fell more than 7 one-minute ATRs under
                 VWAP: usually news, and the 3 Nov 2026 replay lost on those

score = votes / 8. Everything is numpy on plain arrays so it is cheap enough
to run on ~40 stocks every ten seconds. Every value here is measured, never
estimated: the dashboard shows them as they are.
"""
from __future__ import annotations

import math

import numpy as np

CHECKS = ("stoch_rsi", "bollinger", "macd", "mfi", "williams", "cci", "climax", "hammer")
KNIFE_ADX, KNIFE_DI = 35.0, 1.5


# ------------------------------------------------------------ the indicators

def ema(x: np.ndarray, n: int) -> np.ndarray:
    out = np.empty(len(x))
    if not len(x):
        return out
    a = 2.0 / (n + 1)
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out


def wilder(x: np.ndarray, n: int) -> np.ndarray:
    """Wilder's smoothing (an EMA with alpha 1/n), NaN until n values."""
    out = np.full(len(x), np.nan)
    if len(x) < n:
        return out
    out[n - 1] = np.nanmean(x[:n])
    for i in range(n, len(x)):
        out[i] = out[i - 1] + (x[i] - out[i - 1]) / n
    return out


def rsi(close: np.ndarray, n: int = 14) -> np.ndarray:
    if len(close) <= n:
        return np.full(len(close), np.nan)
    d = np.diff(close, prepend=close[0])
    up, down = wilder(np.clip(d, 0, None), n), wilder(np.clip(-d, 0, None), n)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = 100 - 100 / (1 + up / down)
    out[(down == 0) & (up > 0)] = 100.0
    out[(down == 0) & (up == 0)] = 50.0
    return out


def stoch_rsi(close: np.ndarray, n: int = 14, k: int = 3, d: int = 3) -> tuple[np.ndarray, np.ndarray]:
    r = rsi(close, n)
    raw = np.full(len(r), np.nan)
    for i in range(n * 2 - 1, len(r)):
        w = r[i - n + 1:i + 1]
        lo, hi = np.nanmin(w), np.nanmax(w)
        raw[i] = 50.0 if hi - lo <= 0 else (r[i] - lo) / (hi - lo) * 100
    kk = _sma(raw, k)
    return kk, _sma(kk, d)


def _sma(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full(len(x), np.nan)
    for i in range(n - 1, len(x)):
        w = x[i - n + 1:i + 1]
        if not np.any(np.isnan(w)):
            out[i] = w.mean()
    return out


def bollinger_pctb(close: np.ndarray, n: int = 20, width: float = 2.0) -> np.ndarray:
    out = np.full(len(close), np.nan)
    for i in range(n - 1, len(close)):
        w = close[i - n + 1:i + 1]
        mid, sd = w.mean(), w.std()
        out[i] = 0.5 if sd == 0 else (close[i] - (mid - width * sd)) / (2 * width * sd)
    return out


def macd_hist(close: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9) -> np.ndarray:
    line = ema(close, fast) - ema(close, slow)
    return line - ema(line, signal)


def mfi(high: np.ndarray, low: np.ndarray, close: np.ndarray, vol: np.ndarray, n: int = 14) -> float | None:
    if len(close) <= n:
        return None
    tp = (high + low + close) / 3
    flow = tp * vol
    up = down = 0.0
    for i in range(len(tp) - n, len(tp)):
        if tp[i] > tp[i - 1]:
            up += flow[i]
        elif tp[i] < tp[i - 1]:
            down += flow[i]
    if down == 0:
        return 100.0 if up > 0 else 50.0
    return float(100 - 100 / (1 + up / down))


def williams_r(high: np.ndarray, low: np.ndarray, close: np.ndarray, n: int = 14) -> np.ndarray:
    out = np.full(len(close), np.nan)
    for i in range(n - 1, len(close)):
        hi, lo = high[i - n + 1:i + 1].max(), low[i - n + 1:i + 1].min()
        out[i] = -50.0 if hi == lo else (hi - close[i]) / (hi - lo) * -100
    return out


def cci(high: np.ndarray, low: np.ndarray, close: np.ndarray, n: int = 20) -> np.ndarray:
    tp = (high + low + close) / 3
    out = np.full(len(tp), np.nan)
    for i in range(n - 1, len(tp)):
        w = tp[i - n + 1:i + 1]
        dev = np.abs(w - w.mean()).mean()
        out[i] = 0.0 if dev == 0 else (tp[i] - w.mean()) / (0.015 * dev)
    return out


def adx(high: np.ndarray, low: np.ndarray, close: np.ndarray, n: int = 14) -> tuple[float, float, float] | None:
    """(ADX, +DI, -DI) for the last candle, or None without enough history."""
    if len(close) < n * 2 + 1:
        return None
    up = high[1:] - high[:-1]
    down = low[:-1] - low[1:]
    plus = np.where((up > down) & (up > 0), up, 0.0)
    minus = np.where((down > up) & (down > 0), down, 0.0)
    tr = np.maximum(high[1:] - low[1:], np.maximum(np.abs(high[1:] - close[:-1]), np.abs(low[1:] - close[:-1])))
    atr_ = wilder(tr, n)
    with np.errstate(divide="ignore", invalid="ignore"):
        pdi = 100 * wilder(plus, n) / atr_
        mdi = 100 * wilder(minus, n) / atr_
        dx = 100 * np.abs(pdi - mdi) / (pdi + mdi)
    dx = np.nan_to_num(dx, nan=0.0)
    a = wilder(dx[n - 1:], n)
    last = a[-1]
    if math.isnan(last) or math.isnan(pdi[-1]) or math.isnan(mdi[-1]):
        return None
    return float(last), float(pdi[-1]), float(mdi[-1])


# ----------------------------------------------------------------- the vote

def _f(x) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) else v


def dip_confluence(high: np.ndarray, low: np.ndarray, close: np.ndarray, vol: np.ndarray,
                   dip_atr: float = 0.0) -> dict:
    """The vote on buying a one-minute dip. Returns the score (0..1), each
    check with its reading, and the vetoes."""
    high, low, close, vol = (np.asarray(a, dtype=float) for a in (high, low, close, vol))
    votes: dict[str, bool] = {}
    read: dict[str, float | None] = {}

    k, d = stoch_rsi(close)
    kn, dn = _f(k[-1]), _f(d[-1])
    k_low = np.nanmin(k[-4:]) if len(k) >= 4 and not np.all(np.isnan(k[-4:])) else None
    votes["stoch_rsi"] = bool(kn is not None and dn is not None and k_low is not None
                              and k_low < 20 and kn > dn)
    read["stoch_rsi"] = kn

    pb = bollinger_pctb(close)
    pb_low = np.nanmin(pb[-4:]) if len(pb) >= 4 and not np.all(np.isnan(pb[-4:])) else None
    votes["bollinger"] = bool(pb_low is not None and pb_low < 0.05 and _f(pb[-1]) is not None and pb[-1] > pb_low)
    read["bollinger"] = _f(pb[-1])

    h = macd_hist(close)
    votes["macd"] = bool(len(h) >= 3 and h[-1] > h[-2] >= h[-3] - abs(h[-3]) * 0.1) if len(h) >= 3 else False
    read["macd"] = _f(h[-1]) if len(h) else None

    m = mfi(high, low, close, vol)
    votes["mfi"] = bool(m is not None and m < 30)
    read["mfi"] = m

    wr = williams_r(high, low, close)
    wr_low = np.nanmin(wr[-4:]) if len(wr) >= 4 and not np.all(np.isnan(wr[-4:])) else None
    votes["williams"] = bool(wr_low is not None and wr_low < -80 and _f(wr[-1]) is not None and wr[-1] > wr_low)
    read["williams"] = _f(wr[-1])

    c = cci(high, low, close)
    c_low = np.nanmin(c[-3:]) if len(c) >= 3 and not np.all(np.isnan(c[-3:])) else None
    votes["cci"] = bool(c_low is not None and c_low < -100)
    read["cci"] = _f(c[-1])

    base = vol[-65:-5]
    relvol = float(vol[-5:].mean() / base.mean()) if len(base) and base.mean() > 0 else 1.0
    votes["climax"] = relvol >= 1.3
    read["climax"] = relvol

    body = abs(close[-2] - (close[-3] if len(close) >= 3 else close[-2])) if len(close) >= 2 else 0.0
    wick = (min(close[-2], close[-3]) - low[-2]) if len(close) >= 3 else 0.0
    rng = high[-2] - low[-2] if len(close) >= 2 else 0.0
    votes["hammer"] = bool(rng > 0 and wick > 0 and wick >= max(2 * body, 0.5 * rng))
    read["hammer"] = float(wick / rng) if rng > 0 else 0.0

    trend = adx(high, low, close)
    knife = bool(trend is not None and trend[0] > KNIFE_ADX and trend[2] > trend[1] * KNIFE_DI)
    exhausted = dip_atr > 7.0
    score = sum(votes.values()) / len(CHECKS)
    return {
        "score": round(score, 3),
        "votes": votes,
        "readings": {k_: (round(v, 2) if isinstance(v, float) else v) for k_, v in read.items()},
        "adx": None if trend is None else {"adx": round(trend[0], 1), "plus_di": round(trend[1], 1),
                                            "minus_di": round(trend[2], 1)},
        "knife": knife,
        "exhausted": exhausted,
        "veto": "knife" if knife else ("exhausted" if exhausted else None),
    }


def daily_confluence(high: np.ndarray, low: np.ndarray, close: np.ndarray, vol: np.ndarray) -> dict:
    """The same idea on daily candles, for the swing book's pullbacks:
    MACD turning up, Stochastic RSI turning up, back over the lower half of
    the Bollinger band, money flow not collapsing, and a trend (ADX) that is
    not a strong downtrend."""
    high, low, close, vol = (np.asarray(a, dtype=float) for a in (high, low, close, vol))
    votes: dict[str, bool] = {}
    h = macd_hist(close)
    votes["macd"] = bool(len(h) >= 2 and h[-1] > h[-2])
    k, d = stoch_rsi(close)
    votes["stoch_rsi"] = bool(_f(k[-1]) is not None and _f(d[-1]) is not None and k[-1] > d[-1]
                              and np.nanmin(k[-6:]) < 30)
    pb = bollinger_pctb(close)
    votes["bollinger"] = bool(_f(pb[-1]) is not None and np.nanmin(pb[-6:]) < 0.25 and pb[-1] > pb[-2])
    m = mfi(high, low, close, vol)
    votes["mfi"] = bool(m is not None and 20 <= m <= 60)
    trend = adx(high, low, close)
    votes["trend"] = bool(trend is None or not (trend[0] > 30 and trend[2] > trend[1]))
    return {"score": round(sum(votes.values()) / len(votes), 3), "votes": votes}
