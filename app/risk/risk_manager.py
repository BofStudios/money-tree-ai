from __future__ import annotations

import logging
import threading
from datetime import date, datetime, timezone
from typing import Callable

from app.config import RiskConfig
from app.common.models import (
    Action,
    Balance,
    ClosedTrade,
    OrderRequest,
    OrderType,
    Position,
    Side,
    Signal,
    SymbolInfo,
)

log = logging.getLogger(__name__)

# Fraction of available cash held back so exchange fees never make an order unfillable.
FEE_BUFFER = 0.005


class RejectionReason:
    NOT_ARMED = "live trading is not armed"
    DAILY_LOSS_HIT = "daily loss limit reached"
    MAX_POSITIONS = "maximum open positions reached"
    NO_POSITION = "no open position to close"
    POSITION_TOO_SMALL = "position size below exchange minimum"
    INSUFFICIENT_BALANCE = "insufficient available balance"


class RiskManager:
    """The gate every order passes through.

    Live trading always starts disarmed. Nothing persists the armed state, so
    a crash or restart can never leave the bot trading real money unattended.
    """

    def __init__(
        self,
        config: RiskConfig,
        mode: str = "paper",
        clock: Callable[[], date] | None = None,
    ) -> None:
        self.config = config
        self.mode = mode
        # Backtests inject the bar's date so daily counters roll with simulated time.
        self._clock = clock or _utc_today
        self._lock = threading.Lock()
        self._armed = False
        self._day = self._clock()
        self._daily_start_equity: float | None = None
        self._daily_realized_pnl = 0.0
        self._disarm_reason: str | None = None

    @property
    def armed(self) -> bool:
        return self._armed

    @property
    def is_live(self) -> bool:
        return self.mode == "live"

    @property
    def disarm_reason(self) -> str | None:
        return self._disarm_reason

    @property
    def daily_realized_pnl(self) -> float:
        return self._daily_realized_pnl

    def arm(self) -> None:
        with self._lock:
            self._armed = True
            self._disarm_reason = None
        if self.is_live:
            log.warning("LIVE TRADING ARMED - real orders will be placed")
        else:
            log.info("armed in paper mode - no real money at risk")

    def disarm(self, reason: str = "manual") -> None:
        with self._lock:
            was_armed = self._armed
            self._armed = False
            self._disarm_reason = reason
        if was_armed:
            log.warning("disarmed (%s): %s", self.mode, reason)

    def set_mode(self, mode: str) -> None:
        if mode not in ("paper", "live"):
            raise ValueError(f"unknown mode: {mode}")
        with self._lock:
            self.mode = mode
            self._armed = False
            self._disarm_reason = "mode changed"
        log.info("mode set to %s (disarmed)", mode)

    def daily_loss_limit(self, equity: float) -> float:
        base = self._daily_start_equity or equity
        return base * self.config.max_daily_loss_pct / 100.0

    def daily_loss_breached(self, equity: float) -> bool:
        return self._daily_realized_pnl <= -self.daily_loss_limit(equity)

    def stop_distance_pct(self, price: float, atr: float | None) -> float:
        """How far the stop sits from entry, as a percentage of price.

        With `stop_mode: atr` the distance scales with how much the symbol
        actually moves, so a calm stock gets a tight stop and a wild one gets
        room to breathe. Clamped at both ends so a freak ATR cannot produce an
        absurd stop.
        """
        if self.config.stop_mode == "atr" and atr and price > 0:
            distance = atr * self.config.atr_multiple / price * 100.0
        else:
            distance = self.config.stop_loss_pct
        return min(max(distance, self.config.min_stop_pct), self.config.max_stop_pct)

    def size_position(
        self,
        balance: Balance,
        price: float,
        position_pct: float | None = None,
        stop_pct: float | None = None,
    ) -> float:
        """Shares to buy.

        In `risk` mode the cash lost if the stop hits is fixed at
        `risk_per_trade_pct` of equity, and the share count falls out of the stop
        distance — a tight stop buys more shares, a wide stop buys fewer, and the
        money at risk stays the same either way. `position_pct` (a challenge
        bankroll) still caps the total spend.
        """
        if price <= 0:
            return 0.0

        cap_pct = position_pct if position_pct is not None else self.config.max_position_pct
        # Leave room for the entry fee, otherwise a 100% allocation can never fill.
        spendable = min(balance.total * cap_pct / 100.0, balance.available * (1 - FEE_BUFFER))

        if self.config.sizing == "risk" and stop_pct:
            risk_cash = balance.total * self.config.risk_per_trade_pct / 100.0
            per_share_risk = price * stop_pct / 100.0
            if per_share_risk <= 0:
                return 0.0
            allocation = min(risk_cash / per_share_risk * price, spendable)
        else:
            allocation = spendable

        return max(allocation / price, 0.0)

    def validate(
        self,
        signal: Signal,
        balance: Balance,
        position: Position | None,
        price: float,
        symbol: str,
        symbol_info: SymbolInfo | None = None,
        position_pct: float | None = None,
        atr: float | None = None,
    ) -> tuple[OrderRequest | None, str | None]:
        """Returns (order, rejection_reason). Exactly one is non-None."""
        self._roll_day_if_needed(balance.total)

        if not signal.is_actionable:
            return None, None

        if self.is_live and not self._armed:
            return None, RejectionReason.NOT_ARMED

        if signal.action is Action.CLOSE:
            if position is None:
                return None, RejectionReason.NO_POSITION
            return (
                OrderRequest(
                    symbol=symbol,
                    side=Side.SELL if position.side is Side.BUY else Side.BUY,
                    qty=position.qty,
                    order_type=OrderType.MARKET,
                    reason=signal.reason,
                ),
                None,
            )

        if position is not None:
            return None, RejectionReason.MAX_POSITIONS

        if self.daily_loss_breached(balance.total):
            self.disarm("daily loss limit reached")
            return None, RejectionReason.DAILY_LOSS_HIT

        stop_pct = self.stop_distance_pct(price, atr)
        qty = self.size_position(balance, price, position_pct, stop_pct)
        if symbol_info is not None:
            qty = symbol_info.round_qty(qty)
            if qty < symbol_info.min_qty or qty * price < symbol_info.min_notional:
                return None, RejectionReason.POSITION_TOO_SMALL
        if qty <= 0:
            return None, RejectionReason.INSUFFICIENT_BALANCE
        if qty * price > balance.available:
            return None, RejectionReason.INSUFFICIENT_BALANCE

        side = Side.BUY if signal.action is Action.BUY else Side.SELL
        stop_loss, take_profit = self._protective_levels(signal, side, price, stop_pct)
        return (
            OrderRequest(
                symbol=symbol,
                side=side,
                qty=qty,
                order_type=OrderType.MARKET,
                stop_loss=stop_loss,
                take_profit=take_profit,
                reason=signal.reason,
            ),
            None,
        )

    def update_trailing_stop(self, position: Position, price: float) -> float | None:
        """Raise the stop behind a winning trade. Returns the new stop, or None.

        The original stop stays put until the trade is up by `activate_at_pct`;
        after that the stop follows the best price seen, `trail_pct` behind it,
        and never moves backwards.
        """
        trailing = self.config.trailing
        if not trailing.enabled or position.entry_price <= 0:
            return None

        if position.side is Side.BUY:
            gain_pct = (price / position.entry_price - 1) * 100
            if gain_pct < trailing.activate_at_pct:
                return None
            candidate = price * (1 - trailing.trail_pct / 100.0)
            if position.stop_loss is not None and candidate <= position.stop_loss:
                return None
        else:
            gain_pct = (1 - price / position.entry_price) * 100
            if gain_pct < trailing.activate_at_pct:
                return None
            candidate = price * (1 + trailing.trail_pct / 100.0)
            if position.stop_loss is not None and candidate >= position.stop_loss:
                return None

        position.stop_loss = candidate
        return candidate

    def check_protective_exit(self, position: Position, price: float) -> str | None:
        """Engine-side stop-loss / take-profit enforcement, identical in paper and live."""
        if position.side is Side.BUY:
            if position.stop_loss and price <= position.stop_loss:
                return "stop-loss"
            if position.take_profit and price >= position.take_profit:
                return "take-profit"
        else:
            if position.stop_loss and price >= position.stop_loss:
                return "stop-loss"
            if position.take_profit and price <= position.take_profit:
                return "take-profit"
        return None

    def record_closed_trade(self, trade: ClosedTrade, equity: float) -> None:
        self._roll_day_if_needed(equity)
        with self._lock:
            self._daily_realized_pnl += trade.pnl
        if self.daily_loss_breached(equity):
            self.disarm("daily loss limit reached")

    def snapshot(self, equity: float) -> dict:
        limit = self.daily_loss_limit(equity)
        return {
            "mode": self.mode,
            "armed": self._armed,
            "disarm_reason": self._disarm_reason,
            "daily_realized_pnl": round(self._daily_realized_pnl, 2),
            "daily_loss_limit": round(limit, 2),
            "daily_loss_used_pct": round(
                min(max(-self._daily_realized_pnl / limit * 100, 0.0), 100.0), 1
            )
            if limit
            else 0.0,
            "max_position_pct": self.config.max_position_pct,
            "stop_loss_pct": self.config.stop_loss_pct,
            "take_profit_pct": self.config.take_profit_pct,
            "max_daily_loss_pct": self.config.max_daily_loss_pct,
            "max_open_positions": self.config.max_open_positions,
        }

    def _protective_levels(
        self, signal: Signal, side: Side, price: float, stop_pct: float | None = None
    ) -> tuple[float, float]:
        """Stop first, then the target as a multiple of that distance.

        Deriving the target from the stop keeps the reward-to-risk constant no
        matter how wide the stop turned out to be.
        """
        stop_fraction = (stop_pct if stop_pct is not None else self.config.stop_loss_pct) / 100.0
        take_fraction = stop_fraction * self.config.reward_risk
        if side is Side.BUY:
            stop = signal.stop_loss or price * (1 - stop_fraction)
            take = signal.take_profit or price * (1 + take_fraction)
        else:
            stop = signal.stop_loss or price * (1 + stop_fraction)
            take = signal.take_profit or price * (1 - take_fraction)
        return stop, take

    def _roll_day_if_needed(self, equity: float) -> None:
        today = self._clock()
        with self._lock:
            if self._daily_start_equity is None:
                self._daily_start_equity = equity
            if today != self._day:
                self._day = today
                self._daily_realized_pnl = 0.0
                self._daily_start_equity = equity
                log.info("daily risk counters reset for %s", today)


def _utc_today() -> date:
    return datetime.now(timezone.utc).date()
