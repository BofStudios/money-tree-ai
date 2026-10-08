"""Breaking news, fast: official feeds that need no key, plus Alpaca's wire.

Every source here was tested from this PC (2026-10-08) and is meant to be read
by machines: government press feeds are public domain, company press-release
wires publish RSS for syndication, and SEC asks only for a named User-Agent.

  Federal Reserve      rate decisions and statements
  White House          statements, executive orders, presidential actions
  NVIDIA newsroom      NVIDIA's own launches, first-hand
  GlobeNewswire, PR Newswire, Business Wire   company press releases
  Alpaca news          the whole market's wire (Benzinga), when keys are saved

The reader only reports a headline once, and only headlines published after it
started (minus a small window), so old news never starts a trade.
"""
from __future__ import annotations

import hashlib
import html as htmllib
import logging
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests

log = logging.getLogger(__name__)

USER_AGENT = "BofStudios MoneyTree-Desktop/4.1"
TIMEOUT = 12


@dataclass
class Headline:
    id: str
    source: str
    title: str
    summary: str
    url: str
    published: float                  # epoch seconds
    symbols: list[str] = field(default_factory=list)
    kind: str = "company"             # company / gov / fed / wire

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def text(self) -> str:
        return f"{self.title}. {self.summary}"


@dataclass(frozen=True)
class Feed:
    name: str
    url: str
    kind: str
    every: float                      # seconds between reads
    symbols: tuple[str, ...] = ()     # tickers every item of this feed is about


FEEDS = (
    Feed("Federal Reserve", "https://www.federalreserve.gov/feeds/press_all.xml", "fed", 30),
    Feed("White House", "https://www.whitehouse.gov/news/feed/", "gov", 30),
    Feed("White House actions", "https://www.whitehouse.gov/presidential-actions/feed/", "gov", 45),
    Feed("NVIDIA newsroom", "https://nvidianews.nvidia.com/releases.xml", "company", 30, ("NVDA",)),
    Feed("GlobeNewswire", "https://www.globenewswire.com/RssFeed/orgclass/1/feedTitle/"
         "GlobeNewswire%20-%20News%20about%20Public%20Companies", "company", 30),
    Feed("PR Newswire", "https://www.prnewswire.com/rss/news-releases-list.rss", "company", 30),
    Feed("Business Wire", "https://feed.businesswire.com/rss/home/?rss=G1QFDERJXkJeGVtRWA==", "company", 30),
)

# "(NASDAQ: MU)", "(NYSE: ETN)", "Nasdaq: NVDA", "(NYSE American: XYZ)", "(OTCQB: ...)" is ignored.
_TICKER = re.compile(
    r"\b(?:NASDAQ|Nasdaq|NYSE|NYSE American|NYSE Arca|Nasdaq GS|Nasdaq GM|Nasdaq CM|CBOE|Cboe)\s*:\s*"
    r"([A-Z]{1,5}(?:\.[A-Z])?)\b")


def tickers_in(text: str) -> list[str]:
    return list(dict.fromkeys(m.group(1).replace(".", "-") for m in _TICKER.finditer(text or "")))


