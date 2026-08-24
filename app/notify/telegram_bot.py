from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import InvalidToken
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from app.common.events import EventBus
from app.common.models import Position, Side
from app.config import TelegramConfig
from app.engine.portfolio_engine import PortfolioEngine
from app.execution.signal_executor import SignalExecutor
from app.mentor.ai import AIMentor
from app.notify import formatting as fmt

log = logging.getLogger(__name__)

MENU_COMMANDS = [
    ("status", "Equity, market state, open positions"),
    ("run", "The current run — stake, target, progress"),
    ("catalysts", "Upcoming events you are trading around"),
    ("remember", "Tell me something to keep in mind — /remember ..."),
    ("positions", "What I am holding right now"),
    ("watchlist", "Every symbol and where it stands"),
    ("pnl", "Win rate and totals"),
    ("signals", "Signals waiting on your answer"),
    ("chart", "Where one symbol stands — /chart AAPL"),
    ("close", "Close a position now — /close AAPL"),
    ("disarm", "Stop live orders immediately"),
    ("help", "All commands"),
]

HELP = """*Money Tree AI commands*

/status — equity, market state, open positions
/run — the current run: stake, target, progress
/catalysts — upcoming events you are trading around
/remember TEXT — keep this in mind from now on
/memory — everything you have told me to remember
/forget N — drop remembered item number N
/positions — what I am holding right now
/watchlist — every symbol and where it stands
/pnl — win rate and totals
/signals — signals waiting on your answer
/chart SYMBOL — where one symbol stands
/add SYMBOL — add to the watchlist
/remove SYMBOL — drop from the watchlist
/close SYMBOL — close a position now
/arm — allow live orders (live mode only)
/disarm — stop live orders immediately
/equity AMOUNT — tell me your real Midas balance
/help — this message

You can also just talk to me. Ask "why did you buy NVDA" or
"how are we doing today" and I will answer from what I can see."""


