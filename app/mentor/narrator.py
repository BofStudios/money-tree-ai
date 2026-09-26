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
            "signal": "Waking up in signal mode — I do the analysis, you place the trades.",
            "paper": "Waking up in paper mode — real prices, simulated money.",
            "live": f"Waking up in live mode, trading through {executor}.",
        }.get(mode, f"Waking up in {mode} mode.")
        self.say(THINK, opening)
        self.say(
            THINK,
            f"Watching {len(symbols)} symbols on the {timeframe} chart: {', '.join(symbols)}.",
        )
        if mode == "signal":
            self.say(
                THINK,
                "I will not place any orders. When I find something I will tell you "
                "exactly what to enter in Midas, and you decide.",
            )

    def market_state(self, state: MarketState) -> None:
        if state.is_open:
            self.say(THINK, f"US market is open, {state.countdown_text()}. Starting to scan.")
        else:
            self.say(
                THINK,
                f"US market is closed ({state.countdown_text()}). "
                "I will keep the charts fresh and wait rather than trade a dead tape.",
            )

    def scan_start(self, count: int, timeframe: str) -> None:
        if self._quiet:
            return
        self.say(SCAN, f"Scanning {count} symbols on {timeframe}...")

    def observe(self, symbol: str, snapshot: dict, position: Position | None) -> None:
        if not self._chatty:
            return
        self.say(SCAN, self.describe(symbol, snapshot, position), symbol)

    def describe(self, symbol: str, snapshot: dict, position: Position | None) -> str:
        """One honest sentence about where a symbol stands right now."""
        if not snapshot.get("ready"):
            return f"{symbol}: only {snapshot.get('bars', 0)} bars so far, still warming up."

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
        age = f", holding for {bars} bars" if bars else ", just crossed"
        rsi_words = f"RSI {rsi_value:.0f}" if rsi_value is not None else "RSI not ready"

        if position is not None:
            pnl = position.unrealized_pnl_pct
            return (
                f"{symbol} at {price:,.2f} — holding from {position.entry_price:,.2f} "
                f"({pnl:+.2f}%). {trend_words}{age}. {rsi_words}."
            )
        return f"{symbol} at {price:,.2f} — {trend_words}{age}. {rsi_words}."

    def considering(self, symbol: str, reason: str, snapshot: dict) -> None:
        rsi_value = snapshot.get("rsi")
        # The strategy's reason often already quotes RSI; do not say it twice.
        needs_rsi = rsi_value is not None and "rsi" not in reason.lower()
        rsi_words = f" RSI is at {rsi_value:.0f}." if needs_rsi else ""
        self.say(SIGNAL, f"{symbol} caught my eye: {reason}.{rsi_words}", symbol)

    def explain_entry(self, intent: TradeIntent, snapshot: dict, equity: float) -> None:
        share = (intent.notional / equity * 100) if equity else 0.0
        self.say(
            ACTION,
            f"{intent.symbol}: sizing {intent.qty:g} at {intent.price:,.2f} "
            f"= ${intent.notional:,.2f}, {share:.1f}% of ${equity:,.2f} equity.",
            intent.symbol,
        )
        if intent.stop_loss and intent.take_profit:
            self.say(
                ACTION,
                f"{intent.symbol}: stop {intent.stop_loss:,.2f}, target "
                f"{intent.take_profit:,.2f}. Risking ${intent.risk_amount:,.2f} to make "
                f"${intent.reward_amount:,.2f} — {intent.reward_risk:.1f}:1.",
                intent.symbol,
            )
        atr_pct = snapshot.get("atr_pct")
        if atr_pct:
            self.say(
                THINK,
                f"{intent.symbol} is moving about {atr_pct:.2f}% a bar right now, so a "
                f"{abs(intent.price - (intent.stop_loss or intent.price)) / intent.price * 100:.2f}% "
                "stop is roughly "
                f"{abs(intent.price - (intent.stop_loss or intent.price)) / (snapshot['atr'] or 1):.1f} "
                "bars of normal movement away.",
                intent.symbol,
            )

    def rejected(self, symbol: str, wanted: str, rejection: str) -> None:
        self.say(WARN, f"{symbol}: wanted to {wanted} but {rejection}.", symbol)

    def opened(self, position: Position, automatic: bool) -> None:
        verb = "Opened" if automatic else "Tracking"
        self.say(
            RESULT,
            f"{verb} {position.qty:g} {position.symbol} at {position.entry_price:,.2f}.",
            position.symbol,
        )

    def awaiting_confirmation(self, intent: TradeIntent) -> None:
        self.say(
            SIGNAL,
            f"Sent you the {intent.symbol} signal. Place it in Midas and tell me the "
            "fill price, or skip it — I will track it either way.",
            intent.symbol,
        )

    def awaiting_approval(self, intent: TradeIntent, minutes: int) -> None:
        self.say(
            SIGNAL,
            f"I want to buy {intent.qty:g} {intent.symbol} at about {intent.price:,.2f}. "
            f"You are on semi-auto, so I am waiting for your Approve — the request "
            f"lapses in {minutes} minutes if you do not answer.",
            intent.symbol,
        )

    def suggested(self, intent: TradeIntent) -> None:
        self.say(
            SIGNAL,
            f"I would buy {intent.qty:g} {intent.symbol} at about {intent.price:,.2f} "
            f"({intent.reason}). You are on manual, so I am not placing it.",
            intent.symbol,
        )

    def autonomy_changed(self, mode: str) -> None:
        text = {
            "full": "Full auto: I will buy and sell on my own.",
            "semi": "Semi-auto: I will ask before every buy. Sells and stops stay automatic.",
            "manual": (
                "Manual: I will not open anything new, only tell you what I see. "
                "Anything already open keeps its stop-loss."
            ),
        }.get(mode, mode)
        self.say(ACTION, text)

    def protective_exit(self, position: Position, price: float, reason: str) -> None:
        self.say(
            WARN,
            f"{position.symbol} hit its {reason} at {price:,.2f} "
            f"(entry was {position.entry_price:,.2f}). Getting out.",
            position.symbol,
        )

    def closed(self, trade: ClosedTrade) -> None:
        verdict = "Made" if trade.pnl >= 0 else "Lost"
        self.say(
            RESULT,
            f"{trade.symbol} closed at {trade.exit_price:,.2f} — {verdict} "
            f"${abs(trade.pnl):,.2f} ({trade.pnl_pct:+.2f}%) on {trade.exit_reason}.",
            trade.symbol,
        )

    def scan_summary(self, scanned: int, holding: int, signals: int, equity: float) -> None:
        if self._quiet:
            return
        if signals:
            tail = f"{signals} signal{'s' if signals > 1 else ''} raised."
        else:
            tail = "Nothing worth acting on."
        self.say(
            SCAN,
            f"Scanned {scanned}, holding {holding}. {tail} Equity ${equity:,.2f}.",
        )

    def challenge_started(self, state, odds: dict) -> None:
        needed = odds.get("winning_trades_needed")
        self.say(
            ACTION,
            f"New run: ${state.stake:,.2f} to ${state.target:,.2f}. I put the whole "
            f"bankroll on one position at a time, and stop if it falls to "
            f"${state.bust_floor:,.2f}.",
        )
        if needed:
            self.say(
                THINK,
                f"Straight maths: at +{odds['take_profit_pct']:.0f}% a win, that is about "
                f"{needed} winning trades with no losers in between. Losses set it back, "
                "so treat this as a long shot, not a plan.",
            )

    def challenge_progress(self, state) -> None:
        self.say(
            RESULT,
            f"Run at ${state.value:,.2f} of ${state.target:,.2f} "
            f"({state.progress_pct:.0f}%) after {state.trades} trades.",
        )

    def challenge_won(self, state) -> None:
        self.say(
            RESULT,
            f"Run finished: ${state.stake:,.2f} reached ${state.value:,.2f} in "
            f"{state.trades} trades. Target hit.",
        )

    def challenge_lost(self, state) -> None:
        self.say(
            WARN,
            f"Run over: the bankroll fell to ${state.value:,.2f}, through the "
            f"${state.bust_floor:,.2f} floor, after {state.trades} trades. Stopping here.",
        )

    def trailing_stop(self, position: Position, new_stop: float) -> None:
        if self._quiet:
            return
        locked_in = (new_stop - position.entry_price) * position.qty
        tail = (
            f" That locks in ${locked_in:,.2f}."
            if locked_in > 0
            else " Still below entry, but closer."
        )
        self.say(
            THINK,
            f"{position.symbol} moved up, so I raised the stop to {new_stop:,.2f}.{tail}",
            position.symbol,
        )

    def protection_lock(self, reason: str, locks: list[dict]) -> None:
        minutes = max((l.get("minutes_left", 0) for l in locks), default=0)
        self.say(
            WARN,
            f"Pausing new entries — {reason}. Nothing new for about {minutes} minutes. "
            "Open positions are still managed.",
        )

    def kill_switch(self, realised: float, limit: float) -> None:
        self.say(
            WARN,
            f"Daily loss limit hit: down ${abs(realised):,.2f} against a ${limit:,.2f} "
            "cap. Disarming live trading for the rest of the day.",
        )

    def error(self, what: str, detail: str) -> None:
        self.say(WARN, f"{what} failed: {detail}. I will retry.")

    def note(self, text: str) -> None:
        self.say(THINK, text)
