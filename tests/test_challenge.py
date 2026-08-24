import pytest

from app.challenge.manager import ChallengeManager, winning_trades_needed
from app.common.events import EventBus
from app.config import ChallengeConfig, RiskConfig
from app.storage.db import create_session_factory


@pytest.fixture
def manager(tmp_path):
    return ChallengeManager(
        config=ChallengeConfig(position_pct=100.0, bust_drawdown_pct=50.0),
        risk=RiskConfig(take_profit_pct=4.0, stop_loss_pct=2.0),
        session_factory=create_session_factory(tmp_path / "ch.db"),
        events=EventBus(),
        mode="paper",
    )


# ------------------------------------------------------------------- maths


def test_doubling_five_dollars_needs_about_eighteen_wins():
    assert winning_trades_needed(5.0, 10.0, take_profit_pct=4.0, position_pct=100.0) == 18


def test_half_size_positions_need_twice_as_many_wins():
    full = winning_trades_needed(5.0, 10.0, take_profit_pct=4.0, position_pct=100.0)
    half = winning_trades_needed(5.0, 10.0, take_profit_pct=4.0, position_pct=50.0)
    assert half > full


def test_a_target_at_or_below_the_stake_needs_nothing():
    assert winning_trades_needed(5.0, 5.0, 4.0, 100.0) == 0


def test_zero_growth_can_never_reach_the_target():
    assert winning_trades_needed(5.0, 10.0, take_profit_pct=0.0, position_pct=100.0) is None


# --------------------------------------------------------------- lifecycle


def test_starting_a_run_sets_the_bankroll_to_the_stake(manager):
    state = manager.start(stake=5.0, target=10.0)
    assert state.is_active
    assert state.value == pytest.approx(5.0)
    assert state.progress_pct == 0.0
    assert manager.bankroll() == pytest.approx(5.0)


def test_no_bankroll_when_nothing_is_running(manager):
    assert manager.active() is None
    assert manager.bankroll() is None


def test_two_runs_cannot_be_active_at_once(manager):
    manager.start(5.0, 10.0)
    with pytest.raises(ValueError):
        manager.start(5.0, 10.0)


def test_target_must_be_above_the_stake(manager):
    with pytest.raises(ValueError):
        manager.start(stake=5.0, target=5.0)


def test_a_winning_trade_moves_the_dial(manager):
    manager.start(5.0, 10.0)
    state = manager.record_trade(pnl=1.0)

    assert state.value == pytest.approx(6.0)
    assert state.progress_pct == pytest.approx(20.0)
    assert state.trades == 1 and state.wins == 1


def test_reaching_the_target_wins_and_closes_the_run(manager):
    manager.start(5.0, 10.0)
    state = manager.record_trade(pnl=5.0)

    assert state.status == "won"
    assert manager.active() is None


def test_falling_through_the_floor_ends_the_run(manager):
    manager.start(5.0, 10.0)  # floor is 50% of stake = 2.50
    state = manager.record_trade(pnl=-2.6)

    assert state.status == "lost"
    assert manager.active() is None


def test_a_loss_above_the_floor_keeps_the_run_alive(manager):
    manager.start(5.0, 10.0)
    state = manager.record_trade(pnl=-1.0)

    assert state.status == "active"
    assert state.value == pytest.approx(4.0)


def test_open_position_profit_shows_before_the_trade_closes(manager):
    manager.start(5.0, 10.0)
    manager.mark_unrealised(0.5)

    state = manager.active()
    assert state.value == pytest.approx(5.5)
    assert state.realised_pnl == pytest.approx(0.0)


def test_unrealised_profit_alone_does_not_end_the_run(manager):
    """Only closed trades decide a run — an open position can still turn around."""
    manager.start(5.0, 10.0)
    manager.mark_unrealised(20.0)

    assert manager.active().status == "active"


def test_stopping_by_hand_ends_the_run(manager):
    manager.start(5.0, 10.0)
    state = manager.stop()

    assert state.status == "stopped"
    assert manager.active() is None


def test_peak_value_remembers_the_high_water_mark(manager):
    manager.start(5.0, 10.0)
    manager.record_trade(pnl=2.0)
    state = manager.record_trade(pnl=-1.0)

    assert state.value == pytest.approx(6.0)
    assert state.peak_value == pytest.approx(7.0)


def test_finished_runs_appear_in_history(manager):
    manager.start(5.0, 10.0)
    manager.stop()
    manager.start(10.0, 20.0)
    manager.record_trade(pnl=10.0)

    history = manager.history()
    assert [h["status"] for h in history] == ["won", "stopped"]


def test_odds_report_the_floor_and_the_work_required(manager):
    odds = manager.odds(5.0, 10.0)
    assert odds["winning_trades_needed"] == 18
    assert odds["bust_floor"] == pytest.approx(2.5)
    assert odds["position_pct"] == 100.0