class TelegramNotifier:
    """Phone side of the bot: alerts you, and lets you talk back.

    Runs its own asyncio loop on a background thread so it never blocks the
    trading engine.
    """

    def __init__(
        self,
        token: str,
        allowed_chat_ids: set[int],
        config: TelegramConfig,
        engine: PortfolioEngine,
        events: EventBus,
        claude: AIMentor,
        catalysts=None,
    ) -> None:
        self.token = token
        self.allowed = allowed_chat_ids
        self.config = config
        self.engine = engine
        self.events = events
        self.claude = claude
        self.catalysts = catalysts

        self._app: Application | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._signal_messages: dict[str, tuple[int, int]] = {}

        events.subscribe(self._on_event)

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.allowed)

    # ---------------------------------------------------------------- lifecycle

    def start(self) -> None:
        if not self.enabled:
            log.info("telegram disabled (no token or no allowed chat ids)")
            return
        self._thread = threading.Thread(target=self._run, name="telegram", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._loop and self._app:
            asyncio.run_coroutine_threadsafe(self._shutdown(), self._loop)

    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        self._app = Application.builder().token(self.token).build()
        self._register_handlers(self._app)

        try:
            self._loop.run_until_complete(self._serve())
        except InvalidToken:
            log.error(
                "Telegram rejected the bot token. Check TELEGRAM_BOT_TOKEN in .env — "
                "it should look like 123456789:AA... exactly as @BotFather sent it. "
                "Everything else keeps running without Telegram."
            )
        except Exception:
            log.exception("telegram bot stopped unexpectedly")

    async def _serve(self) -> None:
        app = self._app
        await app.initialize()
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        # Registers the "/" menu in Telegram so the commands are discoverable.
        try:
            await app.bot.set_my_commands(MENU_COMMANDS)
        except Exception:
            log.debug("could not set the command menu", exc_info=True)
        log.info("telegram bot listening")
        await self.broadcast("Bot is up. Send /help to see what I can do.")
        while True:
            await asyncio.sleep(3600)

    async def _shutdown(self) -> None:
        try:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
        except Exception:
            log.debug("telegram shutdown error", exc_info=True)

    def _register_handlers(self, app: Application) -> None:
        app.add_handler(CommandHandler(["start", "help"], self._cmd_help))
        app.add_handler(CommandHandler("status", self._cmd_status))
        app.add_handler(CommandHandler("run", self._cmd_run))
        app.add_handler(CommandHandler("catalysts", self._cmd_catalysts))
        app.add_handler(CommandHandler("remember", self._cmd_remember))
        app.add_handler(CommandHandler("memory", self._cmd_memory))
        app.add_handler(CommandHandler("forget", self._cmd_forget))
        app.add_handler(CommandHandler("positions", self._cmd_positions))
        app.add_handler(CommandHandler("watchlist", self._cmd_watchlist))
        app.add_handler(CommandHandler("pnl", self._cmd_pnl))
        app.add_handler(CommandHandler("signals", self._cmd_signals))
        app.add_handler(CommandHandler("chart", self._cmd_chart))
        app.add_handler(CommandHandler("add", self._cmd_add))
        app.add_handler(CommandHandler("remove", self._cmd_remove))
        app.add_handler(CommandHandler("close", self._cmd_close))
        app.add_handler(CommandHandler("arm", self._cmd_arm))
        app.add_handler(CommandHandler("disarm", self._cmd_disarm))
        app.add_handler(CommandHandler("equity", self._cmd_equity))
        app.add_handler(CallbackQueryHandler(self._on_button))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._on_text))

    # ------------------------------------------------------------------- guards

    def _allowed(self, update: Update) -> bool:
        chat = update.effective_chat
        if chat is None:
            return False
        if chat.id in self.allowed:
            return True
        log.warning("ignored telegram message from unapproved chat %s", chat.id)
        return False

    # ----------------------------------------------------------------- commands

    async def _cmd_help(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            await update.message.reply_text(
                f"This bot is private. Your chat id is {update.effective_chat.id} — "
                "add it to TELEGRAM_CHAT_IDS in .env if it is yours."
            )
            return
        await update.message.reply_text(HELP, parse_mode=ParseMode.MARKDOWN)

    async def _cmd_status(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            return
        await update.message.reply_text(
            fmt.status_message(self.engine.status()), parse_mode=ParseMode.MARKDOWN
        )

    async def _cmd_run(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            return
        await update.message.reply_text(
            fmt.run_message(self.engine.status().get("challenge")),
            parse_mode=ParseMode.MARKDOWN,
        )

    async def _cmd_catalysts(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            return
        rows = [] if self.catalysts is None else [c.to_dict() for c in self.catalysts.all()]
        await update.message.reply_text(
            fmt.catalysts_message(rows), parse_mode=ParseMode.MARKDOWN
        )

    async def _cmd_remember(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            return
        text = " ".join(context.args or "").strip()
        if not text:
            await update.message.reply_text("Give me something to remember, like /remember I trade in Midas.")
            return
        try:
            self.claude.memory.remember(text)
        except ValueError as exc:
            await update.message.reply_text(str(exc))
            return
        await update.message.reply_text("Noted. I will keep that in mind from now on.")

    async def _cmd_memory(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            return
        await update.message.reply_text(
            fmt.memory_message(self.claude.memory.facts()), parse_mode=ParseMode.MARKDOWN
        )

    async def _cmd_forget(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            return
        try:
            # Shown to the owner as a 1-based list, stored as a 0-based one.
            index = int((context.args or ["?"])[0]) - 1
        except ValueError:
            await update.message.reply_text("Which one? Use /memory to see the numbers.")
            return
        if not self.claude.memory.forget(index):
            await update.message.reply_text("There is no item with that number.")
            return
        await update.message.reply_text("Forgotten.")

    async def _cmd_positions(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            return
        await update.message.reply_text(
            fmt.positions_message(self.engine.status()["positions"]),
            parse_mode=ParseMode.MARKDOWN,
        )

    async def _cmd_watchlist(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            return
        await update.message.reply_text(
            fmt.watchlist_message(self.engine.watchlist_rows()), parse_mode=ParseMode.MARKDOWN
        )

    async def _cmd_pnl(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            return
        stats = self.engine.repo.trade_stats(self.engine.mode)
        await update.message.reply_text(
            fmt.stats_message(stats), parse_mode=ParseMode.MARKDOWN
        )

    async def _cmd_signals(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            return
        pending = self.engine.status().get("pending_signals", [])
        if not pending:
            await update.message.reply_text("Nothing waiting on you.")
            return
        for signal in pending:
            await update.message.reply_text(
                fmt.signal_message(signal),
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=_signal_buttons(signal["id"]),
            )

    async def _cmd_chart(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            return
        if not context.args:
            await update.message.reply_text("Usage: /chart AAPL")
            return
        symbol = context.args[0].upper()
        rows = {r["symbol"]: r for r in self.engine.watchlist_rows()}
        row = rows.get(symbol)
        if row is None or not row.get("ready"):
            await update.message.reply_text(f"I have no readings for {symbol} yet.")
            return

        await update.message.reply_text(
            self.engine.mentor.describe(
                symbol, self.engine.snapshot_for(symbol), self.engine.position_for(symbol)
            )
        )

    async def _cmd_add(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            return
        if not context.args:
            await update.message.reply_text("Usage: /add NVDA")
            return
        symbol = context.args[0].upper()
        ok = self.engine.add_symbol(symbol)
        await update.message.reply_text(
            f"Watching {symbol} now." if ok else f"{symbol} is already on the list."
        )

    async def _cmd_remove(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            return
        if not context.args:
            await update.message.reply_text("Usage: /remove NVDA")
            return
        symbol = context.args[0].upper()
        ok = self.engine.remove_symbol(symbol)
        await update.message.reply_text(
            f"Dropped {symbol}."
            if ok
            else f"Cannot drop {symbol} — it is not on the list, or I am holding it."
        )

    async def _cmd_close(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            return
        if not context.args:
            await update.message.reply_text("Usage: /close AAPL")
            return
        symbol = context.args[0].upper()
        ok = self.engine.close_position_now(symbol, "closed from Telegram")
        await update.message.reply_text(
            f"Closing {symbol}." if ok else f"No open position in {symbol}."
        )

    async def _cmd_arm(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            return
        if self.engine.mode != "live":
            await update.message.reply_text(
                f"Arming only matters in live mode. I am in {self.engine.mode} mode."
            )
            return
        await update.message.reply_text(
            "*Arm live trading?*\n\nI will place real orders with real money.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(
                [[
                    InlineKeyboardButton("Yes, arm it", callback_data="arm:yes"),
                    InlineKeyboardButton("Cancel", callback_data="arm:no"),
                ]]
            ),
        )

    async def _cmd_disarm(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            return
        self.engine.disarm("disarmed from Telegram")
        await update.message.reply_text("Disarmed. No further live orders.")

    async def _cmd_equity(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            return
        executor = self.engine.executor
        if not isinstance(executor, SignalExecutor):
            await update.message.reply_text(
                "I read the balance from the broker in this mode, so there is nothing to set."
            )
            return
        if not context.args:
            await update.message.reply_text("Usage: /equity 5000")
            return
        try:
            amount = float(context.args[0].replace(",", ""))
        except ValueError:
            await update.message.reply_text("That did not look like a number.")
            return
        executor.set_declared_equity(amount)
        await update.message.reply_text(
            f"Got it — sizing positions against ${amount:,.2f} from now on."
        )

    # ------------------------------------------------------------------ buttons

    async def _on_button(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()
        if not self._allowed(update):
            return

        action, _, payload = query.data.partition(":")

        if action == "arm":
            if payload == "yes":
                self.engine.arm()
                await query.edit_message_text("Live trading is ARMED.")
            else:
                await query.edit_message_text("Cancelled. Still disarmed.")
            return

        if action in ("taken", "skipped"):
            await self._resolve_signal(query, action, payload)

    async def _resolve_signal(self, query, action: str, signal_id: str) -> None:
        executor = self.engine.executor
        if not isinstance(executor, SignalExecutor):
            await query.edit_message_text("Signals are not used in this mode.")
            return

        if action == "skipped":
            executor.confirm_skipped(signal_id)
            await query.edit_message_text(f"{query.message.text}\n\n— Skipped.")
            return

        pending = {s.id: s for s in executor.pending_signals()}
        signal = pending.get(signal_id)
        if signal is None:
            await query.edit_message_text(f"{query.message.text}\n\n— No longer available.")
            return

        if signal.is_exit:
            position = self.engine.position_for(signal.intent.symbol)
            executor.confirm_taken(signal_id, signal.intent.price)
            if position is not None:
                from app.execution.signal_executor import _build_trade

                trade = _build_trade(position, signal.intent.price, signal.intent.reason)
                self.engine.register_confirmed_exit(trade)
                await query.edit_message_text(
                    f"{query.message.text}\n\n— Done. {fmt.signed(trade.pnl)} "
                    f"({fmt.signed(trade.pnl_pct)}%)."
                )
                return
            await query.edit_message_text(f"{query.message.text}\n\n— Marked closed.")
            return

        executor.confirm_taken(signal_id, signal.intent.price)
        position = Position(
            symbol=signal.intent.symbol,
            side=signal.intent.side,
            qty=signal.intent.qty,
            entry_price=signal.intent.price,
            opened_at=datetime.now(timezone.utc),
            stop_loss=signal.intent.stop_loss,
            take_profit=signal.intent.take_profit,
            current_price=signal.intent.price,
        )
        self.engine.register_confirmed_entry(
            signal.intent.symbol, position, signal.intent.reason
        )
        await query.edit_message_text(
            f"{query.message.text}\n\n— Tracking it. I will tell you when to get out."
        )

    # --------------------------------------------------------------- free text

    async def _on_text(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            return
        question = (update.message.text or "").strip()
        if not question:
            return

        quick = self._quick_answer(question)
        if quick:
            await update.message.reply_text(quick, parse_mode=ParseMode.MARKDOWN)
            return

        await update.effective_chat.send_action("typing")
        context = self.engine.mentor_context()
        answer = await asyncio.to_thread(self.claude.answer, question, context)

        if answer:
            await update.message.reply_text(answer)
            return
        await update.message.reply_text(
            "I answer free-text questions only when a Claude API key is set in .env.\n\n"
            "Without it I still handle every command — try /status, /positions, "
            "/watchlist or /pnl."
        )

    def _quick_answer(self, question: str) -> str | None:
        """Handle the obvious questions locally, before spending an API call."""
        lowered = question.lower()
        status = self.engine.status()

        if any(word in lowered for word in ("status", "how are we", "what's up", "durum")):
            return fmt.status_message(status)
        if "position" in lowered or "holding" in lowered:
            return fmt.positions_message(status["positions"])
        if "watchlist" in lowered or "watching" in lowered:
            return fmt.watchlist_message(self.engine.watchlist_rows())
        if "win rate" in lowered or lowered.strip() in ("pnl", "p&l", "performance"):
            return fmt.stats_message(self.engine.repo.trade_stats(self.engine.mode))
        return None

    # -------------------------------------------------------------- outbound

    def broadcast_sync(self, text: str, markup=None) -> None:
        if not (self._loop and self._app):
            return
        asyncio.run_coroutine_threadsafe(self.broadcast(text, markup), self._loop)

    async def broadcast(self, text: str, markup=None) -> None:
        for chat_id in self.allowed:
            try:
                await self._app.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=markup,
                )
            except Exception:
                log.warning("could not message chat %s", chat_id, exc_info=True)

    def _on_event(self, event: dict) -> None:
        """Engine-thread callback. Must not block."""
        if not self.enabled or self._loop is None:
            return
        kind = event.get("type")

        if kind == "signal_raised" and self.config.push_signals:
            signal = event["signal"]
            self.broadcast_sync(
                fmt.signal_message(signal), _signal_buttons(signal["id"])
            )
        elif kind == "trade_opened" and self.config.push_fills:
            position = event["position"]
            self.broadcast_sync(
                f"*Opened {position['symbol']}*\n\n"
                f"{position['qty']:g} @ `{fmt.money(position['entry_price'])}`\n"
                f"Stop `{fmt.money(position['stop_loss'])}` · "
                f"Target `{fmt.money(position['take_profit'])}`\n"
                f"_{event.get('reason', '')}_"
            )
        elif kind == "trade_closed" and self.config.push_fills:
            self.broadcast_sync(fmt.trade_closed_message(event))
        elif kind == "catalyst" and event.get("event") == "window_open":
            self.broadcast_sync(fmt.catalyst_window_message(event["catalyst"]))
        elif kind == "challenge" and event.get("event") in ("started", "won", "lost"):
            self.broadcast_sync(
                fmt.challenge_event_message(
                    event["challenge"], event["event"], event.get("reason", "")
                )
            )
        elif kind == "mentor" and self.config.push_mentor:
            line = event["line"]
            if line["level"] in ("signal", "action", "warn", "result"):
                self.broadcast_sync(f"`{line['clock']}` {line['text']}")


def _signal_buttons(signal_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("Taken", callback_data=f"taken:{signal_id}"),
            InlineKeyboardButton("Skipped", callback_data=f"skipped:{signal_id}"),
        ]]
    )
