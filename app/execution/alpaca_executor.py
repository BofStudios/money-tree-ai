"""Real orders on Alpaca, paper or live.

The rules here are the same as the phone app's broker, so both behave alike
on the same account:

- A whole-share buy goes in as a GTC bracket. The stop-loss and the target
  then sit at Alpaca and keep protecting the position overnight and while
  this PC is off. A DAY bracket's legs expire at the close and leave the
  position unprotected, which is why DAY is never used for one.
- Alpaca refuses brackets on fractional quantities, so a fractional buy is a
  plain DAY market order and the engine watches its stop itself.
- Every order this app sends carries a "mtd-" client id. Positions and orders
  it did not create are reported, never touched.
- A sell first cancels that position's own bracket legs (they reserve the
  shares, so the sell is refused otherwise) and waits for the cancels to land.
"""
from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Iterable, Iterator

from alpaca.common.enums import Sort
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderClass, OrderSide, QueryOrderStatus, TimeInForce
from alpaca.trading.requests import (
    ClosePositionRequest,
    GetOrdersRequest,
    MarketOrderRequest,
    ReplaceOrderRequest,
    StopLossRequest,
    TakeProfitRequest,
)

from app.common.models import Balance, ClosedTrade, Position, Side, TradeIntent
from app.execution.base import AccountSummary, BrokerView, Executor, Holding, tick

log = logging.getLogger(__name__)

CLIENT_PREFIX = "mtd-"      # this desktop app
PHONE_PREFIX = "mt-"        # the phone app, which manages its own positions
FILL_POLLS = 8              # × POLL_SECONDS: how long to wait for a market fill
CANCEL_POLLS = 10
POLL_SECONDS = 0.5
ACCOUNT_TTL_SECONDS = 5.0

_STOP_TYPES = {"stop", "stop_limit", "trailing_stop"}
# Finished orders. Anything else is still working, or about to.
_DONE = {"filled", "canceled", "expired", "replaced", "rejected", "done_for_day", "suspended"}
_FAILED = {"canceled", "expired", "rejected"}


