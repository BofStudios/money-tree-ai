from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from app.common.models import Action, Position, Signal
from app.config import RiskConfig
from app.engine.backtester import run_backtest
from app.strategy.base import Strategy


def make_frame(rows: list[tuple[float, float, float]]) -> pd.DataFrame:
    """rows of (low, high, close)."""
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    index = pd.DatetimeIndex([start + timedelta(hours=i) for i in range(len(rows))])
    return pd.DataFrame(
        {
            "open": [c for _, _, c in rows],
            "high": [h for _, h, _ in rows],
            "low": [low for low, _, _ in rows],
            "close": [c for _, _, c in rows],
            "volume": [1.0] * len(rows),
        },
        index=index,
    )


class BuyOnceStrategy(Strategy):
    """Buys on the first bar after warmup and then never acts again."""

    warmup_bars = 2

    def __init__(self):
        self.bought = False

    def on_bar(self, history: pd.DataFrame, position: Position | None) -> Signal:
        if position is None and not self.bought:
            self.bought = True
            return Signal(Action.BUY, "test entry")
        return Signal(Action.HOLD, "idle")


@pytest.fixture
def config():
    return RiskConfig(
        starting_paper_balance=10_000.0,
        max_position_pct=100.0,
        stop_loss_pct=2.0,
        take_profit_pct=4.0,
        max_daily_loss_pct=50.0,
    )


def test_take_profit_closes_the_trade(config):
    frame = make_frame(
        [(99, 101, 100)] * 3 + [(100, 105, 104)] + [(103, 106, 105)]
    )
    result = run_backtest(frame, BuyOnceStrategy(), config)

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.exit_reason == "take-profit"
    assert trade.exit_price == pytest.approx(104.0)  # entry 100 + 4%
    assert trade.pnl > 0


def test_stop_loss_closes_the_trade(config):
    frame = make_frame(
        [(99, 101, 100)] * 3 + [(97, 101, 98)] + [(96, 99, 97)]
    )
    result = run_backtest(frame, BuyOnceStrategy(), config)

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.exit_reason == "stop-loss"
    assert trade.exit_price == pytest.approx(98.0)  # entry 100 - 2%
    assert trade.pnl < 0


def test_open_position_is_closed_at_the_end_of_the_backtest(config):
    frame = make_frame([(99, 101, 100)] * 6)
    result = run_backtest(frame, BuyOnceStrategy(), config)

    assert len(result.trades) == 1
    assert result.trades[0].exit_reason == "end of backtest"


def test_fees_make_a_flat_round_trip_slightly_negative(config):
    frame = make_frame([(99, 101, 100)] * 6)
    result = run_backtest(frame, BuyOnceStrategy(), config)

    assert result.trades[0].pnl < 0
    assert result.ending_equity < result.starting_equity


def test_equity_curve_is_recorded_for_every_bar_after_warmup(config):
    frame = make_frame([(99, 101, 100)] * 10)
    result = run_backtest(frame, BuyOnceStrategy(), config)

    assert len(result.equity_curve) == 10 - BuyOnceStrategy.warmup_bars


def test_daily_loss_counters_roll_with_simulated_time(config):
    """A losing streak must not permanently lock out a multi-day backtest."""
    config.max_daily_loss_pct = 1.0
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    index = pd.DatetimeIndex([start + timedelta(days=i) for i in range(40)])
    frame = pd.DataFrame(
        {
            "open": [100.0] * 40,
            "high": [101.0] * 40,
            "low": [97.0] * 40,
            "close": [100.0] * 40,
            "volume": [1.0] * 40,
        },
        index=index,
    )

    class AlwaysBuy(Strategy):
        warmup_bars = 2

        def on_bar(self, history, position):
            return Signal(Action.BUY, "always") if position is None else Signal(Action.HOLD, "")

    result = run_backtest(frame, AlwaysBuy(), config)
    # Each day stops out; without the day roll the kill switch would block all but the first.
    assert len(result.trades) > 5
