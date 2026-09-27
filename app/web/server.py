from __future__ import annotations

import asyncio
import logging
import threading
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.common.events import EventBus
from app.engine.portfolio_engine import PortfolioEngine
from app.mentor.ai import AIMentor
from app.mentor.narrator import Narrator
from app.storage.repository import Repository
from app.web.money_routes import build_money_router
from app.web.routes import build_router
from app.web.ws import WebSocketHub

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


def create_app(
    engine: PortfolioEngine,
    repo: Repository,
    mentor: Narrator,
    claude: AIMentor,
    events: EventBus,
    token: str,
    settings=None,
    catalysts=None,
    news=None,
    research=None,
    analyst=None,
    profiles=None,
    keystore=None,
    restarter=None,
    config_path=None,
    key_problems=None,
) -> FastAPI:
    api = FastAPI(title="Money Tree AI", docs_url=None, redoc_url=None)
    hub = WebSocketHub(events)

    @api.on_event("startup")
    async def _bind_loop() -> None:
        hub.bind(asyncio.get_running_loop())

    api.include_router(
        build_router(
            engine, repo, mentor, claude, hub, token, settings, catalysts, news,
            research, analyst, profiles, keystore,
        )
    )
    api.include_router(
        build_money_router(engine, repo, settings, keystore, restarter, token, config_path, key_problems)
    )
    @api.middleware("http")
    async def _revalidate_static(request, call_next):
        """Make the browser check for a newer dashboard on every load.

        QtWebEngine keeps a disk cache, so without this an updated stylesheet or
        script could keep serving from cache after an upgrade and the app would
        look broken in ways the files on disk do not explain.
        """
        response = await call_next(request)
        if not request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response

    api.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return api


class WebServer:
    """Runs uvicorn on a background thread so Qt keeps the main thread."""

    def __init__(self, api: FastAPI, host: str, port: int) -> None:
        # log_config=None leaves logging to us. Uvicorn's own colour formatter
        # calls sys.stdout.isatty(), and a windowed exe has no stdout at all,
        # so letting it configure logging crashes the app on startup.
        config = uvicorn.Config(
            api, host=host, port=port,
            log_level="warning", access_log=False, log_config=None,
        )
        self._server = uvicorn.Server(config)
        self._thread: threading.Thread | None = None
        self.host = host
        self.port = port

    @property
    def local_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> None:
        # After an in-app restart the previous copy may still be letting go of
        # the port; give it a moment instead of failing to bind.
        _wait_for_port(self.host, self.port, timeout=15.0)
        self._thread = threading.Thread(target=self._server.run, name="web-server", daemon=True)
        self._thread.start()
        log.info("dashboard serving on %s (and on your LAN IP for phones)", self.local_url)

    def stop(self) -> None:
        self._server.should_exit = True

    def join(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout)


def _wait_for_port(host: str, port: int, timeout: float) -> None:
    """Wait while something still answers on the port (the previous copy)."""
    import socket
    import time

    target = "127.0.0.1" if host in ("0.0.0.0", "", "::") else host
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((target, port), timeout=0.5):
                pass
        except OSError:
            return  # nothing listening: free
        time.sleep(0.5)
    log.warning("port %s is still answering; starting anyway", port)
