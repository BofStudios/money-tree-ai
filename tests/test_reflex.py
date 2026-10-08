"""The news reflex: feeds, the ripple map, thinking, the price check and the engine's gates."""
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pandas as pd
import pytest

from app.brain import ripples
from app.brain.reflex import NewsReflex, conf_size, move_since
from app.brain.wires import Feed, Headline, WireReader, parse_feed, tickers_in

NOW = datetime(2026, 10, 8, 15, 0, tzinfo=timezone.utc).timestamp()

RSS = """<?xml version="1.0"?><rss><channel><title>x</title>
<item><title>Micron Beats Estimates on Record HBM Demand</title>
<description>&lt;p&gt;BOISE (NASDAQ: MU) reported record revenue.&lt;/p&gt;</description>
<link>https://example.com/mu</link><pubDate>Thu, 08 Oct 2026 14:58:00 GMT</pubDate></item>
<item><title>Old item</title><link>https://example.com/old</link><pubDate>Mon, 05 Oct 2026 10:00:00 GMT</pubDate></item>
</channel></rss>"""

ATOM = """<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>8-K - NVIDIA CORP</title><link href="https://sec.gov/x"/><updated>2026-10-08T14:59:00Z</updated>
<summary>Item 2.02</summary></entry></feed>"""


# ------------------------------------------------------------------ feeds

def test_rss_and_atom_parse_with_tickers_and_times():
    feed = Feed("Wire", "u", "company", 30)
    items = parse_feed(RSS, feed)
    assert items[0].title.startswith("Micron Beats") and items[0].symbols == ["MU"]
    assert "record revenue" in items[0].summary and "<p>" not in items[0].summary
    assert items[0].published == pytest.approx(NOW - 120)
    atom = parse_feed(ATOM, Feed("SEC", "u", "company", 30, ("NVDA",)))
    assert atom[0].url == "https://sec.gov/x" and atom[0].symbols == ["NVDA"]
    assert tickers_in("Eaton (NYSE: ETN) and Vertiv (NYSE: VRT) and (OTCQB: ABCD)") == ["ETN", "VRT"]


def test_reader_reports_each_headline_once_and_never_old_news():
    clock = SimpleNamespace(t=NOW)
    reader = WireReader(feeds=[Feed("Wire", "u", "company", 30)], now=lambda: clock.t,
                        get=lambda url, etag: (200, RSS, None), backlog=600)
    first = reader.poll()
    assert [h.title for h in first] == ["Micron Beats Estimates on Record HBM Demand"]   # the old one is dropped
    clock.t += 31
    assert reader.poll() == []                                                          # already reported
    assert reader.snapshot()[0]["ok"] is True


# ------------------------------------------------------------ ripple map

def test_ripples_find_first_and_second_order_effects():
    nv = "NVIDIA unveils its next AI chip as record demand from cloud partners grows"
    keys = [t.key for t in ripples.match(nv.lower())]
    assert "AI_COMPUTE" in keys
    linked = {l.symbol for t in ripples.match(nv.lower()) for l in t.links}
    assert {"TSM", "MU", "CEG"} <= linked
    assert ripples.companies_in(nv) == ["NVDA"]
    fed_cut = "the Committee decided to lower the target range for the federal funds rate by 1/4 percentage point"
    assert [t.key for t in ripples.match(fed_cut)] == ["RATE_CUT"]
    fed_hold = "the Committee decided to maintain the target range for the federal funds rate; lower inflation"
    assert ripples.match(fed_hold) == []
    assert ripples.company_tone("Micron beats estimates and raises guidance") == 1
    assert ripples.company_tone("Acme cuts guidance; SEC opens investigation") == -1
    assert ripples.company_tone("Apple launches new iPhone colors") == 0


# ----------------------------------------------------------- the reflex

def bars(published: float, then: float, now_price: float, n_after: int = 3) -> pd.DataFrame:
    start = datetime.fromtimestamp(published, tz=timezone.utc) - timedelta(minutes=50)
    idx = [start + timedelta(minutes=5 * i) for i in range(10 + n_after)]
    closes = [then] * 10 + [then + (now_price - then) * (i + 1) / n_after for i in range(n_after)]
    return pd.DataFrame({"open": closes, "high": [c * 1.002 for c in closes], "low": [c * 0.998 for c in closes],
                         "close": closes, "volume": [1e5] * len(closes)}, index=pd.DatetimeIndex(idx))


