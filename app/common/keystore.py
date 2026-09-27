"""API keys typed into the app, kept encrypted on disk.

On Windows each value is sealed with DPAPI (CryptProtectData) under the current
Windows user: the file is unreadable to other accounts and to anyone who copies
it to another machine, and no password is needed because Windows holds the key.
This replaces pasting keys into .env by hand; values in .env still work and are
used when nothing has been saved here.

Only presence and the last four characters ever leave this module towards the
dashboard. The full value is handed to the broker client and nowhere else.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import sys
import threading
from pathlib import Path

log = logging.getLogger(__name__)

NAMES = (
    "alpaca_paper_key", "alpaca_paper_secret",
    "alpaca_live_key", "alpaca_live_secret",
    "groq_api_key", "gemini_api_key", "anthropic_api_key",
)

# Mixed into every DPAPI call so a blob sealed by some other program for the
# same Windows user cannot be swapped in and opened here.
_ENTROPY = b"money-tree-ai/keystore/v1"


class KeyStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self._values = self._load()

    # ---------------------------------------------------------------- public

    def get(self, name: str) -> str | None:
        with self._lock:
            return self._values.get(name)

    def set(self, name: str, value: str | None) -> None:
        if name not in NAMES:
            raise ValueError(f"unknown key name: {name}")
        with self._lock:
            cleaned = (value or "").strip()
            if cleaned:
                self._values[name] = cleaned
            else:
                self._values.pop(name, None)
            self._save()

    def delete(self, name: str) -> None:
        self.set(name, None)

    def describe(self) -> dict[str, dict]:
        """What the dashboard may know: is it set, and how does it end."""
        with self._lock:
            return {
                name: {"set": name in self._values, "tail": _tail(self._values.get(name))}
                for name in NAMES
            }

    # --------------------------------------------------------------- storage

    def _load(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        try:
            sealed = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            log.warning("key store unreadable; starting empty")
            return {}
        values: dict[str, str] = {}
        for name, blob in sealed.items():
            if name not in NAMES:
                continue
            try:
                values[name] = _unseal(base64.b64decode(blob)).decode("utf-8")
            except Exception:
                # Sealed by another Windows user, another PC, or damaged.
                log.warning("could not open saved %s; it needs to be entered again", name)
        return values

    def _save(self) -> None:
        sealed = {
            name: base64.b64encode(_seal(value.encode("utf-8"))).decode("ascii")
            for name, value in self._values.items()
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(sealed, indent=1), encoding="utf-8")
        if not sys.platform.startswith("win"):
            os.chmod(tmp, 0o600)
        tmp.replace(self.path)


def _tail(value: str | None) -> str | None:
    return value[-4:] if value and len(value) >= 8 else None


# ------------------------------------------------------------------- DPAPI

if sys.platform.startswith("win"):
    import ctypes
    from ctypes import wintypes

    class _Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    _crypt32 = ctypes.windll.crypt32
    _kernel32 = ctypes.windll.kernel32
    _CRYPTPROTECT_UI_FORBIDDEN = 0x01

    def _blob(data: bytes) -> tuple[_Blob, ctypes.Array]:
        # The buffer is returned alongside the blob so the caller holds it for
        # the whole call; a blob pointing into a collected buffer reads garbage.
        buffer = ctypes.create_string_buffer(data, len(data))
        return _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))), buffer

    def _call(fn, data: bytes) -> bytes:
        (source, _keep1), (entropy, _keep2), out = _blob(data), _blob(_ENTROPY), _Blob()
        ok = fn(ctypes.byref(source), None, ctypes.byref(entropy), None, None,
                _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out))
        if not ok:
            raise OSError(f"DPAPI call failed ({ctypes.GetLastError()})")
        try:
            return ctypes.string_at(out.pbData, out.cbData)
        finally:
            _kernel32.LocalFree(out.pbData)

    def _seal(data: bytes) -> bytes:
        return _call(_crypt32.CryptProtectData, data)

    def _unseal(data: bytes) -> bytes:
        return _call(_crypt32.CryptUnprotectData, data)

else:
    # No DPAPI off Windows. The file is still owner-only (0600); say so plainly
    # rather than pretend it is encrypted.
    def _seal(data: bytes) -> bytes:
        return data

    def _unseal(data: bytes) -> bytes:
        return data
