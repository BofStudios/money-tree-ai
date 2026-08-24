from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from app.common.events import EventBus
from app.common.models import Action, Position, Signal
from app.config import AppConfig, MentorConfig, RiskConfig, StrategyConfig
from app.data.base import MarketDataSource
from app.engine.portfolio_engine import PortfolioEngine
from app.execution.paper_executor import PaperExecutor
from app.execution.signal_executor import SignalExecutor
from app.mentor.narrator import Narrator
from app.risk.risk_manager import RiskManager
from app.storage.db import create_session_factory
from app.storage.repository import Repository
from app.strategy.ema_rsi import EmaRsiStrategy

START = datetime(2026, 1, 5, 14, 30, tzinfo=timezone.utc)
WATCHLIST = ["AAPL", "MSFT", "NVDA"]


class FakeData(MarketDataSource):
    """Flat candles at a controllable price, so tests drive the price directly."""

    name = "fake"

    def __init__(self) -> None:
        self.prices = {s: 100.0 for s in WATCHLIST}

    def get_ohlcv(self, symbol, timeframe, limit=400):
        price = self.prices[symbol]
        index = pd.DatetimeIndex([START + timedelta(minutes=15 * i) for i in range(60)])
        return pd.DataFrame(
            {
                "open": [price] * 60, "high": [price] * 60, "low": [price] * 60,
                "close": [price] * 60, "volume": [1000.0] * 60,
            },
            index=index,
        )

    def get_many_ohlcv(self, symbols, timeframe, limit=400):
        return {s: self.get_ohlcv(s, timeframe, limit) for s in symbols if s in self.prices}

    def get_quote(self, symbol):
        return self.prices.get(symbol)


class BuyEverything(EmaRsiStrategy):
    """Wants to be long every symbol, so portfolio caps become visible.

    Subclasses the real strategy so `snapshot()` returns genuine indicator
    readings — the dashboard and mentor both depend on those.
    """

    warmup_bars = 1

    def on_bar(self, history: pd.DataFrame, position: Position | None) -> Signal:
        if position is None:
            return Signal(Action.BUY, "test entry")
        return Signal(Action.HOLD, "holding")


def make_config(**overrides) -> AppConfig:
    base = dict(
        mode="paper",
        watchlist=list(WATCHLIST),
        timeframe="15m",
        strategy=StrategyConfig(),
        risk=RiskConfig(
            starting_paper_balance=10_000.0,
            max_position_pct=10.0,
            stop_loss_pct=2.0,
            take_profit_pct=4.0,
            max_daily_loss_pct=50.0,
            max_open_positions=2,
        ),
        mentor=MentorConfig(verbosity="chatty"),
    )
    base.update(overrides)
    return AppConfig(**base)


def build(tmp_path, mode="paper", strategy=None, config=None):
    events = EventBus()
    app_config = config or make_config(mode=mode)
    data = FakeData()
    executor = (
        SignalExecutor(events=events, starting_balance=10_000.0)
        if mode == "signal"
        else PaperExecutor(starting_balance=10_000.0, slippage_pct=0.0)
    )
    engine = PortfolioEngine(
        config=app_config,
        data=data,
        executor=executor,
        strategy=strategy or BuyEverything(),
        risk=RiskManager(app_config.risk, mode=mode),
        repo=Repository(create_session_factory(tmp_path / f"{mode}.db")),
        events=events,
        mentor=Narrator(app_config.mentor, events),
    )
    engine.data = data
    return engine


class FakeMarket:
    is_open = True


# ------------------------------------------------------------------ scanning


def test_scan_reads_every_symbol_on_the_watchlist(tmp_path):
    engine = build(tmp_path)
    engine._scan(FakeMarket(), trade=False)

    rows = {r["symbol"]: r for r in engine.watchlist_rows()}
    assert set(rows) == set(WATCHLIST)
    assert all(rows[s]["ready"] for s in WATCHLIST)
    assert all(rows[s]["price"] == pytest.approx(100.0) for s in WATCHLIST)


