"""Windows pop-ups: only for a buy, a sell, or a buy waiting for the owner."""
from __future__ import annotations

from app.engine.words import Words
from app.gui.notices import notice_for


def test_a_buy_says_what_and_at_what_price():
    event = {"type": "trade_opened", "position": {"symbol": "AAPL", "qty": 2, "entry_price": 231.4}}
    assert notice_for(event, Words(False)) == ("Bought AAPL", "2 at $231.40")
    assert notice_for(event, Words(True)) == ("AAPL alındı", "2 adet, $231.40")


def test_a_sell_leads_with_the_result_and_says_why():
    event = {"type": "trade_closed", "symbol": "NVDA", "pnl": -3.25, "exit_reason": "stop-loss"}
    title, body = notice_for(event, Words(True))
    assert title == "NVDA satıldı · −$3.25"
    assert body == "stop-loss"


def test_an_approval_asks_for_the_ok():
    event = {"type": "approval_needed", "proposal": {"symbol": "MSFT", "qty": 1, "price": 505.0}}
    title, body = notice_for(event, Words(False))
    assert title == "Your OK is needed"
    assert "MSFT" in body and "$505.00" in body


def test_everything_else_stays_quiet():
    assert notice_for({"type": "step", "step": {}}, Words(False)) is None
    assert notice_for({"type": "status"}, Words(False)) is None
    assert notice_for({"type": "trade_opened"}, Words(False)) is None   # malformed: no crash
