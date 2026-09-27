from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class MarketDataSource(ABC):
    """Where candles come from.

    Deliberately separate from order execution: in Midas signal mode the bot
    reads prices from a free public feed and never touches a brokerage API.
    """

    name: str = "base"
    needs_credentials: bool = False

    @abstractmethod
    def get_ohlcv(self, symbol: str, timeframe: str, limit: int = 400) -> pd.DataFrame:
        """Candles indexed by UTC timestamp, columns open/high/low/close/volume."""

    @abstractmethod
    def get_many_ohlcv(
        self, symbols: list[str], timeframe: str, limit: int = 400
    ) -> dict[str, pd.DataFrame]:
        """Batch fetch. Symbols that fail are simply absent from the result."""

    @abstractmethod
    def get_quote(self, symbol: str) -> float | None:
        """Latest price, or None if unavailable."""

    def close(self) -> None:
        return None
