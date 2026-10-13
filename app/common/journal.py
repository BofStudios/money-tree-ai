"""The bot's life so far: since when it runs, how long, and how it grew.

Counters only ever go up (looks, headlines read, strategies tested, trades),
and the growth line keeps the moments that changed the bot: a better strategy
promoted, a rule learned from results, a lesson about a kind of news. The
Memory card reads this; nothing here decides a trade.

Saved to data/journal.json every minute by the Keeper and once more at exit.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)

MAX_EVENTS = 300
MAX_DAYS = 3650


class Journal:
    def __init__(self, path: Path | None, now: Callable[[], float] = time.time) -> None:
        self.path = path
        self._now = now
        self._lock = threading.Lock()
        self.first_start: float | None = None
        self.starts = 0
        self.uptime = 0.0                    # seconds, earlier runs only
        self.counters: dict[str, float] = {}
        self.days: list[str] = []            # days the app was open, "2026-10-13"
        self.events: list[dict] = []         # newest first
        self.level = 0
        self._session_start = now()
        self._load()

    # ------------------------------------------------------------- record

    def started(self) -> None:
        with self._lock:
            self.starts += 1
            if self.first_start is None:
                self.first_start = self._now()
            self._session_start = self._now()
            self._mark_day()
        self.save()

    def add(self, counter: str, n: float = 1) -> None:
        if not n:
            return
        with self._lock:
            self.counters[counter] = self.counters.get(counter, 0) + n

    def set_max(self, counter: str, value: float) -> None:
        """For totals another part keeps itself (strategies tested): never lower."""
        with self._lock:
            if value > self.counters.get(counter, 0):
                self.counters[counter] = value

    def count(self, counter: str) -> float:
        with self._lock:
            return self.counters.get(counter, 0)

    def event(self, kind: str, title: str, detail: str | None = None) -> None:
        with self._lock:
            self.events.insert(0, {"at": self._now(), "kind": kind, "title": title[:200],
                                   "detail": (detail or "")[:400]})
            del self.events[MAX_EVENTS:]

    # -------------------------------------------------------------- views

    def total_uptime(self) -> float:
        with self._lock:
            return self.uptime + max(self._now() - self._session_start, 0.0)

    def snapshot(self) -> dict:
        with self._lock:
            self._mark_day()
            return {
                "first_start": self.first_start,
                "starts": self.starts,
                "uptime": self.uptime + max(self._now() - self._session_start, 0.0),
                "days": len(self.days),
                "counters": dict(self.counters),
                "events": list(self.events[:60]),
                "level": self.level,
            }

    # ------------------------------------------------------------ storage

    def save(self) -> None:
        if self.path is None:
            return
        with self._lock:
            self._mark_day()
            doc = {
                "first_start": self.first_start,
                "starts": self.starts,
                "uptime": self.uptime + max(self._now() - self._session_start, 0.0),
                "counters": self.counters,
                "days": self.days[-MAX_DAYS:],
                "events": self.events,
                "level": self.level,
            }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(doc), encoding="utf-8")
            tmp.replace(self.path)
        except OSError:
            log.exception("could not save the journal")

    def _load(self) -> None:
        if self.path is None:
            return
        try:
            doc = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except (OSError, ValueError):
            log.warning("the journal is unreadable; starting a new one")
            return
        try:
            self.first_start = doc.get("first_start")
            self.starts = int(doc.get("starts", 0))
            self.uptime = float(doc.get("uptime", 0.0))
            self.counters = {str(k): float(v) for k, v in (doc.get("counters") or {}).items()}
            self.days = [str(d) for d in doc.get("days", [])][-MAX_DAYS:]
            self.events = [e for e in doc.get("events", []) if isinstance(e, dict)][:MAX_EVENTS]
            self.level = int(doc.get("level", 0))
        except (TypeError, ValueError):
            log.warning("parts of the journal are unreadable; starting those fresh")

    def _mark_day(self) -> None:
        today = datetime.fromtimestamp(self._now()).strftime("%Y-%m-%d")
        if not self.days or self.days[-1] != today:
            if today not in self.days:
                self.days.append(today)


class Keeper:
    """Saves everything worth remembering every minute, and once more at exit.

    Each job is a plain function; one that fails is logged and the rest still run.
    """

    def __init__(self, every: float = 60.0) -> None:
        self.every = every
        self._jobs: list[tuple[str, Callable[[], None]]] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def add(self, name: str, job: Callable[[], None]) -> None:
        self._jobs.append((name, job))

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="memory-keeper", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self.run_all()

    def run_all(self) -> None:
        for name, job in list(self._jobs):
            try:
                job()
            except Exception:
                log.exception("could not save %s", name)

    def _loop(self) -> None:
        while not self._stop.wait(self.every):
            self.run_all()
