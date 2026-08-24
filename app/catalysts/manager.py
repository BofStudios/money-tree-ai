from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.common.events import EventBus
from app.storage.models import CatalystRow

log = logging.getLogger(__name__)

WATCHING = "watching"   # too early, just tracking the date
ARMED = "armed"         # inside the entry window
HOLDING = "holding"     # you took the position
CLOSED = "closed"
DROPPED = "dropped"

CONVICTIONS = ("low", "medium", "high")
DATE_CONFIDENCE = ("confirmed", "estimated", "rumoured")
EXIT_RULES = ("before", "after")

OPEN_STATES = (WATCHING, ARMED, HOLDING)


@dataclass
class Catalyst:
    id: int
    title: str
    symbol: str
    event_date: datetime
    date_confidence: str
    thesis: str
    conviction: str
    status: str
    entry_days_before: int
    exit_rule: str
    notes: str
    created_at: datetime
    updated_at: datetime

    @property
    def days_away(self) -> int:
        return (self.event_date.date() - datetime.now(timezone.utc).date()).days

    @property
    def in_entry_window(self) -> bool:
        """True once the event is close enough to start building a position."""
        return 0 <= self.days_away <= self.entry_days_before

    @property
    def is_past(self) -> bool:
        return self.days_away < 0

    @property
    def window_opens_in(self) -> int:
        """Days until the entry window opens. 0 once it is open or gone."""
        return max(self.days_away - self.entry_days_before, 0)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "symbol": self.symbol,
            "event_date": self.event_date.date().isoformat(),
            "date_confidence": self.date_confidence,
            "thesis": self.thesis,
            "conviction": self.conviction,
            "status": self.status,
            "entry_days_before": self.entry_days_before,
            "exit_rule": self.exit_rule,
            "notes": self.notes,
            "days_away": self.days_away,
            "in_entry_window": self.in_entry_window,
            "window_opens_in": self.window_opens_in,
            "is_past": self.is_past,
        }