def test_trade_false_scan_never_opens_a_position(tmp_path):
    engine = build(tmp_path)
    engine._scan(FakeMarket(), trade=False)
    assert engine.status()["positions"] == []


def test_portfolio_cap_limits_how_many_positions_open(tmp_path):
    engine = build(tmp_path)  # max_open_positions = 2, strategy wants all three
    engine._scan(FakeMarket())

    assert len(engine.status()["positions"]) == 2


def test_each_position_gets_its_own_stop_and_target(tmp_path):
    engine = build(tmp_path)
    engine._scan(FakeMarket())

    for position in engine.status()["positions"]:
        assert position["stop_loss"] == pytest.approx(98.0)
        assert position["take_profit"] == pytest.approx(104.0)


def test_positions_are_sized_in_whole_shares(tmp_path):
    engine = build(tmp_path)
    engine._scan(FakeMarket())

    for position in engine.status()["positions"]:
        assert position["qty"] == int(position["qty"])


# ---------------------------------------------------------------- exits


def test_a_falling_price_triggers_the_stop_loss(tmp_path):
    engine = build(tmp_path)
    engine._scan(FakeMarket())
    held = engine.status()["positions"][0]["symbol"]

    engine.data.prices[held] = 97.0
    engine._scan(FakeMarket())

    assert all(p["symbol"] != held for p in engine.status()["positions"])
    trades = engine.repo.recent_trades("paper")
    assert trades[0]["symbol"] == held
    assert trades[0]["exit_reason"] == "stop-loss"
    assert trades[0]["pnl"] < 0


def test_a_rising_price_triggers_the_take_profit(tmp_path):
    engine = build(tmp_path)
    engine._scan(FakeMarket())
    held = engine.status()["positions"][0]["symbol"]

    engine.data.prices[held] = 105.0
    engine._scan(FakeMarket())

    trades = engine.repo.recent_trades("paper")
    assert trades[0]["exit_reason"] == "take-profit"
    assert trades[0]["pnl"] > 0


def test_manual_close_exits_and_records_the_trade(tmp_path):
    engine = build(tmp_path)
    engine._scan(FakeMarket())
    held = engine.status()["positions"][0]["symbol"]

    assert engine.close_position_now(held, "manual close") is True
    assert engine.repo.recent_trades("paper")[0]["exit_reason"] == "manual close"


def test_closing_a_symbol_we_do_not_hold_is_a_no_op(tmp_path):
    engine = build(tmp_path)
    assert engine.close_position_now("AAPL") is False


# ------------------------------------------------------------- watchlist


def test_symbols_can_be_added_and_dropped(tmp_path):
    engine = build(tmp_path)
    assert engine.add_symbol("tsla") is True
    assert "TSLA" in engine.symbols
    assert engine.add_symbol("TSLA") is False

    assert engine.remove_symbol("TSLA") is True
    assert "TSLA" not in engine.symbols


def test_a_held_symbol_cannot_be_dropped(tmp_path):
    engine = build(tmp_path)
    engine._scan(FakeMarket())
    held = engine.status()["positions"][0]["symbol"]

    assert engine.remove_symbol(held) is False
    assert held in engine.symbols


# ------------------------------------------------------------ persistence


def test_open_positions_survive_a_restart(tmp_path):
    engine = build(tmp_path)
    engine._scan(FakeMarket())
    held = {p["symbol"] for p in engine.status()["positions"]}

    revived = build(tmp_path)  # same tmp_path, so the same database file
    revived._restore_positions()

    assert {p["symbol"] for p in revived.status()["positions"]} == held


# ----------------------------------------------------------- signal mode


def test_signal_mode_raises_a_signal_instead_of_opening_a_position(tmp_path):
    engine = build(tmp_path, mode="signal")
    engine._scan(FakeMarket())

    status = engine.status()
    assert status["positions"] == []
    assert len(status["pending_signals"]) == 2  # portfolio cap still applies
    signal = status["pending_signals"][0]
    assert signal["kind"] == "entry"
    assert signal["stop_loss"] == pytest.approx(98.0)
    assert signal["reward_risk"] == pytest.approx(2.0)