class AlpacaExecutor(Executor):
    name = "alpaca"
    is_automatic = True
    holds_brackets = True

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        paper: bool = True,
        client: TradingClient | None = None,
        sleep=time.sleep,
    ) -> None:
        self.paper = paper
        self.client = client or TradingClient(api_key, api_secret, paper=paper)
        self._sleep = sleep
        self._entry_prices: dict[str, tuple[float, datetime]] = {}
        # Symbols the engine manages, and leg ids seen under this app's orders.
        # Together they say which open sell orders are ours to cancel or move.
        self._managed: set[str] = set()
        self._our_legs: set[str] = set()
        # Entries sent but not yet confirmed filled: symbol -> order id.
        self._unfilled: dict[str, str] = {}
        self._account_cache: tuple[float, object] | None = None

    @property
    def broker(self) -> str:  # type: ignore[override]
        return "alpaca_paper" if self.paper else "alpaca_live"

    # ------------------------------------------------------------------ orders

    def open_position(self, intent: TradeIntent) -> Position | None:
        qty = round(max(intent.qty, 0.0), 6)
        if qty <= 0:
            log.warning("%s sized to zero, skipping", intent.symbol)
            return None

        symbol = intent.symbol
        side = OrderSide.BUY if intent.side is Side.BUY else OrderSide.SELL
        client_id = CLIENT_PREFIX + uuid.uuid4().hex[:24]
        whole = qty == int(qty)
        stop = tick(intent.stop_loss) if intent.stop_loss else None
        target = tick(intent.take_profit) if intent.take_profit else None

        if whole and stop and target:
            request = MarketOrderRequest(
                symbol=symbol,
                qty=int(qty),
                side=side,
                time_in_force=TimeInForce.GTC,
                order_class=OrderClass.BRACKET,
                stop_loss=StopLossRequest(stop_price=stop),
                take_profit=TakeProfitRequest(limit_price=target),
                client_order_id=client_id,
            )
        else:
            request = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=side,
                # Fractional orders are DAY-only at Alpaca.
                time_in_force=TimeInForce.DAY,
                client_order_id=client_id,
            )

        # A refusal raises with Alpaca's own message; the engine shows it.
        order = self.client.submit_order(request)
        self._account_cache = None
        self._learn_legs([order])
        order = self._await_fill(order)

        status = _state(order)
        filled_qty = _num(order.filled_qty) or 0.0
        average = _num(order.filled_avg_price)
        if status in _FAILED and filled_qty <= 0:
            log.warning("alpaca %s order for %s ended %s", side.value, symbol, status)
            return None

        if average is None or filled_qty <= 0:
            # Accepted but not filled yet: confirmed on the next look.
            self._unfilled[symbol] = str(order.id)
            entry, held = intent.price, qty
        else:
            entry, held = average, filled_qty
            if status != "filled":
                self._unfilled[symbol] = str(order.id)

        opened_at = datetime.now(timezone.utc)
        self._managed.add(symbol)
        self._entry_prices[symbol] = (entry, opened_at)
        log.info("alpaca order %s (%s): %s %s x%g @ %.4f", order.id, status, side.value, symbol, held, entry)
        return Position(
            symbol=symbol,
            side=intent.side,
            qty=held,
            entry_price=entry,
            opened_at=opened_at,
            stop_loss=stop if stop else intent.stop_loss,
            take_profit=target if target else intent.take_profit,
            current_price=entry,
        )

    def close_position(
        self, position: Position, price: float, reason: str
    ) -> ClosedTrade | None:
        symbol = position.symbol
        try:
            self._cancel_protection(symbol)
            holding = self._holding(symbol)
            if holding is None:
                # Already gone: a bracket leg, or the owner in Alpaca's app, sold it.
                trade = self.closing_trade(position)
                if trade is not None:
                    return trade
                raise RuntimeError(f"no {symbol} position at Alpaca")
            qty = min(position.qty, holding.qty)
            # Only the shares this app bought: anything the owner added stays.
            if qty >= holding.qty - 1e-9:
                options = ClosePositionRequest(percentage="100")
            else:
                options = ClosePositionRequest(qty=_qty_text(qty))
            order = self.client.close_position(symbol, options)
        except Exception:
            log.exception("failed to close %s on alpaca", symbol)
            return None

        self._account_cache = None
        order = self._await_fill(order)
        exit_price = _num(order.filled_avg_price) or price
        sold = _num(order.filled_qty) or qty
        self._forget(symbol)
        return _closed(position, min(sold, position.qty), exit_price, reason, datetime.now(timezone.utc))

    def move_stop(self, position: Position, stop: float) -> bool:
        leg = self._stop_leg(position.symbol)
        if leg is None:
            return False
        replaced = self.client.replace_order_by_id(
            str(leg.id), ReplaceOrderRequest(stop_price=tick(stop))
        )
        # A replacement is a new order with a new id.
        self._our_legs.add(str(getattr(replaced, "id", "")))
        return True

    # ----------------------------------------------------------------- reading

    def broker_view(self) -> BrokerView:
        # Orders before positions: an entry that fills between the two reads
        # then shows up as a position, never as neither an order nor a position
        # (which would look like a trade that closed).
        orders = self._open_orders()
        positions = self.client.get_all_positions()

        view = BrokerView()
        for item in positions:
            qty = abs(_num(item.qty) or 0.0)
            average = _num(item.avg_entry_price) or 0.0
            view.holdings[item.symbol] = Holding(
                symbol=item.symbol,
                qty=qty,
                avg_entry=average,
                price=_num(item.current_price) or average,
                unrealized_pl=_num(item.unrealized_pl) or 0.0,
            )

        self._learn_legs(orders)
        for order, root in _walk(orders):
            if _state(order) in _DONE:
                continue
            view.open_orders += 1
            if _side(order) == "buy":
                view.open_buys.add(order.symbol)
                continue
            if not self._is_ours(order, root):
                continue
            kind = _type(order)
            if kind in _STOP_TYPES and _state(order) != "pending_cancel":
                stop = _num(order.stop_price)
                if stop:
                    view.stops[order.symbol] = stop
            elif kind == "limit":
                limit = _num(order.limit_price)
                if limit:
                    view.targets[order.symbol] = limit

        view.fills = self._confirm_fills()
        return view

    def closing_trade(self, position: Position) -> ClosedTrade | None:
        opened = _aware(position.opened_at)
        orders = self.client.get_orders(
            GetOrdersRequest(
                status=QueryOrderStatus.CLOSED,
                symbols=[position.symbol],
                nested=True,
                limit=50,
                after=opened - timedelta(minutes=5),
                direction=Sort.DESC,
            )
        )
        sells = [
            order for order, _ in _walk(orders)
            if _side(order) == "sell"
            and _num(order.filled_avg_price)
            and order.filled_at is not None
            and _aware(order.filled_at) >= opened - timedelta(minutes=1)
        ]
        if not sells:
            return None
        last = max(sells, key=lambda o: _aware(o.filled_at))
        kind = _type(last)
        reason = "stop-loss" if kind in _STOP_TYPES else "take-profit" if kind == "limit" else "closed at Alpaca"
        qty = min(_num(last.filled_qty) or position.qty, position.qty)
        self._forget(position.symbol)
        return _closed(position, qty, _num(last.filled_avg_price), reason, _aware(last.filled_at))

    def get_positions(self) -> list[Position]:
        try:
            raw = self.client.get_all_positions()
        except Exception:
            log.exception("failed to read alpaca positions")
            return []

        positions = []
        for item in raw:
            average = _num(item.avg_entry_price) or 0.0
            entry, opened_at = self._entry_prices.get(item.symbol, (average, datetime.now(timezone.utc)))
            qty = _num(item.qty) or 0.0
            positions.append(
                Position(
                    symbol=item.symbol,
                    side=Side.BUY if qty > 0 else Side.SELL,
                    qty=abs(qty),
                    entry_price=entry,
                    opened_at=opened_at,
                    current_price=_num(item.current_price) or entry,
                )
            )
        return positions

    def get_balance(self) -> Balance:
        try:
            summary = self.account_summary()
        except Exception:
            log.exception("failed to read alpaca account")
            return Balance(total=0.0, available=0.0, currency="USD")
        # Never trade on margin: spendable is the smaller of cash and buying power.
        return Balance(
            total=summary.equity,
            available=max(min(summary.cash, summary.buying_power), 0.0),
            currency=summary.currency,
        )

    def account_summary(self) -> AccountSummary:
        account = self._account()
        return AccountSummary(
            equity=_num(account.equity) or 0.0,
            cash=_num(account.cash) or 0.0,
            buying_power=_num(account.buying_power) or 0.0,
            last_equity=_num(getattr(account, "last_equity", None)),
            currency=getattr(account, "currency", None) or "USD",
            blocked=bool(getattr(account, "trading_blocked", False) or getattr(account, "account_blocked", False)),
        )

    def adopt_position(self, position: Position) -> None:
        self._managed.add(position.symbol)
        self._entry_prices[position.symbol] = (position.entry_price, position.opened_at)

    # --------------------------------------------------------------- internals

    def _account(self):
        now = time.monotonic()
        if self._account_cache and now - self._account_cache[0] < ACCOUNT_TTL_SECONDS:
            return self._account_cache[1]
        account = self.client.get_account()
        self._account_cache = (now, account)
        return account

    def _open_orders(self, symbols: list[str] | None = None) -> list:
        return self.client.get_orders(
            GetOrdersRequest(status=QueryOrderStatus.OPEN, nested=True, limit=500, symbols=symbols)
        )

    def _holding(self, symbol: str) -> Holding | None:
        try:
            item = self.client.get_open_position(symbol)
        except Exception as exc:
            if getattr(exc, "status_code", None) == 404 or "not found" in str(exc).lower() \
                    or "does not exist" in str(exc).lower():
                return None
            raise
        average = _num(item.avg_entry_price) or 0.0
        return Holding(
            symbol=symbol,
            qty=abs(_num(item.qty) or 0.0),
            avg_entry=average,
            price=_num(item.current_price) or average,
            unrealized_pl=_num(item.unrealized_pl) or 0.0,
        )

    def _is_ours(self, order, root: str) -> bool:
        if root.startswith(CLIENT_PREFIX) or str(order.id) in self._our_legs:
            return True
        if root.startswith(PHONE_PREFIX):
            return False
        # A bracket leg listed on its own, for a position this app manages.
        return order.symbol in self._managed and _text(order.order_class) == "bracket"

    def _our_sells(self, symbol: str, include_cancelling: bool = False) -> list:
        wanted = []
        for order, root in _walk(self._open_orders([symbol])):
            state = _state(order)
            if state in _DONE or (state == "pending_cancel" and not include_cancelling):
                continue
            if order.symbol == symbol and _side(order) == "sell" and self._is_ours(order, root):
                wanted.append(order)
        return wanted

    def _stop_leg(self, symbol: str):
        return next((o for o in self._our_sells(symbol) if _type(o) in _STOP_TYPES), None)

    def _cancel_protection(self, symbol: str) -> None:
        legs = self._our_sells(symbol)
        if not legs:
            return
        for leg in legs:
            try:
                self.client.cancel_order_by_id(str(leg.id))
            except Exception as exc:
                # Cancelling one leg of a bracket takes its pair with it.
                log.info("cancel %s leg %s: %s", symbol, leg.id, exc)
        for _ in range(CANCEL_POLLS):
            if not self._our_sells(symbol, include_cancelling=True):
                return
            self._sleep(POLL_SECONDS)
        raise RuntimeError(f"Alpaca did not cancel the {symbol} stop and target in time")

    def _await_fill(self, order):
        for _ in range(FILL_POLLS):
            if _state(order) in _DONE:
                return order
            self._sleep(POLL_SECONDS)
            try:
                order = self.client.get_order_by_id(str(order.id))
            except Exception:
                log.exception("could not re-read order %s", order.id)
                return order
        return order

    def _confirm_fills(self) -> dict[str, tuple[float, float]]:
        fills: dict[str, tuple[float, float]] = {}
        for symbol, order_id in list(self._unfilled.items()):
            try:
                order = self.client.get_order_by_id(order_id)
            except Exception:
                log.exception("could not re-read entry %s for %s", order_id, symbol)
                continue
            qty, average = _num(order.filled_qty) or 0.0, _num(order.filled_avg_price)
            if qty > 0 and average:
                fills[symbol] = (qty, average)
                self._entry_prices[symbol] = (average, self._entry_prices.get(symbol, (0, datetime.now(timezone.utc)))[1])
            if _state(order) in _DONE:
                self._unfilled.pop(symbol, None)
        return fills

    def _learn_legs(self, orders: Iterable) -> None:
        for order, root in _walk(orders):
            if root.startswith(CLIENT_PREFIX) and _side(order) == "sell":
                self._our_legs.add(str(order.id))

    def _forget(self, symbol: str) -> None:
        self._managed.discard(symbol)
        self._unfilled.pop(symbol, None)
        self._entry_prices.pop(symbol, None)