def _clean(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", htmllib.unescape(html or ""))
    text = re.sub(r"<[^>]+>", " ", htmllib.unescape(text))     # escaped HTML inside RSS descriptions
    return " ".join(text.replace(" ", " ").split())


def _when(value: str | None) -> float | None:
    if not value:
        return None
    value = value.strip()
    try:
        return parsedate_to_datetime(value).timestamp()
    except Exception:
        pass
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_feed(xml_text: str | bytes, feed: Feed) -> list[Headline]:
    """RSS <item> or Atom <entry> elements as headlines. Bytes are best: the XML
    declaration then decides the encoding, not a guess from the HTTP headers."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    out: list[Headline] = []
    for el in root.iter():
        if _local(el.tag) not in ("item", "entry"):
            continue
        fields: dict[str, str] = {}
        for child in el:
            name = _local(child.tag)
            if name == "link" and child.get("href"):
                fields.setdefault("link", child.get("href"))
            elif child.text and name not in fields:
                fields[name] = child.text
        title = _clean(fields.get("title", ""))
        if not title:
            continue
        summary = _clean(fields.get("description") or fields.get("summary") or fields.get("encoded") or "")[:1200]
        url = (fields.get("link") or fields.get("guid") or fields.get("id") or "").strip()
        published = _when(fields.get("pubDate") or fields.get("published") or fields.get("updated")
                          or fields.get("date")) or time.time()
        ident = hashlib.sha1(f"{feed.name}|{url or title}".encode("utf-8")).hexdigest()[:16]
        symbols = list(dict.fromkeys(list(feed.symbols) + tickers_in(f"{title} {summary}")))
        out.append(Headline(ident, feed.name, title, summary, url, published, symbols, feed.kind))
    return out


def from_alpaca(n: dict) -> Headline | None:
    try:
        published = datetime.fromisoformat(str(n.get("created_at")).replace("Z", "+00:00")).timestamp()
        return Headline(f"alpaca-{n['id']}", str(n.get("source") or "Alpaca"), _clean(str(n.get("headline", ""))),
                        _clean(str(n.get("summary") or ""))[:1200], str(n.get("url") or ""), published,
                        [str(s).upper() for s in n.get("symbols", [])], "wire")
    except Exception:
        return None


@dataclass
class SourceState:
    name: str
    ok: bool | None = None
    last_read: float | None = None
    items: int = 0
    error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class WireReader:
    """Reads every source on its own clock and returns headlines it has not reported before."""

    def __init__(self, feeds=FEEDS, alpaca=None, now=time.time, get=None, alpaca_every: float = 15.0,
                 backlog: float = 600.0) -> None:
        self.feeds = list(feeds)
        self.alpaca = alpaca
        self._now = now
        self._http = requests.Session()
        self._http.headers["User-Agent"] = USER_AGENT
        self._get = get or self._http_get
        self._next: dict[str, float] = {}
        self._etag: dict[str, str] = {}
        self._seen: dict[str, float] = {}
        self._started = now()
        self.backlog = backlog                       # older than start minus this: never reported
        self.alpaca_every = alpaca_every
        self.state: dict[str, SourceState] = {f.name: SourceState(f.name) for f in self.feeds}
        if alpaca is not None and getattr(alpaca, "available", False):
            self.state["Alpaca news"] = SourceState("Alpaca news")
        self._alpaca_since: float | None = None

    def _http_get(self, url: str, etag: str | None) -> tuple[int, bytes, str | None]:
        headers = {"If-None-Match": etag} if etag else {}
        r = self._http.get(url, headers=headers, timeout=TIMEOUT)
        return r.status_code, r.content if r.status_code == 200 else b"", r.headers.get("ETag")

    def poll(self) -> list[Headline]:
        """Every source that is due. Returns new headlines, oldest first."""
        now = self._now()
        fresh: list[Headline] = []
        for feed in self.feeds:
            if now < self._next.get(feed.name, 0):
                continue
            self._next[feed.name] = now + feed.every
            st = self.state[feed.name]
            try:
                code, body, etag = self._get(feed.url, self._etag.get(feed.name))
                if code == 304:
                    st.ok, st.last_read, st.error = True, now, ""
                    continue
                if code != 200:
                    raise RuntimeError(f"HTTP {code}")
                if etag:
                    self._etag[feed.name] = etag
                items = parse_feed(body, feed)
                st.ok, st.last_read, st.items, st.error = True, now, len(items), ""
                fresh += items
            except Exception as exc:
                st.ok, st.last_read, st.error = False, now, str(exc)[:120]
                self._next[feed.name] = now + max(feed.every, 120)    # back off
        if "Alpaca news" in self.state and now >= self._next.get("Alpaca news", 0):
            self._next["Alpaca news"] = now + self.alpaca_every
            st = self.state["Alpaca news"]
            try:
                since = self._alpaca_since or (self._started - self.backlog)
                raw = self.alpaca.fetch([], since - 5, 50)
                items = [h for h in (from_alpaca(n) for n in raw) if h]
                if items:
                    self._alpaca_since = max(h.published for h in items)
                st.ok, st.last_read, st.items, st.error = True, now, len(items), ""
                fresh += items
            except Exception as exc:
                st.ok, st.last_read, st.error = False, now, str(exc)[:120]
                self._next["Alpaca news"] = now + 60
        out = []
        floor = self._started - self.backlog
        for h in sorted(fresh, key=lambda h: h.published):
            if h.id in self._seen or h.published < floor:
                continue
            self._seen[h.id] = now
            out.append(h)
        if len(self._seen) > 6000:
            for k in sorted(self._seen, key=self._seen.get)[:2000]:
                del self._seen[k]
        return out

    def snapshot(self) -> list[dict]:
        return [s.to_dict() for s in self.state.values()]
