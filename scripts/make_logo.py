"""Render the Money Tree AI fear-light emblem everywhere it is needed.

    python scripts/make_logo.py

assets/mark.svg is the source: a money tree inside a burning yellow ring with
sixteen blades of light (an original mark, 3.0). This writes:

  assets/logo.png        640 px, the app and Telegram avatar
  assets/logo.ico        Windows exe and shortcut icon (several sizes)
  assets/pfp.png         1024 px square, full-bleed — a profile picture
  app/web/static/...     favicon, home-screen icons and the dashboard's mark

Telegram has no API for a bot to set its own picture: send logo.png to
@BotFather with /setuserpic.
"""
from __future__ import annotations

import shutil
import struct
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
STATIC = ROOT / "app" / "web" / "static"
SOURCE = ASSETS / "mark.svg"


def render(size: int, square: bool = False) -> QImage:
    svg = SOURCE.read_text(encoding="utf-8")
    if square:
        # Full-bleed for places that crop to their own shape (Android, profile pictures).
        svg = svg.replace('rx="112"', 'rx="0"')
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    renderer.render(painter)
    painter.end()
    return image


def png_bytes(image: QImage) -> bytes:
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    buffer.close()
    return bytes(data)


def write_ico(path: Path, sizes: tuple[int, ...]) -> None:
    """A Windows icon with one PNG picture per size (Windows Vista and later)."""
    pictures = [(size, png_bytes(render(size))) for size in sizes]
    header = struct.pack("<HHH", 0, 1, len(pictures))
    offset = 6 + 16 * len(pictures)
    entries, blobs = b"", b""
    for size, blob in pictures:
        edge = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", edge, edge, 0, 0, 1, 32, len(blob), offset)
        offset += len(blob)
        blobs += blob
    path.write_bytes(header + entries + blobs)


def main() -> None:
    QGuiApplication.instance() or QGuiApplication(sys.argv)
    render(640).save(str(ASSETS / "logo.png"), "PNG")
    render(640).save(str(ASSETS / "bot-avatar.png"), "PNG")
    render(1024, square=True).save(str(ASSETS / "pfp.png"), "PNG")
    # Windows picks the size it needs out of the .ico, so it gets every size:
    # one 256 px picture alone shows blank or blurred in small places.
    write_ico(ASSETS / "logo.ico", (16, 20, 24, 32, 40, 48, 64, 96, 128, 256))
    render(256).save(str(STATIC / "logo.png"), "PNG")
    render(192).save(str(STATIC / "icon-192.png"), "PNG")
    render(512).save(str(STATIC / "icon-512.png"), "PNG")
    render(512, square=True).save(str(STATIC / "icon-maskable-512.png"), "PNG")
    shutil.copy2(SOURCE, STATIC / "mark.svg")
    for name in ("logo.png", "logo.ico", "pfp.png"):
        print(f"wrote {ASSETS / name}")
    print("\nTelegram: @BotFather -> /setuserpic -> send assets/logo.png")


if __name__ == "__main__":
    main()
