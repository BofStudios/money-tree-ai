from datetime import datetime, timezone

import pytest

from app.common.models import Action, Balance, ClosedTrade, Position, Side, Signal
from app.config import RiskConfig
from app.risk.risk_manager import RejectionReason, RiskManager


@pytest.fixture
def config():
    return RiskConfig(
        starting_paper_balance=10_000.0,
        max_position_pct=10.0,
        stop_loss_pct=2.0,
        take_profit_pct=4.0,
        max_daily_loss_pct=5.0,
    )


@pytest.fixture
def balance():
    return Balance(total=10_000.0, available=10_000.0)


def buy_signal():
    return Signal(Action.BUY, "test entry")


def open_position(qty=0.1, entry=100.0, stop=98.0, target=104.0):
    return Position(
        symbol="BTCUSDT",
        side=Side.BUY,
        qty=qty,
        entry_price=entry,
        opened_at=datetime.now(timezone.utc),
        stop_loss=stop,
        take_profit=target,
    )


def test_starts_disarmed(config):
    assert RiskManager(config, mode="live").armed is False


def test_live_mode_rejects_orders_until_armed(config, balance):
    risk = RiskManager(config, mode="live")

    order, reason = risk.validate(buy_signal(), balance, None, price=100.0, symbol="BTCUSDT")
    assert order is None
    assert reason == RejectionReason.NOT_ARMED

    risk.arm()
    order, reason = risk.validate(buy_signal(), balance, None, price=100.0, symbol="BTCUSDT")
    assert reason is None
    assert order is not None


def test_paper_mode_does_not_require_arming(config, balance):
    risk = RiskManager(config, mode="paper")
    order, reason = risk.validate(buy_signal(), balance, None, price=100.0, symbol="BTCUSDT")
    assert reason is None
    assert order is not None


def test_position_size_respects_max_position_pct(config, balance):
    risk = RiskManager(config, mode="paper")
    order, _ = risk.validate(buy_signal(), balance, None, price=100.0, symbol="BTCUSDT")
    # 10% of 10,000 = 1,000 at price 100 -> 10 units
    assert order.qty == pytest.approx(10.0)


def test_every_entry_gets_a_stop_and_a_target(config, balance):
    risk = RiskManager(config, mode="paper")
    order, _ = risk.validate(buy_signal(), balance, None, price=100.0, symbol="BTCUSDT")
    assert order.stop_loss == pytest.approx(98.0)
    assert order.take_profit == pytest.approx(104.0)


def test_refuses_a_second_position(config, balance):
    risk = RiskManager(config, mode="paper")
    order, reason = risk.validate(
        buy_signal(), balance, open_position(), price=100.0, symbol="BTCUSDT"
    )
    assert order is None
    assert reason == RejectionReason.MAX_POSITIONS


def test_close_signal_produces_an_opposite_side_order(config, balance):
    risk = RiskManager(config, mode="paper")
    position = open_position(qty=0.5)
    order, reason = risk.validate(
        Signal(Action.CLOSE, "exit"), balance, position, price=100.0, symbol="BTCUSDT"
    )
    assert reason is None
    assert order.side is Side.SELL
    assert order.qty == pytest.approx(0.5)


def test_daily_loss_limit_disarms_live_trading(config, balance):
    risk = RiskManager(config, mode="live")
    risk.arm()
    risk.validate(buy_signal(), balance, None, price=100.0, symbol="BTCUSDT")

    losing_trade = ClosedTrade(
        symbol="BTCUSDT",
        side=Side.BUY,
        qty=1.0,
        entry_price=100.0,
        exit_price=40.0,
        opened_at=datetime.now(timezone.utc),
        closed_at=datetime.now(timezone.utc),
        pnl=-600.0,  # over the 5% (500) daily limit
        exit_reason="stop-loss",
    )
    risk.record_closed_trade(losing_trade, equity=9_400.0)

    assert risk.armed is False
    assert risk.disarm_reason == "daily loss limit reached"

    order, reason = risk.validate(buy_signal(), balance, None, price=100.0, symbol="BTCUSDT")
    assert order is None
    assert reason == RejectionReason.NOT_ARMED


def test_switching_mode_always_disarms(config):
    risk = RiskManager(config, mode="live")
    risk.arm()
    risk.set_mode("paper")
    assert risk.armed is False


def test_protective_exit_detects_stop_and_target(config):
    risk = RiskManager(config, mode="paper")
    position = open_position(entry=100.0, stop=98.0, target=104.0)

    assert risk.check_protective_exit(position, price=97.9) == "stop-loss"
    assert risk.check_protective_exit(position, price=104.1) == "take-profit"
    assert risk.check_protective_exit(position, price=101.0) is None


def test_rejects_order_when_no_cash_is_available(config):
    risk = RiskManager(config, mode="paper")
    broke = Balance(total=10_000.0, available=0.0)
    order, reason = risk.validate(buy_signal(), broke, None, price=100.0, symbol="BTCUSDT")
    assert order is None
    assert reason == RejectionReason.INSUFFICIENT_BALANCE


def test_size_is_capped_by_available_cash_not_just_total(config):
    risk = RiskManager(config, mode="paper")
    mostly_invested = Balance(total=10_000.0, available=200.0)
    order, reason = risk.validate(
        buy_signal(), mostly_invested, None, price=100.0, symbol="BTCUSDT"
    )
    assert reason is None
    assert order.qty * 100.0 <= 200.0  # never spends more cash than exists
