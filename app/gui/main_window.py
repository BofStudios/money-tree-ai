from __future__ import annotations

import logging

from PySide6.QtCore import QPointF, QUrl, Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QMainWindow, QMenu, QMessageBox, QSystemTrayIcon

from app.config import APP_NAME, ASSETS
from app.engine.portfolio_engine import PortfolioEngine

log = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """A window around the same dashboard the phone loads, plus a tray icon.

    Closing the window hides it; the engine and web server keep running so the
    bot stays live and reachable from your phone.
    """

    def __init__(self, engine: PortfolioEngine, dashboard_url: str, lan_url: str) -> None:
        super().__init__()
        self.engine = engine
        self.lan_url = lan_url
        self._really_quitting = False

        self.setWindowTitle(
            f"Money Tree AI — {len(engine.symbols)} US stocks, "
            f"{engine.timeframe} [{engine.mode}]"
        )
        self.resize(1480, 960)
        self.setWindowIcon(_app_icon())

        self.view = QWebEngineView()
        self.view.load(QUrl(dashboard_url))
        self.setCentralWidget(self.view)

        self._build_tray()

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
    logo = ASSETS / "logo.png"
    if logo.exists():
        return QIcon(str(logo))

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
