"""Write THIRD-PARTY-NOTICES.txt: every open-source part the exe ships, and its licence.

    python scripts/notices.py [output path]

Run by scripts/build_exe.py. The list comes from the installed packages'
own metadata, so it follows the real build, plus the parts that are not
Python packages (Qt, the chart library, Python itself).
"""
from __future__ import annotations

import sys
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

HEADER = """Money Tree AI - third-party notices
====================================

Money Tree AI includes open-source software. Each part keeps its own licence;
the copyright stays with its authors. The full licence texts ship inside the
program folder (_internal\\...\\*.dist-info\\LICENSE* and similar), or can be
read at each project's home page below.

Qt for Python (PySide6) and Qt
  Licence: GNU Lesser General Public License v3 (LGPL-3.0).
  Qt is used as separate libraries in the _internal folder; you may replace
  them with your own build of the same version. The source code of Qt and
  PySide6 is available at https://download.qt.io and
  https://code.qt.io/cgit/pyside/pyside-setup.git. Ask BofStudios for any
  help needed to relink.

TradingView Lightweight Charts(TM) 4.2.0
  Copyright (c) TradingView, Inc. Licence: Apache License 2.0.
  Charts in this app are made with Lightweight Charts by TradingView:
  https://www.tradingview.com/

Python
  Copyright (c) Python Software Foundation. Licence: PSF License Agreement.

Python packages (name, version, licence, home page)
---------------------------------------------------
"""


def licence_of(dist: metadata.Distribution) -> str:
    meta = dist.metadata
    expression = meta.get("License-Expression")
    if expression:
        return expression
    text = (meta.get("License") or "").strip()
    if text and len(text) < 80 and "\n" not in text:
        return text
    classifiers = [c.split("::")[-1].strip() for c in meta.get_all("Classifier") or [] if c.startswith("License ::")]
    if classifiers:
        return ", ".join(dict.fromkeys(classifiers))
    return "see the package's licence file"


def home_of(dist: metadata.Distribution) -> str:
    meta = dist.metadata
    home = meta.get("Home-page")
    if home:
        return home
    for url in meta.get_all("Project-URL") or []:
        name, _, link = url.partition(",")
        if name.strip().lower() in ("homepage", "home", "source", "repository", "source code"):
            return link.strip()
    return ""


SKIP = {"pip", "setuptools", "wheel", "pyinstaller", "pyinstaller-hooks-contrib", "pytest", "pluggy",
        "iniconfig", "altgraph", "pefile", "pywin32-ctypes", "packaging"}


def build() -> str:
    rows = []
    for dist in metadata.distributions():
        name = dist.metadata.get("Name") or ""
        if not name or name.lower() in SKIP:
            continue
        rows.append((name.lower(), f"{name} {dist.version}\n  Licence: {licence_of(dist)}\n  {home_of(dist)}".rstrip()))
    rows.sort()
    return HEADER + "\n".join(r for _, r in dict(rows).items()) + "\n"


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "THIRD-PARTY-NOTICES.txt"
    out.write_text(build(), encoding="utf-8")
    print(f"notices -> {out}")


if __name__ == "__main__":
    main()
