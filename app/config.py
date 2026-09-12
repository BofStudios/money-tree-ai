from __future__ import annotations

import sys
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_NAME = "Money Tree AI"

FROZEN = getattr(sys, "frozen", False)

# Two different roots once packaged as an exe:
#   PROJECT_ROOT — the folder beside the exe, holding editable config/, .env, data/
#   BUNDLE_ROOT  — PyInstaller's unpacked payload, holding static/ and assets/
PROJECT_ROOT = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent.parent
BUNDLE_ROOT = Path(getattr(sys, "_MEIPASS", PROJECT_ROOT))

CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
LOG_DIR = PROJECT_ROOT / "logs"
ASSETS = BUNDLE_ROOT / "assets"

ExecutionMode = Literal["signal", "paper", "live"]


def write_secret(key: str, value: str) -> None:
    """Set one line in .env, in place, without disturbing the rest of the file.

    Used when the owner pastes an API key from Settings instead of editing .env
    by hand. Only ever touches the single matching line (or appends one) — never
    rewrites the whole file, so comments and unrelated entries survive.
    """
    path = PROJECT_ROOT / ".env"
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []

    prefix = f"{key}="
    for i, line in enumerate(lines):
        if line.startswith(prefix):
            lines[i] = f"{key}={value}"
            break
    else:
        lines.append(f"{key}={value}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class Secrets(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Alpaca — only needed for paper/live execution. Signal mode works without it.
    alpaca_api_key: str = ""
    alpaca_api_secret: str = ""
    alpaca_paper: bool = True

    # Telegram — from @BotFather. Leave empty to run without Telegram.
    telegram_bot_token: str = ""
    telegram_chat_ids: str = ""

    # Optional: upgrades the mentor from rule-based to a real language model.
    # Any one of these is enough; Ollama needs none of them at all.
    gemini_api_key: str = ""      # free tier, aistudio.google.com
    groq_api_key: str = ""        # free tier, console.groq.com
    anthropic_api_key: str = ""   # paid

    dashboard_token: str = ""

    @property
    def mentor_keys(self) -> dict[str, str]:
        """Keyed the way the provider builders expect them."""
        return {
            "gemini": self.gemini_api_key,
            "groq": self.groq_api_key,
            "anthropic": self.anthropic_api_key,
        }

    @property
    def allowed_chat_ids(self) -> set[int]:
        ids = set()
        for part in self.telegram_chat_ids.replace(" ", "").split(","):
            if part:
                try:
                    ids.add(int(part))
                except ValueError:
                    continue
        return ids


class StrategyConfig(BaseModel):
    name: str = "ema_rsi"
    fast_ema: int = 12
    slow_ema: int = 26
    rsi_period: int = 14
    rsi_overbought: float = 70.0
    rsi_oversold: float = 30.0
    atr_period: int = 14


class TrailingConfig(BaseModel):
    """Freqtrade's trailing stop: hold the original stop until the trade is up
    by `activate_at_pct`, then follow the peak `trail_pct` behind it."""

    enabled: bool = True
    activate_at_pct: float = Field(default=2.0, gt=0)
    trail_pct: float = Field(default=1.0, gt=0)


class RiskConfig(BaseModel):
    starting_paper_balance: float = 10_000.0
    max_position_pct: float = Field(default=20.0, gt=0, le=100)
    stop_loss_pct: float = Field(default=2.0, gt=0)
    take_profit_pct: float = Field(default=4.0, gt=0)
    max_daily_loss_pct: float = Field(default=5.0, gt=0)
    max_open_positions: int = Field(default=3, ge=1)
    # Whole shares cannot express a $5 bankroll against a $300 stock, so
    # fractional sizing is on by default. Alpaca supports it on US equities.
    fractional_shares: bool = True
    min_order_value: float = Field(default=1.0, gt=0)

    # How the stop distance is chosen. "atr" scales it to how much the symbol
    # actually moves; "percent" is the flat stop_loss_pct above.
    stop_mode: Literal["atr", "percent"] = "atr"
    atr_period: int = Field(default=14, ge=2)
    atr_multiple: float = Field(default=1.5, gt=0)
    # Caps so a quiet or wild symbol cannot produce an absurd stop.
    min_stop_pct: float = Field(default=0.8, gt=0)
    max_stop_pct: float = Field(default=6.0, gt=0)
    reward_risk: float = Field(default=2.0, gt=0)

    # "risk" fixes the cash lost if the stop hits and derives the share count
    # from the stop distance — the stop comes first, size is the output.
    # "fixed" keeps the older max_position_pct behaviour.
    sizing: Literal["risk", "fixed"] = "risk"
    # Sized so the risk rule is what actually binds: with a ~3% stop this asks for
    # roughly 17% of equity, under max_position_pct. Set it much higher and the
    # position cap takes over and risk sizing stops doing anything.
    risk_per_trade_pct: float = Field(default=0.5, gt=0, le=100)

    trailing: TrailingConfig = TrailingConfig()


class ProtectionsConfig(BaseModel):
    """Locks borrowed from Freqtrade, aimed at whipsaw and losing streaks."""

    enabled: bool = True
    # No re-entry on a symbol straight after closing it.
    cooldown_minutes: int = Field(default=30, ge=0)
    # Stop everything for a while after a run of stop-outs.
    stoploss_guard_lookback_minutes: int = Field(default=240, ge=0)
    stoploss_guard_trades: int = Field(default=3, ge=1)
    stoploss_guard_stop_minutes: int = Field(default=120, ge=0)
    # Stop everything if the recent equity curve falls too far from its peak.
    max_drawdown_lookback_trades: int = Field(default=20, ge=2)
    max_drawdown_pct: float = Field(default=15.0, gt=0)
    max_drawdown_stop_minutes: int = Field(default=240, ge=0)


class ChallengeConfig(BaseModel):
    """A small bankroll the bot tries to grow to a target."""

    enabled: bool = True
    presets: list[float] = [1.0, 5.0, 10.0, 25.0, 50.0, 100.0]
    multipliers: list[float] = [1.5, 2.0, 3.0, 5.0]
    default_stake: float = 5.0
    default_multiplier: float = 2.0
    # A tiny bankroll cannot be diversified, so it rides one position at a time.
    position_pct: float = Field(default=100.0, gt=0, le=100)
    max_open_positions: int = Field(default=1, ge=1)
    # Ends the run once the bankroll has fallen this far from the stake.
    bust_drawdown_pct: float = Field(default=50.0, gt=0, le=100)


class MentorConfig(BaseModel):
    enabled: bool = True
    verbosity: Literal["quiet", "normal", "chatty"] = "normal"
    max_lines: int = 400
    # Which model answers. "auto" takes the first provider that works, trying the
    # free ones before the paid one so nobody is billed for a default.
    provider: Literal["auto", "ollama", "gemini", "groq", "anthropic"] = "auto"
    # Leave empty to use whatever that provider's own default model is.
    model: str = ""
    # Turns of chat kept and resent — the API is stateless, so this is the memory.
    memory_turns: int = Field(default=12, ge=0)


class TelegramConfig(BaseModel):
    enabled: bool = True
    push_signals: bool = True
    push_fills: bool = True
    push_mentor: bool = False  # mentor chatter can be noisy on a phone
    daily_summary: bool = True


class WebConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8765


class AppConfig(BaseModel):
    # signal = analyse only, you place the trade in Midas yourself
    # paper   = Alpaca paper account, simulated money
    # live    = Alpaca live account, real money (still requires arming)
    mode: ExecutionMode = "signal"
    market: Literal["us_stocks"] = "us_stocks"
    watchlist: list[str] = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "SPY"]
    timeframe: str = "15m"
    scan_interval_seconds: int = 60

    strategy: StrategyConfig = StrategyConfig()
    risk: RiskConfig = RiskConfig()
    protections: ProtectionsConfig = ProtectionsConfig()
    challenge: ChallengeConfig = ChallengeConfig()
    mentor: MentorConfig = MentorConfig()
    telegram: TelegramConfig = TelegramConfig()
    web: WebConfig = WebConfig()

    @property
    def is_signal_mode(self) -> bool:
        return self.mode == "signal"


class Settings(BaseModel):
    app: AppConfig
    secrets: Secrets

    @property
    def db_path(self) -> Path:
        return DATA_DIR / "trading.db"

    @property
    def mentor_memory_path(self) -> Path:
        return DATA_DIR / "mentor_memory.json"

    @property
    def user_profile_path(self) -> Path:
        return DATA_DIR / "user_profile.json"


def load_settings(config_path: Path | None = None) -> Settings:
    path = config_path or (CONFIG_DIR / "config.yaml")
    if not path.exists():
        path = CONFIG_DIR / "config.example.yaml"

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    DATA_DIR.mkdir(exist_ok=True)
    LOG_DIR.mkdir(exist_ok=True)
    return Settings(app=AppConfig(**raw), secrets=Secrets())
