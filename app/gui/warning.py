"""The start-up warning: what ten bots cost the PC, said plainly before they start."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
)

from app.config import APP_NAME, ASSETS

STYLE = """
QDialog { background: #050505; border: 2px solid #ffd60a; }
QLabel { color: #f2f2f2; font-family: 'Segoe UI'; font-size: 13px; }
QLabel#title { color: #ffd60a; font-size: 20px; font-weight: 800; letter-spacing: 1px; }
QLabel#warn { color: #ffd60a; font-size: 12px; font-weight: 700; letter-spacing: 2px; }
QLabel#body { color: #d6d6d6; }
QCheckBox { color: #a8a8a8; font-size: 12px; }
QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #ffd60a; background: #000; }
QCheckBox::indicator:checked { background: #ffd60a; }
QPushButton { border-radius: 10px; padding: 10px 18px; font-size: 13px; font-weight: 700; }
QPushButton#full { background: #ffd60a; color: #000; border: 0; }
QPushButton#full:hover { background: #ffe24d; }
QPushButton#light { background: #121212; color: #ffd60a; border: 1px solid #ffd60a; }
QPushButton#quit { background: transparent; color: #8b8b90; border: 1px solid #333; }
"""


def power_warning(bots: int, turkish: bool) -> tuple[int, str, bool] | None:
    """Returns (bots, power, remember) or None when the owner chose to quit."""
    t = (lambda en, tr: tr) if turkish else (lambda en, tr: en)
    cores = os.cpu_count() or 4
    dialog = QDialog()
    dialog.setWindowTitle(f"{APP_NAME} — " + t("power warning", "güç uyarısı"))
    dialog.setWindowIcon(QIcon(str(ASSETS / "logo.ico")))
    dialog.setStyleSheet(STYLE)
    dialog.setMinimumWidth(560)

    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(28, 24, 28, 22)
    layout.setSpacing(12)

    warn = QLabel(t("⚠  WARNING · HIGH RESOURCE USE", "⚠  UYARI · YÜKSEK KAYNAK KULLANIMI"))
    warn.setObjectName("warn")
    title = QLabel(t(f"{bots} strategy bots start now", f"{bots} strateji botu şimdi başlar"))
    title.setObjectName("title")
    title.setWordWrap(True)
    body = QLabel(t(
        f"Money Tree runs {bots} strategy bots as separate processes. Each bot tests thousands of strategies "
        f"a second on real prices. The research desk also reads SEC reports and the news of the whole market.\n\n"
        f"This can use 1–2 GB of RAM and most of your {cores} CPU cores. Know these results:\n"
        f"  •  Other programs and games can become slow.\n"
        f"  •  A laptop gets hot. Its fans get loud. Its battery empties faster.\n"
        f"  •  The PC uses more electricity.\n"
        f"  •  More computing does not give more profit. You can lose real money.\n\n"
        f"The bots run at low priority. You can change the number of bots or the power on the Swarm page.",
        f"Money Tree {bots} strateji botunu ayrı işlemler olarak çalıştırır. Her bot gerçek fiyatlarla saniyede "
        f"binlerce strateji dener. Araştırma masası ayrıca SEC raporlarını ve tüm piyasanın haberlerini okur.\n\n"
        f"Bu, 1–2 GB RAM ve {cores} işlemci çekirdeğinin çoğunu kullanabilir. Sonuçları bil:\n"
        f"  •  Başka programlar ve oyunlar yavaşlayabilir.\n"
        f"  •  Dizüstü ısınır. Fanları ses yapar. Pili daha hızlı biter.\n"
        f"  •  Bilgisayar daha çok elektrik harcar.\n"
        f"  •  Daha çok hesaplama daha çok kâr vermez. Gerçek para kaybedebilirsin.\n\n"
        f"Botlar düşük öncelikte çalışır. Bot sayısını ya da gücü Sürü sayfasından değiştirebilirsin."))
    body.setObjectName("body")
    body.setWordWrap(True)
    remember = QCheckBox(t("Don't show this again", "Bunu bir daha gösterme"))

    buttons = QHBoxLayout()
    full = QPushButton(t(f"Full power — {bots} bots", f"Tam güç — {bots} bot"))
    full.setObjectName("full")
    light = QPushButton(t("Light — 2 bots", "Hafif — 2 bot"))
    light.setObjectName("light")
    quit_ = QPushButton(t("Quit", "Çık"))
    quit_.setObjectName("quit")
    for b in (full, light):
        b.setCursor(Qt.CursorShape.PointingHandCursor)
    buttons.addWidget(quit_)
    buttons.addStretch(1)
    buttons.addWidget(light)
    buttons.addWidget(full)

    for widget in (warn, title, body, remember):
        layout.addWidget(widget)
    layout.addLayout(buttons)

    result: dict = {}
    full.clicked.connect(lambda: (result.update(choice=(bots, "full")), dialog.accept()))
    light.clicked.connect(lambda: (result.update(choice=(2, "light")), dialog.accept()))
    quit_.clicked.connect(dialog.reject)
    full.setDefault(True)

    if dialog.exec() != QDialog.DialogCode.Accepted or "choice" not in result:
        return None
    count, power = result["choice"]
    return count, power, remember.isChecked()
