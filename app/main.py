from __future__ import annotations

import multiprocessing

if __name__ == "__main__":
    # The swarm's bots are separate processes. In the exe each one starts as a
    # copy of it: hand those straight to multiprocessing, before the heavy
    # imports below, so a bot loads only what it needs.
    multiprocessing.freeze_support()

import argparse
import logging
import os
import socket
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.catalysts.manager import CatalystManager
from app.catalysts.news import NewsFeed
from app.challenge.manager import ChallengeManager
from app.common import activity
from app.common.activity import Monitor
from app.common.events import EventBus
from app.common.keystore import KeyStore
from app.common.logging_config import setup_logging
from app.common.restart import Restarter, relaunch, relaunched
from app.config import APP_NAME, KEYSTORE_PATH, LOG_DIR, Settings, load_settings
from app.data.base import MarketDataSource
from app.data.yahoo import YahooData
from app.engine.markets import watchlist_for
from app.engine.portfolio_engine import PortfolioEngine
from app.engine.words import Words
from app.execution.base import Executor
from app.execution.paper_executor import PaperExecutor
from app.execution.signal_executor import SignalExecutor
from app.mentor.ai import AIMentor
from app.mentor.narrator import Narrator
from app.notify.telegram_bot import TelegramNotifier
from app.risk.risk_manager import RiskManager
from app.storage.db import create_session_factory
from app.storage.repository import Repository
from app.strategy.ema_rsi import EmaRsiStrategy
from app.engine.autonomy import HORIZON_TIMEFRAMES, resolve_autonomy
from app.research.analyst import Analyst
from app.research.service import ResearchService
from app.research.user_profile import ProfileStore
from app.research.yahoo_research import YahooResearch
from app.web.server import WebServer, create_app
from app.brain.brain import Brain
from app.brain.sources import AlpacaNews, SecClient, Wikipedia, make_asset_check
from app.brain.words import BrainWords
from app.config import DATA_DIR

log = logging.getLogger(__name__)


# A warning for the Live tab, written once the owner's language is known.
Notice = Callable[[Words], str]


def probe_alpaca(key: str, secret: str, paper: bool) -> str | None:
    """Why Alpaca refuses these keys, or None when they work or it cannot be reached.

    Only a clear refusal counts: offline or a hiccup keeps the keys, and the
    engine's steps show the failures until the connection is back.
    """
    try:
        from alpaca.trading.client import TradingClient

        TradingClient(key, secret, paper=paper).get_account()
        return None
    except Exception as exc:
        try:
            status = getattr(exc, "status_code", None)
        except Exception:
            status = None
        if status in (401, 403):
            return f"HTTP {status}"
        log.warning("could not check the Alpaca keys at startup: %s", exc)
        return None


@dataclass
class Brokerage:
    """What startup settled on: the executor, and what to tell the owner."""

    executor: Executor
    notice: Notice | None = None
    keys: tuple[str, str] | None = None           # the pair Alpaca accepted
    refused: dict[str, str] = field(default_factory=dict)  # "paper"/"live" -> why


def build_executor(settings: Settings, events: EventBus) -> Brokerage:
    """The executor for the money mode.

    signal — Midas: the bot only tells you what to trade.
    paper  — Alpaca's paper account when its keys are saved, else a local simulation.
    live   — Alpaca's live account. Without working live keys it falls back to the
             simulation and says so: nothing real can happen without them.
    """
    mode = settings.app.mode
    secrets = settings.secrets
    starting = settings.app.risk.starting_paper_balance

    if mode == "signal":
        return Brokerage(SignalExecutor(events=events, starting_balance=starting))

    live = mode == "live"
    account = "live" if live else "paper"
    key, secret = secrets.alpaca_keys(live)
    choice = Brokerage(PaperExecutor(starting_balance=starting))
    if key and secret:
        problem = probe_alpaca(key, secret, paper=not live)
        if problem is None:
            from app.execution.alpaca_executor import AlpacaExecutor

            return Brokerage(AlpacaExecutor(key, secret, paper=not live), keys=(key, secret))
        choice.refused[account] = problem
        choice.notice = lambda w: w.keys_refused(live, problem)
    elif live:
        choice.notice = lambda w: w.live_without_keys()

    if live:
        settings.app.mode = "paper"
    return choice


