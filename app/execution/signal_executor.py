from __future__ import annotations

import itertools
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from app.common.events import EventBus
from app.common.models import (
    Action,
    Balance,
    ClosedTrade,
    Position,
    Side,
    TradeIntent,
)

log = logging.getLogger(__name__)

DEFAULT_EXPIRY_MINUTES = 45


@dataclass
class PendingSignal:
    """A recommendation waiting for you to say whether you acted on it."""

    id: str
    intent: TradeIntent
    position: Position | None  # set when this is an exit signal
    expires_at: datetime
    status: str = "pending"  # pending | taken | skipped | expired
    acted_price: float | None = None
    acted_at: datetime | None = None

    @property
    def is_exit(self) -> bool:
        return self.intent.action is Action.CLOSE

    @property
    def expired(self) -> bool:
        return self.status == "pending" and datetime.now(timezone.utc) >= self.expires_at

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": "exit" if self.is_exit else "entry",
            "status": self.status,
            "expires_at": self.expires_at.isoformat(),
            "acted_price": self.acted_price,
            **self.intent.to_dict(),
        }


class SignalExecutor:
    """Midas mode: the bot never places an order, it tells you what to place.

    Flow: the engine produces an intent -> this stores it as a pending signal
    and publishes it (dashboard + Telegram) -> you tap Taken or Skipped ->
    on Taken the bot starts tracking the position and will tell you when to
    get out. Nothing here ever touches a brokerage account.
    """

    name = "signal"
    is_automatic = False
    requires_confirmation = True

    def __init__(
        self,
        events: EventBus,
        starting_balance: float = 10_000.0,
        currency: str = "USD",
        expiry_minutes: int = DEFAULT_EXPIRY_MINUTES,
    ) -> None:
        self.events = events
        self.currency = currency
        self._expiry = timedelta(minutes=expiry_minutes)
        self._declared_equity = starting_balance

        self._lock = threading.RLock()
        self._ids = itertools.count(1)
        self._pending: dict[str, PendingSignal] = {}
        self._positions: dict[str, Position] = {}
        self._last_price: dict[str, float] = {}
        self._history: list[PendingSignal] = []

    # ------------------------------------------------------------------ executor

    def open_position(self, intent: TradeIntent) -> Position | None:
        self._raise_signal(intent, position=None)
        return None

    def close_position(
        self, position: Position, price: float, reason: str
    ) -> ClosedTrade | None:
        with self._lock:
            already = any(
                p.status == "pending" and p.is_exit and p.intent.symbol == position.symbol
                for p in self._pending.values()
            )
        if already:
            return None

        intent = TradeIntent(
            symbol=position.symbol,
            side=Side.SELL if position.side is Side.BUY else Side.BUY,
            action=Action.CLOSE,
            qty=position.qty,
            price=price,
            reason=reason,
        )
        self._raise_signal(intent, position=position)
        return None

    def get_positions(self) -> list[Position]:
        with self._lock:
            for position in self._positions.values():
                position.current_price = self._last_price.get(
                    position.symbol, position.entry_price
                )
            return list(self._positions.values())

    def get_balance(self) -> Balance:
        invested = sum(p.entry_price * p.qty for p in self.get_positions())
        unrealised = sum(p.unrealized_pnl for p in self.get_positions())
        return Balance(
            total=self._declared_equity + unrealised,
            available=max(self._declared_equity - invested, 0.0),
            currency=self.currency,
        )

    def adopt_position(self, position: Position) -> None:
        with self._lock:
            self._positions[position.symbol] = position

    def update_price(self, symbol: str, price: float) -> None:
        with self._lock:
            self._last_price[symbol] = price

    # ------------------------------------------------------------ user responses

    def confirm_taken(self, signal_id: str, price: float | None = None) -> PendingSignal | None:
        """You placed the trade in Midas. Start (or stop) tracking it."""
        with self._lock:
            signal = self._pending.get(signal_id)
            if signal is None or signal.status != "pending":
                return None

            fill = price if price is not None else signal.intent.price
            signal.status = "taken"
            signal.acted_price = fill
            signal.acted_at = datetime.now(timezone.utc)
            self._pending.pop(signal_id, None)
            self._history.append(signal)

            if signal.is_exit:
                closed = self._settle_exit(signal, fill)
            else:
                closed = None
                self._positions[signal.intent.symbol] = Position(
                    symbol=signal.intent.symbol,
                    side=signal.intent.side,
                    qty=signal.intent.qty,
                    entry_price=fill,
                    opened_at=signal.acted_at,
                    stop_loss=signal.intent.stop_loss,
                    take_profit=signal.intent.take_profit,
                    current_price=fill,
                )

        if signal.is_exit and closed is not None:
            self.events.publish(
                "signal_closed", {"signal": signal.to_dict(), "trade": _trade_dict(closed)}
            )
        else:
            self.events.publish("signal_taken", {"signal": signal.to_dict()})
        log.info("signal %s marked TAKEN at %.2f", signal_id, fill)
        return signal

    def confirm_skipped(self, signal_id: str) -> PendingSignal | None:
        with self._lock:
            signal = self._pending.pop(signal_id, None)
            if signal is None or signal.status != "pending":
                return None
            signal.status = "skipped"
            signal.acted_at = datetime.now(timezone.utc)
            self._history.append(signal)

        self.events.publish("signal_skipped", {"signal": signal.to_dict()})
        log.info("signal %s marked SKIPPED", signal_id)
        return signal

    def take_closed_trade(self, signal_id: str, price: float) -> ClosedTrade | None:
        """Convenience for exit signals: confirm and hand back the closed trade."""
        with self._lock:
            signal = self._pending.get(signal_id)
            if signal is None or not signal.is_exit:
                return None
            position = self._positions.get(signal.intent.symbol)
        if position is None:
            return None
        self.confirm_taken(signal_id, price)
        return _build_trade(position, price, signal.intent.reason)

    def set_declared_equity(self, equity: float) -> None:
        """You tell the bot how much is actually in your Midas account."""
        with self._lock:
            self._declared_equity = max(equity, 0.0)

    # ------------------------------------------------------------------- queries

    def pending_signals(self) -> list[PendingSignal]:
        self.expire_stale()
        with self._lock:
            return sorted(self._pending.values(), key=lambda s: s.intent.created_at, reverse=True)

    def recent_signals(self, limit: int = 30) -> list[PendingSignal]:
        with self._lock:
            return list(reversed(self._history[-limit:]))

    def has_pending_for(self, symbol: str) -> bool:
        with self._lock:
            return any(
                s.intent.symbol == symbol and s.status == "pending"
                for s in self._pending.values()
            )

    def expire_stale(self) -> list[PendingSignal]:
        with self._lock:
            stale = [s for s in self._pending.values() if s.expired]
            for signal in stale:
                signal.status = "expired"
                self._pending.pop(signal.id, None)
                self._history.append(signal)
        for signal in stale:
            log.info("signal %s expired unanswered", signal.id)
            self.events.publish("signal_expired", {"signal": signal.to_dict()})
        return stale

    # ----------------------------------------------------------------- internals

    def _raise_signal(self, intent: TradeIntent, position: Position | None) -> PendingSignal:
        with self._lock:
            signal = PendingSignal(
                id=f"sig-{next(self._ids)}",
                intent=intent,
                position=position,
                expires_at=datetime.now(timezone.utc) + self._expiry,
            )
            self._pending[signal.id] = signal

        log.info(
            "SIGNAL %s %s %s x%.4f @ %.2f - %s",
            signal.id, intent.action.value.upper(), intent.symbol,
            intent.qty, intent.price, intent.reason,
        )
        self.events.publish("signal_raised", {"signal": signal.to_dict()})
        return signal

    def _settle_exit(self, signal: PendingSignal, fill: float) -> ClosedTrade | None:
        """Caller holds the lock."""
        position = self._positions.pop(signal.intent.symbol, None)
        if position is None:
            return None
        trade = _build_trade(position, fill, signal.intent.reason)
        self._declared_equity += trade.pnl
        return trade


def _build_trade(position: Position, exit_price: float, reason: str) -> ClosedTrade:
    gross = (exit_price - position.entry_price) * position.qty
    if position.side is Side.SELL:
        gross = -gross
    return ClosedTrade(
        symbol=position.symbol,
        side=position.side,
        qty=position.qty,
        entry_price=position.entry_price,
        exit_price=exit_price,
        opened_at=position.opened_at,
        closed_at=datetime.now(timezone.utc),
        pnl=gross,
        exit_reason=reason,
    )


def _trade_dict(trade: ClosedTrade) -> dict:
    return {
        "symbol": trade.symbol,
        "qty": trade.qty,
        "entry_price": trade.entry_price,
        "exit_price": trade.exit_price,
        "pnl": round(trade.pnl, 2),
        "pnl_pct": round(trade.pnl_pct, 2),
        "exit_reason": trade.exit_reason,
    }