def test_signal_mode_does_not_repeat_a_signal_while_one_is_pending(tmp_path):
    engine = build(tmp_path, mode="signal")
    engine._scan(FakeMarket())
    engine._scan(FakeMarket())

    assert len(engine.status()["pending_signals"]) == 2


def test_confirming_a_signal_starts_tracking_the_position(tmp_path):
    engine = build(tmp_path, mode="signal")
    engine._scan(FakeMarket())
    pending = engine.executor.pending_signals()[0]

    engine.executor.confirm_taken(pending.id, price=101.0)
    position = engine.executor.get_positions()[0]
    engine.register_confirmed_entry(position.symbol, position, pending.intent.reason)

    tracked = engine.status()["positions"]
    assert len(tracked) == 1
    assert tracked[0]["entry_price"] == pytest.approx(101.0)


def test_skipping_a_signal_leaves_us_flat(tmp_path):
    engine = build(tmp_path, mode="signal")
    engine._scan(FakeMarket())
    for signal in engine.executor.pending_signals():
        engine.executor.confirm_skipped(signal.id)

    assert engine.executor.get_positions() == []
    assert engine.status()["pending_signals"] == []


def test_a_tracked_signal_position_produces_an_exit_signal_at_the_stop(tmp_path):
    engine = build(tmp_path, mode="signal")
    engine._scan(FakeMarket())
    pending = engine.executor.pending_signals()[0]
    symbol = pending.intent.symbol

    engine.executor.confirm_taken(pending.id, price=100.0)
    position = next(p for p in engine.executor.get_positions() if p.symbol == symbol)
    engine.register_confirmed_entry(symbol, position, "test entry")

    engine.data.prices[symbol] = 97.0
    engine._scan(FakeMarket())

    exits = [s for s in engine.executor.pending_signals() if s.is_exit]
    assert exits and exits[0].intent.symbol == symbol


# ------------------------------------------------------------- reporting


def test_status_reports_market_and_risk_state(tmp_path):
    engine = build(tmp_path)
    status = engine.status()

    assert status["mode"] == "paper"
    assert status["executor"] == "paper"
    assert "is_open" in status["market"]
    assert status["risk"]["armed"] is False
    assert status["risk"]["max_position_pct"] == 10.0


def test_candles_are_chart_ready(tmp_path):
    engine = build(tmp_path)
    engine._scan(FakeMarket(), trade=False)

    candles = engine.candles("AAPL")
    assert candles
    assert set(candles[0]) == {"time", "open", "high", "low", "close"}
    times = [c["time"] for c in candles]
    assert times == sorted(times) and len(set(times)) == len(times)


# -------------------------------------------------------- fractional sizing


def test_a_tiny_bankroll_still_buys_a_fraction_of_a_share(tmp_path):
    """A $5 stake against a $100 stock is 0.05 shares, not zero."""
    engine = build(tmp_path)
    assert engine._round_qty(0.05, price=100.0) == pytest.approx(0.05)


def test_orders_under_the_minimum_value_are_refused(tmp_path):
    engine = build(tmp_path)
    # 0.005 shares of a $100 stock is 50 cents, below the $1 floor.
    assert engine._round_qty(0.005, price=100.0) == 0.0


def test_whole_share_mode_floors_the_quantity(tmp_path):
    config = make_config()
    config.risk.fractional_shares = False
    engine = build(tmp_path, config=config)
    assert engine._round_qty(2.9, price=100.0) == pytest.approx(2.0)


# ------------------------------------------------------------- challenge


def build_with_challenge(tmp_path, stake=5.0, target=10.0):
    from app.challenge.manager import ChallengeManager
    from app.storage.db import create_session_factory

    config = make_config()
    config.challenge.position_pct = 100.0
    config.challenge.max_open_positions = 1

    session_factory = create_session_factory(tmp_path / "challenge-engine.db")
    events = EventBus()
    engine = PortfolioEngine(
        config=config,
        data=FakeData(),
        executor=PaperExecutor(starting_balance=10_000.0, slippage_pct=0.0),
        strategy=BuyEverything(),
        risk=RiskManager(config.risk, mode="paper"),
        repo=Repository(session_factory),
        events=events,
        mentor=Narrator(config.mentor, events),
        challenges=ChallengeManager(
            config=config.challenge, risk=config.risk,
            session_factory=session_factory, events=events, mode="paper",
        ),
    )
    engine.data = engine.data
    engine.challenges.start(stake, target)
    return engine


