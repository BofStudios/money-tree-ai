"""Alpaca orders, against a fake client: no request leaves the machine.

The rules under test are the ones that protect real money: brackets that
outlive the trading day, sells that only touch this app's own orders and
shares, and prices taken from actual fills.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS

import pytest

from app.common.models import Action, Position, Side, TradeIntent
from app.execution.alpaca_executor import AlpacaExecutor


def _order(symbol, side, type_="market", status="new", client_id=None, legs=None, **extra):
    return NS(
        id=uuid.uuid4(),
        client_order_id=client_id or uuid.uuid4().hex,
        symbol=symbol,
        side=side,
        type=type_,
        order_class=extra.pop("order_class", "simple"),
        status=status,
        qty=extra.pop("qty", "1"),
        filled_qty=extra.pop("filled_qty", "0"),
        filled_avg_price=extra.pop("filled_avg_price", None),
        stop_price=extra.pop("stop_price", None),
        limit_price=extra.pop("limit_price", None),
        filled_at=extra.pop("filled_at", None),
        legs=legs,
    )


class FakeClient:
    """Just enough of alpaca-py's TradingClient, recording what was asked."""

    def __init__(self):
        self.submitted = []
        self.cancelled = []
        self.closed = []
        self.replaced = []
        self.open_orders = []
        self.closed_orders = []
        self.positions = {}
        self.by_id = {}
        self.fill_price = "101.37"
        self.account = NS(
            equity="1000", cash="400", buying_power="800", last_equity="990",
            currency="USD", trading_blocked=False, account_blocked=False,
        )

    # --- orders
    def submit_order(self, request):
        self.submitted.append(request)
        legs = None
        if getattr(request, "order_class", None) is not None:
            legs = [
                _order(request.symbol, "sell", "limit", "new", order_class="bracket",
                       limit_price=str(request.take_profit.limit_price)),
                _order(request.symbol, "sell", "stop", "held", order_class="bracket",
                       stop_price=str(request.stop_loss.stop_price)),
            ]
        order = _order(request.symbol, "buy", status="accepted", client_id=request.client_order_id,
                       qty=str(request.qty), legs=legs)
        self.by_id[str(order.id)] = order
        return order

    def get_order_by_id(self, order_id):
        order = self.by_id[str(order_id)]
        if order.status in ("accepted", "new"):
            order.status = "filled"
            order.filled_qty = order.qty
            order.filled_avg_price = self.fill_price
        return order

    def get_orders(self, filter=None):
        status = getattr(filter.status, "value", filter.status)
        pool = self.open_orders if status == "open" else self.closed_orders
        symbols = filter.symbols
        return [o for o in pool if symbols is None or o.symbol in symbols]

    def cancel_order_by_id(self, order_id):
        self.cancelled.append(str(order_id))
        for parent in list(self.open_orders):
            if str(parent.id) == str(order_id):
                self.open_orders.remove(parent)
            elif parent.legs:
                parent.legs = [leg for leg in parent.legs if str(leg.id) != str(order_id)]

    def replace_order_by_id(self, order_id, request):
        self.replaced.append((str(order_id), request.stop_price))
        return NS(id=uuid.uuid4())

    # --- positions / account
    def get_all_positions(self):
        return list(self.positions.values())

    def get_open_position(self, symbol):
        if symbol not in self.positions:
            raise LookupError("position does not exist")
        return self.positions[symbol]

    def close_position(self, symbol, options=None):
        self.closed.append((symbol, options))
        order = _order(symbol, "sell", status="accepted", qty=options.qty or self.positions[symbol].qty)
        self.by_id[str(order.id)] = order
        return order

    def get_account(self):
        return self.account


def _holding(symbol, qty, avg="100", price="102"):
    return NS(symbol=symbol, qty=str(qty), avg_entry_price=avg, current_price=price, unrealized_pl="4")


def _executor(client=None, paper=True):
    return AlpacaExecutor("k", "s", paper=paper, client=client or FakeClient(), sleep=lambda _: None)


def _intent(qty, price=100.0, stop=97.123, target=106.789):
    return TradeIntent("AAPL", Side.BUY, Action.BUY, qty, price, "test", stop, target)


def _bracket_at_alpaca(client, symbol="AAPL", stop="97.12", target="106.79", client_id="mtd-abc"):
    parent = _order(symbol, "buy", status="filled", client_id=client_id, order_class="bracket", legs=[
        _order(symbol, "sell", "limit", "new", order_class="bracket", limit_price=target),
        _order(symbol, "sell", "stop", "held", order_class="bracket", stop_price=stop),
    ])
    client.open_orders.append(parent)
    return parent


# ------------------------------------------------------------------ buying


def test_whole_shares_go_in_as_a_gtc_bracket_so_the_stop_survives_the_night():
    client = FakeClient()
    position = _executor(client).open_position(_intent(2))

    request = client.submitted[0]
    assert request.time_in_force.value == "gtc"
    assert request.order_class.value == "bracket"
    assert request.stop_loss.stop_price == 97.12       # no sub-penny prices
    assert request.take_profit.limit_price == 106.79
    assert request.client_order_id.startswith("mtd-")
    # The price that actually filled, not the one the engine guessed.
    assert position.entry_price == pytest.approx(101.37)
    assert position.stop_loss == 97.12


