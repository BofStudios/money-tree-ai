"""The first second of the app: one copy only, and something on screen at once.

Runs before the heavy imports (pandas, the brokers, the AI SDKs), which take
5 to 15 seconds in the exe. Without it the window appeared only after all of
that, people clicked the icon again, several copies fought over the same
port, and the window of the copy that lost went grey.

  one copy   A Windows mutex per port. A second launch asks the running copy
             to show its window, then quits. A copy started by an in-app
             restart waits for the old one to let go instead.
  splash     The logo and what is loading, from the first second.

Only the standard library and PySide6 are imported here.
"""
from __future__ import annotations

import os
import sys
import time

RELAUNCHED = "MONEYTREE_RELAUNCHED"

_mutex = None
_app = None
_splash = None
focus_hook = None          # set by the window: show and raise it


def _arg(argv: list[str], name: str) -> str | None:
    for i, a in enumerate(argv):
        if a == name and i + 1 < len(argv):
            return argv[i + 1]
        if a.startswith(name + "="):
            return a.split("=", 1)[1]
    return None


def port_from_args(argv: list[str]) -> int:
    try:
        return int(_arg(argv, "--port") or 8765)
    except ValueError:
        return 8765


def _try_lock(port: int) -> bool:
    """True when this process now holds the one-copy lock for the port."""
    global _mutex
    if sys.platform != "win32":
        return True
    import ctypes

    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel32.CreateMutexW(None, False, f"Local\\BofStudios.MoneyTreeAI.{port}")
    if not handle:
        return True                                  # cannot tell: do not block start-up
    if kernel32.GetLastError() == 183:                # ERROR_ALREADY_EXISTS
        kernel32.CloseHandle(ctypes.c_void_p(handle))
        return False
    _mutex = handle                                  # held until the process ends
    return True


def _ask_running_copy_to_show(port: int) -> None:
    import urllib.request

    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/focus", data=b"{}", method="POST",
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=3).read()
    except Exception:
        pass


def early(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    port = port_from_args(argv)
    if not _try_lock(port):
        if os.environ.get(RELAUNCHED) == "1":
            deadline = time.monotonic() + 25
            while time.monotonic() < deadline and not _try_lock(port):
                time.sleep(0.25)
        else:
            _ask_running_copy_to_show(port)
            sys.exit(0)
    if "--headless" not in argv:
        _show_splash()


def _show_splash() -> None:
    global _app, _splash
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
        from PySide6.QtWidgets import QApplication, QSplashScreen
    except Exception:
        return
    _app = QApplication.instance() or QApplication(sys.argv)
    base = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
    candidates = [os.path.join(getattr(sys, "_MEIPASS", base), "assets", "logo.png"),
                  os.path.join(base, "..", "..", "assets", "logo.png")]
    canvas = QPixmap(460, 300)
    canvas.fill(QColor("#050403"))
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    for path in candidates:
        if os.path.exists(path):
            logo = QPixmap(path).scaled(132, 132, Qt.AspectRatioMode.KeepAspectRatio,
                                        Qt.TransformationMode.SmoothTransformation)
            painter.drawPixmap((460 - logo.width()) // 2, 34, logo)
            break
    painter.setPen(QColor("#ffd60a"))
    font = QFont("Segoe UI", 17)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(canvas.rect().adjusted(0, 180, 0, 0), Qt.AlignmentFlag.AlignHCenter, "Money Tree AI")
    painter.setPen(QColor("#ffd60a"))
    painter.drawRect(0, 0, 459, 299)
    painter.end()
    _splash = QSplashScreen(canvas, Qt.WindowType.WindowStaysOnTopHint)
    _splash.show()
    message("Starting")


def message(text: str) -> None:
    if _splash is None:
        return
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor

    _splash.showMessage(f"{text}…", Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom, QColor("#b8b19a"))
    _app.processEvents()


def close(window=None) -> None:
    global _splash
    if _splash is None:
        return
    if window is not None:
        _splash.finish(window)
    else:
        _splash.close()
    _splash = None


def request_focus() -> bool:
    if focus_hook is None:
        return False
    focus_hook()
    return True