class CatalystManager:
    """Keeps the calendar of events you are trading around.

    It does not decide whether an event is worth trading — that judgement is
    yours. What it does is remember the date, tell you when the entry window
    opens, and put the actual headlines next to your thesis so you can see
    whether the story still holds.
    """

    def __init__(self, session_factory: sessionmaker[Session], events: EventBus) -> None:
        self._session_factory = session_factory
        self.events = events
        self._lock = threading.Lock()
        self._announced: set[int] = set()

    # ------------------------------------------------------------------ read

    def all(self, include_finished: bool = False) -> list[Catalyst]:
        with self._session_factory() as session:
            query = select(CatalystRow)
            if not include_finished:
                query = query.where(CatalystRow.status.in_(OPEN_STATES))
            rows = session.scalars(query.order_by(CatalystRow.event_date)).all()
        return [_to_catalyst(r) for r in rows]

    def get(self, catalyst_id: int) -> Catalyst | None:
        with self._session_factory() as session:
            row = session.get(CatalystRow, catalyst_id)
        return _to_catalyst(row) if row else None

    def symbols(self) -> list[str]:
        """Every ticker with an open catalyst, for the news feed to follow."""
        return sorted({c.symbol for c in self.all()})

    # ----------------------------------------------------------------- write

    def add(
        self,
        title: str,
        symbol: str,
        event_date: datetime,
        thesis: str = "",
        conviction: str = "medium",
        entry_days_before: int = 45,
        exit_rule: str = "before",
        date_confidence: str = "estimated",
        notes: str = "",
    ) -> Catalyst:
        title = title.strip()
        symbol = symbol.strip().upper()
        if not title:
            raise ValueError("give the catalyst a title")
        if not symbol:
            raise ValueError("which ticker does this move?")
        if conviction not in CONVICTIONS:
            raise ValueError(f"conviction must be one of {CONVICTIONS}")
        if exit_rule not in EXIT_RULES:
            raise ValueError(f"exit_rule must be one of {EXIT_RULES}")
        if date_confidence not in DATE_CONFIDENCE:
            raise ValueError(f"date_confidence must be one of {DATE_CONFIDENCE}")
        if entry_days_before < 0:
            raise ValueError("entry window cannot be negative")

        now = datetime.now(timezone.utc)
        row = CatalystRow(
            title=title, symbol=symbol, event_date=event_date,
            date_confidence=date_confidence, thesis=thesis.strip(),
            conviction=conviction, status=WATCHING,
            entry_days_before=entry_days_before, exit_rule=exit_rule,
            notes=notes.strip(), created_at=now, updated_at=now,
        )
        with self._lock, self._session_factory() as session:
            session.add(row)
            session.commit()
            session.refresh(row)

        catalyst = _to_catalyst(row)
        log.info("catalyst added: %s (%s) in %d days", title, symbol, catalyst.days_away)
        self.events.publish("catalyst", {"catalyst": catalyst.to_dict(), "event": "added"})
        return catalyst

    def update(self, catalyst_id: int, **fields) -> Catalyst | None:
        allowed = {
            "title", "symbol", "event_date", "thesis", "conviction", "status",
            "entry_days_before", "exit_rule", "date_confidence", "notes",
        }
        with self._lock, self._session_factory() as session:
            row = session.get(CatalystRow, catalyst_id)
            if row is None:
                return None
            for key, value in fields.items():
                if key in allowed and value is not None:
                    setattr(row, key, value.upper() if key == "symbol" else value)
            row.updated_at = datetime.now(timezone.utc)
            session.commit()
            session.refresh(row)

        catalyst = _to_catalyst(row)
        self.events.publish("catalyst", {"catalyst": catalyst.to_dict(), "event": "updated"})
        return catalyst

    def remove(self, catalyst_id: int) -> bool:
        with self._lock, self._session_factory() as session:
            row = session.get(CatalystRow, catalyst_id)
            if row is None:
                return False
            session.delete(row)
            session.commit()
        self.events.publish("catalyst", {"catalyst": {"id": catalyst_id}, "event": "removed"})
        return True

    # ---------------------------------------------------------------- ticking

    def refresh_windows(self) -> list[Catalyst]:
        """Move catalysts into the entry window and announce it once each.

        Returns the ones that just opened, so the caller can alert on them.
        """
        opened: list[Catalyst] = []
        for catalyst in self.all():
            if catalyst.status == WATCHING and catalyst.in_entry_window:
                self.update(catalyst.id, status=ARMED)
                with self._lock:
                    if catalyst.id in self._announced:
                        continue
                    self._announced.add(catalyst.id)
                refreshed = self.get(catalyst.id)
                if refreshed:
                    opened.append(refreshed)
                    self.events.publish(
                        "catalyst",
                        {"catalyst": refreshed.to_dict(), "event": "window_open"},
                    )
        return opened


def _to_catalyst(row: CatalystRow) -> Catalyst:
    event_date = row.event_date
    if event_date.tzinfo is None:
        event_date = event_date.replace(tzinfo=timezone.utc)
    return Catalyst(
        id=row.id, title=row.title, symbol=row.symbol, event_date=event_date,
        date_confidence=row.date_confidence, thesis=row.thesis,
        conviction=row.conviction, status=row.status,
        entry_days_before=row.entry_days_before, exit_rule=row.exit_rule,
        notes=row.notes, created_at=row.created_at, updated_at=row.updated_at,
    )


def parse_date(value: str) -> datetime:
    """Accepts YYYY-MM-DD, or a loose 'YYYY-MM' meaning the end of that month."""
    value = value.strip()
    try:
        return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    try:
        start = datetime.strptime(value, "%Y-%m").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ValueError("use YYYY-MM-DD, or YYYY-MM for a whole month") from exc
    # last day of that month
    following = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    return following - timedelta(days=1)