def test_fractional_buys_are_plain_day_orders_without_a_bracket():
    client = FakeClient()
    _executor(client).open_position(_intent(0.25))

    request = client.submitted[0]
    assert request.time_in_force.value == "day"
    assert request.order_class is None
    assert request.qty == 0.25


def test_a_refused_order_raises_with_alpacas_reason():
    client = FakeClient()
    client.submit_order = lambda request: (_ for _ in ()).throw(RuntimeError("insufficient buying power"))

    with pytest.raises(RuntimeError, match="insufficient buying power"):
        _executor(client).open_position(_intent(1))


def test_an_entry_that_has_not_filled_yet_is_confirmed_on_the_next_look():
    client = FakeClient()
    client.get_order_by_id = lambda order_id: client.by_id[str(order_id)]   # never fills here
    executor = _executor(client)

    position = executor.open_position(_intent(1, price=100.0))
    assert position.entry_price == 100.0

    order = next(iter(client.by_id.values()))
    order.status, order.filled_qty, order.filled_avg_price = "filled", "1", "100.42"
    view = executor.broker_view()
    assert view.fills["AAPL"] == (1.0, 100.42)


# ----------------------------------------------------------------- selling


def test_a_sell_cancels_its_own_bracket_legs_first_then_uses_the_real_fill():
    client = FakeClient()
    parent = _bracket_at_alpaca(client)
    client.positions["AAPL"] = _holding("AAPL", 2)
    client.fill_price = "103.50"
    executor = _executor(client)
    position = Position("AAPL", Side.BUY, 2, 100.0, datetime.now(timezone.utc))
    executor.adopt_position(position)
    legs = sorted(str(leg.id) for leg in parent.legs)

    trade = executor.close_position(position, price=102.0, reason="signal")

    assert sorted(client.cancelled) == legs
    symbol, options = client.closed[0]
    assert options.percentage == "100"
    assert trade.exit_price == pytest.approx(103.50)
    assert trade.pnl == pytest.approx(7.0)


def test_a_sell_leaves_shares_and_orders_the_owner_added_themselves():
    client = FakeClient()
    _bracket_at_alpaca(client)
    own = _order("AAPL", "sell", "limit", "new", limit_price="150")   # placed by hand in Alpaca
    client.open_orders.append(own)
    client.positions["AAPL"] = _holding("AAPL", 5)
    executor = _executor(client)
    position = Position("AAPL", Side.BUY, 2, 100.0, datetime.now(timezone.utc))
    executor.adopt_position(position)

    executor.close_position(position, price=102.0, reason="signal")

    assert str(own.id) not in client.cancelled
    _, options = client.closed[0]
    assert options.qty == "2"


def test_a_position_the_stop_already_closed_reports_that_fill_instead_of_selling():
    client = FakeClient()
    opened = datetime.now(timezone.utc) - timedelta(hours=2)
    client.closed_orders.append(_order(
        "AAPL", "buy", status="filled", client_id="mtd-x", order_class="bracket", legs=[
            _order("AAPL", "sell", "stop", "filled", filled_qty="2", filled_avg_price="97.10",
                   filled_at=datetime.now(timezone.utc) - timedelta(minutes=5)),
        ],
    ))
    executor = _executor(client)
    position = Position("AAPL", Side.BUY, 2, 100.0, opened)

    trade = executor.close_position(position, price=98.0, reason="signal")

    assert client.closed == []
    assert trade.exit_reason == "stop-loss"
    assert trade.exit_price == pytest.approx(97.10)
    assert trade.pnl == pytest.approx(-5.80)


# ----------------------------------------------------------- trailing stop


def test_a_trailing_stop_is_moved_at_alpaca_not_just_in_memory():
    client = FakeClient()
    parent = _bracket_at_alpaca(client)
    executor = _executor(client)
    position = Position("AAPL", Side.BUY, 2, 100.0, datetime.now(timezone.utc))
    executor.adopt_position(position)

    assert executor.move_stop(position, 103.456) is True
    stop_leg = parent.legs[1]
    assert client.replaced == [(str(stop_leg.id), 103.46)]


def test_no_broker_stop_means_the_move_stays_with_the_engine():
    executor = _executor()
    position = Position("AAPL", Side.BUY, 0.25, 100.0, datetime.now(timezone.utc))
    assert executor.move_stop(position, 103.0) is False


# ----------------------------------------------------------------- reading


def test_the_broker_view_only_counts_this_apps_stops():
    client = FakeClient()
    _bracket_at_alpaca(client, "AAPL")
    _bracket_at_alpaca(client, "MSFT", client_id="mt-phone")   # the phone app's own trade
    client.open_orders.append(_order("NVDA", "buy", status="new"))
    client.positions = {"AAPL": _holding("AAPL", 2), "MSFT": _holding("MSFT", 1)}

    view = _executor(client).broker_view()

    assert view.stops == {"AAPL": 97.12}
    assert view.targets == {"AAPL": 106.79}
    assert view.open_buys == {"NVDA"}   # the filled bracket parents are not open buys
    assert set(view.holdings) == {"AAPL", "MSFT"}


def test_the_bot_never_spends_margin():
    balance = _executor().get_balance()
    assert balance.total == 1000
    assert balance.available == 400   # cash, not the 800 buying power


def test_the_account_summary_carries_todays_change():
    summary = _executor().account_summary()
    assert summary.today == pytest.approx(10.0)


def test_paper_and_live_name_their_money():
    assert _executor(paper=True).broker == "alpaca_paper"
    assert _executor(paper=False).broker == "alpaca_live"
