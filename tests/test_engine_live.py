"""The engine against a brokerage: reconciling, trailing at the broker, and the
Live feed's steps. The broker here is a fake that behaves like Alpaca would."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.common import activity
from app.common.models import ClosedTrade, Side
from app.execution.base import BrokerView, Holding
from app.execution.paper_executor import PaperExecutor
from test_portfolio_engine import FakeMarket, WATCHLIST, build


class FakeBroker(PaperExecutor):
    """Paper fills, plus the brokerage side: brackets, a view, closing fills."""

    broker = "alpaca_paper"
    holds_brackets = True

    def __init__(self) -> None:
        super().__init__(starting_balance=10_000.0, slippage_pct=0.0)
        self.view = BrokerView()
        self.closing: dict[str, ClosedTrade] = {}
        self.moves: list[tuple[str, float]] = []
        self.refuse_moves = False
        self.refuse_orders: str | None = None

    def open_position(self, intent):
        if self.refuse_orders:
            raise RuntimeError(self.refuse_orders)
        position = super().open_position(intent)
        if position is not None:
            self.view.holdings[intent.symbol] = Holding(intent.symbol, position.qty, position.entry_price,
                                                        position.entry_price, 0.0)
            if position.qty == int(position.qty):
                self.view.stops[intent.symbol] = position.stop_loss
                self.view.targets[intent.symbol] = position.take_profit
        return position

    def broker_view(self):
        return self.view

    def move_stop(self, position, stop):
        if self.refuse_moves:
            raise RuntimeError("stop price must be below the market")
        if position.symbol not in self.view.stops:
            return False
        self.moves.append((position.symbol, stop))
        self.view.stops[position.symbol] = stop
        return True

    def closing_trade(self, position):
        return self.closing.get(position.symbol)

    def stop_filled(self, symbol: str, price: float) -> None:
        """Alpaca's stop leg fires while the bot is not looking."""
        position = self._positions.pop(symbol)
        self.view.holdings.pop(symbol, None)
        self.view.stops.pop(symbol, None)
        self.view.targets.pop(symbol, None)
        self.closing[symbol] = ClosedTrade(
            symbol, Side.BUY, position.qty, position.entry_price, price,
            position.opened_at, datetime.now(timezone.utc), (price - position.entry_price) * position.qty,
            "stop-loss",
        )


def broker_engine(tmp_path, language="en"):
    engine = build(tmp_path)
    engine.executor = FakeBroker()
    engine.set_language(language)
    return engine


def titles(engine, kind=None):
    return [s["title"] for s in engine.monitor.snapshot() if kind is None or s["kind"] == kind]


# ------------------------------------------------------------- reconciling


def test_a_stop_that_fired_at_alpaca_is_booked_from_the_real_fill(tmp_path):
    engine = broker_engine(tmp_path)
    engine._scan(FakeMarket())
    held = engine.status()["positions"][0]["symbol"]

    engine.executor.stop_filled(held, 97.9)
    engine._scan(FakeMarket())

    assert held not in {p["symbol"] for p in engine.status()["positions"]}
    trade = engine.repo.recent_trades("paper")[0]
    assert trade["symbol"] == held
    assert trade["exit_reason"] == "stop-loss"
    assert trade["exit_price"] == pytest.approx(97.9)
    assert any("Alpaca closed" in t for t in titles(engine, activity.SELL))


def test_positions_the_bot_did_not_open_are_shown_but_never_sold(tmp_path):
    engine = broker_engine(tmp_path)
    engine.executor.view.holdings["TSLA"] = Holding("TSLA", 3, 250.0, 240.0, -30.0)

    engine.data.prices = {s: 100.0 for s in WATCHLIST}
    engine._scan(FakeMarket())

    status = engine.status()
    assert [h["symbol"] for h in status["unmanaged"]] == ["TSLA"]
    assert "TSLA" not in {p["symbol"] for p in status["positions"]}
    assert not any("TSLA" in t for t in titles(engine, activity.SELL))


def test_a_position_missing_at_the_broker_without_a_fill_is_dropped_not_invented(tmp_path):
    engine = broker_engine(tmp_path)
    engine._scan(FakeMarket())
    held = engine.status()["positions"][0]["symbol"]

    engine.executor.view.holdings.pop(held)   # gone, and no sell on record
    engine._scan(FakeMarket())

    assert held not in {p["symbol"] for p in engine.status()["positions"]}
    assert engine.repo.recent_trades("paper") == []
    assert any(held in t for t in titles(engine, activity.WARN))


# ------------------------------------------------------------------ stops


def test_a_trailing_stop_is_moved_at_the_broker(tmp_path):
    engine = broker_engine(tmp_path)
    engine._scan(FakeMarket())
    held = engine.status()["positions"][0]["symbol"]

    engine.data.prices[held] = 103.0   # up 3%: the trail activates
    engine._scan(FakeMarket())

    symbol, stop = engine.executor.moves[-1]
    assert symbol == held
    assert stop == pytest.approx(101.97)   # 1% under 103, whole cents
    position = next(p for p in engine.status()["positions"] if p["symbol"] == held)
    assert position["stop_loss"] == pytest.approx(101.97)
    assert position["stop_at_broker"] is True


