from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import WebSocket

from app.common.events import EventBus

log = logging.getLogger(__name__)


class WebSocketHub:
    """Bridges engine-thread events onto the asyncio loop and out to browsers."""

    def __init__(self, events: EventBus) -> None:
        self._clients: set[WebSocket] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        events.subscribe(self._on_event)

    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._clients.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self._clients.discard(websocket)

    def _on_event(self, event: dict[str, Any]) -> None:
        if self._loop is None or not self._clients:
            return
        # Called from the engine thread, so hop onto the server's loop.
        asyncio.run_coroutine_threadsafe(self._broadcast(event), self._loop)

    async def _broadcast(self, event: dict[str, Any]) -> None:
        dead: list[WebSocket] = []
        for client in list(self._clients):
            try:
                await client.send_json(event)
            except Exception:
                dead.append(client)
        for client in dead:
            self._clients.discard(client)
