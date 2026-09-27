"""Prices from Alpaca, with Yahoo filling whatever Alpaca did not return.

Alpaca's free feed is IEX only and a rejected or revoked key returns nothing
at all; either way the bot should keep seeing the market. Symbols the primary
source leaves out are fetched from the fallback, and a primary that returns
nothing is rested for a while instead of being asked again every minute.
"""
from __future__ import annotations

import logging
import threading
import time

import pandas as pd

from app.data.base import MarketDataSource

log = logging.getLogger(__name__)

REST_SECONDS = 600


class FallbackData(MarketDataSource):
    def __init__(self, primary: MarketDataSource, fallback: MarketDataSource) -> None:
        self.primary = primary
        self.fallback = fallback
        self._rest_until = 0.0
        self._used_fallback = False
        self._lock = threading.Lock()

    @property
    def name(self) -> str:  # type: ignore[override]
        if self._resting():
            return self.fallback.name
        if self._used_fallback:
            return f"{self.primary.name}+{self.fallback.name}"
        return self.primary.name

    def get_ohlcv(self, symbol: str, timeframe: str, limit: int = 400) -> pd.DataFrame:
        frames = self.get_many_ohlcv([symbol], timeframe, limit)
        return frames.get(symbol, pd.DataFrame())

    def get_many_ohlcv(
        self, symbols: list[str], timeframe: str, limit: int = 400
    ) -> dict[str, pd.DataFrame]:
        frames: dict[str, pd.DataFrame] = {}
        if not self._resting():
            try:
                frames = {
                    s: f for s, f in self.primary.get_many_ohlcv(symbols, timeframe, limit).items()
                    if f is not None and not f.empty
                }
            except Exception:
                log.exception("%s bars failed", self.primary.name)
                frames = {}
            if not frames and symbols:
                log.warning("%s returned no bars; using %s for %ds",
                            self.primary.name, self.fallback.name, REST_SECONDS)
                with self._lock:
                    self._rest_until = time.monotonic() + REST_SECONDS

        missing = [s for s in symbols if s not in frames]
        self._used_fallback = bool(missing)
        if missing:
            try:
                frames.update(self.fallback.get_many_ohlcv(missing, timeframe, limit))
            except Exception:
                log.exception("%s bars failed too", self.fallback.name)
        return frames

    def get_quote(self, symbol: str) -> float | None:
        if not self._resting():
            try:
                price = self.primary.get_quote(symbol)
            except Exception:
                price = None
            if price is not None:
                return price
        return self.fallback.get_quote(symbol)

    def close(self) -> None:
        self.primary.close()
        self.fallback.close()

    def _resting(self) -> bool:
        with self._lock:
            return time.monotonic() < self._rest_until
