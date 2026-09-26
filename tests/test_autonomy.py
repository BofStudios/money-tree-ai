"""Autonomy: who pulls the trigger on a buy, and the checks an approval must pass.

The rules under test are about money, so each one is pinned down directly:
semi-auto never buys without a tap, manual never buys at all, sells are
automatic everywhere, and an approval is re-checked against the market as it
is when the owner answers — not as it was when the bot asked.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.common.models import Action, Side, TradeIntent
from app.engine.autonomy import (
    MAX_DRIFT_PCT,
    ProposalBook,
    resolve_autonomy,
    resolve_timeframe,
)
from test_portfolio_engine import FakeMarket, build


class _State:
    def __init__(self, is_open: bool) -> None:
        self.is_open = is_open

    def to_dict(self) -> dict:
        return {"is_open": self.is_open, "countdown": ""}


class OpenClock:
    def state(self):
        return _State(True)


class ClosedClock:
    def state(self):
        return _State(False)


def engine_with(tmp_path, autonomy: str, mode: str = "paper"):
    engine = build(tmp_path, mode=mode)
    engine.clock = OpenClock()
    engine.set_autonomy(autonomy)
    return engine


def intent(symbol="AAPL", price=100.0) -> TradeIntent:
    return TradeIntent(
        symbol=symbol, side=Side.BUY, action=Action.BUY, qty=5, price=price,
        reason="test", stop_loss=price * 0.97, take_profit=price * 1.06,
    )


# ------------------------------------------------------------------ defaults


def test_real_money_defaults_to_asking_first():
    assert resolve_autonomy(None, "live") == "semi"
    assert resolve_autonomy("unknown", "live") == "semi"


def test_practice_money_defaults_to_running_on_its_own():
    assert resolve_autonomy("unknown", "paper") == "full"


def test_an_explicit_choice_always_wins():
    assert resolve_autonomy("full", "live") == "full"
    assert resolve_autonomy("manual", "paper") == "manual"


def test_horizon_maps_to_a_real_candle_size():
    assert resolve_timeframe("short", "15m") == "15m"
    assert resolve_timeframe("medium", "15m") == "1h"
    assert resolve_timeframe("long", "15m") == "1d"
    assert resolve_timeframe("unknown", "15m") == "15m"


# -------------------------------------------------------------- the gate


def test_full_auto_buys_by_itself(tmp_path):
    engine = engine_with(tmp_path, "full")
    engine._scan(FakeMarket())

    assert len(engine.status()["positions"]) == 2
    assert engine.status()["approvals"] == []


def test_semi_auto_never_buys_without_a_tap(tmp_path):
    engine = engine_with(tmp_path, "semi")
    engine._scan(FakeMarket())

    status = engine.status()
    assert status["positions"] == []
    # Capped at two, the same as full auto would have bought.
    assert len(status["approvals"]) == 2


def test_manual_never_buys_and_holds_no_slots(tmp_path):
    engine = engine_with(tmp_path, "manual")
    engine._scan(FakeMarket())

    status = engine.status()
    assert status["positions"] == []
    assert status["approvals"] == []
    assert len(status["suggestions"]) == 3


def test_the_same_setup_is_not_re_proposed_every_scan(tmp_path):
    engine = engine_with(tmp_path, "semi")
    engine._scan(FakeMarket())
    engine._scan(FakeMarket())
    engine._scan(FakeMarket())

    assert len(engine.status()["approvals"]) == 2


def test_changing_mode_drops_requests_raised_under_the_old_one(tmp_path):
    engine = engine_with(tmp_path, "semi")
    engine._scan(FakeMarket())
    pending = engine.status()["approvals"][0]["id"]

    engine.set_autonomy("manual")

    assert engine.status()["approvals"] == []
    assert engine.approve(pending)["ok"] is False


def test_sells_stay_automatic_on_semi_auto(tmp_path):
    engine = engine_with(tmp_path, "full")
    engine._scan(FakeMarket())
    symbol = engine.status()["positions"][0]["symbol"]

    engine.set_autonomy("semi")
    engine.data.prices[symbol] = 50.0  # far through the stop
    engine._scan(FakeMarket())

    assert symbol not in {p["symbol"] for p in engine.status()["positions"]}


# ------------------------------------------------------------- approving


def test_approving_opens_the_position(tmp_path):
    engine = engine_with(tmp_path, "semi")
    engine._scan(FakeMarket())
    proposal = engine.status()["approvals"][0]

    result = engine.approve(proposal["id"])

    assert result["ok"], result["message"]
    assert proposal["symbol"] in {p["symbol"] for p in engine.status()["positions"]}


def test_an_approval_can_only_be_used_once(tmp_path):
    engine = engine_with(tmp_path, "semi")
    engine._scan(FakeMarket())
    proposal_id = engine.status()["approvals"][0]["id"]

    assert engine.approve(proposal_id)["ok"]
    assert engine.approve(proposal_id)["ok"] is False


def test_it_fills_at_the_current_price_not_the_old_one(tmp_path):
    engine = engine_with(tmp_path, "semi")
    engine._scan(FakeMarket(), trade=True)
    proposal = engine.status()["approvals"][0]
    symbol = proposal["symbol"]

    engine.data.prices[symbol] = 100.5  # inside the drift limit
    engine._scan(FakeMarket(), trade=False)
    engine.approve(proposal["id"])

    held = {p["symbol"]: p for p in engine.status()["positions"]}
    assert held[symbol]["entry_price"] == pytest.approx(100.5)


def test_a_price_that_ran_away_is_refused(tmp_path):
    engine = engine_with(tmp_path, "semi")
    engine._scan(FakeMarket())
    proposal = engine.status()["approvals"][0]

    engine.data.prices[proposal["symbol"]] = 100.0 * (1 + (MAX_DRIFT_PCT + 1) / 100)
    engine._scan(FakeMarket(), trade=False)
    result = engine.approve(proposal["id"])

    assert result["ok"] is False
    assert "moved" in result["message"]
    assert engine.status()["positions"] == []


def test_nothing_is_bought_while_the_market_is_closed(tmp_path):
    engine = engine_with(tmp_path, "semi")
    engine._scan(FakeMarket())
    proposal_id = engine.status()["approvals"][0]["id"]

    engine.clock = ClosedClock()
    result = engine.approve(proposal_id)

    assert result["ok"] is False
    assert "closed" in result["message"]


def test_real_money_needs_to_be_armed_even_when_approved(tmp_path):
    engine = engine_with(tmp_path, "semi")
    engine._scan(FakeMarket())
    proposal_id = engine.status()["approvals"][0]["id"]

    engine.mode = "live"  # disarmed by default
    result = engine.approve(proposal_id)

    assert result["ok"] is False
    assert "armed" in result["message"]


def test_skipping_frees_the_slot(tmp_path):
    engine = engine_with(tmp_path, "semi")
    engine._scan(FakeMarket())
    proposal_id = engine.status()["approvals"][0]["id"]

    assert engine.skip_proposal(proposal_id)
    assert len(engine.status()["approvals"]) == 1


# --------------------------------------------------------------- the book


def test_an_expired_request_cannot_be_approved():
    book = ProposalBook(minutes=15)
    proposal = book.add("approval", intent())
    proposal.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)

    assert book.take(proposal.id) is None
    assert book.recent()[0].status == "expired"


def test_a_suggestion_can_never_be_approved():
    book = ProposalBook()
    suggestion = book.add("suggestion", intent())

    assert book.take(suggestion.id) is None


def test_one_live_proposal_per_symbol():
    book = ProposalBook()
    assert book.add("approval", intent("AAPL")) is not None
    assert book.add("approval", intent("AAPL")) is None
    assert book.add("approval", intent("MSFT")) is not None


def test_horizon_switch_changes_the_candles_read(tmp_path):
    engine = engine_with(tmp_path, "full")

    assert engine.set_horizon("long") == "1d"
    assert engine.status()["timeframe"] == "1d"
    with pytest.raises(ValueError):
        engine.set_horizon("forever")
