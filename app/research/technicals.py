"""Technical indicators, and — more importantly — what they actually mean.

The product rule this module exists to serve: *the user should not need to
understand the market to understand the market.* So every indicator is
computed once and then returned twice — as a raw number for someone who knows
what ADX is, and as a plain sentence for someone who does not.

Nothing here predicts. `Reading.plain` describes what has already happened
("momentum has been unusually strong"), never what happens next, and levels are
called "potential" zones because that is what support and resistance are.

Builds on `app.strategy.indicators`, which the live trading engine already
uses, so the number the research page shows is the number the bot traded on.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd

from app.strategy.indicators import atr as _atr
from app.strategy.indicators import ema as _ema
from app.strategy.indicators import rsi as _rsi


@dataclass
class Reading:
    """One indicator, in both languages the app speaks."""

    key: str
    label: str
    value: float | None
    # A short verdict: "overbought", "trending", "expanding" ...
    state: str | None = None
    # The same thing in a sentence a beginner can act on.
    plain: str | None = None
    # What the indicator is, for the "Explain" panel.
    explain: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TechnicalPicture:
    trend: str | None = None
    momentum: str | None = None
    volatility: str | None = None
    volume: str | None = None
    support: list[float] = field(default_factory=list)
    resistance: list[float] = field(default_factory=list)
    readings: list[Reading] = field(default_factory=list)
    summary: str | None = None
    bars: int = 0

    def to_dict(self) -> dict:
        return {
            "trend": self.trend,
            "momentum": self.momentum,
            "volatility": self.volatility,
            "volume": self.volume,
            "support": self.support,
            "resistance": self.resistance,
            "readings": [r.to_dict() for r in self.readings],
            "summary": self.summary,
            "bars": self.bars,
        }


# --------------------------------------------------------------- indicators


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period, min_periods=period).mean()


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    """Returns (macd line, signal line, histogram)."""
    line = _ema(series, fast) - _ema(series, slow)
    signal_line = _ema(line, signal)
    return line, signal_line, line - signal_line


def bollinger(series: pd.Series, period: int = 20, deviations: float = 2.0):
    """Returns (upper, middle, lower)."""
    middle = sma(series, period)
    spread = series.rolling(period, min_periods=period).std(ddof=0) * deviations
    return middle + spread, middle, middle - spread


def stochastic(frame: pd.DataFrame, period: int = 14, smooth: int = 3):
    """Returns (%K, %D) — where price sits inside its recent range."""
    low = frame["low"].rolling(period, min_periods=period).min()
    high = frame["high"].rolling(period, min_periods=period).max()
    span = (high - low).replace(0, np.nan)
    k = ((frame["close"] - low) / span) * 100.0
    return k, k.rolling(smooth, min_periods=smooth).mean()


def adx(frame: pd.DataFrame, period: int = 14) -> pd.Series:
    """Trend *strength*, regardless of direction. Above 25 is a real trend."""
    up = frame["high"].diff()
    down = -frame["low"].diff()

    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)

    true_range = _atr(frame, period).replace(0, np.nan)
    plus_di = 100.0 * pd.Series(plus_dm, index=frame.index).ewm(
        alpha=1 / period, adjust=False
    ).mean() / true_range
    minus_di = 100.0 * pd.Series(minus_dm, index=frame.index).ewm(
        alpha=1 / period, adjust=False
    ).mean() / true_range

    total = (plus_di + minus_di).replace(0, np.nan)
    dx = ((plus_di - minus_di).abs() / total) * 100.0
    return dx.ewm(alpha=1 / period, adjust=False).mean()


def obv(frame: pd.DataFrame) -> pd.Series:
    """On-balance volume: does volume arrive on up days or down days?"""
    direction = np.sign(frame["close"].diff().fillna(0.0))
    return (direction * frame["volume"]).fillna(0.0).cumsum()


def vwap(frame: pd.DataFrame) -> pd.Series:
    """Volume-weighted average price over the window supplied."""
    typical = (frame["high"] + frame["low"] + frame["close"]) / 3.0
    volume = frame["volume"].replace(0, np.nan)
    return (typical * volume).cumsum() / volume.cumsum()


def levels(frame: pd.DataFrame, lookback: int = 120, count: int = 3):
    """Potential support and resistance, from swing highs and lows.

    A swing point is a bar whose high (or low) beats its two neighbours on each
    side. Clustered levels are merged, because six lines within 0.5% of each
    other are one level drawn six times.
    """
    window = frame.tail(lookback)
    if len(window) < 10:
        return [], []

    highs, lows = [], []
    for i in range(2, len(window) - 2):
        high = window["high"].iloc[i]
        low = window["low"].iloc[i]
        window_highs = window["high"].iloc[i - 2 : i + 3]
        window_lows = window["low"].iloc[i - 2 : i + 3]
        if high >= window_highs.max():
            highs.append(float(high))
        if low <= window_lows.min():
            lows.append(float(low))

    price = float(window["close"].iloc[-1])
    resistance = _cluster([h for h in highs if h > price])
    support = _cluster([l for l in lows if l < price])
    return (
        sorted(support, reverse=True)[:count],
        sorted(resistance)[:count],
    )


def _cluster(values: list[float], tolerance: float = 0.005) -> list[float]:
    """Merge levels that sit within `tolerance` of each other."""
    if not values:
        return []
    merged: list[list[float]] = []
    for value in sorted(values):
        if merged and abs(value - merged[-1][-1]) / merged[-1][-1] <= tolerance:
            merged[-1].append(value)
        else:
            merged.append([value])
    return [round(sum(group) / len(group), 2) for group in merged]


# ------------------------------------------------------------------ reading


def _last(series: pd.Series) -> float | None:
    """The final finite value of a series, or None if there isn't one."""
    if series is None or len(series) == 0:
        return None
    cleaned = series.replace([np.inf, -np.inf], np.nan).dropna()
    return float(cleaned.iloc[-1]) if len(cleaned) else None


