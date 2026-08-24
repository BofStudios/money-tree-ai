from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

from app.common.models import Position, Signal


class Strategy(ABC):
    """Decides what should happen on each closed candle.

    Strategies never size orders or touch the broker; that is the risk
    manager's and engine's job. They only emit intent.
    """

    name: str = "base"
    warmup_bars: int = 100

    @abstractmethod
    def on_bar(self, history: pd.DataFrame, position: Position | None) -> Signal:
        """`history` ends with the just-closed bar, indexed by UTC timestamp."""

    def indicator_series(self, history: pd.DataFrame) -> dict[str, pd.Series]:
        """Optional overlays for the chart. Keys become chart line names."""
        return {}

    def snapshot(self, history: pd.DataFrame) -> dict:
        """Current indicator readings.

        The mentor narrates from this, so everything here must be a real
        measured value — never an estimate or a placeholder.
        """
        return {}
