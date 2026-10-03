"""The news radar: the watchlist's news kept for a week, the whole market's for a day.

Recent items count more (a six-hour half-life) and round-ups that name many
companies count half, so one "stocks to watch" list cannot swing a stock's
mood. Flags only come from items that are really about the stock.
"""
from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass, field

from app.brain import text

HOUR = 3600.0
HALF_LIFE_HOURS = 6.0
KEEP_DAYS = 7
CAP = 600
WIRE_CAP = 2000
SHOWN = 80
BAD_MOOD = -0.35
GOOD_MOOD = 0.15


@dataclass
class NewsItem:
    id: int
    headline: str
    summary: str
    source: str
    symbols: list[str]
    created_at: float          # epoch seconds
    url: str = ""
    score: float | None = None  # word list, filled in on creation
    ai_score: float | None = None
    topics: list[str] | None = None   # worked out from the text unless given
    flags: list[str] | None = None

    def __post_init__(self) -> None:
        if self.score is None:
            self.score = text.score(self.headline, self.summary)
        if self.topics is None:
            self.topics = sorted(text.topics(self.headline + " " + self.summary))
        if self.flags is None:
            self.flags = text.red_flags(self.headline, self.summary)

    @property
    def mood(self) -> float:
        """The AI's reading wins when there is one: it reads context a word list cannot."""
        return self.ai_score if self.ai_score is not None else (self.score or 0.0)

    @property
    def roundup(self) -> bool:
        return len(self.symbols) > 4

    def to_dict(self) -> dict:
        d = asdict(self)
        d["mood"] = round(self.mood, 3)
        d["hits"] = [{"word": h.word, "weight": h.weight} for h in text.hits(self.headline)]
        return d

    @staticmethod
    def from_dict(d: dict) -> "NewsItem":
        keys = {"id", "headline", "summary", "source", "symbols", "created_at", "url", "score", "ai_score", "topics", "flags"}
        return NewsItem(**{k: v for k, v in d.items() if k in keys})


@dataclass(frozen=True)
class RedFlag:
    kind: str
    symbol: str
    at: float
    headline: str

    def to_dict(self) -> dict:
        return {"kind": self.kind, "symbol": self.symbol, "at": self.at, "headline": self.headline,
                "severe": text.severe(self.kind), "blocks": text.blocks_buys(self.kind)}


