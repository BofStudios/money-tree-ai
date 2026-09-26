"""The "still up" ping has one job: make silence meaningful, and never claim
the bot is healthy when it is up but not actually working."""
from __future__ import annotations

from app.config import TelegramConfig
from app.notify.formatting import heartbeat_message

BASE = {
    "mode": "paper",
    "equity": 10_000.0,
    "positions": [],
    "running": True,
    "market": {"is_open": False},
    "last_error": None,
}


def test_a_healthy_bot_says_so_with_uptime():
    text = heartbeat_message(BASE, 6 * 3600 + 12 * 60)

    assert "still up" in text
    assert "6h 12m" in text
    assert "Engine is stopped" not in text


def test_short_uptime_reads_in_minutes():
    assert "5m" in heartbeat_message(BASE, 5 * 60 + 20)


def test_a_stopped_engine_is_not_reported_as_fine():
    text = heartbeat_message({**BASE, "running": False}, 60)

    assert "Engine is stopped" in text


def test_the_last_error_is_surfaced():
    text = heartbeat_message({**BASE, "last_error": "broker timeout"}, 60)

    assert "broker timeout" in text


def test_heartbeat_defaults_on_and_can_be_switched_off():
    assert TelegramConfig().heartbeat_hours == 6.0
    assert TelegramConfig(heartbeat_hours=0).heartbeat_hours == 0