def test_a_refused_move_keeps_the_stop_the_broker_really_has(tmp_path):
    engine = broker_engine(tmp_path)
    engine._scan(FakeMarket())
    held = engine.status()["positions"][0]["symbol"]
    engine.executor.refuse_moves = True

    engine.data.prices[held] = 103.0
    engine._scan(FakeMarket())

    position = next(p for p in engine.status()["positions"] if p["symbol"] == held)
    assert position["stop_loss"] == pytest.approx(98.0)
    failed = [s for s in engine.monitor.snapshot() if s["kind"] == activity.TRAIL]
    assert failed[-1]["state"] == activity.FAILED
    assert "below the market" in failed[-1]["detail"]


def test_a_broker_held_stop_is_left_to_the_broker(tmp_path):
    engine = broker_engine(tmp_path)
    engine._scan(FakeMarket())
    held = engine.status()["positions"][0]["symbol"]

    # The bar closes under the stop, but Alpaca holds the real stop: the bot
    # does not race it with a market sell of its own.
    engine.data.prices[held] = 97.0
    engine._scan(FakeMarket())

    assert held in {p["symbol"] for p in engine.status()["positions"]}
    assert not any(held in t for t in titles(engine, activity.SELL))


def test_a_refused_order_fails_its_step_and_the_scan_carries_on(tmp_path):
    engine = broker_engine(tmp_path)
    engine.executor.refuse_orders = "insufficient buying power"

    engine._scan(FakeMarket())

    orders = [s for s in engine.monitor.snapshot() if s["kind"] == activity.ORDER]
    assert orders and all(s["state"] == activity.FAILED for s in orders)
    assert orders[0]["detail"] == "insufficient buying power"
    assert engine.monitor.snapshot()[-1]["kind"] == activity.WAIT


def test_whole_shares_win_when_one_fits_so_the_stop_can_sit_at_alpaca(tmp_path):
    engine = broker_engine(tmp_path)
    assert engine.config.risk.fractional_shares is True

    assert engine._round_qty(3.7, 100.0) == 3.0
    assert engine._round_qty(0.4, 100.0) == pytest.approx(0.4)


# -------------------------------------------------------------- the feed


def test_a_scan_reads_as_a_sequence_of_finished_steps(tmp_path):
    engine = broker_engine(tmp_path)
    engine._scan(FakeMarket())

    steps = engine.monitor.snapshot()
    kinds = [s["kind"] for s in steps]
    for kind in (activity.CLOCK, activity.ACCOUNT, activity.POSITIONS, activity.BARS, activity.ANALYSE):
        assert kind in kinds
    assert kinds.index(activity.BARS) < kinds.index(activity.ANALYSE) < kinds.index(activity.ORDER)
    assert all(s["state"] != activity.RUNNING for s in steps)
    analysis = next(s for s in steps if s["kind"] == activity.ANALYSE)
    assert len(analysis["lines"]) == len(WATCHLIST)


def test_the_feed_speaks_turkish_when_the_owner_does(tmp_path):
    engine = broker_engine(tmp_path, language="tr")
    engine._scan(FakeMarket())

    assert "Bot hesabını okur." in titles(engine, activity.ACCOUNT)
    assert any(t.startswith("Bot emir gönderir") for t in titles(engine, activity.ORDER))


def test_a_closed_market_review_looks_but_never_trades(tmp_path):
    engine = broker_engine(tmp_path)

    class Closed:
        is_open = False
        next_open = None

    engine._scan(Closed(), trade=False)

    assert engine.status()["positions"] == []
    assert titles(engine, activity.ORDER) == []
    assert any("examines the charts" in t for t in titles(engine, activity.INFO))
    analysis = next(s for s in engine.monitor.snapshot() if s["kind"] == activity.ANALYSE)
    assert "does not trade" in analysis["detail"]


def test_switching_markets_keeps_watching_what_is_held(tmp_path):
    engine = broker_engine(tmp_path)
    engine._scan(FakeMarket())
    held = {p["symbol"] for p in engine.status()["positions"]}

    engine.set_watchlist(["ASML", "SAP"])

    assert engine.symbols == ["ASML", "SAP"]
    scanned = {row["symbol"] for row in engine.watchlist_rows()}
    assert held <= scanned


# ------------------------------------------------------------ manual close


def test_a_manual_close_waits_for_the_open_so_the_stop_stays_at_alpaca(tmp_path):
    from test_autonomy import ClosedClock, OpenClock

    engine = broker_engine(tmp_path)
    engine._scan(FakeMarket())
    held = engine.status()["positions"][0]["symbol"]

    engine.clock = ClosedClock()
    assert "market is closed" in engine.why_not_close(held)
    assert engine.close_position_now(held) is False
    assert held in {p["symbol"] for p in engine.status()["positions"]}

    engine.clock = OpenClock()
    assert engine.why_not_close(held) is None
    assert engine.close_position_now(held) is True


def test_the_simulation_can_close_at_any_hour(tmp_path):
    from test_autonomy import ClosedClock

    engine = build(tmp_path)          # PaperExecutor: nothing is held at a broker
    engine._scan(FakeMarket())
    held = engine.status()["positions"][0]["symbol"]
    engine.clock = ClosedClock()

    assert engine.close_position_now(held) is True
