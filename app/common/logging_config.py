from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

_SECRET_PATTERNS = [
    re.compile(r"(?i)\b(api[_-]?key|api[_-]?secret|secret|token|signature)\b\s*[=:]\s*\S+"),
    # Telegram bot tokens ("123456789:AA...") ride inside every Bot API URL.
    # The part after the colon contains _ and -, so the generic rule below
    # never matched it and the token was written to the log in full.
    # No leading \b: in the URL it follows "bot" directly ("/bot123456:AA..."),
    # and there is no word boundary between "t" and "1".
    re.compile(r"(?<!\d)\d{6,}:[A-Za-z0-9_-]{30,}"),
    # Prefixed provider keys: Groq gsk_..., Anthropic sk-ant-..., OpenAI-style sk-...
    re.compile(r"\b(?:gsk|sk-ant|sk)[-_][A-Za-z0-9_-]{16,}"),
    re.compile(r"\b[A-Za-z0-9]{40,}\b"),
]


class RedactingFilter(logging.Filter):
    """Strips anything that looks like an API key or secret out of log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for pattern in _SECRET_PATTERNS:
            message = pattern.sub("[REDACTED]", message)
        record.msg = message
        record.args = ()
        return True


def setup_logging(log_dir: Path, level: int = logging.INFO) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(
        "%(asctime)s  %(levelname)-7s  %(name)-24s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    redactor = RedactingFilter()

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    console.addFilter(redactor)

    file_handler = RotatingFileHandler(
        log_dir / "bot.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(redactor)

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(console)
    root.addHandler(file_handler)

    # httpx/httpcore log every request URL at INFO — for Telegram that is the
    # bot token itself, every few seconds. Redaction catches it now, but there
    # is no reason to write those lines at all.
    for noisy in ("urllib3", "websockets", "uvicorn.access", "asyncio", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
