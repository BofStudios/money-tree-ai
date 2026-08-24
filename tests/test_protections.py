from datetime import datetime, timedelta, timezone

import pytest

from app.common.models import ClosedTrade, Side
from app.config import ProtectionsConfig
from app.risk.protections import COOLDOWN, MAX_DRAWDOWN, STOPLOSS_GUARD, Protections

START = datetime(2026, 3, 2, 15, 0, tzinfo=timezone.utc)


def trade(symbol="AAPL", pnl=-10.0, reason="stop-loss", at=START):
    return ClosedTrade(
        symbol=symbol, side=Side.BUY, qty=1.0,
        entry_price=100.0, exit_price=100.0 + pnl,
        opened_at=at - timedelta(minutes=30), closed_at=at,
        pnl=pnl, exit_reason=reason,
    )


@pytest.fixture
def config():
    return ProtectionsConfig(
        cooldown_minutes=30,
        stoploss_guard_lookback_minutes=240,
        stoploss_guard_trades=3,
        stoploss_guard_stop_minutes=120,
        max_drawdown_lookback_trades=4,
        max_drawdown_pct=15.0,
        max_drawdown_stop_minutes=240,
    )


# ------------------------------------------------------------------ cooldown


def test_a_symbol_is_locked_straight_after_a_trade(config):
    p = Protections(config)
    p.record_trade(trade("AAPL"), equity=1000.0, now=START)

    assert COOLDOWN in (p.blocked("AAPL", now=START) or "")


def test_the_cooldown_only_touches_the_symbol_that_traded(config):
    p = Protections(config)
    p.record_trade(trade("AAPL"), equity=1000.0, now=START)

    assert p.blocked("MSFT", now=START) is None


def test_the_cooldown_expires(config):
    p = Protections(config)
    p.record_trade(trade("AAPL"), equity=1000.0, now=START)

    assert p.blocked("AAPL", now=START + timedelta(minutes=31)) is None


def test_the_reason_says_how_long_is_left(config):
    p = Protections(config)
    p.record_trade(trade("AAPL"), equity=1000.0, now=START)

    assert "m left)" in p.blocked("AAPL", now=START)


# ------------------------------------------------------------ stoploss guard


def test_three_stop_outs_halt_every_symbol(config):
    p = Protections(config)
    for i, sym in enumerate(["AAPL", "MSFT", "NVDA"]):
        triggered = p.record_trade(
            trade(sym, at=START + timedelta(minutes=i)), equity=1000.0,
            now=START + timedelta(minutes=i),
        )

    assert STOPLOSS_GUARD in triggered
    # a symbol that never traded is locked too
    assert STOPLOSS_GUARD in (p.blocked("TSLA", now=START + timedelta(minutes=3)) or "")


def test_wins_do_not_count_toward_the_stoploss_guard(config):
    p = Protections(config)
    for i, sym in enumerate(["AAPL", "MSFT", "NVDA"]):
        at = START + timedelta(minutes=i)
        p.record_trade(trade(sym, pnl=5.0, reason="take-profit", at=at), 1000.0, now=at)

    assert p.blocked("TSLA", now=START + timedelta(minutes=3)) is None


def test_stop_outs_outside_the_window_are_forgotten(config):
    p = Protections(config)
    old = START - timedelta(hours=10)
    for i, sym in enumerate(["AAPL", "MSFT"]):
        p.record_trade(trade(sym, at=old + timedelta(minutes=i)), 1000.0, now=old + timedelta(minutes=i))

    p.record_trade(trade("NVDA", at=START), 1000.0, now=START)
    assert p.blocked("TSLA", now=START) is None


# --------------------------------------------------------------- drawdown


def test_a_deep_drawdown_halts_trading(config):
    p = Protections(config)
    # build a peak first
    for i in range(3):
        at = START + timedelta(minutes=i)
        p.record_trade(trade(f"S{i}", pnl=5.0, reason="take-profit", at=at), 1000.0, now=at)

    triggered = p.record_trade(
        trade("S4", pnl=-5.0, at=START + timedelta(minutes=4)),
        equity=800.0,  # 20% below the 1000 peak
        now=START + timedelta(minutes=4),
    )

    assert MAX_DRAWDOWN in triggered


def test_a_shallow_dip_does_not_halt_trading(config):
    p = Protections(config)
    for i in range(4):
        at = START + timedelta(minutes=i)
        p.record_trade(trade(f"S{i}", pnl=1.0, reason="take-profit", at=at), 1000.0, now=at)

    triggered = p.record_trade(
        trade("S5", pnl=-1.0, at=START + timedelta(minutes=5)),
        equity=950.0,  # only 5% off the peak
        now=START + timedelta(minutes=5),
    )

    assert MAX_DRAWDOWN not in triggered


def test_drawdown_needs_a_minimum_number_of_trades(config):
    p = Protections(config)
    triggered = p.record_trade(trade("AAPL"), equity=100.0, now=START)

    assert MAX_DRAWDOWN not in triggered


# ------------------------------------------------------------------ general


def test_disabled_protections_never_block(config):
    config.enabled = False
    p = Protections(config)
    for i in range(5):
        p.record_trade(trade(at=START + timedelta(minutes=i)), 100.0, now=START)

    assert p.blocked("AAPL", now=START) is None


def test_locks_are_reported_for_the_dashboard(config):
    p = Protections(config)
    p.record_trade(trade("AAPL"), equity=1000.0, now=START)

    locks = p.active_locks(now=START)
    assert len(locks) == 1
    assert locks[0]["symbol"] == "AAPL"
    assert locks[0]["minutes_left"] == 30


def test_clearing_removes_every_lock(config):
    p = Protections(config)
    p.record_trade(trade("AAPL"), equity=1000.0, now=START)
    p.clear()

    assert p.blocked("AAPL", now=START) is None
