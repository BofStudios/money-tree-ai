"""The trading loop: look at the market, manage what is held, act on signals.

Every piece of real work is also a step in the Live tab (app/common/activity.py):
opened before the work starts, closed when it ends, in the owner's language.
Nothing on that screen moves without an operation behind it.

With a brokerage behind the executor (Alpaca), each look also reconciles with
it: positions a bracket leg closed while the bot was not looking are recorded
from their real fills, and positions the bot did not open are shown but never
touched.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Protocol

import pandas as pd

from app.common import activity
from app.common.activity import Monitor
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
from app.engine.autonomy import (
    APPROVAL_MINUTES,
    AUTONOMY_MODES,
    HORIZON_TIMEFRAMES,
    MAX_DRIFT_PCT,
    ProposalBook,
)
from app.engine.words import Words
from app.execution.base import AccountSummary, BrokerView, Executor, Holding, tick
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

class Explainer(Protocol):
    """Anything that can put a buy into plain words (app/mentor/ai.py)."""

    @property
    def available(self) -> bool: ...

    def explain_entry(self, facts: str, turkish: bool) -> str | None: ...


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
        monitor: Monitor | None = None,
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
        self.monitor = monitor or Monitor(events)

        self.symbols = list(config.watchlist)
        self.timeframe = config.timeframe
        self.mode = config.mode
        # Who pulls the trigger on a buy — see app/engine/autonomy.py. Full
        # until main() applies the owner's choice from their profile.
        self.autonomy = "full"
        self.proposals = ProposalBook()
        self.language = "en"
        # Optional helpers wired in by main(): headlines before a buy, and an
        # AI that explains a buy in plain words after it fills.
        self.news = None
        self.explainer: Explainer | None = None

        self._history: dict[str, pd.DataFrame] = {}
        self._snapshots: dict[str, dict] = {}
        self._positions: dict[str, Position] = {}
        self._entry_reasons: dict[str, str] = {}
        self._last_signal: dict[str, Signal] = {}
        self._last_scan_at: datetime | None = None
        self._scan_count = 0
        self._started_at: datetime | None = None
        self._last_error: str | None = None

        # What the brokerage said on the last look.
        self._broker_stops: set[str] = set()      # symbols whose stop sits at the broker
        self._unmanaged: list[Holding] = []       # positions this app did not open
        self._account: AccountSummary | None = None

        self._focus: str | None = None            # the symbol being looked at right now
        self._next_look_at: datetime | None = None
        self._force_look = False
        self._closed_reviewed = False

        self._lock = threading.RLock()
        # One trading action at a time: a scan, a manual close, an approval.
        self._trade_lock = threading.RLock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None

    def words(self) -> Words:
        return Words(self.language == "tr")

    # ---------------------------------------------------------------- lifecycle

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._started_at = datetime.now(timezone.utc)
        self._thread = threading.Thread(target=self._run, name="portfolio-engine", daemon=True)
        self._thread.start()
        self.mentor.boot(self.mode, self.symbols, self.timeframe, self.executor.name)
        self.monitor.info(
            activity.INFO,
            self.words().started(self.mode, self.executor.broker, self.autonomy, self.timeframe),
        )

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        self.mentor.note("Stopping. Open positions stay open — I just stop watching them.")
        self.events.publish("status", self.status())

    def join(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout)

    def scan_now(self) -> None:
        """Look again right away — with a full review even while the market is closed."""
        self._force_look = True
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
        with self._trade_lock:
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

    def set_watchlist(self, symbols: list[str]) -> list[str]:
        """Swap the whole list, e.g. when the owner picks another market.

        Stocks already held stay under management: they keep being priced and
        their stops keep being watched, they just stop being bought again.
        """
        clean: list[str] = []
        for symbol in symbols:
            symbol = symbol.strip().upper()
            if symbol and symbol not in clean:
                clean.append(symbol)
        if not clean:
            raise ValueError("the watchlist cannot be empty")
        with self._lock:
            if clean == self.symbols:
                return clean
            self.symbols = clean
            for symbol in list(self._history):
                if symbol not in clean and symbol not in self._positions:
                    self._history.pop(symbol, None)
                    self._snapshots.pop(symbol, None)
                    self._last_signal.pop(symbol, None)
        self.proposals.clear_pending()
        self.mentor.note(f"Now watching {', '.join(clean)}.")
        self.scan_now()
        return clean

    def set_small_account(self, enabled: bool) -> None:
        """Fractional shares, for an account too small to buy a whole share."""
        self.config.risk.fractional_shares = bool(enabled)
        self.events.publish("status", self.status())

    def set_language(self, language: str) -> None:
        self.language = "tr" if language == "tr" else "en"

    # ------------------------------------------------------------------- status

    def status(self) -> dict:
        market = self.clock.state()
        balance = self.executor.get_balance()
        try:
            account = self.executor.account_summary()
        except Exception:
            account = self._account
        with self._lock:
            positions = [
                {**p.to_dict(), "stop_at_broker": p.symbol in self._broker_stops}
                for p in self._positions.values()
            ]
            snapshots = dict(self._snapshots)
            scanned = self._scan_count
            last_scan = self._last_scan_at
            error = self._last_error
            unmanaged = [h.to_dict() for h in self._unmanaged]

        return {
            "mode": self.mode,
            "executor": self.executor.name,
            "broker": self.executor.broker,
            "automatic": self.executor.is_automatic,
            "data_source": self.data.name,
            "timeframe": self.timeframe,
            "running": self.running,
            "market": market.to_dict(),
            "balance": balance.to_dict(),
            "equity": round(balance.total, 2),
            "account": account.to_dict() if account else None,
            "positions": positions,
            "unmanaged": unmanaged,
            "watchlist": self.watchlist_rows(snapshots),
            "scans": scanned,
            "last_scan_at": last_scan.isoformat() if last_scan else None,
            "next_look_at": self._next_look_at.isoformat() if self._next_look_at else None,
            "focus": self._focus,
            "started_at": self._started_at.isoformat() if self._started_at else None,
            "last_error": error,
            "risk": self.risk.snapshot(balance.total),
            "small_account": self.config.risk.fractional_shares,
            "language": self.language,
            "pending_signals": self._pending_signal_dicts(),
            "challenge": self._challenge_dict(),
            "locks": self.protections.active_locks(),
            "autonomy": self.autonomy,
            "approvals": [p.to_dict() for p in self.proposals.pending("approval")],
            "suggestions": [p.to_dict() for p in self.proposals.pending("suggestion")],
            "proposal_history": [p.to_dict() for p in self.proposals.recent(8)],
        }

    def look_state(self) -> dict:
        """What the Live tab's header needs between steps."""
        return {
            "running": self.running,
            "focus": self._focus,
            "next_look_at": self._next_look_at.isoformat() if self._next_look_at else None,
            "language": self.language,
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
            symbols = self._scan_symbols()

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
            forced, self._force_look = self._force_look, False
            market = self.clock.state()
            try:
                if announced != market.is_open:
                    self.mentor.market_state(market)
                    announced = market.is_open

                if market.is_open:
                    self._closed_reviewed = False
                    self._scan(market)
                    delay = self.config.scan_interval_seconds
                else:
                    # One full review so the screen shows real, current work on
                    # a weekend; after that the closed market is left alone
                    # until the open, unless the owner asks for another look.
                    if forced or not self._closed_reviewed:
                        self._scan(market, trade=False)
                        self._closed_reviewed = True
                    delay = _closed_delay(market)
                self._last_error = None
            except Exception as exc:
                self._last_error = str(exc)
                log.exception("scan failed")
                self.mentor.error("Scan", str(exc))
                self.monitor.info(activity.WARN, self.words().cycle_failed(), _short(exc))
                self.events.publish("error", {"message": str(exc)})
                delay = ERROR_BACKOFF
            finally:
                self._focus = None

            self._next_look_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
            self.events.publish("status", self.status())
            self._wake.wait(delay)
            self._wake.clear()

    def _scan(self, market, trade: bool = True) -> None:
        with self._trade_lock:
            self._scan_locked(market, trade)

    def _scan_locked(self, market, trade: bool) -> None:
        w = self.words()
        m = self.monitor
        is_open = bool(getattr(market, "is_open", False))
        if is_open:
            m.info(activity.CLOCK, w.market_open(getattr(market, "next_close", None)))
        else:
            m.info(activity.CLOCK, w.market_closed(getattr(market, "next_open", None)))
            m.info(activity.INFO, w.closed_review())

        self._read_account(w)
        self._sync_broker(w)

        with self._lock:
            symbols = self._scan_symbols()
        self.mentor.scan_start(len(symbols), self.timeframe)
        frames = self._fetch_bars(symbols, w)
        looked = self._analyse(symbols, frames, trade, w)

        signals_raised = 0
        if trade:
            for symbol, snapshot, price, signal in looked:
                if self._manage(symbol, snapshot, price, signal, w):
                    signals_raised += 1

        self._scan_count += 1
        self._last_scan_at = datetime.now(timezone.utc)

        if isinstance(self.executor, SignalExecutor):
            self.executor.expire_stale()
        for stale in self.proposals.expire():
            self.events.publish("proposal_expired", {"proposal": stale.to_dict()})

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
        if is_open:
            m.info(activity.WAIT, w.scan_done(holding, self.config.scan_interval_seconds))
        else:
            m.info(activity.WAIT, w.waiting_for_open(getattr(market, "next_open", None)))
        self.events.publish("status", self.status())

    # ------------------------------------------------------------ scan steps

    def _read_account(self, w: Words) -> AccountSummary | None:
        handle = self.monitor.begin(activity.ACCOUNT, w.reading_account())
        try:
            account = self.executor.account_summary()
        except Exception as exc:
            handle.fail(_short(exc))
            return None
        self._account = account
        handle.done(w.account_summary(account.equity, account.cash, account.today))
        if account.blocked:
            self.monitor.info(activity.WARN, w.account_blocked())
        return account

    def _sync_broker(self, w: Words) -> BrokerView | None:
        handle = self.monitor.begin(activity.POSITIONS, w.checking_positions())
        try:
            view = self.executor.broker_view()
        except Exception as exc:
            handle.fail(_short(exc))
            return None
        if view is None:
            with self._lock:
                held = len(self._positions)
            handle.done(w.positions_summary(held, None))
            return None

        closed, dropped = self._reconcile(view)
        with self._lock:
            held = len(self._positions)
            unmanaged = list(self._unmanaged)
        handle.done(
            w.positions_summary(held, view.open_orders),
            [w.unmanaged_line(h.symbol, h.qty, h.unrealized_pl) for h in unmanaged],
        )
        for trade in closed:
            self.monitor.info(
                activity.SELL,
                w.closed_at_broker(trade.symbol, trade.exit_reason, trade.pnl),
                w.fill_detail(trade.qty, trade.entry_price, trade.exit_price),
            )
        for symbol in dropped:
            self.monitor.info(activity.WARN, w.lost_track(symbol))
        return view

    def _reconcile(self, view: BrokerView) -> tuple[list[ClosedTrade], list[str]]:
        """Bring the engine's positions in line with what the broker holds."""
        closed: list[ClosedTrade] = []
        dropped: list[str] = []
        with self._lock:
            held = dict(self._positions)

        for symbol, position in held.items():
            before = (position.qty, position.entry_price, position.stop_loss, position.take_profit)
            fill = view.fills.get(symbol)
            if fill is not None:
                position.qty, position.entry_price = fill
            holding = view.holdings.get(symbol)
            if holding is not None:
                # Shares the owner sold by hand in Alpaca's app are gone for us too.
                position.qty = min(position.qty, holding.qty)
                position.current_price = holding.price
                position.stop_loss = view.stops.get(symbol, position.stop_loss)
                position.take_profit = view.targets.get(symbol, position.take_profit)
                if before != (position.qty, position.entry_price, position.stop_loss, position.take_profit):
                    self.repo.save_open_position(position, self.mode, self._entry_reasons.get(symbol, ""))
                continue
            if symbol in view.open_buys:
                continue  # the entry is still working

            # Gone at the broker: a stop or target filled, or the owner sold it.
            try:
                trade = self.executor.closing_trade(position)
            except Exception:
                log.exception("could not read how %s was closed", symbol)
                continue
            if trade is None:
                self._forget_position(symbol)
                dropped.append(symbol)
            else:
                self._record_closed(trade)
                closed.append(trade)

        with self._lock:
            self._broker_stops = {s for s in view.stops if s in self._positions}
            self._unmanaged = [
                holding for symbol, holding in sorted(view.holdings.items())
                if symbol not in self._positions
            ]
        return closed, dropped

    def _fetch_bars(self, symbols: list[str], w: Words) -> dict[str, pd.DataFrame]:
        # One batched request: that is how both data sources work, so the step
        # stays open for exactly as long as that request takes.
        handle = self.monitor.begin(activity.BARS, w.fetching_bars(len(symbols), self.timeframe))
        try:
            frames = self.data.get_many_ohlcv(symbols, self.timeframe, limit=HISTORY_BARS)
        except Exception as exc:
            handle.fail(_short(exc))
            raise
        frames = {s: f for s, f in (frames or {}).items() if f is not None and not f.empty}
        if not frames:
            handle.fail(w.no_data(len(symbols)))
            raise RuntimeError(f"no market data returned for {len(symbols)} symbols")
        missing = [w.no_data_for(s) for s in symbols if s not in frames]
        handle.done(w.bars_summary(len(frames), len(symbols)), missing)
        return frames

    def _analyse(
        self, symbols: list[str], frames: dict[str, pd.DataFrame], trade: bool, w: Words
    ) -> list[tuple[str, dict, float, Signal]]:
        handle = self.monitor.begin(activity.ANALYSE, w.analysing(len(frames)))
        looked: list[tuple[str, dict, float, Signal]] = []
        lines: list[str] = []
        buys = sells = 0
        for index, symbol in enumerate(symbols, 1):
            history = frames.get(symbol)
            if history is None:
                continue
            self._focus = symbol
            handle.progress(f"{symbol} · {index}/{len(symbols)}")

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

            # Worked out on a closed market too, so the review says what the
            # rules would do at the open; only an open-market scan acts on it.
            signal = self.strategy.on_bar(history, position)
            if trade:
                with self._lock:
                    self._last_signal[symbol] = signal
            action = signal.action.value if signal.is_actionable else "hold"
            if action == "buy":
                buys += 1
            elif action == "close" and position is not None:
                sells += 1
            lines.append(w.analysis_line(symbol, snapshot, action))
            looked.append((symbol, snapshot, price, signal))
        self._focus = None
        handle.done(w.analysis_summary(buys, sells, trade), lines)
        return looked

    def _manage(self, symbol: str, snapshot: dict, price: float, signal: Signal, w: Words) -> bool:
        with self._lock:
            position = self._positions.get(symbol)
        if position is not None and self._protect(position, price, w):
            return False
        if not signal.is_actionable:
            return False
        return self._act(symbol, signal, snapshot, price, w)

    # ------------------------------------------------------------------ actions

    def _protect(self, position: Position, price: float, w: Words) -> bool:
        """Trail the stop behind a winner, then exit if a stop or target is hit.

        Returns True when the position was sold. A stop held at Alpaca is moved
        there; the exits themselves are left to Alpaca, which sees every trade
        rather than one price a minute, and the next look records the fill.
        """
        symbol = position.symbol
        with self._lock:
            at_broker = symbol in self._broker_stops

        old = position.stop_loss
        raised = self.risk.update_trailing_stop(position, price)
        if raised is not None:
            position.stop_loss = tick(raised)
            if at_broker:
                handle = self.monitor.begin(activity.TRAIL, w.raising_stop(symbol, old, position.stop_loss))
                try:
                    moved = self.executor.move_stop(position, position.stop_loss)
                except Exception as exc:
                    position.stop_loss = old  # the broker still has the old one
                    handle.fail(_short(exc))
                else:
                    if not moved:
                        # Its stop is gone at the broker; this PC holds it from now.
                        at_broker = False
                        with self._lock:
                            self._broker_stops.discard(symbol)
                    handle.done(w.stop_moved(moved))
            else:
                self.monitor.info(
                    activity.TRAIL, w.raising_stop(symbol, old, position.stop_loss), w.stop_moved(False)
                )
            if position.stop_loss != old:
                self.repo.save_open_position(position, self.mode, self._entry_reasons.get(symbol, ""))
                self.mentor.trailing_stop(position, position.stop_loss)

        if at_broker:
            return False
        reason = self.risk.check_protective_exit(position, price)
        if not reason:
            return False
        self.mentor.protective_exit(position, price, reason)
        self._exit(position, price, reason, w)
        return True

    def _act(self, symbol: str, signal: Signal, snapshot: dict, price: float, w: Words) -> bool:
        with self._lock:
            position = self._positions.get(symbol)
            open_count = len(self._positions)

        if signal.action is Action.CLOSE:
            if position is None:
                return False
            self._exit(position, price, signal.reason, w)
            return True

        if isinstance(self.executor, SignalExecutor) and self.executor.has_pending_for(symbol):
            return False
        # A buy already waiting on the owner (or already suggested) is not
        # re-proposed every minute while the same bar is still the latest.
        if position is None and self.proposals.has_pending_for(symbol):
            return False

        locked = self.protections.blocked(symbol)
        if position is None and locked:
            self.mentor.rejected(symbol, f"buy on '{signal.reason}'", locked)
            self.monitor.info(activity.INFO, w.not_placed(symbol, locked))
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
            self.monitor.info(
                activity.INFO, w.cap_reached(symbol, open_count, committed - open_count, max_positions)
            )
            return False

        order, rejection = self.risk.validate(
            signal, balance, position, price, symbol,
            position_pct=position_pct, atr=snapshot.get("atr"),
        )
        if order is None:
            if rejection:
                self.mentor.rejected(symbol, f"buy on '{signal.reason}'", rejection)
                self.monitor.info(activity.WARN if self.risk.is_live else activity.INFO,
                                  w.not_placed(symbol, rejection))
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
            self.monitor.info(activity.INFO, w.too_small(symbol))
            return False

        self.mentor.explain_entry(intent, snapshot, balance.total)
        self.events.publish("intent", {"intent": intent.to_dict()})

        # The autonomy gate. Signal mode already defers every order to the
        # owner, so it only applies to executors that would act on their own.
        if self.executor.is_automatic and self.autonomy != "full":
            kind = "approval" if self.autonomy == "semi" else "suggestion"
            proposal = self.proposals.add(kind, intent)
            if proposal is None:
                return False
            if kind == "approval":
                self.mentor.awaiting_approval(intent, APPROVAL_MINUTES)
                self.monitor.info(
                    activity.APPROVAL, w.waiting_approval(symbol, intent.qty, price), w.reason(intent.reason)
                )
                self.events.publish("approval_needed", {"proposal": proposal.to_dict()})
            else:
                self.mentor.suggested(intent)
                self.monitor.info(
                    activity.INFO, w.suggestion(symbol, intent.qty, price), w.reason(intent.reason)
                )
                self.events.publish("suggestion", {"proposal": proposal.to_dict()})
            return True

        headlines = self._read_news(symbol, w)
        opened, _ = self._place(intent, w)
        if opened is None:
            # Signal mode: raised for the owner to act on in Midas.
            return not self.executor.is_automatic

        self._register_position(opened, intent.reason)
        self.mentor.opened(opened, self.executor.is_automatic)
        self.events.publish(
            "trade_opened", {"position": opened.to_dict(), "reason": intent.reason}
        )
        self._explain(intent, opened, headlines, w)
        return True

    def _place(self, intent: TradeIntent, w: Words) -> tuple[Position | None, str | None]:
        """Send the order as a Live step. Returns (position, why it failed)."""
        symbol = intent.symbol
        if not self.executor.is_automatic:
            self.executor.open_position(intent)  # raises the signal for the owner
            self.mentor.awaiting_confirmation(intent)
            self.monitor.info(
                activity.ORDER, w.signal_sent(symbol, intent.qty, intent.price), w.signal_detail()
            )
            return None, None

        where = self._stop_home(intent.qty)
        handle = self.monitor.begin(
            activity.ORDER, w.placing(symbol, intent.qty, intent.stop_loss, intent.take_profit, where)
        )
        try:
            opened = self.executor.open_position(intent)
        except Exception as exc:
            handle.fail(_short(exc))
            self.mentor.rejected(symbol, "place the buy", str(exc))
            return None, str(exc)
        if opened is None:
            handle.fail(w.order_not_filled())
            return None, "the order was not filled"
        handle.done(w.filled(opened.qty, symbol, opened.entry_price, where))
        if where == "broker":
            with self._lock:
                self._broker_stops.add(symbol)
        return opened, None

    def _stop_home(self, qty: float) -> str:
        """Where a new position's stop will live: at Alpaca, on this PC, or simulated."""
        if self.executor.broker == "simulation":
            return "sim"
        if self.executor.holds_brackets and qty == int(qty):
            return "broker"
        return "pc"

    def _read_news(self, symbol: str, w: Words) -> list:
        feed = self.news
        if feed is None or not getattr(feed, "available", False):
            return []
        handle = self.monitor.begin(activity.NEWS, w.reading_news(symbol))
        try:
            headlines = feed.for_symbol(symbol, limit=3)
        except Exception as exc:
            handle.fail(_short(exc))
            return []
        handle.done(w.news_summary(len(headlines)), [f"{h.source}: {h.headline}" for h in headlines])
        return headlines

    def _explain(self, intent: TradeIntent, opened: Position, headlines: list, w: Words) -> None:
        explainer = self.explainer
        if explainer is None or not explainer.available:
            return
        facts = (
            f"Bought {opened.qty:g} {opened.symbol} at {opened.entry_price:.2f}. "
            f"Rule that fired: {intent.reason}. "
        )
        if opened.stop_loss and opened.take_profit:
            risk = abs(opened.entry_price - opened.stop_loss) * opened.qty
            facts += (
                f"Stop-loss {opened.stop_loss:.2f}, target {opened.take_profit:.2f}. "
                f"Money at risk if the stop fills: {risk:.2f} USD. "
            )
        if headlines:
            facts += "Recent headlines: " + "; ".join(f"{h.source}: {h.headline}" for h in headlines) + "."
        handle = self.monitor.begin(activity.AI, w.asking_ai())
        try:
            text = explainer.explain_entry(facts, self.language == "tr")
        except Exception as exc:
            handle.fail(_short(exc))
            return
        if not text:
            handle.fail(w.ai_silent())
            return
        handle.done(text.strip()[:700])

    def _exit(self, position: Position, price: float, reason: str, w: Words | None = None) -> bool:
        w = w or self.words()
        symbol = position.symbol
        automatic = self.executor.is_automatic
        title = w.selling(symbol, reason) if automatic else w.exit_signal(symbol, reason)
        handle = self.monitor.begin(activity.SELL, title)
        try:
            trade = self.executor.close_position(position, price, reason)
        except Exception as exc:
            handle.fail(_short(exc))
            return False

        if trade is None:
            if automatic:
                # Its bracket may already be cancelled; watch the stop here.
                with self._lock:
                    self._broker_stops.discard(symbol)
                handle.fail(w.sell_failed())
            else:
                # Signal mode: the exit is a recommendation until you confirm it.
                handle.done(w.exit_sent())
            return False

        self._record_closed(trade)
        handle.done(
            w.sold(symbol, trade.pnl), [w.fill_detail(trade.qty, trade.entry_price, trade.exit_price)]
        )
        return True

    def _record_closed(self, trade: ClosedTrade) -> None:
        """Book a finished trade: storage, risk, protections, challenge, screens."""
        with self._lock:
            self._positions.pop(trade.symbol, None)
            entry_reason = self._entry_reasons.pop(trade.symbol, "")
            self._broker_stops.discard(trade.symbol)

        self.repo.save_closed_trade(trade, self.mode, self.executor.name, entry_reason)
        self.repo.clear_open_position(trade.symbol, self.mode)
        equity = self.executor.get_balance().total
        self.risk.record_closed_trade(trade, equity)

        self.mentor.closed(trade)
        for lock in self.protections.record_trade(trade, equity):
            self.mentor.protection_lock(lock, self.protections.active_locks())
        self._credit_challenge(trade)
        if not self.risk.armed and self.risk.disarm_reason == "daily loss limit reached":
            self.mentor.kill_switch(
                self.risk.daily_realized_pnl, self.risk.daily_loss_limit(equity)
            )

        self.events.publish("trade_closed", _trade_event(trade))
        self.events.publish("status", self.status())

    def _forget_position(self, symbol: str) -> None:
        with self._lock:
            self._positions.pop(symbol, None)
            self._entry_reasons.pop(symbol, None)
            self._broker_stops.discard(symbol)
        self.repo.clear_open_position(symbol, self.mode)
        # Whatever took it away, do not buy it straight back.
        self.protections.cool_down(symbol)
        self.mentor.note(f"{symbol} is no longer in the account, so I stopped tracking it.")

    # ------------------------------------------------------------- autonomy

    def set_autonomy(self, mode: str) -> None:
        if mode not in AUTONOMY_MODES:
            raise ValueError(f"autonomy must be one of {AUTONOMY_MODES}")
        if mode == self.autonomy:
            return
        self.autonomy = mode
        # Waiting requests were raised under the old rule. Left alone, a switch
        # to manual would leave buys that can still be approved.
        self.proposals.clear_pending()
        self.mentor.autonomy_changed(mode)
        self.events.publish("status", self.status())

    def set_horizon(self, horizon: str) -> str:
        timeframe = HORIZON_TIMEFRAMES.get(horizon)
        if timeframe is None:
            raise ValueError(f"horizon must be one of {tuple(HORIZON_TIMEFRAMES)}")
        if timeframe != self.timeframe:
            with self._lock:
                self.timeframe = timeframe
                # Indicators computed on 15-minute bars mean nothing on daily ones.
                self._history.clear()
                self._snapshots.clear()
                self._last_signal.clear()
            self.proposals.clear_pending()
            self.mentor.note(f"Now reading {timeframe} candles.")
            self.scan_now()
        return timeframe

    def approve(self, proposal_id: str) -> dict:
        """The owner tapped Approve on a semi-auto buy.

        Re-checked against the market as it is now, not as it was when the
        request went out: the owner may have answered minutes later.
        """
        with self._trade_lock:
            return self._approve(proposal_id)

    def _approve(self, proposal_id: str) -> dict:
        proposal = self.proposals.take(proposal_id)
        if proposal is None:
            return {"ok": False, "message": "That request expired or was already answered."}
        intent = proposal.intent
        symbol = intent.symbol
        w = self.words()

        def fail(message: str) -> dict:
            self.proposals.finish(proposal, "failed", message)
            self.mentor.rejected(symbol, "make the buy you approved", message)
            self.monitor.info(activity.WARN, w.not_placed(symbol, message))
            self.events.publish("proposal_resolved", {"proposal": proposal.to_dict()})
            return {"ok": False, "message": f"Did not buy {symbol}: {message}."}

        if not self.clock.state().is_open:
            return fail("the market is closed")
        if self.mode == "live" and not self.risk.armed:
            return fail("live trading is not armed")

        with self._lock:
            held = symbol in self._positions
            open_count = len(self._positions)
            history = self._history.get(symbol)
        if held:
            return fail(f"I already hold {symbol}")
        _, max_positions, _ = self._effective_limits()
        if open_count + self._pending_entry_count() >= max_positions:
            return fail(f"that would exceed the {max_positions}-position cap")
        if history is None or history.empty:
            return fail("I have no current price for it")

        price = float(history["close"].iloc[-1])
        drift = abs(price - intent.price) / intent.price * 100.0
        if drift > MAX_DRIFT_PCT:
            return fail(f"the price moved {drift:.1f}% since I asked, over the {MAX_DRIFT_PCT}% limit")
        buying = intent.side is Side.BUY
        if intent.stop_loss is not None and (
            price <= intent.stop_loss if buying else price >= intent.stop_loss
        ):
            return fail("the price is already through the stop-loss")
        if intent.take_profit is not None and (
            price >= intent.take_profit if buying else price <= intent.take_profit
        ):
            return fail("the price already reached the target")

        # Filled at today's price, never the one from when the request was raised.
        opened, error = self._place(replace(intent, price=price), w)
        if opened is None:
            return fail(error or "the order was not filled")

        self._register_position(opened, intent.reason)
        self.mentor.opened(opened, True)
        self.proposals.finish(proposal, "approved")
        self.events.publish("trade_opened", {"position": opened.to_dict(), "reason": intent.reason})
        self.events.publish("proposal_resolved", {"proposal": proposal.to_dict()})
        self.events.publish("status", self.status())
        return {
            "ok": True,
            "message": f"Bought {opened.qty:g} {symbol} at {opened.entry_price:,.2f}.",
            "position": opened.to_dict(),
        }

    def skip_proposal(self, proposal_id: str) -> bool:
        proposal = self.proposals.skip(proposal_id)
        if proposal is None:
            return False
        self.events.publish("proposal_resolved", {"proposal": proposal.to_dict()})
        self.events.publish("status", self.status())
        return True

    # ---------------------------------------------- signal-mode confirmations

    def register_confirmed_entry(self, symbol: str, position: Position, reason: str) -> None:
        """Called after you confirm in Telegram that you took a signal in Midas."""
        self._register_position(position, reason)
        self.mentor.opened(position, automatic=False)
        self.events.publish("trade_opened", {"position": position.to_dict(), "reason": reason})

    def register_confirmed_exit(self, trade: ClosedTrade) -> None:
        self._record_closed(trade)

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
        """Pick up what was open last time — every stock, not only the watched ones,
        so a market switch never leaves a held position without its stop."""
        restored = 0
        for stored, reason in self.repo.load_open_positions(self.mode):
            with self._lock:
                self._positions[stored.symbol] = stored
                self._entry_reasons[stored.symbol] = reason
            self.executor.adopt_position(stored)
            restored += 1
        if restored:
            self.mentor.note(
                f"Picked up {restored} open position{'s' if restored > 1 else ''} "
                "from last session."
            )
            self.monitor.info(activity.INFO, self.words().restored(restored))

    def _scan_symbols(self) -> list[str]:
        """The watchlist plus anything held that is not on it. Call under the lock."""
        return list(self.symbols) + [s for s in self._positions if s not in self.symbols]

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
        """Shares the broker will actually accept, or 0 if the order is too small.

        When at least one whole share fits and the broker can hold a bracket,
        whole shares win even in small-account mode: rounding down never adds
        risk, and it puts the stop-loss at Alpaca instead of on this PC.
        """
        risk = self.config.risk
        if risk.fractional_shares and not (qty >= 1 and self.executor.holds_brackets):
            rounded = round(qty, 6)
        else:
            rounded = float(int(qty))
        if rounded * price < risk.min_order_value:
            return 0.0
        return rounded

    def _pending_entry_count(self) -> int:
        # Approvals hold a slot: approving them all must never exceed the cap.
        # Suggestions do not — manual mode never turns them into positions.
        waiting = len(self.proposals.pending("approval"))
        if not isinstance(self.executor, SignalExecutor):
            return waiting
        return waiting + sum(1 for s in self.executor.pending_signals() if not s.is_exit)

    def _pending_signal_dicts(self) -> list[dict]:
        if not isinstance(self.executor, SignalExecutor):
            return []
        return [s.to_dict() for s in self.executor.pending_signals()]


def _closed_delay(market) -> float:
    """Sleep while closed, but wake in time for the open."""
    seconds = getattr(market, "seconds_until_open", None)
    if seconds is None:
        return CLOSED_MARKET_SLEEP
    return max(5.0, min(float(CLOSED_MARKET_SLEEP), seconds + 2.0))


def _short(exc: BaseException) -> str:
    """An error as one readable line for the Live tab."""
    text = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
    return text[:240]


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
