"""Desktop 7.0: the portfolio's three books."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import numpy as np
import pytest

from app.common.models import Action, ClosedTrade, Side, Signal
from app.engine import books as B
from tests.test_portfolio_engine import FakeMarket, news_engine


def daily(close):
    close = np.asarray(close, dtype=float)
    return {"close": close, "high": close * 1.01, "low": close * 0.99}


def rising(n=260, start=100.0, step=0.4):
    return daily(start + step * np.arange(n))


def test_trend_reads_a_long_uptrend():
    t = B.trend(rising())
    assert t["uptrend"] and t["mom126"] > 0 and t["sma50"] > t["sma200"]
    assert B.trend(daily(np.ones(150))) is None, "needs 200 days"


def test_the_split_follows_results_and_keeps_the_long_floor(tmp_path):
    engine = news_engine(tmp_path)
    now = datetime.now(timezone.utc)
    for i in range(6):   # the short book lost 3% six times
        engine.repo.save_closed_trade(ClosedTrade("AAA", Side.BUY, 1, 100, 97, now - timedelta(hours=i + 1), now, -3.0,
                                                  "stop-loss"), "paper", "paper", "news: something")
    for i in range(6):   # the swing book made 4% six times
        engine.repo.save_closed_trade(ClosedTrade("BBB", Side.BUY, 1, 100, 104, now - timedelta(hours=i + 1), now, 4.0,
                                                  "take-profit"), "paper", "paper", "Swing: pullback")
    w = engine.books.weights()
    assert abs(sum(w.values()) - 1) < 1e-9
    assert w["swing"] > B.BASE["swing"] and w["short"] < B.BASE["short"]
    assert w["long"] >= B.LONG_FLOOR


def test_a_long_holding_is_never_sold_by_the_15_minute_strategy(tmp_path):
    engine = news_engine(tmp_path)
    assert engine.book_buy("AAPL", "long", "Long-term: test", 500, 15.0, 20.0) == "bought"
    assert engine.book_of("AAPL") == "long"
    p = engine.position_for("AAPL")
    assert p.qty * p.entry_price == pytest.approx(500, rel=0.02), "sized by the book's allocation"
    assert p.stop_loss == pytest.approx(p.entry_price * 0.85, rel=0.01)
    engine._manage("AAPL", {}, p.entry_price, Signal(Action.CLOSE, "RSI overbought at 85"), engine.words())
    assert engine.position_for("AAPL") is not None
    assert engine.book_sell("AAPL", "Long-term: the long trend broke") == "sold"
    assert engine.book_of("AAPL") == "short", "the book is forgotten once sold"


def test_a_news_trade_is_not_sold_seconds_later_by_a_chart_signal(tmp_path):
    engine = news_engine(tmp_path)
    assert engine.news_buy("AAPL", "news: test", size=1.0, hours=4) == "bought"
    p = engine.position_for("AAPL")
    engine._manage("AAPL", {}, p.entry_price, Signal(Action.CLOSE, "RSI overbought at 85"), engine.words())
    assert engine.position_for("AAPL") is not None


def test_each_book_trails_with_its_own_distance(tmp_path):
    engine = news_engine(tmp_path)
    engine.book_buy("AAPL", "long", "Long-term: test", 500, 15.0, 20.0)
    p = engine.position_for("AAPL")
    stop = p.stop_loss
    engine._protect(p, p.entry_price * 1.05, engine.words())   # +5%: the short book would trail, the long one not
    assert p.stop_loss == stop
    engine._protect(p, p.entry_price * 1.20, engine.words())   # +20%: trail 15% behind
    assert p.stop_loss == pytest.approx(p.entry_price * 1.20 * 0.85, rel=0.01)


def test_the_review_buys_the_best_long_candidates_and_respects_a_falling_market(tmp_path):
    engine = news_engine(tmp_path)
    reports = {s: SimpleNamespace(decision="BUY_ZONE", score=4.5) for s in ("AAPL", "MSFT", "NVDA")}
    engine.brain = SimpleNamespace(daily={"SPY": rising(), "AAPL": rising(step=0.8), "MSFT": rising(step=0.5),
                                          "NVDA": daily(200 - 0.3 * np.arange(260))},
                                   reports=reports, discovered_symbols=lambda: [])
    done = engine.books.review(force=True)
    bought = {r["symbol"] for r in done if r["action"] == "buy"}
    assert bought & {"AAPL", "MSFT"} and "NVDA" not in bought, "a falling stock is not a long-term buy"
    assert all(engine.book_of(s) == "long" for s in bought)

    other = news_engine(tmp_path / "b")
    other.brain = SimpleNamespace(daily={"SPY": daily(200 - 0.3 * np.arange(260)), "AAPL": rising()}, reports=reports,
                                   discovered_symbols=lambda: [])
    rows = other.books.review(force=True)
    assert not [r for r in rows if r["action"] == "buy" and r["book"] == "long"]
    assert any(r["action"] == "wait" for r in rows)


def test_the_short_book_keeps_to_its_budget(tmp_path):
    engine = news_engine(tmp_path)
    budget = engine.books.budgets()["short"]["budget"]
    engine._scan(FakeMarket())
    used = sum(p.qty * p.entry_price for s, p in engine._positions.items() if engine.book_of(s) == "short")
    assert used <= budget * 1.01
