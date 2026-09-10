from __future__ import annotations

import argparse
import logging
import os
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.catalysts.manager import CatalystManager
from app.catalysts.news import NewsFeed
from app.challenge.manager import ChallengeManager
from app.common.events import EventBus
from app.common.logging_config import setup_logging
from app.config import APP_NAME, LOG_DIR, Settings, load_settings
from app.data.base import MarketDataSource
from app.data.yahoo import YahooData
from app.engine.portfolio_engine import PortfolioEngine
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
from app.research.analyst import Analyst
from app.research.service import ResearchService
from app.research.user_profile import ProfileStore
from app.research.yahoo_research import YahooResearch
from app.web.server import WebServer, create_app

log = logging.getLogger(__name__)


def build_data_source(settings: Settings) -> MarketDataSource:
    secrets = settings.secrets
    if secrets.alpaca_api_key and secrets.alpaca_api_secret:
        from app.data.alpaca_data import AlpacaData

        return AlpacaData(secrets.alpaca_api_key, secrets.alpaca_api_secret)
    # No keys: free public candles. This is what makes signal mode work on day one.
    return YahooData()


def build_executor(settings: Settings, events: EventBus) -> Executor:
    mode = settings.app.mode
    secrets = settings.secrets
    starting = settings.app.risk.starting_paper_balance

    if mode == "signal":
        return SignalExecutor(events=events, starting_balance=starting)

    if mode == "paper":
        return PaperExecutor(starting_balance=starting)

    if not (secrets.alpaca_api_key and secrets.alpaca_api_secret):
        raise SystemExit(
            "Live mode needs ALPACA_API_KEY and ALPACA_API_SECRET in .env.\n"
            "Copy config/.env.example to .env and fill them in, or switch to\n"
            "  mode: signal   (Midas — the bot tells you what to trade)\n"
            "  mode: paper    (simulated money, no account needed)"
        )
    from app.execution.alpaca_executor import AlpacaExecutor

    return AlpacaExecutor(
        secrets.alpaca_api_key, secrets.alpaca_api_secret, paper=secrets.alpaca_paper
    )


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
    args = parser.parse_args()

    setup_logging(LOG_DIR)
    settings = load_settings()
    if args.mode:
        settings.app.mode = args.mode

    events = EventBus()
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

    data = build_data_source(settings)
    executor = build_executor(settings, events)
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
    )

    catalysts = CatalystManager(session_factory, events)
    news = NewsFeed(settings.secrets.alpaca_api_key, settings.secrets.alpaca_api_secret)

    # Company research runs off its own free provider and its own daily candles,
    # so it keeps working in signal mode where no brokerage is connected at all.
    research = ResearchService(YahooResearch(), YahooData(), timeframe="1d")
    analyst = Analyst(claude)
    profiles = ProfileStore(settings.user_profile_path)

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
        research, analyst, profiles,
    )
    web = WebServer(api, settings.app.web.host, settings.app.web.port)
    web.start()

    suffix = f"?token={token}" if token else ""
    phone_url = f"http://{lan_ip()}:{settings.app.web.port}/{suffix}"
    _print_banner(settings, web.local_url + "/" + suffix, phone_url, telegram, claude, data)

    engine.start()

    if args.headless:
        try:
            engine._thread.join()
        except KeyboardInterrupt:
            pass
        finally:
            engine.stop()
            telegram.stop()
            web.stop()
        return

    from PySide6.QtWidgets import QApplication

    from app.gui.main_window import MainWindow

    qt_app = QApplication(sys.argv)
    qt_app.setQuitOnLastWindowClosed(False)

    window = MainWindow(engine, f"{web.local_url}/{suffix}", phone_url)
    window.show()

    exit_code = qt_app.exec()
    engine.stop()
    telegram.stop()
    web.stop()
    sys.exit(exit_code)


def _print_banner(
    settings: Settings,
    desktop_url: str,
    phone_url: str,
    telegram: TelegramNotifier,
    claude: AIMentor,
    data: MarketDataSource,
) -> None:
    app = settings.app
    mode_note = {
        "signal": "analysis only — you place the trades in Midas",
        "paper": "simulated money on real prices",
        "live": "REAL MONEY (still needs arming in the dashboard)",
    }[app.mode]

    print(f"\n  {APP_NAME} — US stocks, {app.timeframe}")
    print(f"  Mode     : {app.mode} — {mode_note}")
    print(f"  Data     : {data.name}")
    print(f"  Watching : {', '.join(app.watchlist)}")
    print(f"  Desktop  : {desktop_url}")
    print(f"  Phone    : {phone_url}")
    print(f"  Telegram : {'on' if telegram.enabled else 'off (set TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_IDS)'}")
    print(f"  Mentor   : {'Claude' if claude.available else 'rule-based (set ANTHROPIC_API_KEY for more)'}")
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
