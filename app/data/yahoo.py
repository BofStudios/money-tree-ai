from __future__ import annotations

import logging
import threading
import time

import pandas as pd
import yfinance as yf

from app.data.base import MarketDataSource

log = logging.getLogger(__name__)

# yfinance caps how far back each intraday interval reaches.
_MAX_PERIOD = {
    "1m": "7d",
    "2m": "60d",
    "5m": "60d",
    "15m": "60d",
    "30m": "60d",
    "60m": "730d",
    "1h": "730d",
    "1d": "2y",
    "1wk": "5y",
}

_ALIASES = {"1h": "60m", "4h": "60m"}

_COLUMNS = ["open", "high", "low", "close", "volume"]
CACHE_SECONDS = 45


class YahooData(MarketDataSource):
    """Free US market candles with no account and no API key.

    This is what makes Midas signal mode work on day one: the bot can analyse
    the market without any brokerage integration at all. Data is delayed by
    roughly 15 minutes, which is fine for 15m-and-slower strategies but not
    for scalping.
    """

    name = "yahoo"
    needs_credentials = False

    def __init__(self, cache_seconds: int = CACHE_SECONDS) -> None:
        self._cache: dict[tuple[str, str], tuple[float, pd.DataFrame]] = {}
        self._lock = threading.Lock()
        self._cache_seconds = cache_seconds

    def get_ohlcv(self, symbol: str, timeframe: str, limit: int = 400) -> pd.DataFrame:
        frames = self.get_many_ohlcv([symbol], timeframe, limit)
        return frames.get(symbol, _empty())

    def get_many_ohlcv(
        self, symbols: list[str], timeframe: str, limit: int = 400
    ) -> dict[str, pd.DataFrame]:
        if not symbols:
            return {}

        interval = _ALIASES.get(timeframe, timeframe)
        fresh, cached = self._split_by_cache(symbols, interval)
        result = dict(cached)

        if fresh:
            try:
                downloaded = self._download(fresh, interval, limit)
            except Exception:
                log.exception("yahoo download failed for %s", ",".join(fresh))
                downloaded = {}
            result.update(downloaded)
            self._store(downloaded, interval)

        return {s: f.tail(limit) for s, f in result.items() if not f.empty}

    def get_quote(self, symbol: str) -> float | None:
        frame = self.get_ohlcv(symbol, "1m" if _market_probably_open() else "15m", limit=2)
        if frame.empty:
            return None
        return float(frame["close"].iloc[-1])

    # ------------------------------------------------------------------ internals

    def _download(
        self, symbols: list[str], interval: str, limit: int
    ) -> dict[str, pd.DataFrame]:
        raw = yf.download(
            tickers=symbols,
            period=_MAX_PERIOD.get(interval, "60d"),
            interval=interval,
            auto_adjust=True,
            prepost=False,
            progress=False,
            threads=True,
            group_by="ticker",
        )
        if raw is None or raw.empty:
            return {}

        frames: dict[str, pd.DataFrame] = {}
        for symbol in symbols:
            try:
                slice_ = raw[symbol] if isinstance(raw.columns, pd.MultiIndex) else raw
            except KeyError:
                continue
            frame = _normalise(slice_)
            if not frame.empty:
                frames[symbol] = frame
        return frames

    def _split_by_cache(
        self, symbols: list[str], interval: str
    ) -> tuple[list[str], dict[str, pd.DataFrame]]:
        now = time.monotonic()
        stale: list[str] = []
        fresh: dict[str, pd.DataFrame] = {}
        with self._lock:
            for symbol in symbols:
                entry = self._cache.get((symbol, interval))
                if entry and now - entry[0] < self._cache_seconds:
                    fresh[symbol] = entry[1]
                else:
                    stale.append(symbol)
        return stale, fresh

    def _store(self, frames: dict[str, pd.DataFrame], interval: str) -> None:
        now = time.monotonic()
        with self._lock:
            for symbol, frame in frames.items():
                self._cache[(symbol, interval)] = (now, frame)


def _normalise(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return _empty()

    out = frame.rename(columns=str.lower)
    missing = [c for c in _COLUMNS if c not in out.columns]
    if missing:
        return _empty()

    out = out[_COLUMNS].dropna(how="all")
    if out.empty:
        return _empty()

    index = pd.to_datetime(out.index, utc=True)
    out = out.set_axis(index).sort_index()
    out = out[~out.index.duplicated(keep="last")]
    return out.astype(float).dropna()


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=_COLUMNS, index=pd.DatetimeIndex([], tz="UTC"))


def _market_probably_open() -> bool:
    """Cheap guard so quote lookups do not ask for 1m bars at 3am."""
    from app.common.market_clock import MarketClock

    return MarketClock().state().is_open
