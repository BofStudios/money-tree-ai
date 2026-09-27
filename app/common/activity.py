"""The Live tab's feed: one entry per thing the engine actually did.

Each step is opened before the work starts and closed when it finishes, so the
dashboard shows a spinner for exactly as long as the real call takes — nothing
on screen is animated without an operation behind it. A failed step keeps its
error. Same model as the phone app's monitor, so both read the same way.

Every change is published on the event bus as a "step" event; the web socket
forwards it, and /api/steps serves the whole list to a page that just opened.
"""
from __future__ import annotations

import itertools
import threading
import time
from collections import deque
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from typing import Iterator

from app.common.events import EventBus

# What kind of work a step is; the page picks a bullet colour from it.
CLOCK, ACCOUNT, POSITIONS, BARS, ANALYSE, NEWS = "clock", "account", "positions", "bars", "analyse", "news"
ORDER, TRAIL, SELL, AI, APPROVAL, WAIT, WARN, INFO = (
    "order", "trail", "sell", "ai", "approval", "wait", "warn", "info"
)

RUNNING, DONE, FAILED, NOTE = "running", "done", "failed", "info"


def _now_ms() -> int:
    return int(time.time() * 1000)


@dataclass
class Step:
    id: int
    kind: str
    title: str
    state: str
    started_at: int
    ended_at: int | None = None
    detail: str | None = None
    lines: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class Monitor:
    def __init__(self, events: EventBus | None = None, cap: int = 300) -> None:
        self._events = events
        self._ids = itertools.count(1)
        self._lock = threading.Lock()
        self._steps: deque[Step] = deque(maxlen=cap)

    def snapshot(self) -> list[dict]:
        with self._lock:
            return [s.to_dict() for s in self._steps]

    def begin(self, kind: str, title: str) -> "StepHandle":
        step = Step(next(self._ids), kind, title, RUNNING, _now_ms())
        self._add(step)
        return StepHandle(self, step.id)

    def info(self, kind: str, title: str, detail: str | None = None, lines: list[str] | None = None) -> None:
        now = _now_ms()
        self._add(Step(next(self._ids), kind, title, NOTE, now, now, detail, list(lines or [])))

    @contextmanager
    def step(self, kind: str, title: str) -> Iterator["StepHandle"]:
        """`with monitor.step(...) as s:` — DONE on exit, FAILED if it raises.

        Call s.done(...) inside to set the result line; if the block finishes
        without it, the step is closed with no detail.
        """
        handle = self.begin(kind, title)
        try:
            yield handle
        except BaseException as exc:
            handle.fail(str(exc) or type(exc).__name__)
            raise
        else:
            handle.done_if_open()

    # ------------------------------------------------------------- internals

    def _add(self, step: Step) -> None:
        with self._lock:
            self._steps.append(step)
        self._publish(step)

    def _update(self, step_id: int, **changes) -> None:
        with self._lock:
            step = next((s for s in self._steps if s.id == step_id), None)
            if step is None:
                return
            if step.state != RUNNING and "detail" in changes and "state" not in changes:
                return  # a finished step is not rewritten by a late progress call
            for key, value in changes.items():
                setattr(step, key, value)
            snapshot = Step(**step.to_dict())
        self._publish(snapshot)

    def _publish(self, step: Step) -> None:
        if self._events is not None:
            self._events.publish("step", {"step": step.to_dict()})


class StepHandle:
    def __init__(self, monitor: Monitor, step_id: int) -> None:
        self._monitor = monitor
        self._id = step_id
        self._closed = False

    def progress(self, detail: str) -> None:
        """Say what a still-running step is doing, e.g. which symbol is in flight."""
        self._monitor._update(self._id, detail=detail)

    def done(self, detail: str | None = None, lines: list[str] | None = None) -> None:
        self._closed = True
        self._monitor._update(self._id, state=DONE, ended_at=_now_ms(), detail=detail, lines=list(lines or []))

    def fail(self, detail: str) -> None:
        self._closed = True
        self._monitor._update(self._id, state=FAILED, ended_at=_now_ms(), detail=detail)

    def done_if_open(self) -> None:
        if not self._closed:
            self.done()
