from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.common.models import ClosedTrade, Side
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

    def __init__(self, config: ProtectionsConfig, state_path: Path | None = None) -> None:
        self.config = config
        self._lock = threading.Lock()
        self._locks: list[Lock] = []
        self._closed: list[ClosedTrade] = []
        self._equity_peak: float | None = None
        # Remembered, so closing and opening the app never lifts a pause early.
        self._state_path = state_path
        self._load()

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

    def cool_down(self, symbol: str, now: datetime | None = None) -> None:
        """The cooldown alone, for a position that vanished with no trade to record."""
        if self.config.enabled and self.config.cooldown_minutes:
            now = now or _now()
            self._add(Lock(now + timedelta(minutes=self.config.cooldown_minutes), COOLDOWN, symbol))

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

        self._save()
        return triggered

    def clear(self) -> None:
        with self._lock:
            self._locks.clear()
        self._save()

    # ---------------------------------------------------------------- memory

    def _save(self) -> None:
        if self._state_path is None:
            return
        now = _now()
        with self._lock:
            doc = {
                "locks": [{"until": l.until.isoformat(), "reason": l.reason, "symbol": l.symbol}
                          for l in self._locks if l.active(now)],
                "closed": [_trade_dict(t) for t in self._closed[-60:]],
                "equity_peak": self._equity_peak,
            }
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._state_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(doc), encoding="utf-8")
            tmp.replace(self._state_path)
        except OSError:
            log.exception("could not save the protection locks")

    def _load(self) -> None:
        if self._state_path is None:
            return
        try:
            doc = json.loads(self._state_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except (OSError, ValueError):
            log.warning("protection locks unreadable; starting without them")
            return
        now = _now()
        try:
            for row in doc.get("locks", []):
                lock = Lock(datetime.fromisoformat(row["until"]), str(row["reason"]), row.get("symbol"))
                if lock.active(now):
                    self._locks.append(lock)
            self._closed = [_trade_from(row) for row in doc.get("closed", [])]
            peak = doc.get("equity_peak")
            self._equity_peak = float(peak) if peak else None
        except (KeyError, TypeError, ValueError):
            log.warning("parts of the protection locks are unreadable; starting those fresh")

    # -------------------------------------------------------------- internals

    def _add(self, lock: Lock) -> None:
        with self._lock:
            # One lock per (reason, symbol); extend rather than pile up duplicates.
            for existing in self._locks:
                if existing.reason == lock.reason and existing.symbol == lock.symbol:
                    existing.until = max(existing.until, lock.until)
                    break
            else:
                self._locks.append(lock)
                log.info("protection lock: %s (%s)", lock.reason, lock.symbol or "all symbols")
        self._save()

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


def _trade_dict(t: ClosedTrade) -> dict:
    return {"symbol": t.symbol, "side": t.side.value, "qty": t.qty, "entry_price": t.entry_price,
            "exit_price": t.exit_price, "opened_at": t.opened_at.isoformat(),
            "closed_at": t.closed_at.isoformat(), "pnl": t.pnl, "exit_reason": t.exit_reason}


def _trade_from(row: dict) -> ClosedTrade:
    return ClosedTrade(str(row["symbol"]), Side(row["side"]), float(row["qty"]), float(row["entry_price"]),
                       float(row["exit_price"]), datetime.fromisoformat(row["opened_at"]),
                       datetime.fromisoformat(row["closed_at"]), float(row["pnl"]), str(row["exit_reason"]))
