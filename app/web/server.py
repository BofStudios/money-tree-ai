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
from app.web.auth import COOKIE, COOKIE_DAYS, SAFE_METHODS, Auth, same_origin
from app.web.brain_routes import build_brain_router
from app.web.lab_routes import build_lab_router
from app.web.privacy_routes import build_privacy_router
from app.web.mode_routes import build_mode_router
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
    auth = Auth(token)          # one lockout counter for every router

    @api.on_event("startup")
    async def _bind_loop() -> None:
        hub.bind(asyncio.get_running_loop())

    api.include_router(
        build_router(
            engine, repo, mentor, claude, hub, auth, settings, catalysts, news,
            research, analyst, profiles, keystore,
        )
    )
    api.include_router(
        build_money_router(engine, repo, settings, keystore, restarter, auth, config_path, key_problems)
    )
    api.include_router(build_brain_router(engine, auth))
    api.include_router(build_mode_router(engine, auth))
    api.include_router(build_lab_router(engine, repo, auth))
    api.include_router(build_privacy_router(engine, repo, claude, restarter, auth))

    @api.middleware("http")
    async def _only_by_address(request, call_next):
        """Answer only to this PC and the home network, by address.

        A web page on some other site can make a browser on this PC talk to
        127.0.0.1 under its own domain name (DNS rebinding). Such a request
        carries that domain as Host and is refused here.
        """
        if not _host_allowed(request.headers.get("host", "")):
            from fastapi.responses import PlainTextResponse

            return PlainTextResponse("forbidden host", status_code=403)
        return await call_next(request)

    @api.middleware("http")
    async def _own_origin_only(request, call_next):
        """A change that names an Origin must come from this page's own host.
        Another web page cannot make the browser press buttons here (CSRF)."""
        if request.method not in SAFE_METHODS:
            origin = request.headers.get("origin")
            if origin is not None and not same_origin(origin, request.headers.get("host", "")):
                from fastapi.responses import PlainTextResponse

                return PlainTextResponse("foreign origin", status_code=403)
        return await call_next(request)

    @api.middleware("http")
    async def _first_visit(request, call_next):
        """The link with ?token= logs in once: the password becomes an HttpOnly,
        SameSite=Strict cookie and the address bar is cleaned by a redirect."""
        if request.method == "GET" and request.url.path in ("/", "/index.html") and "token" in request.query_params:
            if auth.first_visit(request):
                from urllib.parse import urlencode

                from fastapi.responses import RedirectResponse

                rest = [(k, v) for k, v in request.query_params.multi_items() if k != "token"]
                target = request.url.path + (f"?{urlencode(rest)}" if rest else "")
                response = RedirectResponse(target, status_code=303)
                response.set_cookie(COOKIE, auth.token, max_age=COOKIE_DAYS * 86400, httponly=True,
                                    samesite="strict", path="/")
                return response
        return await call_next(request)

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

    @api.middleware("http")
    async def _safe_headers(request, call_next):
        """Outermost: every answer, errors included, carries these."""
        response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        return response

    api.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return api


# The page loads only its own files. Styles may be inline (the screens set
# widths and colours from data); scripts may not, so a script injected into a
# page can run nowhere. Images may be data: or blob: (the screenshots you add).
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; connect-src 'self' ws: wss:; font-src 'self' data:; "
        "object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}


def _host_allowed(host: str) -> bool:
    import ipaddress

    name = host.strip().lower()
    if name.startswith("["):                       # [::1]:8765
        name = name[1:].split("]", 1)[0]
    elif name.count(":") == 1:
        name = name.split(":", 1)[0]
    if name in ("localhost", "testserver", ""):
        return name != ""
    try:
        ipaddress.ip_address(name)
        return True
    except ValueError:
        return False


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
        # Only a restart has an old copy to wait for: the one-copy lock
        # (app/common/startup.py) rules out a second running copy.
        from app.common.restart import relaunched

        if relaunched():
            _wait_for_port(self.host, self.port, timeout=15.0)
        self._thread = threading.Thread(target=self._server.run, name="web-server", daemon=True)
        self._thread.start()
        log.info("dashboard serving on %s %s", self.local_url,
                 "(and on your LAN IP for phones)" if self.host in ("0.0.0.0", "::") else "(this PC only)")

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
