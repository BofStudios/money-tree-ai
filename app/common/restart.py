"""Restarting the app from inside it.

New Alpaca keys or a switch between practice and real money change which
brokerage account the whole app talks to, so they take effect through a clean
restart rather than by swapping objects under a running engine.

The request is answered first (a short delay lets the HTTP reply reach the
page), then the hooks stop the loop that keeps the process alive, and main()
starts the replacement once this copy has let go of the web port.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
from typing import Callable

from app.config import FROZEN, PROJECT_ROOT

log = logging.getLogger(__name__)


class Restarter:
    def __init__(self) -> None:
        self.requested = threading.Event()
        self._hooks: list[Callable[[], None]] = []

    def on_request(self, hook: Callable[[], None]) -> None:
        self._hooks.append(hook)

    def request(self, delay: float = 0.8) -> None:
        def fire() -> None:
            time.sleep(delay)
            self.requested.set()
            for hook in self._hooks:
                try:
                    hook()
                except Exception:
                    log.exception("restart hook failed")

        threading.Thread(target=fire, name="restart", daemon=True).start()


def relaunch() -> None:
    """Start a fresh copy of the app, detached from this one."""
    if FROZEN:
        command = [sys.executable, *sys.argv[1:]]
    else:
        command = [sys.executable, "-m", "app.main", *sys.argv[1:]]
    flags = 0
    if os.name == "nt":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    log.info("restarting: %s", " ".join(command))
    subprocess.Popen(command, cwd=str(PROJECT_ROOT), creationflags=flags, close_fds=True)
