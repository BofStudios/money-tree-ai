"""Build "Money Tree AI.exe" with PyInstaller.

    python scripts/build_exe.py

The result lands in dist/. It is a one-folder build on purpose: a one-file build
has to unpack Qt's WebEngine runtime to a temp directory on every launch, which
makes startup slow and sometimes trips antivirus.

config/, .env and data/ stay outside the bundle so you can edit settings without
rebuilding — the exe reads them from beside itself.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME = "Money Tree AI"
DIST = ROOT / "dist"
BUILD = ROOT / "build"


def main() -> None:
    icon = ROOT / "assets" / "logo.ico"
    if not icon.exists():
        print("assets/logo.ico is missing — run: python scripts/make_logo.py")
        raise SystemExit(1)

    for path in (DIST, BUILD):
        shutil.rmtree(path, ignore_errors=True)

    args = [
        sys.executable, "-m", "PyInstaller",
        "--name", NAME,
        "--noconsole",                      # no black terminal behind the window
        "--icon", str(icon),
        "--noconfirm", "--clean",
        # The dashboard is loaded off disk at runtime, so it has to ship.
        "--add-data", f"{ROOT / 'app' / 'web' / 'static'}{os_sep()}app/web/static",
        "--add-data", f"{ROOT / 'assets'}{os_sep()}assets",
        # PyInstaller cannot see these — they are reached dynamically at runtime.
        "--hidden-import", "app.data.alpaca_data",
        "--hidden-import", "app.execution.alpaca_executor",
        # uvicorn picks its event loop and protocol implementations by name.
        "--collect-submodules", "uvicorn",
        "--collect-all", "pandas_market_calendars",
        "--collect-all", "yfinance",
        "--collect-all", "alpaca",
        "--collect-all", "telegram",
        "--collect-all", "anthropic",
        "--collect-all", "curl_cffi",
        str(ROOT / "app" / "main.py"),
    ]

    print("building — this takes a few minutes\n")
    subprocess.run(args, cwd=ROOT, check=True)

    target = DIST / NAME
    # Ship editable settings next to the exe rather than frozen inside it —
    # the examples only, never this machine's own config.yaml or keys.
    config_out = target / "config"
    config_out.mkdir(parents=True, exist_ok=True)
    for example in (ROOT / "config").glob("*example*"):
        shutil.copy2(example, config_out / example.name)
    shutil.copy2(ROOT / "README.md", target / "README.md")

    print(f"\ndone -> {target / (NAME + '.exe')}")
    print("Copy the whole folder wherever you like, then make a shortcut to the exe.")
    print("Keys go in the app: Settings -> Money & keys (or a .env next to the exe).")


def os_sep() -> str:
    return ";" if sys.platform.startswith("win") else ":"


if __name__ == "__main__":
    main()
