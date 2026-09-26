"""Draw the Money Tree AI mark.

    python scripts/make_logo.py

Writes assets/logo.png (app + Telegram avatar), assets/logo.ico (Windows exe)
and assets/mark.svg (the dashboard header). Telegram has no API for a bot to set
its own picture, so send logo.png to @BotFather with /setuserpic.

The mark is a tree: a canopy of green discs in two shades so it has depth, a
white trunk that tapers as it rises, and a dollar sign sitting in the crown.
Everything is drawn from fractions of the canvas, so the same geometry holds at
16px in a browser tab and at 640px as an app icon.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QGuiApplication,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
STATIC = ROOT / "app" / "web" / "static"

BLACK = QColor("#000000")
WHITE = QColor("#ffffff")
GREEN = QColor("#32d583")
GREEN_DEEP = QColor("#1f9d63")  # the shaded half of the canopy

# Canopy discs as (cx, cy, r) fractions. The deep set sits lower and behind the
# bright set, which is what gives the crown its roundness.
CANOPY_BACK = [(0.325, 0.435, 0.155), (0.675, 0.435, 0.155), (0.50, 0.485, 0.165)]
CANOPY_FRONT = [(0.345, 0.36, 0.135), (0.655, 0.36, 0.135), (0.50, 0.275, 0.158)]


def _dollar(size: int) -> tuple[QPainterPath, QPainterPath]:
    """The S and the bar of a dollar sign, centred in the crown."""
    s = QPainterPath()
    s.moveTo(size * 0.56, size * 0.215)
    s.cubicTo(size * 0.56, size * 0.18, size * 0.533, size * 0.16, size * 0.50, size * 0.16)
    s.cubicTo(size * 0.467, size * 0.16, size * 0.44, size * 0.178, size * 0.44, size * 0.21)
    s.cubicTo(size * 0.44, size * 0.242, size * 0.467, size * 0.256, size * 0.50, size * 0.27)
    s.cubicTo(size * 0.533, size * 0.284, size * 0.56, size * 0.298, size * 0.56, size * 0.33)
    s.cubicTo(size * 0.56, size * 0.362, size * 0.533, size * 0.38, size * 0.50, size * 0.38)
    s.cubicTo(size * 0.467, size * 0.38, size * 0.44, size * 0.36, size * 0.44, size * 0.325)

    bar = QPainterPath()
    bar.moveTo(size * 0.50, size * 0.132)
    bar.lineTo(size * 0.50, size * 0.408)
    return s, bar


def _trunk(size: int) -> QPainterPath:
    """A trunk that is wider at the roots than where it meets the canopy."""
    path = QPainterPath()
    path.moveTo(size * 0.436, size * 0.855)
    path.cubicTo(size * 0.442, size * 0.73, size * 0.466, size * 0.63, size * 0.472, size * 0.53)
    path.lineTo(size * 0.528, size * 0.53)
    path.cubicTo(size * 0.534, size * 0.63, size * 0.558, size * 0.73, size * 0.564, size * 0.855)
    path.closeSubpath()
    return path


def draw(size: int, rounded: bool = True) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    p.setBrush(QBrush(BLACK))
    p.setPen(Qt.PenStyle.NoPen)
    if rounded:
        p.drawRoundedRect(QRectF(0, 0, size, size), size * 0.235, size * 0.235)
    else:
        p.drawRect(QRectF(0, 0, size, size))

    # trunk and roots first, so the canopy overlaps where they meet
    p.setBrush(QBrush(WHITE))
    p.drawPath(_trunk(size))

    pen = QPen(WHITE)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setBrush(Qt.BrushStyle.NoBrush)

    pen.setWidthF(size * 0.046)
    p.setPen(pen)
    p.drawLine(QPointF(size * 0.385, size * 0.855), QPointF(size * 0.615, size * 0.855))

    # two branches reaching up into the crown
    pen.setWidthF(size * 0.042)
    p.setPen(pen)
    p.drawLine(QPointF(size * 0.50, size * 0.60), QPointF(size * 0.385, size * 0.495))
    p.drawLine(QPointF(size * 0.50, size * 0.555), QPointF(size * 0.615, size * 0.455))

    # canopy
    p.setPen(Qt.PenStyle.NoPen)
    for colour, discs in ((GREEN_DEEP, CANOPY_BACK), (GREEN, CANOPY_FRONT)):
        p.setBrush(QBrush(colour))
        for cx, cy, r in discs:
            p.drawEllipse(QPointF(size * cx, size * cy), size * r, size * r)

    # the dollar sitting in the crown
    s, bar = _dollar(size)
    pen = QPen(WHITE)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    pen.setWidthF(size * 0.032)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(s)
    pen.setWidthF(size * 0.028)
    p.setPen(pen)
    p.drawPath(bar)

    p.end()
    return pixmap


SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" fill="none">
  <path d="M43.6 85.5 C44.2 73 46.6 63 47.2 53 L52.8 53 C53.4 63 55.8 73 56.4 85.5 Z"
        fill="currentColor"/>
  <path d="M38.5 85.5 H61.5" stroke="currentColor" stroke-width="4.6" stroke-linecap="round"/>
  <path d="M50 60 L38.5 49.5 M50 55.5 L61.5 45.5" stroke="currentColor"
        stroke-width="4.2" stroke-linecap="round"/>
  <g fill="#1f9d63">
    <circle cx="32.5" cy="43.5" r="15.5"/>
    <circle cx="67.5" cy="43.5" r="15.5"/>
    <circle cx="50" cy="48.5" r="16.5"/>
  </g>
  <g fill="#32d583">
    <circle cx="34.5" cy="36" r="13.5"/>
    <circle cx="65.5" cy="36" r="13.5"/>
    <circle cx="50" cy="27.5" r="15.8"/>
  </g>
  <path d="M56 21.5 C56 18 53.3 16 50 16 C46.7 16 44 17.8 44 21 C44 24.2 46.7 25.6 50 27
           C53.3 28.4 56 29.8 56 33 C56 36.2 53.3 38 50 38 C46.7 38 44 36 44 32.5"
        stroke="#ffffff" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M50 13.2 V40.8" stroke="#ffffff" stroke-width="2.8" stroke-linecap="round"/>
</svg>
"""


