"""Start Money Tree AI automatically when Windows starts.

    python scripts/install_startup.py           # add it
    python scripts/install_startup.py --remove   # take it out again

This is what "24/7" means on a home PC: the bot comes back up on its own after a
reboot. It still stops when the machine is off or asleep — for genuinely
uninterrupted running you need a machine that never sleeps, or a small VPS.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME = "Money Tree AI"

STARTUP = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def target() -> Path:
    """Prefer the built exe; fall back to the .bat that runs from source."""
    exe = ROOT / "dist" / NAME / f"{NAME}.exe"
    return exe if exe.exists() else ROOT / f"{NAME}.bat"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Money Tree AI at login")
    parser.add_argument("--remove", action="store_true")
    args = parser.parse_args()

    if not sys.platform.startswith("win"):
        raise SystemExit("This only applies to Windows.")
    if not STARTUP.exists():
        raise SystemExit(f"Could not find the Startup folder at {STARTUP}")

    link = STARTUP / f"{NAME}.lnk"

    if args.remove:
        if link.exists():
            link.unlink()
            print(f"removed {link}")
        else:
            print("nothing to remove")
        return

    launcher = target()
    if not launcher.exists():
        raise SystemExit(
            f"Could not find {launcher}.\n"
            "Build the exe first (python scripts/build_exe.py), or keep the .bat in place."
        )

    # A .lnk needs the Windows shell; PowerShell is the least painful way in.
    import subprocess

    script = (
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut('%s');"
        "$s.TargetPath = '%s';"
        "$s.WorkingDirectory = '%s';"
        "$s.IconLocation = '%s';"
        "$s.Description = 'Money Tree AI trading bot';"
        "$s.Save()"
    ) % (link, launcher, launcher.parent, ROOT / "assets" / "logo.ico")

    subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True)
    print(f"added {link}")
    print(f"  -> {launcher}")
    print("\nIt will start on your next login. Remove it with --remove.")


if __name__ == "__main__":
    main()