def test_an_active_challenge_caps_spending_at_its_bankroll(tmp_path):
    """The account holds $10,000 but a $5 run must only ever deploy $5."""
    engine = build_with_challenge(tmp_path, stake=5.0)
    engine._scan(FakeMarket())

    positions = engine.status()["positions"]
    assert len(positions) == 1  # challenge cap is one at a time
    spent = positions[0]["qty"] * positions[0]["entry_price"]
    assert spent <= 5.0


def test_a_challenge_holds_only_one_position_at_a_time(tmp_path):
    engine = build_with_challenge(tmp_path)
    engine._scan(FakeMarket())
    engine._scan(FakeMarket())

    assert len(engine.status()["positions"]) == 1


def test_closed_trades_move_the_challenge_dial(tmp_path):
    engine = build_with_challenge(tmp_path, stake=5.0, target=10.0)
    engine._scan(FakeMarket())
    held = engine.status()["positions"][0]["symbol"]

    engine.data.prices[held] = 105.0  # take-profit
    engine._scan(FakeMarket())

    challenge = engine.status()["challenge"]
    assert challenge is not None
    assert challenge["trades"] == 1
    assert challenge["value"] > 5.0


def test_status_carries_the_challenge_for_the_dashboard(tmp_path):
    engine = build_with_challenge(tmp_path)
    challenge = engine.status()["challenge"]

    assert challenge["stake"] == 5.0
    assert challenge["target"] == 10.0
    assert challenge["active"] is True
    assert challenge["progress_pct"] == 0.0


def test_no_challenge_means_full_account_sizing(tmp_path):
    engine = build(tmp_path)
    balance, max_positions, position_pct = engine._effective_limits()

    assert balance.total == pytest.approx(10_000.0)
    assert max_positions == 2  # from make_config
    assert position_pct is None


# ----------------------------------------------------------- protections


def test_a_cooldown_blocks_re_entry_after_a_trade_closes(tmp_path):
    """Freqtrade's cooldown: closing a symbol should stop it reopening at once."""
    config = make_config()
    config.protections.enabled = True
    config.protections.cooldown_minutes = 60
    engine = build(tmp_path, config=config)

    engine._scan(FakeMarket())
    held = engine.status()["positions"][0]["symbol"]

    engine.data.prices[held] = 97.0        # stop out
    engine._scan(FakeMarket())
    assert engine.repo.recent_trades("paper")[0]["symbol"] == held

    engine.data.prices[held] = 100.0       # price is fine again
    engine._scan(FakeMarket())

    assert all(p["symbol"] != held for p in engine.status()["positions"])
    assert engine.protections.blocked(held) is not None


def test_locks_are_reported_on_status(tmp_path):
    config = make_config()
    config.protections.enabled = True
    engine = build(tmp_path, config=config)

    engine._scan(FakeMarket())
    held = engine.status()["positions"][0]["symbol"]
    engine.data.prices[held] = 97.0
    engine._scan(FakeMarket())

    locks = engine.status()["locks"]
    assert locks and locks[0]["symbol"] == held


def test_disabled_protections_allow_immediate_re_entry(tmp_path):
    config = make_config()
    config.protections.enabled = False
    engine = build(tmp_path, config=config)

    engine._scan(FakeMarket())
    held = engine.status()["positions"][0]["symbol"]
    engine.data.prices[held] = 97.0
    engine._scan(FakeMarket())

    assert engine.protections.blocked(held) is None


def test_mentor_context_is_json_shaped_for_claude(tmp_path):
    import json

    engine = build(tmp_path)
    engine._scan(FakeMarket())
    context = engine.mentor_context()

    json.dumps(context, default=str)  # must not raise
    assert set(context) >= {"mode", "equity", "open_positions", "watchlist", "strategy"}
