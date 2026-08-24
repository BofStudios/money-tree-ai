from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

import pandas as pd

from app.common.events import EventBus
from app.common.market_clock import MarketClock
from app.common.models import (
    Action,
    Balance,
    ClosedTrade,
    Position,
    Side,
    Signal,
    TradeIntent,
)
from app.config import AppConfig
from app.data.base import MarketDataSource
from app.execution.base import Executor
from app.execution.signal_executor import SignalExecutor
from app.mentor.narrator import Narrator
from app.challenge.manager import ChallengeManager
from app.risk.protections import Protections
from app.risk.risk_manager import RiskManager
from app.storage.repository import Repository
from app.strategy.base import Strategy

log = logging.getLogger(__name__)

HISTORY_BARS = 400
CLOSED_MARKET_SLEEP = 300
ERROR_BACKOFF = 30


class PortfolioEngine:
    """Scans a watchlist of US stocks on a fixed interval and acts on what it finds.

    Polling rather than streaming: US equity data sources are request-based, and
    a scan loop keeps the same code path working for Yahoo, Alpaca, and the
    signal-only Midas mode.
    """

    def __init__(
        self,
        config: AppConfig,
        data: MarketDataSource,
        executor: Executor,
        strategy: Strategy,
        risk: RiskManager,
        repo: Repository,
        events: EventBus,
        mentor: Narrator,
        challenges: "ChallengeManager | None" = None,
    ) -> None:
        self.config = config
        self.data = data
        self.executor = executor
        self.strategy = strategy
        self.risk = risk
        self.repo = repo
        self.events = events
        self.mentor = mentor
        self.challenges = challenges
        self.protections = Protections(config.protections)
        self.clock = MarketClock()

        self.symbols = list(config.watchlist)
        self.timeframe = config.timeframe
        self.mode = config.mode

        self._history: dict[str, pd.DataFrame] = {}
        self._snapshots: dict[str, dict] = {}
        self._positions: dict[str, Position] = {}
        self._entry_reasons: dict[str, str] = {}
        self._last_signal: dict[str, Signal] = {}
        self._last_scan_at: datetime | None = None
        self._scan_count = 0
        self._started_at: datetime | None = None
        self._last_error: str | None = None

        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None

    # ---------------------------------------------------------------- lifecycle

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._started_at = datetime.now(timezone.utc)
        self._thread = threading.Thread(target=self._run, name="portfolio-engine", daemon=True)
        self._thread.start()
        self.mentor.boot(self.mode, self.symbols, self.timeframe, self.executor.name)

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        self.mentor.note("Stopping. Open positions stay open — I just stop watching them.")
        self.events.publish("status", self.status())

    def scan_now(self) -> None:
        self._wake.set()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive() and not self._stop.is_set()

    # ------------------------------------------------------------------ actions

    def arm(self) -> None:
        self.risk.arm()
        self.events.publish("status", self.status())

    def disarm(self, reason: str = "manual") -> None:
        self.risk.disarm(reason)
        self.events.publish("status", self.status())

    def close_position_now(self, symbol: str, reason: str = "manual close") -> bool:
        with self._lock:
            position = self._positions.get(symbol)
        if position is None:
            return False
        price = position.current_price or position.entry_price
        self._exit(position, price, reason)
        return True

    def add_symbol(self, symbol: str) -> bool:
        symbol = symbol.strip().upper()
        if not symbol:
            return False
        with self._lock:
            if symbol in self.symbols:
                return False
            self.symbols.append(symbol)
        self.mentor.note(f"Added {symbol} to the watchlist.")
        self._wake.set()
        return True

    def remove_symbol(self, symbol: str) -> bool:
        symbol = symbol.strip().upper()
        with self._lock:
            if symbol not in self.symbols or symbol in self._positions:
                return False
            self.symbols.remove(symbol)
            self._history.pop(symbol, None)
            self._snapshots.pop(symbol, None)
        self.mentor.note(f"Removed {symbol} from the watchlist.")
        return True

    # ------------------------------------------------------------------- status

    def status(self) -> dict:
        market = self.clock.state()
        balance = self.executor.get_balance()
        with self._lock:
            positions = [p.to_dict() for p in self._positions.values()]
            snapshots = dict(self._snapshots)
            scanned = self._scan_count
            last_scan = self._last_scan_at
            error = self._last_error

        return {
            "mode": self.mode,
            "executor": self.executor.name,
            "automatic": self.executor.is_automatic,
            "data_source": self.data.name,
            "timeframe": self.timeframe,
            "running": self.running,
            "market": market.to_dict(),
            "balance": balance.to_dict(),
            "equity": round(balance.total, 2),
            "positions": positions,
            "watchlist": self.watchlist_rows(snapshots),
            "scans": scanned,
            "last_scan_at": last_scan.isoformat() if last_scan else None,
            "started_at": self._started_at.isoformat() if self._started_at else None,
            "last_error": error,
            "risk": self.risk.snapshot(balance.total),
            "pending_signals": self._pending_signal_dicts(),
            "challenge": self._challenge_dict(),
            "locks": self.protections.active_locks(),
        }

    def _challenge_dict(self) -> dict | None:
        if self.challenges is None:
            return None
        state = self.challenges.active()
        return state.to_dict() if state else None

    def watchlist_rows(self, snapshots: dict[str, dict] | None = None) -> list[dict]:
        with self._lock:
            snaps = snapshots if snapshots is not None else dict(self._snapshots)
            positions = dict(self._positions)
            signals = dict(self._last_signal)
            symbols = list(self.symbols)

        rows = []
        for symbol in symbols:
            snapshot = snaps.get(symbol, {})
            position = positions.get(symbol)
            signal = signals.get(symbol)
            rows.append(
                {
                    "symbol": symbol,
                    "ready": bool(snapshot.get("ready")),
                    "price": snapshot.get("price"),
                    "trend": snapshot.get("trend"),
                    "spread_pct": _round(snapshot.get("spread_pct"), 2),
                    "rsi": _round(snapshot.get("rsi"), 0),
                    "rsi_zone": snapshot.get("rsi_zone"),
                    "atr_pct": _round(snapshot.get("atr_pct"), 2),
                    "bars_since_cross": snapshot.get("bars_since_cross"),
                    "change_pct": _round(snapshot.get("window_change_pct"), 2),
                    "position": position.to_dict() if position else None,
                    "last_signal": (
                        {"action": signal.action.value, "reason": signal.reason}
                        if signal
                        else None
                    ),
                }
            )
        return rows

    def position_for(self, symbol: str) -> Position | None:
        with self._lock:
            return self._positions.get(symbol.upper())

    def snapshot_for(self, symbol: str) -> dict:
        with self._lock:
            return dict(self._snapshots.get(symbol.upper(), {}))

    def candles(self, symbol: str) -> list[dict]:
        with self._lock:
            history = self._history.get(symbol)
            history = history.copy() if history is not None else None
        if history is None or history.empty:
            return []
        return [
            {
                "time": int(ts.timestamp()),
                "open": float(row.open),
                "high": float(row.high),
                "low": float(row.low),
                "close": float(row.close),
            }
            for ts, row in history.iterrows()
        ]

    def overlays(self, symbol: str) -> dict[str, list[dict]]:
        with self._lock:
            history = self._history.get(symbol)
            history = history.copy() if history is not None else None
        if history is None or history.empty:
            return {}
        return {
            name: [
                {"time": int(ts.timestamp()), "value": round(float(value), 4)}
                for ts, value in series.items()
                if pd.notna(value)
            ]
            for name, series in self.strategy.indicator_series(history).items()
        }

    def mentor_context(self) -> dict:
        """Compact state for the Claude mentor and for answering questions."""
        status = self.status()
        return {
            "mode": status["mode"],
            "market": {
                "is_open": status["market"]["is_open"],
                "countdown": status["market"]["countdown"],
            },
            "equity": status["equity"],
            "balance": status["balance"],
            "risk": status["risk"],
            "open_positions": status["positions"],
            "watchlist": [
                {
                    k: v
                    for k, v in row.items()
                    if k in ("symbol", "price", "trend", "spread_pct", "rsi", "rsi_zone", "change_pct")
                }
                for row in status["watchlist"]
            ],
            "recent_trades": self.repo.recent_trades(self.mode, limit=10),
            "stats": self.repo.trade_stats(self.mode),
            "strategy": {
                "name": self.strategy.name,
                "fast_ema": self.config.strategy.fast_ema,
                "slow_ema": self.config.strategy.slow_ema,
                "rsi_period": self.config.strategy.rsi_period,
                "rsi_overbought": self.config.strategy.rsi_overbought,
            },
        }

    # ---------------------------------------------------------------- main loop

    def _run(self) -> None:
        self._restore_positions()
        announced: bool | None = None  # last market-open state the mentor commented on

        while not self._stop.is_set():
            market = self.clock.state()
            try:
                if announced != market.is_open:
                    self.mentor.market_state(market)
                    announced = market.is_open

                if market.is_open:
                    self._scan(market)
                    delay = self.config.scan_interval_seconds
                else:
                    # Refresh charts once so the dashboard is not blank out of hours.
                    if self._scan_count == 0:
                        self._scan(market, trade=False)
                    delay = CLOSED_MARKET_SLEEP
                self._last_error = None
            except Exception as exc:
                self._last_error = str(exc)
                log.exception("scan failed")
                self.mentor.error("Scan", str(exc))
                self.events.publish("error", {"message": str(exc)})
                delay = ERROR_BACKOFF

            self._wake.wait(delay)
            self._wake.clear()

    def _scan(self, market, trade: bool = True) -> None:
        with self._lock:
            symbols = list(self.symbols)

        self.mentor.scan_start(len(symbols), self.timeframe)
        frames = self.data.get_many_ohlcv(symbols, self.timeframe, limit=HISTORY_BARS)
        if not frames:
            raise RuntimeError(f"no market data returned for {len(symbols)} symbols")

        signals_raised = 0
        for symbol in symbols:
            history = frames.get(symbol)
            if history is None or history.empty:
                continue

            snapshot = self.strategy.snapshot(history)
            price = float(history["close"].iloc[-1])

            with self._lock:
                self._history[symbol] = history
                self._snapshots[symbol] = snapshot
                position = self._positions.get(symbol)

            self.executor.update_price(symbol, price)
            if position is not None:
                position.current_price = price

            self.mentor.observe(symbol, snapshot, position)

            if not trade:
                continue

            if position is not None and self._check_protective_exit(position, price):
                continue

            with self._lock:
                position = self._positions.get(symbol)

            signal = self.strategy.on_bar(history, position)
            with self._lock:
                self._last_signal[symbol] = signal

            if signal.is_actionable and self._act(symbol, signal, snapshot, price):
                signals_raised += 1

        self._scan_count += 1
        self._last_scan_at = datetime.now(timezone.utc)

        if isinstance(self.executor, SignalExecutor):
            self.executor.expire_stale()

        if self.challenges is not None:
            with self._lock:
                self.challenges.mark_unrealised(
                    sum(p.unrealized_pnl for p in self._positions.values())
                )

        balance = self.executor.get_balance()
        self.repo.record_equity(balance.total, self.mode)
        with self._lock:
            holding = len(self._positions)
        self.mentor.scan_summary(len(symbols), holding, signals_raised, balance.total)
        self.events.publish("status", self.status())

    # ------------------------------------------------------------------ actions

    def _check_protective_exit(self, position: Position, price: float) -> bool:
        # Ratchet the stop up behind a winner before testing whether it is hit,
        # so a trade that ran and then turned still exits in profit.
        raised = self.risk.update_trailing_stop(position, price)
        if raised is not None:
            self.repo.save_open_position(
                position, self.mode, self._entry_reasons.get(position.symbol, "")
            )
            self.mentor.trailing_stop(position, raised)

        reason = self.risk.check_protective_exit(position, price)
        if not reason:
            return False
        self.mentor.protective_exit(position, price, reason)
        self._exit(position, price, reason)
        return True

    def _act(self, symbol: str, signal: Signal, snapshot: dict, price: float) -> bool:
        with self._lock:
            position = self._positions.get(symbol)
            open_count = len(self._positions)

        if signal.action is Action.CLOSE:
            if position is None:
                return False
            self._exit(position, price, signal.reason)
            return True

        if isinstance(self.executor, SignalExecutor) and self.executor.has_pending_for(symbol):
            return False

        locked = self.protections.blocked(symbol)
        if position is None and locked:
            self.mentor.rejected(symbol, f"buy on '{signal.reason}'", locked)
            return False

        balance, max_positions, position_pct = self._effective_limits()

        # Signals you have not answered yet still count against the cap, otherwise
        # signal mode would queue up far more trades than the limit allows.
        committed = open_count + self._pending_entry_count()
        if position is None and committed >= max_positions:
            held = (
                f"I already hold {open_count} positions"
                if committed == open_count
                else f"I hold {open_count} and have {committed - open_count} signals waiting"
            )
            self.mentor.rejected(
                symbol, f"buy on '{signal.reason}'", f"{held}, and my cap is {max_positions}"
            )
            return False

        order, rejection = self.risk.validate(
            signal, balance, position, price, symbol,
            position_pct=position_pct, atr=snapshot.get("atr"),
        )
        if order is None:
            if rejection:
                self.mentor.rejected(symbol, f"buy on '{signal.reason}'", rejection)
                self.events.publish(
                    "rejected",
                    {"symbol": symbol, "reason": signal.reason, "rejection": rejection},
                )
            return False

        self.mentor.considering(symbol, signal.reason, snapshot)

        intent = TradeIntent(
            symbol=symbol,
            side=order.side,
            action=signal.action,
            qty=self._round_qty(order.qty, price),
            price=price,
            reason=signal.reason,
            stop_loss=order.stop_loss,
            take_profit=order.take_profit,
        )
        if intent.qty <= 0:
            unit = "one share" if not self.config.risk.fractional_shares else \
                f"the ${self.config.risk.min_order_value:.0f} minimum order"
            self.mentor.rejected(symbol, "buy", f"the position would be under {unit}")
            return False

        self.mentor.explain_entry(intent, snapshot, balance.total)
        self.events.publish("intent", {"intent": intent.to_dict()})

        opened = self.executor.open_position(intent)
        if opened is None:
            self.mentor.awaiting_confirmation(intent)
            return True

        self._register_position(opened, intent.reason)
        self.mentor.opened(opened, self.executor.is_automatic)
        self.events.publish(
            "trade_opened", {"position": opened.to_dict(), "reason": intent.reason}
        )
        return True

    def _exit(self, position: Position, price: float, reason: str) -> None:
        trade = self.executor.close_position(position, price, reason)
        if trade is None:
            # Signal mode: the exit is a recommendation until you confirm it.
            return

        with self._lock:
            self._positions.pop(position.symbol, None)
            entry_reason = self._entry_reasons.pop(position.symbol, "")

        self.repo.save_closed_trade(trade, self.mode, self.executor.name, entry_reason)
        self.repo.clear_open_position(position.symbol)
        self.risk.record_closed_trade(trade, self.executor.get_balance().total)

        self.mentor.closed(trade)
        equity = self.executor.get_balance().total
        for lock in self.protections.record_trade(trade, equity):
            self.mentor.protection_lock(lock, self.protections.active_locks())
        self._credit_challenge(trade)
        if not self.risk.armed and self.risk.disarm_reason == "daily loss limit reached":
            equity = self.executor.get_balance().total
            self.mentor.kill_switch(
                self.risk.daily_realized_pnl, self.risk.daily_loss_limit(equity)
            )

        self.events.publish("trade_closed", _trade_event(trade))
        self.events.publish("status", self.status())

    # ---------------------------------------------- signal-mode confirmations

    def register_confirmed_entry(self, symbol: str, position: Position, reason: str) -> None:
        """Called after you confirm in Telegram that you took a signal in Midas."""
        self._register_position(position, reason)
        self.mentor.opened(position, automatic=False)
        self.events.publish("trade_opened", {"position": position.to_dict(), "reason": reason})

    def register_confirmed_exit(self, trade: ClosedTrade) -> None:
        with self._lock:
            self._positions.pop(trade.symbol, None)
            entry_reason = self._entry_reasons.pop(trade.symbol, "")

        self.repo.save_closed_trade(trade, self.mode, self.executor.name, entry_reason)
        self.repo.clear_open_position(trade.symbol)
        self.risk.record_closed_trade(trade, self.executor.get_balance().total)
        self.mentor.closed(trade)
        self._credit_challenge(trade)
        self.events.publish("trade_closed", _trade_event(trade))
        self.events.publish("status", self.status())

    # ---------------------------------------------------------------- internals

    def _credit_challenge(self, trade: ClosedTrade) -> None:
        if self.challenges is None:
            return
        state = self.challenges.record_trade(trade.pnl)
        if state is None:
            return
        if state.status == "won":
            self.mentor.challenge_won(state)
        elif state.status == "lost":
            self.mentor.challenge_lost(state)
        else:
            self.mentor.challenge_progress(state)

    def _register_position(self, position: Position, reason: str) -> None:
        with self._lock:
            self._positions[position.symbol] = position
            self._entry_reasons[position.symbol] = reason
        self.repo.save_open_position(position, self.mode, reason)

    def _restore_positions(self) -> None:
        restored = 0
        for symbol in list(self.symbols):
            stored, reason = self.repo.load_open_position(symbol, self.mode)
            if stored is None:
                continue
            with self._lock:
                self._positions[symbol] = stored
                self._entry_reasons[symbol] = reason
            self.executor.adopt_position(stored)
            restored += 1
        if restored:
            self.mentor.note(
                f"Picked up {restored} open position{'s' if restored > 1 else ''} "
                "from last session."
            )

    def _effective_limits(self) -> tuple[Balance, int, float | None]:
        """Money and caps for the next entry, honouring an active challenge.

        A challenge ring-fences its own bankroll: a $5 run can only ever deploy
        the $5 it started with plus whatever it has made, never the whole account.
        """
        account = self.executor.get_balance()
        challenge = self.challenges.active() if self.challenges else None
        if challenge is None or not challenge.is_active:
            return account, self.config.risk.max_open_positions, None

        with self._lock:
            deployed = sum(p.entry_price * p.qty for p in self._positions.values())
        bankroll = max(challenge.value, 0.0)
        return (
            Balance(
                total=bankroll,
                available=max(min(bankroll - deployed, account.available), 0.0),
                currency=account.currency,
            ),
            self.config.challenge.max_open_positions,
            self.config.challenge.position_pct,
        )

    def _round_qty(self, qty: float, price: float) -> float:
        """Shares the broker will actually accept, or 0 if the order is too small."""
        risk = self.config.risk
        if risk.fractional_shares:
            rounded = round(qty, 6)
        else:
            rounded = float(int(qty))
        if rounded * price < risk.min_order_value:
            return 0.0
        return rounded

    def _pending_entry_count(self) -> int:
        if not isinstance(self.executor, SignalExecutor):
            return 0
        return sum(1 for s in self.executor.pending_signals() if not s.is_exit)

    def _pending_signal_dicts(self) -> list[dict]:
        if not isinstance(self.executor, SignalExecutor):
            return []
        return [s.to_dict() for s in self.executor.pending_signals()]


def _trade_event(trade: ClosedTrade) -> dict:
    return {
        "symbol": trade.symbol,
        "qty": trade.qty,
        "entry_price": trade.entry_price,
        "exit_price": trade.exit_price,
        "pnl": round(trade.pnl, 2),
        "pnl_pct": round(trade.pnl_pct, 2),
        "exit_reason": trade.exit_reason,
    }


def _round(value, digits: int):
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None
