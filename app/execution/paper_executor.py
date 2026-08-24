from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

from app.common.models import Balance, ClosedTrade, Position, Side, TradeIntent
from app.execution.base import Executor

log = logging.getLogger(__name__)

# US equities are commission-free at Alpaca; this covers slippage instead.
DEFAULT_SLIPPAGE_PCT = 0.02


class PaperExecutor(Executor):
    """Simulated money against real prices. No brokerage account involved."""

    name = "paper"
    is_automatic = True

    def __init__(
        self,
        starting_balance: float = 10_000.0,
        slippage_pct: float = DEFAULT_SLIPPAGE_PCT,
        currency: str = "USD",
    ) -> None:
        self.currency = currency
        self.slippage_pct = slippage_pct
        self._cash = starting_balance
        self._positions: dict[str, Position] = {}
        self._last_price: dict[str, float] = {}
        self._lock = threading.RLock()

    def open_position(self, intent: TradeIntent) -> Position | None:
        fill = self._apply_slippage(intent.price, intent.side)
        cost = fill * intent.qty
        with self._lock:
            if cost > self._cash:
                log.warning(
                    "paper account cannot afford %s: needs %.2f, has %.2f",
                    intent.symbol, cost, self._cash,
                )
                return None
            self._cash -= cost
            position = Position(
                symbol=intent.symbol,
                side=intent.side,
                qty=intent.qty,
                entry_price=fill,
                opened_at=datetime.now(timezone.utc),
                stop_loss=intent.stop_loss,
                take_profit=intent.take_profit,
                current_price=fill,
            )
            self._positions[intent.symbol] = position
        return position

    def close_position(
        self, position: Position, price: float, reason: str
    ) -> ClosedTrade | None:
        exit_side = Side.SELL if position.side is Side.BUY else Side.BUY
        fill = self._apply_slippage(price, exit_side)
        with self._lock:
            if self._positions.pop(position.symbol, None) is None:
                return None
            self._cash += fill * position.qty

        gross = (fill - position.entry_price) * position.qty
        if position.side is Side.SELL:
            gross = -gross
        return ClosedTrade(
            symbol=position.symbol,
            side=position.side,
            qty=position.qty,
            entry_price=position.entry_price,
            exit_price=fill,
            opened_at=position.opened_at,
            closed_at=datetime.now(timezone.utc),
            pnl=gross,
            exit_reason=reason,
        )

    def get_positions(self) -> list[Position]:
        with self._lock:
            for position in self._positions.values():
                position.current_price = self._last_price.get(
                    position.symbol, position.entry_price
                )
            return list(self._positions.values())

    def get_balance(self) -> Balance:
        market_value = sum(p.market_value for p in self.get_positions())
        with self._lock:
            cash = self._cash
        return Balance(total=cash + market_value, available=cash, currency=self.currency)

    def adopt_position(self, position: Position) -> None:
        with self._lock:
            self._positions[position.symbol] = position
            self._cash -= position.entry_price * position.qty

    def update_price(self, symbol: str, price: float) -> None:
        with self._lock:
            self._last_price[symbol] = price

    def _apply_slippage(self, price: float, side: Side) -> float:
        drift = price * self.slippage_pct / 100.0
        return price + drift if side is Side.BUY else price - drift
