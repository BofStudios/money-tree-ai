from __future__ import annotations

import logging
from datetime import datetime, timezone

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest

from app.common.models import Balance, ClosedTrade, Position, Side, TradeIntent
from app.execution.base import Executor

log = logging.getLogger(__name__)


class AlpacaExecutor(Executor):
    """Real orders on Alpaca. Accepts Turkish residents; US residency is not required.

    Stops and targets are attached as a bracket order so the exchange protects
    the position even if this bot is not running.
    """

    name = "alpaca"
    is_automatic = True

    def __init__(self, api_key: str, api_secret: str, paper: bool = True) -> None:
        self.paper = paper
        self.client = TradingClient(api_key, api_secret, paper=paper)
        self._entry_prices: dict[str, tuple[float, datetime]] = {}

    def open_position(self, intent: TradeIntent) -> Position | None:
        qty = round(max(intent.qty, 0.0), 6)
        if qty <= 0:
            log.warning("%s sized to zero, skipping", intent.symbol)
            return None

        fractional = qty != int(qty)
        request = MarketOrderRequest(
            symbol=intent.symbol,
            qty=qty,
            side=OrderSide.BUY if intent.side is Side.BUY else OrderSide.SELL,
            # Alpaca only accepts fractional quantities as day orders, and it
            # rejects brackets on them — those get engine-side stops instead.
            time_in_force=TimeInForce.DAY,
        )
        if intent.stop_loss and intent.take_profit and not fractional:
            from alpaca.trading.enums import OrderClass
            from alpaca.trading.requests import StopLossRequest, TakeProfitRequest

            request.order_class = OrderClass.BRACKET
            request.stop_loss = StopLossRequest(stop_price=round(intent.stop_loss, 2))
            request.take_profit = TakeProfitRequest(limit_price=round(intent.take_profit, 2))

        order = self.client.submit_order(request)
        fill = float(order.filled_avg_price or intent.price)
        opened_at = datetime.now(timezone.utc)
        self._entry_prices[intent.symbol] = (fill, opened_at)

        log.info(
            "alpaca order %s: %s %s x%g @ %.2f", order.id, order.side, intent.symbol, qty, fill
        )
        return Position(
            symbol=intent.symbol,
            side=intent.side,
            qty=float(order.filled_qty or qty),
            entry_price=fill,
            opened_at=opened_at,
            stop_loss=intent.stop_loss,
            take_profit=intent.take_profit,
            current_price=fill,
        )

    def close_position(
        self, position: Position, price: float, reason: str
    ) -> ClosedTrade | None:
        try:
            self.client.close_position(position.symbol)
        except Exception:
            log.exception("failed to close %s on alpaca", position.symbol)
            return None

        self._entry_prices.pop(position.symbol, None)
        gross = (price - position.entry_price) * position.qty
        if position.side is Side.SELL:
            gross = -gross
        return ClosedTrade(
            symbol=position.symbol,
            side=position.side,
            qty=position.qty,
            entry_price=position.entry_price,
            exit_price=price,
            opened_at=position.opened_at,
            closed_at=datetime.now(timezone.utc),
            pnl=gross,
            exit_reason=reason,
        )

    def get_positions(self) -> list[Position]:
        try:
            raw = self.client.get_all_positions()
        except Exception:
            log.exception("failed to read alpaca positions")
            return []

        positions = []
        for item in raw:
            entry, opened_at = self._entry_prices.get(
                item.symbol, (float(item.avg_entry_price), datetime.now(timezone.utc))
            )
            positions.append(
                Position(
                    symbol=item.symbol,
                    side=Side.BUY if float(item.qty) > 0 else Side.SELL,
                    qty=abs(float(item.qty)),
                    entry_price=entry,
                    opened_at=opened_at,
                    current_price=float(item.current_price or entry),
                )
            )
        return positions

    def get_balance(self) -> Balance:
        try:
            account = self.client.get_account()
        except Exception:
            log.exception("failed to read alpaca account")
            return Balance(total=0.0, available=0.0, currency="USD")
        return Balance(
            total=float(account.equity),
            available=float(account.buying_power),
            currency=account.currency or "USD",
        )

    def adopt_position(self, position: Position) -> None:
        self._entry_prices[position.symbol] = (position.entry_price, position.opened_at)