# ------------------------------------------------------------------- helpers


def _walk(orders: Iterable | None, root: str | None = None) -> Iterator[tuple[object, str]]:
    """Each order and its legs, with the client id of the order at the top."""
    for order in orders or []:
        top = root if root is not None else (getattr(order, "client_order_id", None) or "")
        yield order, top
        yield from _walk(getattr(order, "legs", None), top)


def _text(value) -> str:
    return str(getattr(value, "value", value) or "").lower()


def _state(order) -> str:
    return _text(getattr(order, "status", None))


def _side(order) -> str:
    return _text(getattr(order, "side", None))


def _type(order) -> str:
    return _text(getattr(order, "type", None) or getattr(order, "order_type", None))


def _num(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _qty_text(qty: float) -> str:
    return f"{qty:.9f}".rstrip("0").rstrip(".")


def _aware(when: datetime) -> datetime:
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def _closed(position: Position, qty: float, exit_price: float, reason: str, closed_at: datetime) -> ClosedTrade:
    gross = (exit_price - position.entry_price) * qty
    if position.side is Side.SELL:
        gross = -gross
    return ClosedTrade(
        symbol=position.symbol,
        side=position.side,
        qty=qty,
        entry_price=position.entry_price,
        exit_price=exit_price,
        opened_at=_aware(position.opened_at),
        closed_at=closed_at,
        pnl=gross,
        exit_reason=reason,
    )