def data_keys(settings: Settings, choice: Brokerage) -> tuple[str, str] | None:
    """Keys for prices and news: the ones that just worked, else any saved pair
    that Alpaca has not already refused."""
    if choice.keys:
        return choice.keys
    for live in (False, True):
        if ("live" if live else "paper") in choice.refused:
            continue
        key, secret = settings.secrets.alpaca_keys(live)
        if key and secret:
            return key, secret
    return None


def build_data_source(keys: tuple[str, str] | None) -> MarketDataSource:
    if keys:
        from app.data.alpaca_data import AlpacaData
        from app.data.fallback import FallbackData

        # Yahoo fills whatever Alpaca leaves out, including everything when the keys fail.
        return FallbackData(AlpacaData(*keys), YahooData())
    # No keys: free public candles. This is what makes signal mode work on day one.
    return YahooData()


def lan_ip() -> str:
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("8.8.8.8", 80))
        return probe.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        probe.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=f"{APP_NAME} — US stocks")
    parser.add_argument("--headless", action="store_true", help="run without the desktop window")
    parser.add_argument("--mode", choices=["signal", "paper", "live"], default=None)
    parser.add_argument("--no-telegram", action="store_true")
    parser.add_argument("--host", default=None, help="bind address (default from config: all interfaces)")
    parser.add_argument("--port", type=int, default=None, help="dashboard port (default from config)")
    args = parser.parse_args()

    setup_logging(LOG_DIR)
    settings = load_settings()
    if args.mode:
        settings.app.mode = args.mode
    if args.host:
        settings.app.web.host = args.host
    if args.port:
        settings.app.web.port = args.port

    events = EventBus()
    monitor = Monitor(events)
    keystore = KeyStore(KEYSTORE_PATH)
    restarter = Restarter()
    mentor = Narrator(settings.app.mentor, events)
    claude = AIMentor(
        settings.app.mentor, settings.secrets.mentor_keys, settings.mentor_memory_path
    )

    strategy_config = settings.app.strategy
    strategy = EmaRsiStrategy(
        fast_ema=strategy_config.fast_ema,
        slow_ema=strategy_config.slow_ema,
        rsi_period=strategy_config.rsi_period,
        rsi_overbought=strategy_config.rsi_overbought,
        rsi_oversold=strategy_config.rsi_oversold,
    )

    brokerage = build_executor(settings, events)
    executor, notice = brokerage.executor, brokerage.notice
    keys = data_keys(settings, brokerage)
    data = build_data_source(keys)
    session_factory = create_session_factory(settings.db_path)
    repo = Repository(session_factory)
    risk = RiskManager(settings.app.risk, mode=settings.app.mode)
    challenges = ChallengeManager(
        config=settings.app.challenge,
        risk=settings.app.risk,
        session_factory=session_factory,
        events=events,
        mode=settings.app.mode,
    )

    engine = PortfolioEngine(
        config=settings.app,
        data=data,
        executor=executor,
        strategy=strategy,
        risk=risk,
        repo=repo,
        events=events,
        mentor=mentor,
        challenges=challenges,
        monitor=monitor,
    )

    catalysts = CatalystManager(session_factory, events)
    news = NewsFeed(*(keys or ("", "")))
    engine.news = news
    engine.explainer = claude
    brain = build_brain(engine, data, keys, claude, monitor, events, risk, mentor)

    # Company research runs off its own free provider and its own daily candles,
    # so it keeps working in signal mode where no brokerage is connected at all.
    research = ResearchService(YahooResearch(), YahooData(), timeframe="1d")
    analyst = Analyst(claude)
    profiles = ProfileStore(settings.user_profile_path)

    # The onboarding answers change what the bot does, so apply them before the
    # first scan. An unanswered question keeps the config's behaviour, except
    # that real money never defaults to buying without asking.
    chosen = profiles.get()
    engine.set_language(chosen.language)
    engine.set_autonomy(resolve_autonomy(chosen.autonomy, settings.app.mode))
    if chosen.trading_horizon in HORIZON_TIMEFRAMES:
        engine.set_horizon(chosen.trading_horizon)
    market = watchlist_for(chosen.market)
    if market:
        engine.set_watchlist(market)
    engine.config.risk.fractional_shares = chosen.small_account
    if notice:
        monitor.info(activity.WARN, notice(Words(chosen.language == "tr")))

    telegram = TelegramNotifier(
        token="" if args.no_telegram else settings.secrets.telegram_bot_token,
        allowed_chat_ids=settings.secrets.allowed_chat_ids,
        config=settings.app.telegram,
        engine=engine,
        events=events,
        claude=claude,
        catalysts=catalysts,
    )
    if settings.app.telegram.enabled:
        telegram.start()

    token = settings.secrets.dashboard_token
    api = create_app(
        engine, repo, mentor, claude, events, token, settings, catalysts, news,
        research, analyst, profiles, keystore=keystore, restarter=restarter,
        key_problems=brokerage.refused,
    )
    web = WebServer(api, settings.app.web.host, settings.app.web.port)
    web.start()

    suffix = f"?token={token}" if token else ""
    phone_url = f"http://{lan_ip()}:{settings.app.web.port}/{suffix}"
    _print_banner(settings, executor, web.local_url + "/" + suffix, phone_url, telegram, claude, data)

    engine.start()
    brain.start()

    if args.headless:
        if not brain.settings.warned:
            print(f"  Brain    : {brain.settings.bots} strategy bots in parallel processes — this can use a lot of RAM and CPU.")
        restarter.on_request(engine.stop)
        try:
            while engine.running:
                engine.join(1.0)
        except KeyboardInterrupt:
            pass
        finally:
            brain.stop()
            engine.stop()
            telegram.stop()
            web.stop()
        if restarter.requested.is_set():
            web.join(5.0)
            relaunch()
        return

    from PySide6.QtWidgets import QApplication

    from app.gui.main_window import MainWindow

    qt_app = QApplication(sys.argv)
    qt_app.setQuitOnLastWindowClosed(False)

    from app.gui.warning import power_warning
    if not brain.settings.warned and not relaunched():
        choice = power_warning(brain.settings.bots, chosen.language == "tr")
        if choice is None:
            brain.stop()
            engine.stop()
            telegram.stop()
            web.stop()
            sys.exit(0)
        bots, power, remember = choice
        brain.apply_settings({"bots": bots, "power": power, "warned": remember})

    window = MainWindow(engine, f"{web.local_url}/{suffix}", phone_url, events)
    restarter.on_request(window.restart_requested.emit)
    window.show()

    exit_code = qt_app.exec()
    brain.stop()
    engine.stop()
    telegram.stop()
    web.stop()
    if restarter.requested.is_set():
        web.join(5.0)
        relaunch()
        exit_code = 0
    sys.exit(exit_code)


