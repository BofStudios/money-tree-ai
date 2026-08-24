from __future__ import annotations

from abc import ABC, abstractmethod

from app.common.models import Balance, ClosedTrade, Position, TradeIntent


class Executor(ABC):
    """What happens after the bot decides something.

    Three shapes exist: tell the user (signal mode, for Midas), simulate
    (paper), or actually send the order (Alpaca live).
    """

    name: str = "base"
    is_automatic: bool = True
    requires_confirmation: bool = False

    @abstractmethod
    def open_position(self, intent: TradeIntent) -> Position | None:
        """Returns the opened position, or None when execution is deferred to the user."""

    @abstractmethod
    def close_position(
        self, position: Position, price: float, reason: str
    ) -> ClosedTrade | None:
        """Returns the closed trade, or None when execution is deferred to the user."""

    @abstractmethod
    def get_positions(self) -> list[Position]: ...

    @abstractmethod
    def get_balance(self) -> Balance: ...

    def adopt_position(self, position: Position) -> None:
        """Restore a position loaded from storage after a restart."""

    def update_price(self, symbol: str, price: float) -> None:
        """Let the executor mark open positions to market."""

    def close(self) -> None:
        return None
