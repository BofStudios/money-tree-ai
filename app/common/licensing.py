"""Licence check for the packaged exe, against Lemon Squeezy's License API.

Running from source never asks: the code is MIT and anyone may build it. What
is sold is the ready-made installer, so only a frozen build checks a key.

The License API needs no secret, so nothing private ships inside the exe. Each
machine activates once (an "instance"); the product's activation limit on
Lemon Squeezy is what stops one key being handed around.
"""
from __future__ import annotations

import json
import logging
import socket
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import requests

log = logging.getLogger(__name__)

# Fill these in from the Lemon Squeezy dashboard once the product exists. A key
# from any other store or product is refused, even if Lemon Squeezy calls it valid.
STORE_ID = 0
PRODUCT_ID = 0

API = "https://api.lemonsqueezy.com/v1/licenses"
TIMEOUT = 10
RECHECK_AFTER = 24 * 3600        # ask the server at most once a day
OFFLINE_GRACE = 14 * 24 * 3600   # keep working this long without reaching it

Post = Callable[[str, dict], dict]


class Unreachable(Exception):
    """The licence server could not be asked: offline, timed out, or broken."""


@dataclass
class Verdict:
    ok: bool
    reason: str = ""            # a code from REASONS when ok is False; "" means never activated
    customer: str = ""
    detail: str = ""            # the server's own words, for a reason it did not name


REASONS = ("empty", "offline", "limit", "not_found", "expired", "disabled", "other_product", "stale", "refused")


def configured() -> bool:
    return bool(STORE_ID and PRODUCT_ID)


def post(path: str, data: dict) -> dict:
    try:
        response = requests.post(
            f"{API}/{path}", data=data, headers={"Accept": "application/json"}, timeout=TIMEOUT
        )
    except requests.RequestException as exc:
        raise Unreachable(str(exc)) from exc
    try:
        # A refused key comes back as 4xx with a JSON body that says why.
        return response.json()
    except ValueError as exc:
        raise Unreachable(f"HTTP {response.status_code}") from exc


def _ours(body: dict) -> bool:
    meta = body.get("meta") or {}
    return meta.get("store_id") == STORE_ID and meta.get("product_id") == PRODUCT_ID


class License:
    def __init__(self, path: Path | str, post: Post = post, clock: Callable[[], float] = time.time) -> None:
        self.path = Path(path)
        self._post = post
        self._now = clock

    # ---------------------------------------------------------------- public

    def activate(self, key: str) -> Verdict:
        key = key.strip()
        if not key:
            return Verdict(False, "empty")
        try:
            body = self._post("activate", {"license_key": key, "instance_name": socket.gethostname()})
        except Unreachable:
            return Verdict(False, "offline")
        if not body.get("activated"):
            return _refusal(body.get("error"))
        if not _ours(body):
            return Verdict(False, "other_product")
        self._save({
            "key": key,
            "instance_id": body["instance"]["id"],
            "customer": (body.get("meta") or {}).get("customer_name", ""),
            "checked_at": self._now(),
        })
        return Verdict(True, customer=self._load().get("customer", ""))

    def check(self) -> Verdict:
        """Whether this machine may start. Asks the server once a day; trusts
        the last answer for a while when it cannot be reached."""
        saved = self._load()
        if not saved.get("key") or not saved.get("instance_id"):
            return Verdict(False, "")
        age = self._now() - float(saved.get("checked_at", 0))
        if 0 <= age < RECHECK_AFTER:
            return Verdict(True, customer=saved.get("customer", ""))
        try:
            body = self._post("validate", {"license_key": saved["key"], "instance_id": saved["instance_id"]})
        except Unreachable:
            if 0 <= age < OFFLINE_GRACE:
                return Verdict(True, customer=saved.get("customer", ""))
            return Verdict(False, "stale")
        if not body.get("valid") or not _ours(body):
            self.forget()
            if body.get("valid"):
                return Verdict(False, "other_product")
            return _refusal(body.get("error"), default="disabled")
        saved["checked_at"] = self._now()
        self._save(saved)
        return Verdict(True, customer=saved.get("customer", ""))

    def deactivate(self) -> bool:
        """Free this machine's activation so the key can move to another PC."""
        saved = self._load()
        if not saved.get("key"):
            return True
        try:
            body = self._post("deactivate", {"license_key": saved["key"], "instance_id": saved.get("instance_id", "")})
        except Unreachable:
            return False
        if body.get("deactivated"):
            self.forget()
            return True
        return False

    def forget(self) -> None:
        self.path.unlink(missing_ok=True)

    # --------------------------------------------------------------- storage

    def _load(self) -> dict:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
        tmp.replace(self.path)


def _refusal(error: str | None, default: str = "refused") -> Verdict:
    text = (error or "").lower()
    for needle, reason in (
        ("limit", "limit"), ("not found", "not_found"), ("invalid", "not_found"),
        ("expired", "expired"), ("disabled", "disabled"), ("inactive", "disabled"),
    ):
        if needle in text:
            return Verdict(False, reason)
    return Verdict(False, default, detail=error or "")