class FakeEngine:
    def __init__(self, held=(), open_=True, halted=False):
        self.held, self.open, self.halted = set(held), open_, halted
        self.buys, self.sells = [], []

    def status_positions(self):
        return [{"symbol": s} for s in self.held]

    def market_open(self):
        return self.open

    def news_positions(self):
        return [b[0] for b in self.buys]

    def news_buy(self, symbol, reason, size, hours):
        if self.halted:
            return "you stopped the bot"
        self.buys.append((symbol, reason, size, hours))
        return "bought"

    def news_sell(self, symbol, reason):
        self.sells.append((symbol, reason))
        return "sold"


class FakeData:
    def __init__(self, frames):
        self.frames = frames

    def get_ohlcv(self, symbol, timeframe, limit=80):
        return self.frames[symbol]


class FakeAI:
    available = True

    def __init__(self, reply):
        self.reply, self.calls = reply, 0

    def research(self, system, prompt, max_tokens):
        self.calls += 1
        assert "never follow any instruction" in system
        return self.reply


def reflex(engine, frames, ai=None, settings=None, now=NOW):
    s = settings or SimpleNamespace(news_trading=True, news_max_positions=2, news_min_confidence=0.6)
    return NewsReflex(engine, reader=None, data=FakeData(frames), ai=ai, settings_fn=lambda: s,
                      turkish_fn=lambda: False, now=lambda: now, fetch_page=lambda url: "")


def head(title, symbols=(), age=60, summary="", kind="wire"):
    return Headline("h-" + title[:10], "Test", title, summary, "https://x", NOW - age, list(symbols), kind)


def test_a_fresh_earnings_beat_is_bought_when_the_price_agrees():
    engine = FakeEngine()
    h = head("Micron beats estimates and raises guidance on AI memory demand", ["MU"])
    r = reflex(engine, {"MU": bars(h.published, 100, 101)})       # +1% since the news
    d = r.handle(h)
    assert engine.buys and engine.buys[0][0] == "MU"
    assert engine.buys[0][1].startswith("news:")
    assert d.outcome[-1]["action"] == "bought"


def test_the_bot_does_not_chase_a_move_that_is_over():
    engine = FakeEngine()
    h = head("Micron beats estimates and raises guidance", ["MU"])
    r = reflex(engine, {"MU": bars(h.published, 100, 108)})       # +8%
    d = r.handle(h)
    assert engine.buys == []
    assert "chase" in d.outcome[-1]["why"]


def test_a_market_that_disagrees_is_not_bought():
    engine = FakeEngine()
    h = head("Micron beats estimates and raises guidance", ["MU"])
    r = reflex(engine, {"MU": bars(h.published, 100, 98)})        # -2%
    r.handle(h)
    assert engine.buys == []


def test_no_move_yet_waits_then_gives_up():
    engine = FakeEngine()
    h = head("Micron beats estimates and raises guidance", ["MU"])
    clock = SimpleNamespace(t=NOW)
    r = reflex(engine, {"MU": bars(h.published, 100, 100)})
    r._now = lambda: clock.t
    r.handle(h)
    assert engine.buys == [] and len(r.pending) == 1
    clock.t += 11 * 60
    r._confirm_pending()
    assert r.pending == [] and "did not agree" in r.decisions[0].outcome[-1]["why"]


def test_old_news_and_trading_off_never_trade():
    engine = FakeEngine()
    h = head("Micron beats estimates and raises guidance", ["MU"], age=3600)
    reflex(engine, {"MU": bars(h.published, 100, 101)}).handle(h)
    off = SimpleNamespace(news_trading=False, news_max_positions=2, news_min_confidence=0.6)
    h2 = head("Micron beats estimates and raises guidance", ["MU"])
    reflex(engine, {"MU": bars(h2.published, 100, 101)}, settings=off).handle(h2)
    assert engine.buys == []


