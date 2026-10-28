"""Desktop 8.0: Money Ter Ter Ter, the scalper."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from app.common.models import Action, ClosedTrade, Side, Signal
from app.engine import scalper as S
from tests.test_portfolio_engine import news_engine

NOW = datetime(2026, 10, 28, 11, 0, 5, tzinfo=S.NY)   # a Wednesday, mid-morning in New York
DIP = (-0.08, 0.02)          # falling all session, the last candle up: oversold and turning
RISE = (0.06, -0.03)


def frame(step=DIP, n=150, now=NOW):
    close = [100.0]
    for i in range(1, n):
        close.append(close[-1] + step[i % 2])
    close = np.array(close)
    index = pd.DatetimeIndex([now.replace(second=0) - timedelta(minutes=n - i) for i in range(n)]).tz_convert("UTC")
    return pd.DataFrame({"open": close, "high": close * 1.0005, "low": close * 0.9995, "close": close,
                         "volume": np.full(n, 1000.0)}, index=index)


def scalp_engine(tmp_path):
    engine = news_engine(tmp_path)
    engine.style = "scalp"
    return engine


def test_the_chart_rules_buy_a_turning_dip_and_refuse_a_rise_or_a_stale_chart():
    c = S.read_chart(frame(), NOW)
    assert c["price"] < c["vwap"] and c["rsi"] <= S.RSI_MAX and c["price"] > c["prev"]
    got = S.score(c, tipped=False)
    assert got is not None and got[1] == "dip" and got[0] >= S.DIP_ATR
    assert S.score(c, tipped=True)[0] == pytest.approx(got[0] + 1.5), "the news lifts a stock up the radar"
    assert S.STOP_MIN <= S.stop_for(c) <= S.STOP_MAX

    assert S.score(S.read_chart(frame(RISE), NOW), False) is None
    still_falling = dict(c, price=c["prev"] - 0.01)
    assert S.score(still_falling, False) is None, "a dip that has not turned is not bought"
    old = S.read_chart(frame(), NOW + timedelta(minutes=10))
    assert old is None or S.score(old, False) is None, "a candle minutes old is not a live chart"


def test_a_tick_buys_the_deepest_dip_into_the_scalp_book(tmp_path):
    engine = scalp_engine(tmp_path)
    frames = {"AAPL": frame(), "MSFT": frame((-0.05, 0.03)), "NVDA": frame(RISE)}
    rows = engine.scalper.tick(frames, now=NOW)
    assert [r["symbol"] for r in rows if r["action"] == "buy"] == ["AAPL"]
    assert engine.book_of("AAPL") == "scalp"
    p = engine.position_for("AAPL")
    equity = engine.executor.get_balance().total
    assert p.qty * p.entry_price == pytest.approx(equity * S.ALLOC, rel=0.05)
    stop = (1 - p.stop_loss / p.entry_price) * 100
    assert S.STOP_MIN - 0.01 <= stop <= S.STOP_MAX + 0.01
    assert (p.take_profit / p.entry_price - 1) * 100 == pytest.approx(stop * S.RR, rel=0.02)
    assert engine.scalper.radar[0]["symbol"] == "AAPL"


def test_no_scalp_before_9_45_and_never_more_than_the_slots(tmp_path):
    engine = scalp_engine(tmp_path)
    early = NOW.replace(hour=9, minute=40)
    engine.scalper.tick({"AAPL": frame(now=early)}, now=early)
    assert engine.position_for("AAPL") is None and "9:45" in engine.scalper.state

    frames = {s: frame() for s in ("AAPL", "MSFT", "NVDA")}
    for _ in range(4):
        engine.scalper.tick(frames, now=NOW)
        for p in engine._positions.values():
            p.opened_at = NOW   # bought "just now" on the test's clock
    held = [s for s in ("AAPL", "MSFT", "NVDA") if engine.position_for(s)]
    assert len(held) == S.SLOTS and "open" in engine.scalper.state


@pytest.mark.parametrize("later, why", [
    (timedelta(minutes=S.MAX_HOLD_MIN + 1), "time is up"),
    (timedelta(hours=5), "flat before the close"),
])
def test_the_scalper_sells_by_its_own_rules(tmp_path, later, why):
    engine = scalp_engine(tmp_path)
    assert engine.book_buy("AAPL", "scalp", "Scalp: test", 500, 0.5, 1.5) == "bought"
    engine.position_for("AAPL").opened_at = NOW
    assert engine.scalper.tick({}, now=NOW + timedelta(minutes=5)) == [] or engine.position_for("AAPL")
    rows = engine.scalper.tick({}, now=NOW + later)
    assert engine.position_for("AAPL") is None
    assert any(r["action"] == "sell" and why in r["why"] for r in rows)
    trade = engine.repo.recent_trades("paper")[0]
    assert trade["exit_reason"].startswith(S.PREFIX) and trade["entry_reason"].startswith(S.PREFIX)


def test_a_scalp_is_not_sold_by_the_chart_strategy(tmp_path):
    engine = scalp_engine(tmp_path)
    engine.book_buy("AAPL", "scalp", "Scalp: test", 500, 0.5, 1.5)
    p = engine.position_for("AAPL")
    engine._manage("AAPL", {}, p.entry_price, Signal(Action.CLOSE, "RSI overbought at 85"), engine.words())
    assert engine.position_for("AAPL") is not None
    engine._manage("MSFT", {}, 100.0, Signal(Action.BUY, "EMA12 crossed above EMA26"), engine.words())
    assert engine.position_for("MSFT") is None, "only the scalper opens positions"


def test_news_only_puts_a_stock_on_the_radar_and_the_day_trade_rule_stops_entries(tmp_path):
    engine = scalp_engine(tmp_path)
    assert engine.news_buy("AAPL", "news: big contract").startswith("watching")
    assert engine.position_for("AAPL") is None and "AAPL" in engine.scalper.symbols()

    assert engine.scalper.refused_for_day_trades("403: trade denied due to pattern day trading protection")
    engine.scalper.pdt_day = NOW.strftime("%Y-%m-%d")
    engine.scalper.tick({"AAPL": frame()}, now=NOW)
    assert engine.position_for("AAPL") is None and "day-trade" in engine.scalper.state


def test_a_losing_day_stops_new_scalps(tmp_path):
    engine = scalp_engine(tmp_path)
    when = NOW.astimezone(timezone.utc)
    for i in range(S.GUARD_MIN):
        engine.repo.save_closed_trade(ClosedTrade("AMD", Side.BUY, 1, 100, 99.7, when - timedelta(minutes=30),
                                                  when - timedelta(minutes=20 - i), -0.3, "stop-loss"),
                                      "paper", "paper", "Scalp: dip")
    engine.scalper.tick({"AAPL": frame()}, now=NOW)
    assert engine.position_for("AAPL") is None and "lost" in engine.scalper.state


def test_the_snapshot_shows_today(tmp_path):
    engine = scalp_engine(tmp_path)
    engine.book_buy("AAPL", "scalp", "Scalp: dip", 500, 0.5, 1.5)
    engine.book_sell("AAPL", "Scalp: time is up")
    snap = engine.scalper.snapshot()
    assert snap["style"] == "scalp" and snap["today"]["scalps"] == 1 and snap["open"] == []


def test_minute_candles_fetch_about_a_session_not_a_week():
    from app.data.alpaca_data import _lookback_for

    assert _lookback_for("1m", S.HISTORY_BARS) < timedelta(days=4)
    assert _lookback_for("15m", 400) > timedelta(days=20)