def build_brain(engine, data, keys, claude, monitor, events, risk, mentor) -> Brain:
    """The research desk and the swarm, wired to the engine. Reads without keys
    too (SEC, Wikipedia); news and discovery need Alpaca's."""
    brain = Brain(
        DATA_DIR / "brain", data,
        sec=SecClient(), news=AlpacaNews(*keys) if keys else None, wiki=Wikipedia(), ai=claude,
        asset_check=make_asset_check(*keys) if keys else None,
        latest_price=getattr(data, "get_quote", None), monitor=monitor,
    )
    brain.symbols_fn = engine.watched_symbols
    brain.timeframe_fn = lambda: engine.timeframe
    brain.turkish_fn = lambda: engine.language == "tr"
    brain.risk_fn = lambda: (risk.config.min_stop_pct, risk.config.max_stop_pct)

    def promoted(p) -> None:
        w = BrainWords(engine.language == "tr")
        monitor.info("learn", w.promotion_title(p), None, w.promotion_text(p).splitlines())
        events.publish("brain_promotion", {"title": w.promotion_title(p), "text": w.promotion_text(p)})
        engine.scan_now()

    def found(d: dict) -> None:
        w = BrainWords(engine.language == "tr")
        events.publish("brain_found", {"title": w.discovered(d["symbol"], d["name"], d["decision"], d["score"], d["mentions"])})

    brain.on_promotion = promoted
    brain.swarm.on_promotion = promoted
    brain.on_found = found
    engine.brain = brain
    return brain