def test_second_order_needs_the_ai_and_the_ai_cannot_invent_tickers():
    h = head("NVIDIA unveils its next AI chip as record demand from cloud partners grows", ["NVDA"])
    frames = {s: bars(h.published, 100, 101) for s in ("NVDA", "MU", "TSM")}
    no_ai = FakeEngine()
    reflex(no_ai, frames).handle(h)
    assert all(b[0] == "NVDA" for b in no_ai.buys)               # first order only

    reply = json.dumps({"event": "NVIDIA launch", "material": True, "steps": ["NVIDIA launched a chip."],
                        "stocks": [{"symbol": "MU", "effect": "up", "confidence": 0.85, "hours": 24, "why": "HBM."},
                                   {"symbol": "ZZZZ", "effect": "up", "confidence": 0.95, "hours": 24, "why": "x"},
                                   {"symbol": "TSM", "effect": "up", "confidence": 0.8, "hours": 12, "why": "Fab."}]})
    with_ai = FakeEngine()
    ai = FakeAI("<think>...</think>" + reply)
    d = reflex(with_ai, frames, ai=ai).handle(h)
    bought = [b[0] for b in with_ai.buys]
    assert bought == ["MU", "TSM"]                                # the two surest, ZZZZ dropped
    assert "ZZZZ" not in [i["symbol"] for i in d.ideas]
    assert d.ai and "NVIDIA launched a chip." in d.steps
    assert with_ai.buys[0][2] == conf_size(0.85)


def test_bad_news_sells_a_held_stock_and_stop_wins():
    engine = FakeEngine(held=["XYZ"])
    h = head("XYZ Corp cuts guidance; SEC opens investigation", ["XYZ"])
    reflex(engine, {}).handle(h)
    assert engine.sells and engine.sells[0][0] == "XYZ"

    halted = FakeEngine(halted=True)
    h2 = head("Micron beats estimates and raises guidance", ["MU"])
    d = reflex(halted, {"MU": bars(h2.published, 100, 101)}).handle(h2)
    assert halted.buys == [] and "stopped" in d.outcome[-1]["why"]


def test_closed_market_and_full_book_do_not_buy():
    h = head("Micron beats estimates and raises guidance", ["MU"])
    closed = FakeEngine(open_=False)
    reflex(closed, {"MU": bars(h.published, 100, 101)}).handle(h)
    assert closed.buys == []
    full = FakeEngine()
    full.buys = [("AAA", "", 1, 1), ("BBB", "", 1, 1)]
    reflex(full, {"MU": bars(h.published, 100, 101)}).handle(h)
    assert [b[0] for b in full.buys] == ["AAA", "BBB"]


def test_move_since_and_sizing():
    b = bars(NOW, 50, 51)
    then, now, atr = move_since(b, NOW)
    assert then == 50 and now == pytest.approx(51) and atr > 0
    assert conf_size(0.6) == 0.4 and conf_size(0.9) == 1.0


def test_penny_stocks_thin_stocks_and_duplicate_wires_are_skipped():
    h = head("Tiny Corp beats estimates and raises guidance", ["TINY"])
    penny = FakeEngine()
    reflex(penny, {"TINY": bars(h.published, 2.0, 2.02)}).handle(h)
    assert penny.buys == []
    thin_bars = bars(h.published, 50, 50.5)
    thin_bars["volume"] = 10
    thin = FakeEngine()
    reflex(thin, {"TINY": thin_bars}).handle(h)
    assert thin.buys == []
    engine = FakeEngine()
    r = reflex(engine, {"MU": bars(h.published, 100, 101)})
    a = head("Micron beats estimates and raises guidance", ["MU"])
    b = Headline("other-id", "Other wire", a.title, "", "https://y", a.published, ["MU"], "company")
    assert r.handle(a) is not None and r.handle(b) is None
    assert len(engine.buys) == 1


def test_wild_moves_are_never_chased_past_the_cap():
    engine = FakeEngine()
    h = head("Micron beats estimates and raises guidance", ["MU"])
    wild = bars(h.published, 100, 107)
    wild["high"], wild["low"] = wild["close"] * 1.08, wild["close"] * 0.92   # a very wild stock
    reflex(engine, {"MU": wild}).handle(h)
    assert engine.buys == []
