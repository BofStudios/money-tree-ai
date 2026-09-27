from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.storage.models import Base, OpenPositionRow


def create_session_factory(db_path: Path) -> sessionmaker[Session]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    Base.metadata.create_all(engine)
    _migrate_open_positions(engine)
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def _migrate_open_positions(engine) -> None:
    """Older databases allowed one open row per symbol across every mode, so a
    live buy silently erased the paper position in the same stock. Rebuild the
    table with the (mode, symbol) key, keeping every row."""
    with engine.begin() as conn:
        row = conn.exec_driver_sql(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='open_positions'"
        ).fetchone()
        if row is None or "UNIQUE (symbol)" not in (row[0] or ""):
            return
        columns = "id, mode, symbol, side, qty, entry_price, stop_loss, take_profit, entry_reason, opened_at"
        conn.exec_driver_sql("ALTER TABLE open_positions RENAME TO open_positions_old")
        OpenPositionRow.__table__.create(conn)
        conn.exec_driver_sql(
            f"INSERT INTO open_positions ({columns}) SELECT {columns} FROM open_positions_old"
        )
        conn.exec_driver_sql("DROP TABLE open_positions_old")
