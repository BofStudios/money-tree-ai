"""Build "Money Tree AI.exe" with PyInstaller, then the Windows installer.

    python scripts/build_exe.py              # the build you sell: needs licence ids
    python scripts/build_exe.py --personal   # your own copy: never asks for a key

The result lands in dist/. It is a one-folder build on purpose: a one-file build
has to unpack Qt's WebEngine runtime to a temp directory on every launch, which
makes startup slow and sometimes trips antivirus.

config/, .env and data/ stay outside the bundle so you can edit settings without
rebuilding — the exe reads them from beside itself. None of this machine's
keys, settings or data are ever copied in.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import __version__  # noqa: E402
from app.common import licensing  # noqa: E402

NAME = "Money Tree AI"
DIST = ROOT / "dist"
BUILD = ROOT / "build"
FLAG = ROOT / "app" / "_build.py"
ISS = ROOT / "installer" / "money-tree-ai.iss"
ISCC = [
    Path.home() / "AppData/Local/Programs/Inno Setup 6/ISCC.exe",
    Path("C:/Program Files (x86)/Inno Setup 6/ISCC.exe"),
    Path("C:/Program Files/Inno Setup 6/ISCC.exe"),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--personal", action="store_true",
                        help="build for your own PC: no licence check, no installer")
    args = parser.parse_args()

    if not args.personal and not licensing.configured():
        print("Licence ids are not set. Create the product on Lemon Squeezy, then put its\n"
              "STORE_ID and PRODUCT_ID in app/common/licensing.py.\n"
              "For a copy only you will use: python scripts/build_exe.py --personal")
        raise SystemExit(1)

    icon = ROOT / "assets" / "logo.ico"
    if not icon.exists():
        print("assets/logo.ico is missing — run: python scripts/make_logo.py")
        raise SystemExit(1)

    original = FLAG.read_text(encoding="utf-8")
    FLAG.write_text(f"PERSONAL = {args.personal}\n", encoding="utf-8")
    try:
        build_exe()
    finally:
        FLAG.write_text(original, encoding="utf-8")

    if not args.personal:
        build_installer()


def build_exe() -> None:
    for path in (DIST, BUILD):
        shutil.rmtree(path, ignore_errors=True)

    args = [
        sys.executable, "-m", "PyInstaller",
        "--name", NAME,
        "--noconsole",                      # no black terminal behind the window
        "--icon", str(ROOT / "assets" / "logo.ico"),
        "--noconfirm", "--clean",
        # The dashboard is loaded off disk at runtime, so it has to ship.
        "--add-data", f"{ROOT / 'app' / 'web' / 'static'}{os_sep()}app/web/static",
        "--add-data", f"{ROOT / 'assets'}{os_sep()}assets",
        # PyInstaller cannot see these — they are reached dynamically at runtime.
        "--hidden-import", "app.data.alpaca_data",
        "--hidden-import", "app.execution.alpaca_executor",
        "--hidden-import", "app.common.licensing",
        "--hidden-import", "app.gui.license",
        "--hidden-import", "app._build",
        # The swarm's bots run app.brain in their own processes.
        "--collect-submodules", "app.brain",
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
    refuse_secrets(target)

    print(f"\ndone -> {target / (NAME + '.exe')}")
    print("Keys go in the app: Settings -> Money & keys (or a .env next to the exe).")


# Anything that would carry this machine's keys, licence or history to a buyer.
PRIVATE = (".env", "keys.dat", "license.json", "config.yaml", "trading.db",
           "mentor_memory.json", "user_profile.json")


def refuse_secrets(target: Path) -> None:
    found = [p for p in target.rglob("*") if p.name in PRIVATE]
    if (target / "data").exists():
        found.append(target / "data")
    if found:
        listed = "\n  ".join(str(p.relative_to(target)) for p in found)
        print(f"STOP: private files ended up in the build:\n  {listed}")
        raise SystemExit(1)


def build_installer() -> None:
    iscc = next((p for p in ISCC if p.exists()), None)
    if iscc is None:
        print("Inno Setup is not installed, so no installer was made.\n"
              "  winget install JRSoftware.InnoSetup --scope user")
        raise SystemExit(1)
    # Launching the exe to try it writes data/ and logs/ beside it; never pack those.
    refuse_secrets(DIST / NAME)
    subprocess.run(
        [str(iscc), f"/DAppVersion={__version__}", f"/DSourceDir={DIST / NAME}", str(ISS)],
        check=True,
    )
    print(f"\ninstaller -> {DIST / f'MoneyTreeAI-Setup-{__version__}.exe'}")


def os_sep() -> str:
    return ";" if sys.platform.startswith("win") else ":"


if __name__ == "__main__":
    main()