def main() -> None:
    QGuiApplication([])
    ASSETS.mkdir(parents=True, exist_ok=True)

    draw(640).save(str(ASSETS / "logo.png"), "PNG")
    # Windows picks the size it needs out of the .ico, so ship several.
    icon = draw(256)
    icon.save(str(ASSETS / "logo.ico"), "ICO")
    (ASSETS / "mark.svg").write_text(SVG, encoding="utf-8")

    # keep the old filename working for anyone who already set it in BotFather
    draw(640).save(str(ASSETS / "bot-avatar.png"), "PNG")
    # the dashboard serves its favicon straight out of the static folder
    draw(256).save(str(STATIC / "logo.png"), "PNG")

    # Home-screen install on a phone. Rendered from the geometry at each size
    # rather than scaled from the 256 favicon, which would blur at 512.
    draw(192).save(str(STATIC / "icon-192.png"), "PNG")
    draw(512).save(str(STATIC / "icon-512.png"), "PNG")
    # Android crops "maskable" icons to its own shape, so this one is square
    # and full-bleed — its own rounding would otherwise show as a frame.
    draw(512, rounded=False).save(str(STATIC / "icon-maskable-512.png"), "PNG")

    print(f"wrote {ASSETS / 'logo.png'}")
    print(f"wrote {ASSETS / 'logo.ico'}")
    print(f"wrote {ASSETS / 'mark.svg'}")
    print("\nTelegram: @BotFather -> /setuserpic -> send assets/logo.png")


if __name__ == "__main__":
    main()
