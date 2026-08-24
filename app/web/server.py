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
) -> FastAPI:
    api = FastAPI(title="Money Tree AI", docs_url=None, redoc_url=None)
    hub = WebSocketHub(events)

    @api.on_event("startup")
    async def _bind_loop() -> None:
        hub.bind(asyncio.get_running_loop())

    api.include_router(
        build_router(engine, repo, mentor, claude, hub, token, settings, catalysts, news)
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
        self._thread = threading.Thread(target=self._server.run, name="web-server", daemon=True)
        self._thread.start()
        log.info("dashboard serving on %s (and on your LAN IP for phones)", self.local_url)

    def stop(self) -> None:
        self._server.should_exit = True