def analyse(frame: pd.DataFrame) -> TechnicalPicture:
    """Everything the technical panel needs, from one candle frame."""
    picture = TechnicalPicture(bars=len(frame) if frame is not None else 0)
    if frame is None or len(frame) < 30:
        picture.summary = "Not enough price history yet to read the technical picture."
        return picture

    close = frame["close"]
    price = _last(close)
    readings: list[Reading] = []

    # --- trend: where price sits against its moving averages -------------
    ema20, ema50, ema200 = _last(_ema(close, 20)), _last(_ema(close, 50)), _last(_ema(close, 200))
    above = [m for m in (ema20, ema50, ema200) if m is not None and price is not None and price > m]
    total_ma = len([m for m in (ema20, ema50, ema200) if m is not None])

    if total_ma:
        if len(above) == total_ma:
            picture.trend = "bullish"
        elif not above:
            picture.trend = "bearish"
        else:
            picture.trend = "mixed"

    for label, key, value in (
        ("EMA 20", "ema20", ema20), ("EMA 50", "ema50", ema50), ("EMA 200", "ema200", ema200)
    ):
        if value is None:
            continue
        side = "above" if price and price > value else "below"
        readings.append(Reading(
            key=key, label=label, value=round(value, 2), state=side,
            plain=f"Price is trading {side} its {label.lower()} average.",
            explain=(
                f"{label} is the average closing price of the last {label.split()[1]} "
                "bars, weighted toward recent ones. Price above it means recent "
                "trading has been stronger than that average."
            ),
        ))

    # --- momentum: RSI and MACD -----------------------------------------
    rsi_value = _last(_rsi(close, 14))
    if rsi_value is not None:
        if rsi_value >= 70:
            state, plain = "overbought", (
                "Momentum has been unusually strong — the kind of run that often "
                "cools off, though strong stocks can stay here for a while."
            )
        elif rsi_value <= 30:
            state, plain = "oversold", (
                "Selling has been unusually heavy, which sometimes precedes a "
                "bounce, but weak stocks can stay weak."
            )
        else:
            state, plain = "neutral", "Momentum is in its normal range — no extreme either way."
        picture.momentum = (
            "strong" if rsi_value >= 60 else "weak" if rsi_value <= 40 else "moderate"
        )
        readings.append(Reading(
            key="rsi", label="RSI (14)", value=round(rsi_value, 1), state=state, plain=plain,
            explain=(
                "RSI measures how quickly price has moved up versus down over the "
                "last 14 bars, on a 0-100 scale. Above 70 is conventionally called "
                "overbought and below 30 oversold — but it is a description of what "
                "already happened, not a signal on its own."
            ),
        ))

    line, signal_line, histogram = macd(close)
    hist = _last(histogram)
    if hist is not None:
        state = "positive" if hist > 0 else "negative"
        readings.append(Reading(
            key="macd", label="MACD (12/26/9)", value=round(hist, 3), state=state,
            plain=(
                "Short-term momentum is running ahead of the longer-term trend."
                if hist > 0 else
                "Short-term momentum is lagging the longer-term trend."
            ),
            explain=(
                "MACD compares a fast and a slow moving average. The histogram "
                "shown here is the gap between that comparison and its own average "
                "— positive means momentum is building, negative means it is fading."
            ),
        ))

    # --- trend strength ---------------------------------------------------
    adx_value = _last(adx(frame))
    if adx_value is not None:
        strong = adx_value >= 25
        readings.append(Reading(
            key="adx", label="ADX (14)", value=round(adx_value, 1),
            state="trending" if strong else "ranging",
            plain=(
                "The move has real direction behind it." if strong
                else "There is no strong trend right now — price is mostly ranging."
            ),
            explain=(
                "ADX measures how strong a trend is without saying which way it "
                "goes. Above 25 usually means a genuine trend; below that, price is "
                "chopping sideways."
            ),
        ))

    # --- volatility -------------------------------------------------------
    atr_value = _last(_atr(frame, 14))
    if atr_value is not None and price:
        atr_pct = atr_value / price * 100.0
        picture.volatility = "high" if atr_pct >= 4 else "low" if atr_pct <= 1.5 else "medium"
        readings.append(Reading(
            key="atr", label="ATR (14)", value=round(atr_value, 2), state=picture.volatility,
            plain=f"On a typical bar this moves about {atr_pct:.1f}% of its price.",
            explain=(
                "ATR is the average distance between a bar's high and low. It is a "
                "measure of how much this stock normally moves — useful for judging "
                "whether today's swing is unusual, and for sizing a stop."
            ),
        ))

    upper, middle, lower = bollinger(close)
    upper_v, lower_v = _last(upper), _last(lower)
    if upper_v and lower_v and price:
        if price > upper_v:
            state, plain = "above band", "Price has pushed above its normal range."
        elif price < lower_v:
            state, plain = "below band", "Price has dropped below its normal range."
        else:
            state, plain = "inside band", "Price is inside its normal trading range."
        readings.append(Reading(
            key="bollinger", label="Bollinger (20, 2)",
            value=round((upper_v - lower_v) / price * 100.0, 2), state=state, plain=plain,
            explain=(
                "Bollinger Bands draw a channel two standard deviations either side "
                "of a 20-bar average. Roughly 95% of trading happens inside it, so "
                "the band width is a read on volatility. The number shown is that "
                "width as a percentage of price."
            ),
        ))

    # --- volume -----------------------------------------------------------
    recent_volume = frame["volume"].tail(5).mean()
    baseline_volume = frame["volume"].tail(60).mean()
    if baseline_volume and not np.isnan(baseline_volume) and baseline_volume > 0:
        ratio = recent_volume / baseline_volume
        picture.volume = (
            "increasing" if ratio >= 1.25 else "declining" if ratio <= 0.75 else "normal"
        )
        readings.append(Reading(
            key="volume", label="Relative volume", value=round(ratio, 2), state=picture.volume,
            plain=(
                f"Recent volume is {ratio:.1f}x its usual level — "
                + ("more people are trading it than normal." if ratio >= 1.25
                   else "interest is lighter than normal." if ratio <= 0.75
                   else "participation is about average.")
            ),
            explain=(
                "Compares the last five bars of volume against the last sixty. "
                "Moves backed by heavy volume are generally taken more seriously "
                "than moves on thin trading."
            ),
        ))

    stoch_k, _ = stochastic(frame)
    k_value = _last(stoch_k)
    if k_value is not None:
        readings.append(Reading(
            key="stochastic", label="Stochastic %K", value=round(k_value, 1),
            state="high" if k_value >= 80 else "low" if k_value <= 20 else "mid",
            plain=f"Price is sitting {k_value:.0f}% of the way up its recent range.",
            explain=(
                "The stochastic shows where the current price sits between the "
                "highest high and lowest low of the recent window — 100 means at "
                "the very top of that range, 0 at the very bottom."
            ),
        ))

    obv_value = _last(obv(frame))
    if obv_value is not None:
        obv_series = obv(frame)
        earlier = _last(obv_series.head(max(len(obv_series) - 20, 1)))
        rising = earlier is not None and obv_value > earlier
        readings.append(Reading(
            key="obv", label="OBV", value=round(obv_value, 0),
            state="rising" if rising else "falling",
            plain=(
                "Volume has been arriving more on up days than down days."
                if rising else
                "Volume has been arriving more on down days than up days."
            ),
            explain=(
                "On-balance volume adds a bar's volume when price closes up and "
                "subtracts it when price closes down. A rising line suggests buying "
                "pressure is doing the work."
            ),
        ))

    vwap_value = _last(vwap(frame.tail(60)))
    if vwap_value is not None and price:
        readings.append(Reading(
            key="vwap", label="VWAP (60 bars)", value=round(vwap_value, 2),
            state="above" if price > vwap_value else "below",
            plain=(
                "Price is above the average price people actually paid recently."
                if price > vwap_value else
                "Price is below the average price people actually paid recently."
            ),
            explain=(
                "VWAP is the average price weighted by how much volume traded "
                "there, so it approximates what the average participant paid. "
                "Institutions often use it as a benchmark for execution quality."
            ),
        ))

    picture.support, picture.resistance = levels(frame)
    picture.readings = readings
    picture.summary = _summarise(picture)
    return picture


def _summarise(picture: TechnicalPicture) -> str:
    """One sentence a beginner can read without looking anything up."""
    parts = []
    if picture.trend == "bullish":
        parts.append("The trend has been pointing up")
    elif picture.trend == "bearish":
        parts.append("The trend has been pointing down")
    elif picture.trend == "mixed":
        parts.append("The trend is mixed — short and long term disagree")
    else:
        parts.append("There is not enough history to call the trend")

    if picture.momentum:
        parts.append(f"momentum looks {picture.momentum}")
    if picture.volatility:
        parts.append(f"day-to-day swings are {picture.volatility}")
    if picture.volume and picture.volume != "normal":
        parts.append(f"trading volume is {picture.volume}")

    return ", ".join(parts) + "."
