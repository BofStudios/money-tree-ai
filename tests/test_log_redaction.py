"""Secrets must never reach a log line, in any of the shapes they arrive in.

The fake values below are shaped like the real thing but are not real keys.
"""
from __future__ import annotations

import logging

from app.common.logging_config import RedactingFilter


def redact(message: str) -> str:
    record = logging.LogRecord("t", logging.INFO, __file__, 1, message, (), None)
    RedactingFilter().filter(record)
    return record.msg


def test_a_telegram_bot_token_inside_a_url_is_removed():
    # Assembled at runtime so the repo never contains a token-shaped literal
    # for secret scanners to flag. It is not a real token.
    token = "1234567890:" + "AAF" + "abcdefghij_klmnopqrs-tuvwxyz01234"
    line = redact(f'POST https://api.telegram.org/bot{token}/getUpdates "HTTP/1.1 200 OK"')

    assert token not in line
    assert "AAFabcdef" not in line
    assert "getUpdates" in line  # the useful part of the line survives


def test_a_groq_key_is_removed():
    key = "gsk_" + "Ab1" * 17
    assert key[4:20] not in redact(f"using key {key}")


def test_an_anthropic_key_is_removed():
    key = "sk-ant-api03-" + "x9_Y" * 10
    assert "x9_Yx9_Y" not in redact(f"client created with {key}")


def test_key_equals_value_is_removed():
    assert "hunter2abc" not in redact("api_key=hunter2abc")


def test_ordinary_lines_are_left_alone():
    line = "Scanned 8, holding 0. Nothing worth acting on. Equity $10,000.00."
    assert redact(line) == line
