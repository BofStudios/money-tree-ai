"""The owner's privacy choices (10.1), kept on this PC in data/privacy.json.

  lan            phone access: the dashboard listens on the home network, not
                 only on this PC. Off for a new install. An install that
                 already existed keeps it on until the owner is asked once.
  ai_level       what the AI may see of the account:
                   full     today's behaviour: amounts, positions, trades
                   percent  only percentages and symbols: no balance, no
                            share counts, no dollar profit or loss
                   none     only the question you typed (and screenshots you add)
  remember_chat  keep the conversation with the AI on this PC between runs
  gemini_images  let screenshots go to Google's free Gemini when Groq cannot
                 read them (Google may use free-tier data and people may read it)
  log_days       how long log files are kept
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

log = logging.getLogger(__name__)

AI_LEVELS = ("full", "percent", "none")
DEFAULTS = {
    "lan": False,
    "lan_asked": True,
    "ai_level": "full",
    "remember_chat": True,
    "gemini_images": False,
    "log_days": 14,
}
LOG_DAYS = (1, 7, 14, 30, 90)


class Prefs:
    def __init__(self, path: Path | str, existing_install: bool = False) -> None:
        self.path = Path(path)
        self._existing = existing_install
        self._lock = threading.Lock()
        self._data = self._load()

    def _load(self) -> dict:
        data = dict(DEFAULTS)
        try:
            saved = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                data.update({k: v for k, v in saved.items() if k in DEFAULTS and self._valid(k, v)})
            return data
        except FileNotFoundError:
            if self._existing:
                data.update(lan=True, lan_asked=False)      # keep phone access until the owner chooses
            return data
        except Exception:
            log.warning("privacy choices could not be read; using the safe defaults")
            return data

    @staticmethod
    def _valid(key: str, value) -> bool:
        if key == "ai_level":
            return value in AI_LEVELS
        if key == "log_days":
            return value in LOG_DAYS
        return isinstance(value, bool)

    def get(self, key: str):
        with self._lock:
            return self._data[key]

    def all(self) -> dict:
        with self._lock:
            return dict(self._data)

    def update(self, changes: dict) -> dict:
        """Apply known keys with valid values. Raises ValueError on a wrong one."""
        for key, value in changes.items():
            if key not in DEFAULTS:
                raise ValueError(f"unknown choice: {key}")
            if not self._valid(key, value):
                raise ValueError(f"wrong value for {key}")
        with self._lock:
            self._data.update(changes)
            if "lan" in changes:
                self._data["lan_asked"] = True
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                tmp = self.path.with_suffix(".tmp")
                tmp.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
                tmp.replace(self.path)
            except OSError:
                log.exception("could not save the privacy choices")
            return dict(self._data)
