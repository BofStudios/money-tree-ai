"""Where the app keeps what it knows, so an update never starts it from zero.

Before 6.0 every copy kept its keys, settings and learning beside its own exe.
Each new version went into a new folder, so each one started with no keys, no
learning and no history. Now there is one home per Windows user, and every
version uses it:

  exe            %LOCALAPPDATA%\\BofStudios\\Money Tree AI
  portable exe   the exe's own folder, when a file named portable.txt is there
  source run     the repository folder, as before
  MONEYTREE_HOME overrides all of them (tests, a copy on a USB stick)

The first start of an exe on a PC without a home copies (never moves) the
data/, config/config.yaml and .env of the old layout beside the exe, so the
owner's keys and learning come along. The old files stay where they were.

Only the standard library: this runs before the heavy imports.
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import sys
import time
from pathlib import Path

ENV = "MONEYTREE_HOME"
FROZEN = getattr(sys, "frozen", False)
MARKER = ".home"
# What makes a data folder worth keeping: keys, trades or learning.
STATE_FILES = ("keys.dat", "trading.db", "brain/brain.json", "brain/swarm.json", "user_profile.json")


def install_dir() -> Path:
    """The folder of the exe, or the repository when run from source."""
    if FROZEN:
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent.parent


def root() -> Path:
    env = os.environ.get(ENV, "").strip()
    if env:
        return Path(env)
    here = install_dir()
    if not FROZEN or (here / "portable.txt").exists():
        return here
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "BofStudios" / "Money Tree AI"


def has_state(data: Path) -> bool:
    return any((data / name).exists() for name in STATE_FILES)


def migrate(home: Path | None = None, legacy: Path | None = None) -> list[str]:
    """Copy the old beside-the-exe data into the home, once. Returns what was copied.

    Only an exe has the old layout. A source run (the repository, or a test or
    sandbox with MONEYTREE_HOME) never copies the repository's own data."""
    if legacy is None and not FROZEN:
        return []
    home = Path(home or root())
    legacy = Path(legacy or install_dir())
    try:
        if home.resolve() == legacy.resolve():
            return []
    except OSError:
        return []
    marker = home / "data" / MARKER
    if marker.exists():
        return []
    copied: list[str] = []
    old = legacy / "data"
    if old.is_dir() and has_state(old) and not has_state(home / "data"):
        for src in sorted(old.rglob("*")):
            if src.is_dir() or src.suffix == ".tmp" or src.name in ("gpu.off", MARKER):
                continue
            dst = home / "data" / src.relative_to(old)
            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                if src.suffix == ".db":
                    copy_sqlite(src, dst)
                else:
                    shutil.copy2(src, dst)
                copied.append(str(src.relative_to(legacy)))
            except OSError:
                continue
    for rel in ("config/config.yaml", ".env"):
        src, dst = legacy / rel, home / rel
        if src.is_file() and not dst.exists():
            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                copied.append(rel)
            except OSError:
                pass
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(
            "Money Tree AI keeps its keys, settings and learning in this folder.\n"
            f"Set up {time.strftime('%Y-%m-%d %H:%M')}."
            + (f" Copied from {legacy}.\n" if copied else "\n"),
            encoding="utf-8",
        )
    except OSError:
        pass
    return copied


def copy_sqlite(src: Path, dst: Path) -> None:
    """A consistent copy of a database another copy of the app may still have open."""
    tmp = dst.with_suffix(".copying")
    try:
        source = sqlite3.connect(f"file:{src.as_posix()}?mode=ro", uri=True, timeout=10)
        try:
            target = sqlite3.connect(str(tmp))
            try:
                source.backup(target)
            finally:
                target.close()
        finally:
            source.close()
        os.replace(tmp, dst)
    except sqlite3.Error:
        tmp.unlink(missing_ok=True)
        shutil.copy2(src, dst)
