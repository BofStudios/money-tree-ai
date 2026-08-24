from __future__ import annotations

import pandas as pd

from app.common.models import Action, Position, Signal
from app.strategy.base import Strategy
from app.strategy.indicators import atr, ema, rsi


class EmaRsiStrategy(Strategy):
    """Classic EMA crossover with an RSI filter.

    Long only, one position at a time — the simplest thing that is genuinely
    backtestable and readable on a chart.

    Entry: fast EMA crosses above slow EMA while RSI is below the overbought line.
    Exit:  fast EMA crosses back below slow EMA, or RSI runs past overbought.
    """

    name = "ema_rsi"

    def __init__(
        self,
        fast_ema: int = 12,
        slow_ema: int = 26,
        rsi_period: int = 14,
        rsi_overbought: float = 70.0,
        rsi_oversold: float = 30.0,
    ) -> None:
        self.fast_ema = fast_ema
        self.slow_ema = slow_ema
        self.rsi_period = rsi_period
        self.rsi_overbought = rsi_overbought
        self.rsi_oversold = rsi_oversold
        self.warmup_bars = max(slow_ema, rsi_period) * 3

    def on_bar(self, history: pd.DataFrame, position: Position | None) -> Signal:
        if len(history) < self.warmup_bars:
            return Signal(Action.HOLD, "warming up")

        close = history["close"]
        fast = ema(close, self.fast_ema)
        slow = ema(close, self.slow_ema)
        strength = rsi(close, self.rsi_period)

        fast_now, fast_prev = fast.iloc[-1], fast.iloc[-2]
        slow_now, slow_prev = slow.iloc[-1], slow.iloc[-2]
        rsi_now = strength.iloc[-1]

        if pd.isna(rsi_now):
            return Signal(Action.HOLD, "indicators not ready")

        crossed_up = fast_prev <= slow_prev and fast_now > slow_now
        crossed_down = fast_prev >= slow_prev and fast_now < slow_now

        if position is None:
            if crossed_up and rsi_now < self.rsi_overbought:
                return Signal(
                    Action.BUY,
                    f"EMA{self.fast_ema} crossed above EMA{self.slow_ema}, RSI {rsi_now:.0f}",
                )
            if crossed_up:
                return Signal(Action.HOLD, f"crossover skipped, RSI overbought at {rsi_now:.0f}")
            return Signal(Action.HOLD, "no entry signal")

        if crossed_down:
            return Signal(
                Action.CLOSE,
                f"EMA{self.fast_ema} crossed below EMA{self.slow_ema}",
            )
        if rsi_now > self.rsi_overbought:
            return Signal(Action.CLOSE, f"RSI overbought at {rsi_now:.0f}")
        return Signal(Action.HOLD, "holding position")

    def indicator_series(self, history: pd.DataFrame) -> dict[str, pd.Series]:
        close = history["close"]
        return {
            f"EMA {self.fast_ema}": ema(close, self.fast_ema),
            f"EMA {self.slow_ema}": ema(close, self.slow_ema),
        }

    def snapshot(self, history: pd.DataFrame) -> dict:
        if len(history) < max(self.slow_ema, self.rsi_period) + 2:
            return {"ready": False, "bars": len(history)}

        close = history["close"]
        fast = ema(close, self.fast_ema)
        slow = ema(close, self.slow_ema)
        strength = rsi(close, self.rsi_period)
        volatility = atr(history, 14)

        price = float(close.iloc[-1])
        fast_now = float(fast.iloc[-1])
        slow_now = float(slow.iloc[-1])
        rsi_now = float(strength.iloc[-1]) if pd.notna(strength.iloc[-1]) else None
        atr_now = float(volatility.iloc[-1]) if pd.notna(volatility.iloc[-1]) else None

        above = fast > slow
        trend = "up" if above.iloc[-1] else "down"

        # How long the current trend has held, capped at the window we have.
        bars_since_cross = 0
        for i in range(len(above) - 1, 0, -1):
            if above.iloc[i] != above.iloc[i - 1]:
                break
            bars_since_cross += 1

        zone = "neutral"
        if rsi_now is not None:
            if rsi_now >= self.rsi_overbought:
                zone = "overbought"
            elif rsi_now <= self.rsi_oversold:
                zone = "oversold"

        change_pct = None
        if len(close) > 1:
            first = float(close.iloc[0])
            change_pct = (price / first - 1) * 100 if first else None

        return {
            "ready": True,
            "bars": len(history),
            "price": price,
            "fast_ema": fast_now,
            "slow_ema": slow_now,
            "fast_period": self.fast_ema,
            "slow_period": self.slow_ema,
            "spread_pct": ((fast_now - slow_now) / slow_now * 100) if slow_now else 0.0,
            "trend": trend,
            "bars_since_cross": bars_since_cross,
            "rsi": rsi_now,
            "rsi_zone": zone,
            "rsi_overbought": self.rsi_overbought,
            "rsi_oversold": self.rsi_oversold,
            "atr": atr_now,
            "atr_pct": (atr_now / price * 100) if atr_now and price else None,
            "window_change_pct": change_pct,
        }
