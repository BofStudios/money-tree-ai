"""The activation window a packaged copy shows until it holds a working key."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout,
)

from app.common.licensing import License, Verdict
from app.config import APP_NAME, ASSETS

STYLE = """
QDialog { background: #050505; border: 2px solid #ffd60a; }
QLabel { color: #f2f2f2; font-family: 'Segoe UI'; font-size: 13px; }
QLabel#title { color: #ffd60a; font-size: 22px; font-weight: 800; letter-spacing: 1px; }
QLabel#body { color: #bdbdbd; }
QLabel#error { color: #ff6b6b; font-size: 12px; font-weight: 600; }
QLineEdit { background: #121212; color: #f2f2f2; border: 1px solid #3a3a3a; border-radius: 10px;
            padding: 10px 12px; font-family: 'Consolas'; font-size: 14px; }
QLineEdit:focus { border-color: #ffd60a; }
QPushButton { border-radius: 10px; padding: 10px 18px; font-size: 13px; font-weight: 700; }
QPushButton#go { background: #ffd60a; color: #000; border: 0; }
QPushButton#go:hover { background: #ffe24d; }
QPushButton#go:disabled { background: #6b5d12; color: #222; }
QPushButton#quit { background: transparent; color: #8b8b90; border: 1px solid #333; }
"""

_TEXT = {
    "empty": ("Enter the licence key from your purchase email.",
              "Satın alma e-postandaki lisans anahtarını gir."),
    "offline": ("Could not reach the licence server. Check the internet connection and try again.",
                "Lisans sunucusuna ulaşılamadı. İnternet bağlantını kontrol edip tekrar dene."),
    "limit": ("This key is already active on the maximum number of computers. Deactivate it on another PC first.",
              "Bu anahtar izin verilen sayıda bilgisayarda zaten etkin. Önce başka bir bilgisayarda devre dışı bırak."),
    "not_found": ("That licence key was not recognised. Copy it exactly from the purchase email.",
                  "Bu lisans anahtarı tanınmadı. E-postadan birebir kopyala."),
    "expired": ("This licence has expired.", "Bu lisansın süresi dolmuş."),
    "disabled": ("This licence is no longer active (refunded or revoked).",
                 "Bu lisans artık etkin değil (iade edilmiş ya da iptal edilmiş)."),
    "other_product": ("This key belongs to a different product.", "Bu anahtar başka bir ürüne ait."),
    "stale": ("The licence has not been checked for two weeks. Connect to the internet once to continue.",
              "Lisans iki haftadır doğrulanamadı. Devam etmek için bir kez internete bağlan."),
    "refused": ("The licence server refused this key.", "Lisans sunucusu bu anahtarı reddetti."),
}


def explain(verdict: Verdict, turkish: bool) -> str:
    if verdict.reason == "refused" and verdict.detail:
        return verdict.detail
    en, tr = _TEXT.get(verdict.reason, ("", ""))
    return tr if turkish else en


def activate(lic: License, first: Verdict, turkish: bool) -> bool:
    """Show the window until a key works (True) or the owner quits (False)."""
    QApplication.instance() or QApplication([])
    t = (lambda en, tr: tr) if turkish else (lambda en, tr: en)

    dialog = QDialog()
    dialog.setWindowTitle(f"{APP_NAME} — " + t("activate", "etkinleştir"))
    dialog.setWindowIcon(QIcon(str(ASSETS / "logo.ico")))
    dialog.setStyleSheet(STYLE)
    dialog.setMinimumWidth(520)

    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(28, 26, 28, 22)
    layout.setSpacing(12)

    logo = QLabel()
    logo.setPixmap(QPixmap(str(ASSETS / "logo.png")).scaled(
        72, 72, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
    title = QLabel(t("Activate Money Tree AI", "Money Tree AI'ı etkinleştir"))
    title.setObjectName("title")
    body = QLabel(t(
        "Paste the licence key from your purchase email. The app checks it online one time. "
        "Then it also works offline. One key works on the number of PCs in your order.",
        "Satın alma e-postandaki lisans anahtarını yapıştır. Uygulama anahtarı bir kez internetten kontrol eder. "
        "Sonra internetsiz de çalışır. Bir anahtar, siparişindeki PC sayısı kadar çalışır."))
    body.setObjectName("body")
    body.setWordWrap(True)
    field = QLineEdit()
    field.setPlaceholderText("XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX")
    error = QLabel(explain(first, turkish) if first.reason else "")
    error.setObjectName("error")
    error.setWordWrap(True)

    buttons = QHBoxLayout()
    quit_ = QPushButton(t("Quit", "Çık"))
    quit_.setObjectName("quit")
    go = QPushButton(t("Activate", "Etkinleştir"))
    go.setObjectName("go")
    go.setDefault(True)
    go.setCursor(Qt.CursorShape.PointingHandCursor)
    buttons.addWidget(quit_)
    buttons.addStretch(1)
    buttons.addWidget(go)

    for widget in (logo, title, body, field, error):
        layout.addWidget(widget)
    layout.addLayout(buttons)

    def attempt() -> None:
        go.setEnabled(False)
        go.setText(t("Checking…", "Kontrol ediliyor…"))
        QApplication.processEvents()
        verdict = lic.activate(field.text())
        go.setEnabled(True)
        go.setText(t("Activate", "Etkinleştir"))
        if verdict.ok:
            dialog.accept()
        else:
            error.setText(explain(verdict, turkish))

    go.clicked.connect(attempt)
    field.returnPressed.connect(attempt)
    quit_.clicked.connect(dialog.reject)
    return dialog.exec() == QDialog.DialogCode.Accepted
