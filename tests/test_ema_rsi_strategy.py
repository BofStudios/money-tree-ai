from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from app.common.models import Action, Position, Side, Signal
from app.strategy.ema_rsi import EmaRsiStrategy


def make_frame(closes: list[float]) -> pd.DataFrame:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    index = pd.DatetimeIndex([start + timedelta(hours=i) for i in range(len(closes))])
    return pd.DataFrame(
        {
            "open": closes,
            "high": [c * 1.001 for c in closes],
            "low": [c * 0.999 for c in closes],
            "close": closes,
            "volume": [1.0] * len(closes),
        },
        index=index,
    )


def replay(strategy: EmaRsiStrategy, closes: list[float], position: Position | None = None):
    """Feed bars one at a time, the way the engine does, and collect every signal."""
    frame = make_frame(closes)
    return [
        strategy.on_bar(frame.iloc[: i + 1], position)
        for i in range(strategy.warmup_bars, len(frame))
    ]


def actions(signals: list[Signal]) -> set[Action]:
    return {s.action for s in signals}


# A gradual recovery: steep enough to cross the EMAs, gentle enough that RSI
# is still well below the overbought filter when it does.
DECLINE_THEN_RECOVERY = [100 - i * 0.5 for i in range(60)] + [70 + i * 0.15 for i in range(40)]
RALLY_THEN_SELLOFF = [100 + i * 0.5 for i in range(60)] + [130 - i * 0.15 for i in range(40)]


@pytest.fixture
def strategy():
    return EmaRsiStrategy(fast_ema=5, slow_ema=10, rsi_period=14)


def open_position():
    return Position(
        symbol="BTCUSDT",
        side=Side.BUY,
        qty=1.0,
        entry_price=100.0,
        opened_at=datetime.now(timezone.utc),
    )


def test_holds_while_warming_up(strategy):
    frame = make_frame([100.0] * 5)
    assert strategy.on_bar(frame, None).action is Action.HOLD


def test_buys_when_fast_ema_crosses_above_slow(strategy):
    signals = replay(strategy, DECLINE_THEN_RECOVERY)
    buys = [s for s in signals if s.action is Action.BUY]
    assert buys, "a recovery through the slow EMA should produce a buy"
    assert "crossed above" in buys[0].reason


def test_no_buy_signal_during_a_steady_decline(strategy):
    signals = replay(strategy, [100 - i * 0.5 for i in range(60)])
    assert Action.BUY not in actions(signals)


def test_closes_when_fast_ema_crosses_back_below(strategy):
    signals = replay(strategy, RALLY_THEN_SELLOFF, position=open_position())
    closes = [s for s in signals if s.action is Action.CLOSE]
    assert closes, "a selloff through the slow EMA should produce a close"


def test_skips_entry_when_rsi_is_overbought(strategy):
    strategy.rsi_overbought = 10.0  # forces every crossover to be filtered out
    signals = replay(strategy, DECLINE_THEN_RECOVERY)

    assert Action.BUY not in actions(signals)
    assert any("overbought" in s.reason for s in signals)


def test_never_signals_buy_while_already_in_a_position(strategy):
    signals = replay(strategy, DECLINE_THEN_RECOVERY, position=open_position())
    assert Action.BUY not in actions(signals)


def test_exposes_ema_overlays_for_the_chart(strategy):
    frame = make_frame([100.0 + i for i in range(60)])
    overlays = strategy.indicator_series(frame)
    assert set(overlays) == {"EMA 5", "EMA 10"}
    assert len(overlays["EMA 5"]) == 60
