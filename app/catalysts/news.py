from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

log = logging.getLogger(__name__)

CACHE_SECONDS = 600  # headlines do not change minute to minute
LOOKBACK_DAYS = 30


@dataclass
class Headline:
    created_at: datetime
    headline: str
    summary: str
    source: str
    url: str
    symbols: list[str]

    def to_dict(self) -> dict:
        return {
            "created_at": self.created_at.isoformat(),
            "headline": self.headline,
            "summary": self.summary,
            "source": self.source,
            "url": self.url,
            "symbols": self.symbols,
        }


class NewsFeed:
    """Headlines per ticker, from Alpaca's news endpoint.

    It comes with the same free Alpaca account the bot already uses, so there is
    no extra key to manage. Without credentials every call returns nothing and
    the rest of the app carries on.
    """

    def __init__(self, api_key: str = "", api_secret: str = "") -> None:
        self._client = None
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[float, list[Headline]]] = {}

        if api_key and api_secret:
            try:
                from alpaca.data.historical.news import NewsClient

                self._client = NewsClient(api_key, api_secret)
                log.info("news feed enabled")
            except Exception:
                log.exception("could not start the news feed")

    @property
    def available(self) -> bool:
        return self._client is not None

    def for_symbols(self, symbols: list[str], limit: int = 20) -> list[Headline]:
        if not self.available or not symbols:
            return []

        key = ",".join(sorted(symbols))
        with self._lock:
            entry = self._cache.get(key)
            if entry and time.monotonic() - entry[0] < CACHE_SECONDS:
                return entry[1][:limit]

        try:
            from alpaca.data.requests import NewsRequest

            response = self._client.get_news(
                NewsRequest(
                    symbols=key,
                    start=datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS),
                    limit=min(limit * 2, 50),
                    exclude_contentless=True,
                    sort="desc",
                )
            )
        except Exception:
            log.warning("news request failed", exc_info=True)
            return []

        items = response.data.get("news", []) if hasattr(response, "data") else list(response)
        headlines = [_to_headline(item) for item in items]
        headlines = [h for h in headlines if h is not None]

        with self._lock:
            self._cache[key] = (time.monotonic(), headlines)
        return headlines[:limit]

    def for_symbol(self, symbol: str, limit: int = 10) -> list[Headline]:
        return self.for_symbols([symbol.upper()], limit)


def _to_headline(item) -> Headline | None:
    try:
        created = getattr(item, "created_at", None)
        if created is None:
            return None
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        summary = (getattr(item, "summary", "") or "").strip()
        return Headline(
            created_at=created,
            headline=(getattr(item, "headline", "") or "").strip(),
            # Some sources dump the whole article in; keep it to a preview.
            summary=summary[:280],
            source=getattr(item, "source", "") or "",
            url=getattr(item, "url", "") or "",
            # Alpaca occasionally pads symbols with spaces.
            symbols=[s.strip() for s in (getattr(item, "symbols", []) or []) if s.strip()],
        )
    except Exception:
        return None
