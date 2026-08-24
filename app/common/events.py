from __future__ import annotations

import logging
import threading
from collections import deque
from typing import Any, Callable

log = logging.getLogger(__name__)

Subscriber = Callable[[dict[str, Any]], None]


class EventBus:
    """Fan-out bus bridging the engine thread to the web/GUI layers.

    Subscribers are invoked on the publishing thread, so they must not block.
    """

    def __init__(self, history_size: int = 200) -> None:
        self._lock = threading.Lock()
        self._subscribers: list[Subscriber] = []
        self._history: deque[dict[str, Any]] = deque(maxlen=history_size)

    def subscribe(self, callback: Subscriber) -> Callable[[], None]:
        with self._lock:
            self._subscribers.append(callback)

        def unsubscribe() -> None:
            with self._lock:
                if callback in self._subscribers:
                    self._subscribers.remove(callback)

        return unsubscribe

    def publish(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        event = {"type": event_type, **(payload or {})}
        with self._lock:
            self._history.append(event)
            subscribers = list(self._subscribers)
        for callback in subscribers:
            try:
                callback(event)
            except Exception:
                log.exception("event subscriber failed for %s", event_type)

    def recent(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._history)
