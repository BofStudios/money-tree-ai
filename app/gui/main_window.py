from __future__ import annotations

import logging

from PySide6.QtCore import QPointF, QUrl, Qt, Signal
from PySide6.QtGui import QAction, QColor, QDesktopServices, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QMainWindow, QMenu, QMessageBox, QSystemTrayIcon

from app.common.events import EventBus
from app.config import APP_NAME, ASSETS
from app.engine.portfolio_engine import PortfolioEngine
from app.gui.notices import notice_for

log = logging.getLogger(__name__)


class _DashboardPage(QWebEnginePage):
    """The dashboard stays in the window; every other site opens in the
    system browser (Alpaca's funding pages, news articles, docs)."""

    def __init__(self, home: QUrl, parent=None) -> None:
        super().__init__(parent)
        self._home = home

    def acceptNavigationRequest(self, url: QUrl, nav_type, is_main_frame: bool) -> bool:
        if is_main_frame and not _same_origin(url, self._home):
            QDesktopServices.openUrl(url)
            return False
        return super().acceptNavigationRequest(url, nav_type, is_main_frame)

    def createWindow(self, _type) -> QWebEnginePage:
        # A link with target=_blank: its first navigation goes to the system browser.
        return _ExternalPage(self)


class _ExternalPage(QWebEnginePage):
    def acceptNavigationRequest(self, url: QUrl, nav_type, is_main_frame: bool) -> bool:
        if url.scheme() in ("http", "https"):
            QDesktopServices.openUrl(url)
        self.deleteLater()
        return False


def _same_origin(url: QUrl, home: QUrl) -> bool:
    return (url.scheme(), url.host(), url.port()) == (home.scheme(), home.host(), home.port())


class MainWindow(QMainWindow):
    """A window around the same dashboard the phone loads, plus a tray icon.

    Closing the window hides it; the engine and web server keep running so the
    bot stays live and reachable from your phone.
    """

    # Emitted from other threads (web server, engine); Qt delivers them on the window's.
    restart_requested = Signal()
    notify_requested = Signal(str, str)

    def __init__(
        self,
        engine: PortfolioEngine,
        dashboard_url: str,
        lan_url: str,
        events: EventBus | None = None,
    ) -> None:
        super().__init__()
        self.engine = engine
        self.lan_url = lan_url
        self._really_quitting = False

        money = {"alpaca_live": "REAL MONEY", "alpaca_paper": "Alpaca paper",
                 "simulation": "simulation"}.get(engine.executor.broker, engine.mode)
        self.setWindowTitle(f"{APP_NAME} — {money}")
        self.resize(1480, 960)
        self.setWindowIcon(_app_icon())

        home = QUrl(dashboard_url)
        self.view = QWebEngineView()
        self.view.setPage(_DashboardPage(home, self.view))
        self.view.load(home)
        self.setCentralWidget(self.view)

        self._build_tray()
        self.restart_requested.connect(self._restart_now)
        self.notify_requested.connect(self._notify)
        if events is not None:
            events.subscribe(self._on_event)

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(_app_icon(), self)
        self.tray.setToolTip("Money Tree AI")

        menu = QMenu()
        show = QAction("Show dashboard", self)
        show.triggered.connect(self._show_window)

        phone = QAction("Copy phone link", self)
        phone.triggered.connect(self._copy_phone_link)

        scan = QAction("Scan now", self)
        scan.triggered.connect(self.engine.scan_now)

        disarm = QAction("Disarm live trading", self)
        disarm.triggered.connect(lambda: self.engine.disarm("tray"))

        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self._quit)

        menu.addAction(show)
        menu.addAction(phone)
        menu.addAction(scan)
        menu.addSeparator()
        menu.addAction(disarm)
        menu.addSeparator()
        menu.addAction(quit_action)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda reason: self._show_window()
            if reason == QSystemTrayIcon.ActivationReason.Trigger
            else None
        )
        self.tray.show()

    def _show_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _copy_phone_link(self) -> None:
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(self.lan_url)
        self.tray.showMessage(APP_NAME, f"Phone link copied:\n{self.lan_url}", msecs=4000)

    def _quit(self) -> None:
        from PySide6.QtWidgets import QApplication

        open_positions = len(self.engine.status()["positions"])
        if open_positions or self.engine.risk.armed:
            answer = QMessageBox.question(
                self,
                "Positions are still open" if open_positions else "Live trading is armed",
                f"{open_positions} position(s) are open.\n\n"
                "Quitting stops the engine, so I will stop watching their stops and "
                "targets. The positions themselves stay open — nothing is sold — but "
                "nobody is minding them until you start the bot again.\n\n"
                "Quit anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        self._really_quitting = True
        self.tray.hide()
        QApplication.quit()

    def _on_event(self, event: dict) -> None:
        # The engine's thread: only work out the text here, show it on Qt's.
        notice = notice_for(event, self.engine.words())
        if notice:
            self.notify_requested.emit(*notice)

    def _notify(self, title: str, body: str) -> None:
        """A Windows notification for a buy, a sell or a buy awaiting approval —
        unless the dashboard is already in front, where the page shows it."""
        if self.isVisible() and self.isActiveWindow():
            return
        self.tray.showMessage(title, body, QSystemTrayIcon.MessageIcon.Information, 8000)

    def _restart_now(self) -> None:
        """Leave the event loop without asking; main() starts the new copy."""
        from PySide6.QtWidgets import QApplication

        self._really_quitting = True
        self.tray.hide()
        QApplication.quit()

    def closeEvent(self, event) -> None:
        if self._really_quitting:
            event.accept()
            return
        event.ignore()
        self.hide()
        self.tray.showMessage(
            f"{APP_NAME} is still running",
            "The bot keeps trading in the background. Right-click the tray icon to quit.",
            msecs=4000,
        )


def _app_icon() -> QIcon:
    """The Money Tree mark. Falls back to a drawn one if the asset is missing."""
    icon = QIcon()
    for name in ("logo.ico", "logo.png"):
        if (ASSETS / name).exists():
            icon.addFile(str(ASSETS / name))
    if not icon.isNull():
        return icon

    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor("#32d583"))
    painter.setPen(Qt.PenStyle.NoPen)
    for cx, cy, r in ((26, 28, 7), (36, 20, 9), (46, 15, 6)):
        painter.drawEllipse(QPointF(cx, cy), r, r)
    pen = QPen(QColor("#ffffff"))
    pen.setWidthF(3.4)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPolyline([QPointF(19, 50), QPointF(27, 42), QPointF(32, 45), QPointF(45, 26)])
    painter.end()
    return QIcon(pixmap)
