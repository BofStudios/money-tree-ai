from __future__ import annotations

import logging
import re
import threading
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

from app.data.base import MarketDataSource

log = logging.getLogger(__name__)

_COLUMNS = ["open", "high", "low", "close", "volume"]
_UNITS = {"m": TimeFrameUnit.Minute, "h": TimeFrameUnit.Hour, "d": TimeFrameUnit.Day}


class AlpacaData(MarketDataSource):
    """Alpaca market data. The free tier is IEX only — a small slice of volume.

    Good enough for 15m-and-slower signals; for tighter timeframes the Yahoo
    feed or a paid Alpaca plan will track the consolidated tape more closely.
    """

    name = "alpaca"
    needs_credentials = True

    def __init__(self, api_key: str, api_secret: str, cache_seconds: int = 45) -> None:
        self.client = StockHistoricalDataClient(api_key, api_secret)
        self._cache: dict[tuple[str, str], tuple[float, pd.DataFrame]] = {}
        self._lock = threading.Lock()
        self._cache_seconds = cache_seconds

    def get_ohlcv(self, symbol: str, timeframe: str, limit: int = 400) -> pd.DataFrame:
        return self.get_many_ohlcv([symbol], timeframe, limit).get(symbol, _empty())

    def get_many_ohlcv(
        self, symbols: list[str], timeframe: str, limit: int = 400
    ) -> dict[str, pd.DataFrame]:
        if not symbols:
            return {}

        stale, cached = self._split_by_cache(symbols, timeframe)
        if not stale:
            return {s: f.tail(limit) for s, f in cached.items()}

        symbols = stale
        step = _to_timeframe(timeframe)
        lookback = _lookback_for(timeframe, limit)
        # No `limit` here on purpose: Alpaca applies it as a total across every
        # symbol in the request, so the alphabetically first tickers eat the whole
        # quota and the rest come back empty. The date range bounds the size instead,
        # and each symbol is trimmed to `limit` below.
        request = StockBarsRequest(
            symbol_or_symbols=list(symbols),
            timeframe=step,
            start=datetime.now(timezone.utc) - lookback,
        )
        try:
            bars = self.client.get_stock_bars(request)
        except Exception:
            log.exception("alpaca bars request failed")
            return {s: f.tail(limit) for s, f in cached.items()}

        frame = bars.df
        fetched: dict[str, pd.DataFrame] = {}
        if frame is not None and not frame.empty:
            for symbol in symbols:
                try:
                    sliced = frame.xs(symbol, level="symbol")
                except KeyError:
                    continue
                normalised = _normalise(sliced)
                if not normalised.empty:
                    fetched[symbol] = normalised

        self._store(fetched, timeframe)
        merged = {**cached, **fetched}
        return {s: f.tail(limit) for s, f in merged.items()}

    def _split_by_cache(
        self, symbols: list[str], timeframe: str
    ) -> tuple[list[str], dict[str, pd.DataFrame]]:
        now = time.monotonic()
        stale: list[str] = []
        fresh: dict[str, pd.DataFrame] = {}
        with self._lock:
            for symbol in symbols:
                entry = self._cache.get((symbol, timeframe))
                if entry and now - entry[0] < self._cache_seconds:
                    fresh[symbol] = entry[1]
                else:
                    stale.append(symbol)
        return stale, fresh

    def _store(self, frames: dict[str, pd.DataFrame], timeframe: str) -> None:
        now = time.monotonic()
        with self._lock:
            for symbol, frame in frames.items():
                self._cache[(symbol, timeframe)] = (now, frame)

    def get_quote(self, symbol: str) -> float | None:
        frame = self.get_ohlcv(symbol, "1m", limit=2)
        if frame.empty:
            return None
        return float(frame["close"].iloc[-1])


def _to_timeframe(timeframe: str) -> TimeFrame:
    match = re.fullmatch(r"(\d+)([mhd])", timeframe.lower())
    if not match:
        raise ValueError(f"unsupported timeframe: {timeframe}")
    amount, unit = int(match.group(1)), match.group(2)
    return TimeFrame(amount, _UNITS[unit])


def _lookback_for(timeframe: str, limit: int) -> timedelta:
    match = re.fullmatch(r"(\d+)([mhd])", timeframe.lower())
    if not match:
        return timedelta(days=60)
    amount, unit = int(match.group(1)), match.group(2)
    minutes = {"m": 1, "h": 60, "d": 60 * 24}[unit] * amount
    # Roughly 6.5 trading hours a day, so pad generously for nights and weekends.
    bars_per_day = max((6.5 * 60) / minutes, 1)
    days = (limit / bars_per_day) * 2.2 + 5
    return timedelta(days=min(days, 730))


def _normalise(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.rename(columns=str.lower)
    if any(column not in out.columns for column in _COLUMNS):
        return _empty()
    out = out[_COLUMNS]
    out = out.set_axis(pd.to_datetime(out.index, utc=True)).sort_index()
    return out[~out.index.duplicated(keep="last")].astype(float).dropna()


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=_COLUMNS, index=pd.DatetimeIndex([], tz="UTC"))
