"""One place the rest of the app asks about a company.

Caching is deliberately per-kind rather than one global TTL, because these
things go stale at wildly different speeds: a quote is old within a minute,
a balance sheet is good for a day. Getting this wrong in either direction is a
real cost — too long and the screen lies, too short and every page view burns
another slow provider round trip.

Assembling a full company view is several network calls, so the service builds
sections independently and never lets one failure take down the rest: a company
with no analyst coverage still shows its financials.
"""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable

from app.data.base import MarketDataSource
from app.research import technicals
from app.research.provider import ResearchProvider

log = logging.getLogger(__name__)

# How long each kind of answer stays usable, in seconds.
TTL = {
    "price": 60,          # moves constantly
    "profile": 86400,     # a company changes sector about never
    "valuation": 900,     # moves with price, but not tick by tick
    "quality": 21600,     # only changes when results are published
    "statements": 86400,
    "earnings": 21600,
    "analysts": 21600,
    "ownership": 86400,   # filed quarterly
    "dividend": 86400,
    "technicals": 300,
    "search": 3600,
}

# Sections a full company view is built from, and the depth each belongs to.
DEPTHS = {
    "quick": ["profile", "price", "technicals"],
    "standard": ["profile", "price", "valuation", "quality", "technicals", "earnings"],
    "deep": [
        "profile", "price", "valuation", "quality", "technicals",
        "earnings", "analysts", "statements", "dividend",
    ],
    "full": [
        "profile", "price", "valuation", "quality", "technicals",
        "earnings", "analysts", "statements", "dividend", "ownership",
    ],
}


@dataclass
class _Entry:
    value: Any
    stored_at: float


class ResearchService:
    """Company data, cached and assembled. Provider-agnostic by construction."""

    def __init__(
        self,
        provider: ResearchProvider,
        candles: MarketDataSource | None = None,
        timeframe: str = "1d",
    ) -> None:
        self.provider = provider
        self.candles = candles
        self.timeframe = timeframe
        self._cache: dict[tuple[str, str], _Entry] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ cache

    def _cached(self, kind: str, symbol: str, build: Callable[[], Any]) -> Any:
        key = (kind, symbol.upper())
        ttl = TTL.get(kind, 300)
        now = time.monotonic()

        with self._lock:
            entry = self._cache.get(key)
            if entry is not None and now - entry.stored_at < ttl:
                return entry.value

        # Built outside the lock: these are slow network calls and holding the
        # lock through them would serialise every symbol behind the first.
        try:
            value = build()
        except Exception:
            log.exception("research: %s failed for %s", kind, symbol)
            value = None

        with self._lock:
            self._cache[key] = _Entry(value=value, stored_at=time.monotonic())
        return value

    def clear(self, symbol: str | None = None) -> None:
        with self._lock:
            if symbol is None:
                self._cache.clear()
            else:
                wanted = symbol.upper()
                for key in [k for k in self._cache if k[1] == wanted]:
                    del self._cache[key]

    # --------------------------------------------------------------- sections

    def profile(self, symbol: str):
        return self._cached("profile", symbol, lambda: self.provider.profile(symbol))

    def price(self, symbol: str):
        return self._cached("price", symbol, lambda: self.provider.price(symbol))

    def valuation(self, symbol: str):
        return self._cached("valuation", symbol, lambda: self.provider.valuation(symbol))

    def quality(self, symbol: str):
        return self._cached("quality", symbol, lambda: self.provider.quality(symbol))

    def statements(self, symbol: str):
        return self._cached("statements", symbol, lambda: self.provider.statements(symbol))

    def earnings(self, symbol: str):
        return self._cached("earnings", symbol, lambda: self.provider.earnings(symbol))

    def analysts(self, symbol: str):
        return self._cached("analysts", symbol, lambda: self.provider.analysts(symbol))

    def ownership(self, symbol: str):
        return self._cached("ownership", symbol, lambda: self.provider.ownership(symbol))

    def dividend(self, symbol: str):
        return self._cached("dividend", symbol, lambda: self.provider.dividend(symbol))

    def search(self, query: str, limit: int = 8) -> list[dict]:
        key = f"{query.strip().lower()}:{limit}"
        return self._cached("search", key, lambda: self.provider.search(query, limit)) or []

    def technicals(self, symbol: str):
        def build():
            if self.candles is None:
                return None
            frame = self.candles.get_ohlcv(symbol.upper(), self.timeframe, limit=300)
            if frame is None or frame.empty:
                return None
            return technicals.analyse(frame)

        return self._cached("technicals", symbol, build)

    # ------------------------------------------------------------------- view

    def company(self, symbol: str, depth: str = "standard") -> dict:
        """Assemble a company view at the requested depth.

        Sections are fetched in parallel because they are independent network
        calls; a deep view is otherwise the sum of eight round trips.
        """
        symbol = symbol.upper()
        wanted = DEPTHS.get(depth, DEPTHS["standard"])
        builders = {
            "profile": self.profile, "price": self.price, "valuation": self.valuation,
            "quality": self.quality, "technicals": self.technicals, "earnings": self.earnings,
            "analysts": self.analysts, "statements": self.statements,
            "dividend": self.dividend, "ownership": self.ownership,
        }

        out: dict[str, Any] = {"symbol": symbol, "depth": depth}
        with ThreadPoolExecutor(max_workers=min(6, len(wanted))) as pool:
            futures = {name: pool.submit(builders[name], symbol) for name in wanted}
            for name, future in futures.items():
                try:
                    value = future.result()
                except Exception:
                    log.exception("research: section %s failed for %s", name, symbol)
                    value = None
                out[name] = value.to_dict() if hasattr(value, "to_dict") else value

        # Sections the caller asked for but the provider could not fill. Naming
        # them explicitly is what stops the UI inventing a plausible blank.
        out["unavailable"] = [name for name in wanted if out.get(name) is None]
        return out
