from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.common.models import ClosedTrade
from app.config import ProtectionsConfig

log = logging.getLogger(__name__)

# Reasons, kept as constants so the mentor and the tests agree on the wording.
COOLDOWN = "cooldown after the last trade"
STOPLOSS_GUARD = "too many stop-outs recently"
MAX_DRAWDOWN = "drawdown limit hit"


@dataclass
class Lock:
    until: datetime
    reason: str
    symbol: str | None  # None means every symbol

    def active(self, now: datetime) -> bool:
        return now < self.until

    def to_dict(self, now: datetime) -> dict:
        return {
            "reason": self.reason,
            "symbol": self.symbol,
            "until": self.until.isoformat(),
            "minutes_left": max(int((self.until - now).total_seconds() // 60), 0),
        }


class Protections:
    """Pauses trading after the kinds of losing patterns that eat an account.

    Modelled on Freqtrade's protection plugins:
      - a cooldown stops the bot re-entering a symbol it just closed,
      - a stoploss guard halts everything after a run of stop-outs,
      - a drawdown guard halts everything when recent equity falls too far.

    These exist because the backtest showed the strategy churning: many small
    trades, most of them losers. Locks turn that churn off for a while.
    """

    def __init__(self, config: ProtectionsConfig) -> None:
        self.config = config
        self._lock = threading.Lock()
        self._locks: list[Lock] = []
        self._closed: list[ClosedTrade] = []
        self._equity_peak: float | None = None

    # ------------------------------------------------------------------ query

    def blocked(self, symbol: str, now: datetime | None = None) -> str | None:
        """Reason this symbol cannot be entered right now, or None."""
        if not self.config.enabled:
            return None
        now = now or _now()
        with self._lock:
            self._locks = [l for l in self._locks if l.active(now)]
            for lock in self._locks:
                if lock.symbol is None or lock.symbol == symbol:
                    minutes = max(int((lock.until - now).total_seconds() // 60), 1)
                    return f"{lock.reason} ({minutes}m left)"
        return None

    def active_locks(self, now: datetime | None = None) -> list[dict]:
        now = now or _now()
        with self._lock:
            self._locks = [l for l in self._locks if l.active(now)]
            return [l.to_dict(now) for l in self._locks]

    # ------------------------------------------------------------------ input

    def record_trade(self, trade: ClosedTrade, equity: float, now: datetime | None = None) -> list[str]:
        """Fold a closed trade in and return any locks it just triggered."""
        if not self.config.enabled:
            return []
        now = now or _now()
        triggered: list[str] = []

        with self._lock:
            self._closed.append(trade)
            # Only the recent tail matters to any of the rules.
            self._closed = self._closed[-200:]
            self._equity_peak = max(self._equity_peak or equity, equity)

        if self.config.cooldown_minutes:
            self._add(
                Lock(now + timedelta(minutes=self.config.cooldown_minutes), COOLDOWN, trade.symbol)
            )

        if self._stoploss_guard_tripped(now):
            self._add(
                Lock(
                    now + timedelta(minutes=self.config.stoploss_guard_stop_minutes),
                    STOPLOSS_GUARD,
                    None,
                )
            )
            triggered.append(STOPLOSS_GUARD)

        if self._drawdown_tripped(equity):
            self._add(
                Lock(
                    now + timedelta(minutes=self.config.max_drawdown_stop_minutes),
                    MAX_DRAWDOWN,
                    None,
                )
            )
            triggered.append(MAX_DRAWDOWN)

        return triggered

    def clear(self) -> None:
        with self._lock:
            self._locks.clear()

    # -------------------------------------------------------------- internals

    def _add(self, lock: Lock) -> None:
        with self._lock:
            # One lock per (reason, symbol); extend rather than pile up duplicates.
            for existing in self._locks:
                if existing.reason == lock.reason and existing.symbol == lock.symbol:
                    existing.until = max(existing.until, lock.until)
                    return
            self._locks.append(lock)
        log.info("protection lock: %s (%s)", lock.reason, lock.symbol or "all symbols")

    def _stoploss_guard_tripped(self, now: datetime) -> bool:
        window = now - timedelta(minutes=self.config.stoploss_guard_lookback_minutes)
        with self._lock:
            recent = [
                t for t in self._closed
                if t.closed_at >= window and t.exit_reason == "stop-loss"
            ]
        return len(recent) >= self.config.stoploss_guard_trades

    def _drawdown_tripped(self, equity: float) -> bool:
        with self._lock:
            enough = len(self._closed) >= self.config.max_drawdown_lookback_trades
            peak = self._equity_peak
        if not enough or not peak:
            return False
        drawdown = (peak - equity) / peak * 100.0
        return drawdown >= self.config.max_drawdown_pct


def _now() -> datetime:
    return datetime.now(timezone.utc)