def _print_banner(
    settings: Settings,
    executor: Executor,
    desktop_url: str,
    phone_url: str,
    telegram: TelegramNotifier,
    claude: AIMentor,
    data: MarketDataSource,
) -> None:
    app = settings.app
    mode_note = {
        "signal": "analysis only — you place the trades in Midas",
        "simulation": "simulated money on real prices",
        "alpaca_paper": "Alpaca paper account — practice money",
        "alpaca_live": "REAL MONEY at Alpaca (still needs arming in the dashboard)",
    }.get(executor.broker, app.mode)

    print(f"\n  {APP_NAME} — US stocks, {app.timeframe}")
    print(f"  Mode     : {app.mode} — {mode_note}")
    print(f"  Data     : {data.name}")
    print(f"  Watching : {', '.join(app.watchlist)}")
    print(f"  Desktop  : {desktop_url}")
    print(f"  Phone    : {phone_url}")
    print(f"  Telegram : {'on' if telegram.enabled else 'off (set TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_IDS)'}")
    ai = claude.backend
    print(f"  AI       : {ai['provider'] + ' · ' + ai['model'] if ai['available'] else 'rule-based (connect a free Groq key in Settings)'}")
    if not settings.secrets.dashboard_token:
        print("  Warning  : no DASHBOARD_TOKEN — anyone on your Wi-Fi can control the bot.")
    print()


def _ensure_streams() -> None:
    """Give the app real stdout/stderr even in a windowed exe.

    PyInstaller's --noconsole build sets both to None, so any print() or
    StreamHandler blows up with AttributeError on a NoneType.
    """
    devnull = None
    for name in ("stdout", "stderr"):
        if getattr(sys, name, None) is None:
            devnull = devnull or open(os.devnull, "w", encoding="utf-8")
            setattr(sys, name, devnull)


def _run() -> None:
    """Entry point that never dies silently.

    A --noconsole exe has nowhere to print a traceback, so a crash shows an
    unhelpful dialog and nothing else. Write it to a file beside the exe and
    say where it went.
    """
    try:
        _ensure_streams()
        main()
    except SystemExit:
        raise
    except BaseException:
        import traceback

        report = traceback.format_exc()
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            crash = LOG_DIR / "crash.log"
            crash.write_text(report, encoding="utf-8")
            where = str(crash)
        except Exception:
            where = "(could not write the log)"

        print(report, file=sys.stderr)
        if getattr(sys, "frozen", False):
            try:
                from PySide6.QtWidgets import QApplication, QMessageBox

                app = QApplication.instance() or QApplication([])
                QMessageBox.critical(
                    None, f"{APP_NAME} could not start",
                    f"{report.strip().splitlines()[-1]}\n\nFull details:\n{where}",
                )
            except Exception:
                pass
        raise SystemExit(1)


if __name__ == "__main__":
    _run()
