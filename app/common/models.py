from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


class Action(str, Enum):
    BUY = "buy"
    SELL = "sell"
    CLOSE = "close"
    HOLD = "hold"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"


@dataclass(frozen=True)
class Bar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    def to_dict(self) -> dict:
        return {
            "time": int(self.timestamp.timestamp()),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
        }


@dataclass(frozen=True)
class Signal:
    action: Action
    reason: str
    stop_loss: float | None = None
    take_profit: float | None = None
    symbol: str = ""
    detail: dict = field(default_factory=dict)

    @property
    def is_actionable(self) -> bool:
        return self.action is not Action.HOLD


@dataclass
class SymbolInfo:
    symbol: str
    base_asset: str
    quote_asset: str
    price_precision: int
    qty_precision: int
    min_qty: float
    min_notional: float

    def round_qty(self, qty: float) -> float:
        return round(qty, self.qty_precision)

    def round_price(self, price: float) -> float:
        return round(price, self.price_precision)


@dataclass
class OrderRequest:
    symbol: str
    side: Side
    qty: float
    order_type: OrderType = OrderType.MARKET
    price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    reason: str = ""


@dataclass
class OrderResult:
    order_id: str
    symbol: str
    side: Side
    qty: float
    filled_price: float
    status: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    stop_loss: float | None = None
    take_profit: float | None = None


@dataclass
class Position:
    symbol: str
    side: Side
    qty: float
    entry_price: float
    opened_at: datetime
    stop_loss: float | None = None
    take_profit: float | None = None
    current_price: float | None = None

    @property
    def market_value(self) -> float:
        return self.qty * (self.current_price or self.entry_price)

    @property
    def unrealized_pnl(self) -> float:
        price = self.current_price or self.entry_price
        delta = price - self.entry_price
        if self.side is Side.SELL:
            delta = -delta
        return delta * self.qty

    @property
    def unrealized_pnl_pct(self) -> float:
        cost = self.entry_price * self.qty
        return (self.unrealized_pnl / cost * 100) if cost else 0.0

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "side": self.side.value,
            "qty": self.qty,
            "entry_price": self.entry_price,
            "current_price": self.current_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "unrealized_pnl": round(self.unrealized_pnl, 2),
            "unrealized_pnl_pct": round(self.unrealized_pnl_pct, 2),
            "opened_at": self.opened_at.isoformat(),
        }


@dataclass
class Balance:
    total: float
    available: float
    currency: str = "USDT"

    def to_dict(self) -> dict:
        return {
            "total": round(self.total, 2),
            "available": round(self.available, 2),
            "currency": self.currency,
        }


@dataclass
class TradeIntent:
    """What the bot wants to do, before anything is executed.

    In signal mode this is the whole product: it gets formatted into a message
    you act on inside Midas. In paper/live modes it becomes an actual order.
    """

    symbol: str
    side: Side
    action: Action
    qty: float
    price: float
    reason: str
    stop_loss: float | None = None
    take_profit: float | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def notional(self) -> float:
        return self.qty * self.price

    @property
    def risk_amount(self) -> float:
        if self.stop_loss is None:
            return 0.0
        return abs(self.price - self.stop_loss) * self.qty

    @property
    def reward_amount(self) -> float:
        if self.take_profit is None:
            return 0.0
        return abs(self.take_profit - self.price) * self.qty

    @property
    def reward_risk(self) -> float:
        risk = self.risk_amount
        return (self.reward_amount / risk) if risk else 0.0

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "side": self.side.value,
            "action": self.action.value,
            "qty": self.qty,
            "price": self.price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "notional": round(self.notional, 2),
            "risk_amount": round(self.risk_amount, 2),
            "reward_risk": round(self.reward_risk, 2),
            "reason": self.reason,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class ClosedTrade:
    symbol: str
    side: Side
    qty: float
    entry_price: float
    exit_price: float
    opened_at: datetime
    closed_at: datetime
    pnl: float
    exit_reason: str

    @property
    def pnl_pct(self) -> float:
        cost = self.entry_price * self.qty
        return (self.pnl / cost * 100) if cost else 0.0
