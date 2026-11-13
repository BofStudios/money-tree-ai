"""Who may use the dashboard (10.1). One place, instead of four copies.

How a request proves it may drive the bot, in this order:
  1. ?token=...           the first visit (the link in the app and in the phone QR)
  2. Authorization: Bearer ...
  3. the mt_session cookie, set when the first visit carried a good token

The first visit is answered with a redirect to the same page without the
token, and the cookie is HttpOnly and SameSite=Strict: the password is no
longer left in the address bar, in the history, or in the reach of a script.

Wrong tries are counted per address: after 5 the address waits a minute, then
two, four ... up to 15 minutes. Asking with no credential at all is not a try.

Changing requests that carry an Origin must come from the page's own host:
another site cannot make the browser drive the bot (CSRF), even with a cookie.
"""
from __future__ import annotations

import secrets
import threading
import time
from urllib.parse import urlsplit

from fastapi import HTTPException
from starlette.requests import HTTPConnection

COOKIE = "mt_session"
COOKIE_DAYS = 180
LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}
FAILS_BEFORE_LOCK = 5
LOCK_FIRST, LOCK_MAX = 60, 900
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


class Lockout:
    """Wrong-password counter per address, with waiting that doubles."""

    def __init__(self, clock=time.time) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._state: dict[str, list] = {}      # address -> [fails, locked_until, strikes]

    def left(self, address: str) -> int:
        with self._lock:
            row = self._state.get(address)
            return max(0, int(row[1] - self._clock())) if row else 0

    def fail(self, address: str) -> None:
        with self._lock:
            row = self._state.setdefault(address, [0, 0.0, 0])
            row[0] += 1
            if row[0] >= FAILS_BEFORE_LOCK:
                row[2] += 1
                row[0] = 0
                row[1] = self._clock() + min(LOCK_FIRST * 2 ** (row[2] - 1), LOCK_MAX)
            if len(self._state) > 2000:         # never grows without end
                for key in [k for k, v in self._state.items() if v[1] < self._clock()][:1000]:
                    self._state.pop(key, None)

    def ok(self, address: str) -> None:
        with self._lock:
            self._state.pop(address, None)


def address_of(conn: HTTPConnection) -> str:
    return conn.client.host if conn.client else ""


def same_origin(origin: str, host: str) -> bool:
    """True when an Origin header names the host the request was sent to."""
    if not origin or origin == "null":
        return False
    return urlsplit(origin).netloc.lower() == (host or "").strip().lower()


class Auth:
    def __init__(self, token: str, clock=time.time) -> None:
        self.token = token or ""
        self.lockout = Lockout(clock)

    # ----------------------------------------------------------- credentials
    def _candidates(self, conn: HTTPConnection) -> list[str]:
        out = [conn.query_params.get("token", "")]
        auth = conn.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            out.append(auth[7:].strip())
        out.append(conn.cookies.get(COOKIE, ""))
        return [c for c in out if c]

    def _good(self, value: str) -> bool:
        return bool(self.token) and secrets.compare_digest(value.encode(), self.token.encode())

    def check(self, conn: HTTPConnection) -> bool:
        """True when the request may use the dashboard. No token configured = open
        (local-only use). Raises 429 while the address is locked out."""
        if not self.token:
            return True
        address = address_of(conn)
        wait = self.lockout.left(address)
        if wait:
            raise HTTPException(status_code=429, detail=f"too many wrong tries: wait {wait} s",
                                headers={"Retry-After": str(wait)})
        given = self._candidates(conn)
        if any(self._good(c) for c in given):
            self.lockout.ok(address)
            return True
        if given:
            self.lockout.fail(address)
        return False

    def first_visit(self, conn: HTTPConnection) -> bool:
        """The page was opened with ?token=: good tokens log in, wrong ones count."""
        given = conn.query_params.get("token", "")
        if not given or not self.token:
            return False
        if self.lockout.left(address_of(conn)):
            return False
        if self._good(given):
            self.lockout.ok(address_of(conn))
            return True
        self.lockout.fail(address_of(conn))
        return False

    # ----------------------------------------------------------- dependencies
    def guard(self):
        def require_token(conn: HTTPConnection) -> None:
            if not self.check(conn):
                raise HTTPException(status_code=401, detail="invalid token")
        return require_token

    def owner(self, what: str = "This can only be changed on the PC running the bot."):
        def require_owner(conn: HTTPConnection) -> None:
            if self.token:
                if not self.check(conn):
                    raise HTTPException(status_code=401, detail="invalid token")
                return
            if address_of(conn) not in LOCAL_HOSTS:
                raise HTTPException(status_code=403, detail=what)
        return require_owner

    def websocket_ok(self, conn: HTTPConnection) -> bool:
        try:
            if not self.check(conn):
                return False
        except HTTPException:
            return False
        origin = conn.headers.get("origin", "")
        return not origin or same_origin(origin, conn.headers.get("host", ""))
