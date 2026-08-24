"""Risk-based sizing, ATR stops and the trailing stop."""
from datetime import datetime, timezone

import pytest

from app.common.models import Action, Balance, Position, Side, Signal
from app.config import RiskConfig
from app.risk.risk_manager import RiskManager


@pytest.fixture
def config():
    return RiskConfig(
        starting_paper_balance=10_000.0,
        max_position_pct=100.0,      # let risk sizing decide, not the cap
        stop_loss_pct=2.0,
        max_daily_loss_pct=100.0,
        sizing="risk",
        risk_per_trade_pct=1.0,
        stop_mode="atr",
        atr_multiple=1.5,
        min_stop_pct=0.8,
        max_stop_pct=6.0,
        reward_risk=2.0,
    )


@pytest.fixture
def balance():
    return Balance(total=10_000.0, available=10_000.0)


def buy():
    return Signal(Action.BUY, "test entry")


def position(entry=100.0, stop=98.0, qty=10.0, side=Side.BUY):
    return Position(
        symbol="AAPL", side=side, qty=qty, entry_price=entry,
        opened_at=datetime.now(timezone.utc), stop_loss=stop, take_profit=entry * 1.04,
    )


# ------------------------------------------------------------- stop distance


def test_a_volatile_symbol_gets_a_wider_stop(config):
    risk = RiskManager(config, mode="paper")
    calm = risk.stop_distance_pct(price=100.0, atr=1.0)     # 1.5%
    wild = risk.stop_distance_pct(price=100.0, atr=3.0)     # 4.5%

    assert wild > calm
    assert calm == pytest.approx(1.5)
    assert wild == pytest.approx(4.5)


def test_the_stop_distance_is_clamped_at_both_ends(config):
    risk = RiskManager(config, mode="paper")

    assert risk.stop_distance_pct(100.0, atr=0.01) == pytest.approx(config.min_stop_pct)
    assert risk.stop_distance_pct(100.0, atr=50.0) == pytest.approx(config.max_stop_pct)


def test_percent_mode_ignores_atr(config):
    config.stop_mode = "percent"
    risk = RiskManager(config, mode="paper")

    assert risk.stop_distance_pct(100.0, atr=9.0) == pytest.approx(config.stop_loss_pct)


def test_a_missing_atr_falls_back_to_the_flat_stop(config):
    risk = RiskManager(config, mode="paper")
    assert risk.stop_distance_pct(100.0, atr=None) == pytest.approx(config.stop_loss_pct)


# ------------------------------------------------------------------- sizing


def test_risk_sizing_puts_the_same_cash_at_risk_whatever_the_stop(config, balance):
    """The whole point of risk sizing: the loss if the stop hits is constant."""
    risk = RiskManager(config, mode="paper")

    # Both stops are wide enough that the account balance is not the binding
    # constraint, so this measures the risk rule and not the cash cap.
    tight, wide = 2.0, 4.0
    qty_tight = risk.size_position(balance, price=100.0, stop_pct=tight)
    qty_wide = risk.size_position(balance, price=100.0, stop_pct=wide)

    risked_tight = qty_tight * 100.0 * tight / 100
    risked_wide = qty_wide * 100.0 * wide / 100
    assert risked_tight == pytest.approx(risked_wide)
    assert risked_tight == pytest.approx(100.0)  # 1% of 10,000


def test_available_cash_caps_the_size_when_the_stop_is_very_tight(config, balance):
    """A 1% stop wants the whole account; it gets trimmed to what is spendable."""
    risk = RiskManager(config, mode="paper")

    qty = risk.size_position(balance, price=100.0, stop_pct=1.0)
    assert qty * 100.0 <= balance.available


def test_a_tighter_stop_buys_more_shares(config, balance):
    risk = RiskManager(config, mode="paper")

    assert risk.size_position(balance, 100.0, stop_pct=1.0) > \
           risk.size_position(balance, 100.0, stop_pct=4.0)


def test_the_position_cap_still_wins_over_risk_sizing(config, balance):
    config.max_position_pct = 5.0  # $500 max
    risk = RiskManager(config, mode="paper")

    qty = risk.size_position(balance, price=100.0, stop_pct=0.5)
    assert qty * 100.0 <= 500.0


def test_fixed_sizing_ignores_the_stop_distance(config, balance):
    config.sizing = "fixed"
    config.max_position_pct = 10.0
    risk = RiskManager(config, mode="paper")

    tight = risk.size_position(balance, 100.0, stop_pct=1.0)
    wide = risk.size_position(balance, 100.0, stop_pct=5.0)
    assert tight == pytest.approx(wide)


# ------------------------------------------------------- levels on an order


def test_the_target_is_a_multiple_of_the_stop_distance(config, balance):
    risk = RiskManager(config, mode="paper")
    order, _ = risk.validate(buy(), balance, None, price=100.0, symbol="AAPL", atr=2.0)

    # atr 2.0 x1.5 = 3% stop -> 97.0, target 2R away -> 106.0
    assert order.stop_loss == pytest.approx(97.0)
    assert order.take_profit == pytest.approx(106.0)


def test_reward_to_risk_holds_when_the_stop_widens(config, balance):
    risk = RiskManager(config, mode="paper")
    for atr in (1.0, 2.0, 3.0):
        order, _ = risk.validate(buy(), balance, None, price=100.0, symbol="AAPL", atr=atr)
        reward = order.take_profit - 100.0
        risked = 100.0 - order.stop_loss
        assert reward / risked == pytest.approx(config.reward_risk)


# ---------------------------------------------------------- trailing stop


def test_the_stop_does_not_move_before_the_activation_point(config):
    config.trailing.activate_at_pct = 2.0
    risk = RiskManager(config, mode="paper")
    p = position(entry=100.0, stop=98.0)

    assert risk.update_trailing_stop(p, price=101.0) is None
    assert p.stop_loss == pytest.approx(98.0)


def test_the_stop_follows_a_winner_once_it_is_far_enough_up(config):
    config.trailing.activate_at_pct = 2.0
    config.trailing.trail_pct = 1.0
    risk = RiskManager(config, mode="paper")
    p = position(entry=100.0, stop=98.0)

    raised = risk.update_trailing_stop(p, price=110.0)
    assert raised == pytest.approx(108.9)  # 1% behind 110
    assert p.stop_loss == pytest.approx(108.9)


def test_the_stop_never_moves_back_down(config):
    risk = RiskManager(config, mode="paper")
    p = position(entry=100.0, stop=98.0)

    risk.update_trailing_stop(p, price=110.0)
    assert risk.update_trailing_stop(p, price=105.0) is None
    assert p.stop_loss == pytest.approx(108.9)


def test_trailing_can_be_switched_off(config):
    config.trailing.enabled = False
    risk = RiskManager(config, mode="paper")
    p = position(entry=100.0, stop=98.0)

    assert risk.update_trailing_stop(p, price=140.0) is None


def test_a_trailed_stop_then_triggers_the_exit(config):
    risk = RiskManager(config, mode="paper")
    p = position(entry=100.0, stop=98.0)

    risk.update_trailing_stop(p, price=110.0)          # stop now 108.9
    assert risk.check_protective_exit(p, price=108.0) == "stop-loss"