class NewsRadar:
    def __init__(self, now=time.time) -> None:
        self._now = now
        self._lock = threading.Lock()
        self._items: dict[int, NewsItem] = {}
        self._wire: dict[int, NewsItem] = {}

    # ---------------------------------------------------------------- ingest

    def ingest(self, fresh: list[NewsItem]) -> int:
        added = 0
        with self._lock:
            for n in fresh:
                old = self._items.get(n.id)
                if old is None:
                    added += 1
                elif old.ai_score is not None and n.ai_score is None:
                    n.ai_score = old.ai_score  # an update keeps the AI's earlier reading
                self._items[n.id] = n
            self._prune()
        return added

    def ingest_wire(self, fresh: list[NewsItem]) -> int:
        added = 0
        with self._lock:
            for n in fresh:
                if n.id not in self._wire:
                    added += 1
                self._wire[n.id] = n
            cutoff = self._now() - 24 * HOUR
            for k in [k for k, v in self._wire.items() if v.created_at < cutoff]:
                del self._wire[k]
            if len(self._wire) > WIRE_CAP:
                for v in sorted(self._wire.values(), key=lambda x: x.created_at)[: len(self._wire) - WIRE_CAP]:
                    del self._wire[v.id]
        return added

    def restore(self, saved: list[NewsItem]) -> None:
        with self._lock:
            for n in saved:
                self._items[n.id] = n
            self._prune()

    def apply_scores(self, scores: dict[int, float]) -> None:
        with self._lock:
            for i, s in scores.items():
                if i in self._items:
                    self._items[i].ai_score = max(-1.0, min(1.0, float(s)))

    # ----------------------------------------------------------------- reads

    def all(self) -> list[NewsItem]:
        with self._lock:
            return sorted(self._items.values(), key=lambda n: n.created_at, reverse=True)

    def latest_at(self) -> float | None:
        with self._lock:
            return max((n.created_at for n in self._items.values()), default=None)

    def wire_latest_at(self) -> float | None:
        with self._lock:
            return max((n.created_at for n in self._wire.values()), default=None)

    def unscored(self, limit: int) -> list[NewsItem]:
        return [n for n in self.all() if n.ai_score is None][:limit]

    def mood(self, symbol: str, hours: float = 48) -> float | None:
        t = self._now()
        total = weights = 0.0
        for n in self.all():
            if symbol not in n.symbols:
                continue
            age = max(0.0, t - n.created_at) / HOUR
            if age > hours:
                continue
            w = 0.5 ** (age / HALF_LIFE_HOURS) * (0.5 if n.roundup else 1.0)
            total += w * n.mood
            weights += w
        return total / weights if weights > 0 else None

    def count(self, symbol: str, hours: float = 24) -> int:
        since = self._now() - hours * HOUR
        return sum(1 for n in self.all() if symbol in n.symbols and n.created_at >= since)

    def flags(self, symbol: str | None = None) -> list[RedFlag]:
        t = self._now()
        out: dict[tuple, RedFlag] = {}
        for n in self.all():
            if n.roundup:
                continue
            for kind in n.flags:
                if t - n.created_at > text.flag_hours(kind) * HOUR:
                    continue
                for s in n.symbols:
                    if symbol is None or s == symbol:
                        out[(kind, s, n.headline)] = RedFlag(kind, s, n.created_at, n.headline)
        return list(out.values())

    def hot(self, exclude: set[str] | None = None, minimum: int = 3) -> list[dict]:
        """The stocks the whole wire mentions most in a day, round-ups left out."""
        exclude = exclude or set()
        t = self._now()
        with self._lock:
            pool = {**self._wire, **self._items}.values()
            by: dict[str, list[NewsItem]] = {}
            for n in pool:
                if n.roundup or t - n.created_at > 24 * HOUR:
                    continue
                for s in n.symbols:
                    if s not in exclude:
                        by.setdefault(s, []).append(n)
        rows = [{"symbol": s, "mentions": len(v), "mood": sum(x.mood for x in v) / len(v)}
                for s, v in by.items() if len(v) >= minimum]
        return sorted(rows, key=lambda r: r["mentions"], reverse=True)

    def snapshot(self, symbols: list[str]) -> dict:
        t = self._now()
        items = self.all()
        day = [n for n in items if t - n.created_at <= 24 * HOUR]
        timeline = []
        for h in range(23, -1, -1):
            lo, hi = t - (h + 1) * HOUR, t - h * HOUR
            vals = [n.mood for n in items if lo <= n.created_at < hi]
            timeline.append(sum(vals) / len(vals) if vals else None)
        recent = [n for n in items if t - n.created_at <= 12 * HOUR]
        market = None
        if recent:
            ws = [0.5 ** (((t - n.created_at) / HOUR) / HALF_LIFE_HOURS) for n in recent]
            market = sum(w * n.mood for w, n in zip(ws, recent)) / sum(ws)
        topic_rows = []
        for name in text.TOPICS:
            with_topic = [n for n in day if name in n.topics]
            if with_topic:
                topic_rows.append({"topic": name, "count": len(with_topic),
                                   "mood": sum(n.mood for n in with_topic) / len(with_topic)})
        topic_rows.sort(key=lambda r: r["count"], reverse=True)
        with self._lock:
            wire_size = len(self._wire)
        return {
            "items": [n.to_dict() for n in items[:SHOWN]],
            "moods": {s: {"mood": self.mood(s), "count": self.count(s)} for s in symbols},
            "market": market,
            "timeline": timeline,
            "topics": topic_rows,
            "flags": [f.to_dict() for f in self.flags()],
            "ai_read": sum(1 for n in items if n.ai_score is not None),
            "hot": self.hot(set(symbols))[:12],
            "wire_size": wire_size,
        }

    def _prune(self) -> None:
        cutoff = self._now() - KEEP_DAYS * 24 * HOUR
        for k in [k for k, v in self._items.items() if v.created_at < cutoff]:
            del self._items[k]
        if len(self._items) > CAP:
            for v in sorted(self._items.values(), key=lambda x: x.created_at)[: len(self._items) - CAP]:
                del self._items[v.id]
