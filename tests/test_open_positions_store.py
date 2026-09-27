"""Open positions survive restarts per money mode, and old databases upgrade."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from app.common.models import Position, Side
from app.storage.db import create_session_factory
from app.storage.repository import Repository


def _position(symbol="AAPL", qty=2.0):
    return Position(symbol, Side.BUY, qty, 100.0, datetime(2026, 9, 25, 14, 30, tzinfo=timezone.utc), 97.0, 106.0)


def test_practice_and_real_money_can_hold_the_same_stock(tmp_path):
    repo = Repository(create_session_factory(tmp_path / "t.db"))
    repo.save_open_position(_position(qty=2), "paper", "practice")
    repo.save_open_position(_position(qty=1), "live", "real")

    paper, _ = repo.load_open_position("AAPL", "paper")
    live, _ = repo.load_open_position("AAPL", "live")
    assert (paper.qty, live.qty) == (2, 1)

    repo.clear_open_position("AAPL", "live")
    assert repo.load_open_position("AAPL", "paper")[0] is not None
    assert repo.load_open_position("AAPL", "live")[0] is None


def test_loaded_times_carry_a_zone_so_they_compare_with_broker_times(tmp_path):
    repo = Repository(create_session_factory(tmp_path / "t.db"))
    repo.save_open_position(_position(), "paper")

    (position, _), = repo.load_open_positions("paper")
    assert position.opened_at.tzinfo is not None
    assert position.opened_at < datetime.now(timezone.utc)


def test_an_old_database_is_upgraded_without_losing_rows(tmp_path):
    path = tmp_path / "old.db"
    db = sqlite3.connect(path)
    db.execute(
        """CREATE TABLE open_positions (
            id INTEGER NOT NULL, mode VARCHAR(8) NOT NULL, symbol VARCHAR(24) NOT NULL,
            side VARCHAR(8) NOT NULL, qty FLOAT NOT NULL, entry_price FLOAT NOT NULL,
            stop_loss FLOAT, take_profit FLOAT, entry_reason VARCHAR(200) NOT NULL,
            opened_at DATETIME NOT NULL, PRIMARY KEY (id), UNIQUE (symbol))"""
    )
    db.execute(
        "INSERT INTO open_positions VALUES (1, 'paper', 'MSFT', 'buy', 3, 400, 390, 420, 'old', '2026-09-20 15:00:00')"
    )
    db.commit()
    db.close()

    repo = Repository(create_session_factory(path))
    repo.save_open_position(_position("MSFT", 1), "live")

    assert repo.load_open_position("MSFT", "paper")[0].qty == 3
    assert repo.load_open_position("MSFT", "live")[0].qty == 1
