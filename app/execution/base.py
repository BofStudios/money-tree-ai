from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.common.models import Balance, ClosedTrade, Position, TradeIntent


def tick(price: float) -> float:
    """A price the exchange accepts: whole cents above $1 (no sub-penny orders)."""
    return round(price, 2) if price >= 1 else round(price, 4)


@dataclass(frozen=True)
class Holding:
    """A position exactly as the brokerage reports it."""

    symbol: str
    qty: float
    avg_entry: float
    price: float
    unrealized_pl: float

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "qty": self.qty,
            "avg_entry": round(self.avg_entry, 4),
            "price": round(self.price, 4),
            "unrealized_pl": round(self.unrealized_pl, 2),
        }


@dataclass
class BrokerView:
    """One read of the brokerage per scan: what it holds and what protects it.

    `stops` and `targets` only list orders this app placed, so a symbol in
    `stops` is one whose stop-loss is live at the broker and keeps working
    while this PC is off.
    """

    holdings: dict[str, Holding] = field(default_factory=dict)
    stops: dict[str, float] = field(default_factory=dict)
    targets: dict[str, float] = field(default_factory=dict)
    # Symbols with a buy that has not filled yet: no position, but not closed either.
    open_buys: set[str] = field(default_factory=set)
    open_orders: int = 0
    # Entries confirmed since the last look, as (qty, average fill price).
    fills: dict[str, tuple[float, float]] = field(default_factory=dict)


@dataclass(frozen=True)
class AccountSummary:
    equity: float
    cash: float
    buying_power: float
    # Equity at the previous close — the base for today's profit or loss.
    last_equity: float | None = None
    currency: str = "USD"
    blocked: bool = False

    @property
    def today(self) -> float | None:
        if not self.last_equity:
            return None
        return self.equity - self.last_equity

    def to_dict(self) -> dict:
        today = self.today
        return {
            "equity": round(self.equity, 2),
            "cash": round(self.cash, 2),
            "buying_power": round(self.buying_power, 2),
            "last_equity": round(self.last_equity, 2) if self.last_equity else None,
            "today": round(today, 2) if today is not None else None,
            "currency": self.currency,
            "blocked": self.blocked,
        }


class Executor(ABC):
    """What happens after the bot decides something.

    Three shapes exist: tell the user (signal mode, for Midas), simulate
    (paper), or actually send the order (Alpaca live).
    """

    name: str = "base"
    is_automatic: bool = True
    requires_confirmation: bool = False
    # What the dashboard calls the money behind this executor:
    # alpaca_live | alpaca_paper | simulation | signal
    broker: str = "base"
    # True when a stop-loss and target can be left with the broker itself.
    holds_brackets: bool = False

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

    def account_summary(self) -> AccountSummary:
        balance = self.get_balance()
        return AccountSummary(
            equity=balance.total,
            cash=balance.available,
            buying_power=balance.available,
            currency=balance.currency,
        )

    def broker_view(self) -> BrokerView | None:
        """The brokerage's own records, or None when there is no brokerage
        to reconcile against (simulation, signals)."""
        return None

    def move_stop(self, position: Position, stop: float) -> bool:
        """Move a stop-loss held at the broker. False when the broker holds none."""
        return False

    def closing_trade(self, position: Position) -> ClosedTrade | None:
        """How a position that vanished at the broker was closed, from its fills."""
        return None

    def adopt_position(self, position: Position) -> None:
        """Restore a position loaded from storage after a restart."""

    def update_price(self, symbol: str, price: float) -> None:
        """Let the executor mark open positions to market."""

    def close(self) -> None:
        return None
