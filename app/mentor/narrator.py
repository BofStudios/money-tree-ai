from __future__ import annotations

import logging
import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone

from app.common.events import EventBus
from app.common.market_clock import MarketState
from app.common.models import ClosedTrade, Position, TradeIntent
from app.config import MentorConfig

log = logging.getLogger(__name__)

# Levels double as colour keys in the dashboard terminal.
THINK = "think"
SCAN = "scan"
SIGNAL = "signal"
ACTION = "action"
WARN = "warn"
RESULT = "result"


@dataclass
class MentorLine:
    timestamp: datetime
    level: str
    text: str
    symbol: str | None = None

    def to_dict(self) -> dict:
        return {
            "time": self.timestamp.isoformat(),
            "clock": self.timestamp.astimezone().strftime("%H:%M:%S"),
            "level": self.level,
            "symbol": self.symbol,
            "text": self.text,
        }


class Narrator:
    """Explains what the bot is doing, in plain English, as it happens.

    Every sentence is built from measured state that was passed in. The mentor
    is not allowed to speculate about prices or invent numbers — if a value is
    missing it says so rather than filling the gap.
    """

    def __init__(self, config: MentorConfig, events: EventBus) -> None:
        self.config = config
        self.events = events
        self._lines: deque[MentorLine] = deque(maxlen=config.max_lines)
        self._lock = threading.Lock()

    # --------------------------------------------------------------------- feed

    def say(self, level: str, text: str, symbol: str | None = None) -> MentorLine:
        line = MentorLine(datetime.now(timezone.utc), level, text, symbol)
        with self._lock:
            self._lines.append(line)
        self.events.publish("mentor", {"line": line.to_dict()})
        return line

    def lines(self, limit: int = 200) -> list[dict]:
        with self._lock:
            return [line.to_dict() for line in list(self._lines)[-limit:]]

    @property
    def _chatty(self) -> bool:
        return self.config.verbosity == "chatty"

    @property
    def _quiet(self) -> bool:
        return self.config.verbosity == "quiet"

    # ------------------------------------------------------------------ moments

    def boot(self, mode: str, symbols: list[str], timeframe: str, executor: str) -> None:
        opening = {
            "paper": "The bot started with practice money. The prices are real. The money is not real.",
            "live": f"The bot started with REAL money. It trades through {executor}.",
        }.get(mode, f"The bot started in {mode} mode.")
        self.say(THINK, opening)
        self.say(
            THINK,
            f"The bot monitors {len(symbols)} stocks on the {timeframe} chart: {', '.join(symbols)}.",
        )

    def market_state(self, state: MarketState) -> None:
        if state.is_open:
            self.say(THINK, f"The US market is open ({state.countdown_text()}). The bot starts to examine the stocks.")
        else:
            self.say(
                THINK,
                f"The US market is closed ({state.countdown_text()}). "
                "The bot keeps the charts current. It does not trade until the open.",
            )

    def scan_start(self, count: int, timeframe: str) -> None:
        if self._quiet:
            return
        self.say(SCAN, f"The bot examines {count} stocks on the {timeframe} chart.")

    def observe(self, symbol: str, snapshot: dict, position: Position | None) -> None:
        if not self._chatty:
            return
        self.say(SCAN, self.describe(symbol, snapshot, position), symbol)

    def describe(self, symbol: str, snapshot: dict, position: Position | None) -> str:
        """One honest sentence about where a symbol stands right now."""
        if not snapshot.get("ready"):
            return f"{symbol}: only {snapshot.get('bars', 0)} bars. The bot needs more data."

        price = snapshot["price"]
        fast, slow = snapshot["fast_ema"], snapshot["slow_ema"]
        spread = snapshot["spread_pct"]
        rsi_value = snapshot.get("rsi")
        bars = snapshot.get("bars_since_cross", 0)

        trend_words = (
            f"EMA{snapshot['fast_period']} {fast:,.2f} is "
            f"{'above' if spread >= 0 else 'below'} EMA{snapshot['slow_period']} {slow:,.2f} "
            f"({spread:+.2f}%)"
        )
        age = f" for {bars} bars" if bars else ", crossed on this bar"
        rsi_words = f"RSI {rsi_value:.0f}" if rsi_value is not None else "RSI not ready"

        if position is not None:
            pnl = position.unrealized_pnl_pct
            return (
                f"{symbol} at {price:,.2f}. The bot holds it from {position.entry_price:,.2f} "
                f"({pnl:+.2f}%). {trend_words}{age}. {rsi_words}."
            )
        return f"{symbol} at {price:,.2f}. {trend_words}{age}. {rsi_words}."

    def considering(self, symbol: str, reason: str, snapshot: dict) -> None:
        rsi_value = snapshot.get("rsi")
        # The strategy's reason often already quotes RSI; do not say it twice.
        needs_rsi = rsi_value is not None and "rsi" not in reason.lower()
        rsi_words = f" RSI is at {rsi_value:.0f}." if needs_rsi else ""
        self.say(SIGNAL, f"{symbol}: buy signal. Reason: {reason}.{rsi_words}", symbol)

    def explain_entry(self, intent: TradeIntent, snapshot: dict, equity: float) -> None:
        share = (intent.notional / equity * 100) if equity else 0.0
        self.say(
            ACTION,
            f"{intent.symbol}: size {intent.qty:g} at {intent.price:,.2f}. "
            f"Cost: ${intent.notional:,.2f}. That is {share:.1f}% of ${equity:,.2f}.",
            intent.symbol,
        )
        if intent.stop_loss and intent.take_profit:
            self.say(
                ACTION,
                f"{intent.symbol}: stop-loss {intent.stop_loss:,.2f}. Target "
                f"{intent.take_profit:,.2f}. Risk: ${intent.risk_amount:,.2f}. Possible gain: "
                f"${intent.reward_amount:,.2f} ({intent.reward_risk:.1f}:1).",
                intent.symbol,
            )
        atr_pct = snapshot.get("atr_pct")
        if atr_pct:
            self.say(
                THINK,
                f"{intent.symbol} moves approximately {atr_pct:.2f}% a bar now. The "
                f"{abs(intent.price - (intent.stop_loss or intent.price)) / intent.price * 100:.2f}% "
                "stop is approximately "
                f"{abs(intent.price - (intent.stop_loss or intent.price)) / (snapshot['atr'] or 1):.1f} "
                "bars of normal movement away.",
                intent.symbol,
            )

    def rejected(self, symbol: str, wanted: str, rejection: str) -> None:
        self.say(WARN, f"{symbol}: the bot did not {wanted}. Reason: {rejection}.", symbol)

    def opened(self, position: Position, automatic: bool) -> None:
        verb = "Done. The bot bought" if automatic else "The bot monitors"
        self.say(
            RESULT,
            f"{verb} {position.qty:g} {position.symbol} at {position.entry_price:,.2f}.",
            position.symbol,
        )

    def awaiting_approval(self, intent: TradeIntent, minutes: int) -> None:
        self.say(
            SIGNAL,
            f"The bot wants to buy {intent.qty:g} {intent.symbol} at approximately {intent.price:,.2f}. "
            f"Semi-auto is on. Press Approve to buy. "
            f"The request stops after {minutes} minutes.",
            intent.symbol,
        )

    def suggested(self, intent: TradeIntent) -> None:
        self.say(
            SIGNAL,
            f"Idea: buy {intent.qty:g} {intent.symbol} at approximately {intent.price:,.2f} "
            f"({intent.reason}). Manual is on. The bot does not buy.",
            intent.symbol,
        )

    def autonomy_changed(self, mode: str) -> None:
        text = {
            "full": "Full auto is on. The bot buys and sells without approval.",
            "semi": "Semi-auto is on. The bot asks before each buy. Sales and stop-losses stay automatic.",
            "manual": (
                "Manual is on. The bot does not buy. It only shows its ideas. "
                "Open positions keep their stop-loss."
            ),
        }.get(mode, mode)
        self.say(ACTION, text)

    def protective_exit(self, position: Position, price: float, reason: str) -> None:
        self.say(
            WARN,
            f"{position.symbol} touched its {reason} at {price:,.2f}. "
            f"The buy price was {position.entry_price:,.2f}. The bot sells.",
            position.symbol,
        )

    def closed(self, trade: ClosedTrade) -> None:
        verdict = "Gain" if trade.pnl >= 0 else "Loss"
        self.say(
            RESULT,
            f"Done. {trade.symbol} closed at {trade.exit_price:,.2f}. {verdict}: "
            f"${abs(trade.pnl):,.2f} ({trade.pnl_pct:+.2f}%). Reason: {trade.exit_reason}.",
            trade.symbol,
        )

    def scan_summary(self, scanned: int, holding: int, signals: int, equity: float) -> None:
        if self._quiet:
            return
        if signals:
            tail = f"Signals: {signals}."
        else:
            tail = "No action is necessary."
        self.say(
            SCAN,
            f"Done. Stocks examined: {scanned}. Positions: {holding}. {tail} Equity: ${equity:,.2f}.",
        )

    def challenge_started(self, state, odds: dict) -> None:
        needed = odds.get("winning_trades_needed")
        self.say(
            ACTION,
            f"New run: ${state.stake:,.2f} to ${state.target:,.2f}. The bot uses all "
            f"of the run money on one position at a time. The run stops at "
            f"${state.bust_floor:,.2f}.",
        )
        if needed:
            self.say(
                THINK,
                f"At +{odds['take_profit_pct']:.0f}% a win, the run needs approximately "
                f"{needed} wins and no losses. Each loss moves it back. "
                "The chance is small.",
            )

    def challenge_progress(self, state) -> None:
        self.say(
            RESULT,
            f"Run: ${state.value:,.2f} of ${state.target:,.2f} "
            f"({state.progress_pct:.0f}%). Trades: {state.trades}.",
        )

    def challenge_won(self, state) -> None:
        self.say(
            RESULT,
            f"Done. The run is complete: ${state.stake:,.2f} became ${state.value:,.2f}. "
            f"Trades: {state.trades}. The bot reached the target.",
        )

    def challenge_lost(self, state) -> None:
        self.say(
            WARN,
            f"The run stopped. The run money fell to ${state.value:,.2f}. "
            f"The limit was ${state.bust_floor:,.2f}. Trades: {state.trades}.",
        )

    def trailing_stop(self, position: Position, new_stop: float) -> None:
        if self._quiet:
            return
        locked_in = (new_stop - position.entry_price) * position.qty
        tail = (
            f" The stop now keeps ${locked_in:,.2f} of gain."
            if locked_in > 0
            else " It is below the buy price, but nearer."
        )
        self.say(
            THINK,
            f"{position.symbol} went up. The bot moved the stop-loss up to {new_stop:,.2f}.{tail}",
            position.symbol,
        )

    def protection_lock(self, reason: str, locks: list[dict]) -> None:
        minutes = max((l.get("minutes_left", 0) for l in locks), default=0)
        self.say(
            WARN,
            f"The bot stops new buys for approximately {minutes} minutes. Reason: {reason}. "
            "Open positions keep their stop-loss.",
        )

    def kill_switch(self, realised: float, limit: float) -> None:
        self.say(
            WARN,
            f"The daily loss limit is reached: -${abs(realised):,.2f}. The limit is ${limit:,.2f}. "
            "Real-money trades stop for the rest of the day.",
        )

    def error(self, what: str, detail: str) -> None:
        self.say(WARN, f"{what} failed: {detail}. The bot tries again.")

    def note(self, text: str) -> None:
        self.say(THINK, text)
