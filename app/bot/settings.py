"""The owner's limits for the bot (12.0): budget, risk a trade, daily loss, positions, pace.

Every limit is optional: unset means the bot works exactly as before. A set
limit only ever makes the bot do less: the effective value is the stricter
of this and the engine's own rules. On the real account, loosening a limit
(or choosing the aggressive pace) needs confirm=true.

A pause the daily loss limit causes is kept by the engine's own risk counters;
nothing here can arm real money, and the armed state is never saved.
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

from app.bot import pace as P

log = logging.getLogger(__name__)

FIELDS = ("budget", "per_trade_pct", "daily_loss", "max_positions")
DEFAULTS: dict = {"budget": None, "per_trade_pct": None, "daily_loss": None, "max_positions": None, "pace": "balanced"}


class NeedsConfirm(Exception):
    """A real-account change that loosens a limit, sent without confirm."""


def _num(v) -> float | None:
    if v is None or v == "":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        raise ValueError(f"not a number: {v!r}") from None
    if f != f or f in (float("inf"), float("-inf")):
        raise ValueError("not a number")
    return f


def _looser(field: str, old, new) -> bool:
    if new is None:
        return old is not None          # removing a limit loosens it
    if old is None:
        return False                    # adding one tightens
    return new > old


class BotSettings:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._v = dict(DEFAULTS)
        self._load()

    def get(self, key: str):
        with self._lock:
            return self._v.get(key)

    def all(self) -> dict:
        with self._lock:
            return dict(self._v)

    def pace(self) -> P.Pace:
        return P.get(self.get("pace"))

    def update(self, changes: dict, equity: float, live: bool, confirm: bool = False) -> tuple[dict, list[str]]:
        """Check, clamp and save. Returns (the values now, the fields that were clamped)."""
        clamped: list[str] = []
        with self._lock:
            new = dict(self._v)
        cap_equity = max(float(equity or 0), 1.0)
        for field in FIELDS:
            if field not in changes:
                continue
            v = _num(changes[field])
            if v is not None:
                if field == "budget":
                    lo, hi = 1.0, cap_equity
                elif field == "per_trade_pct":
                    lo, hi = 0.25, 5.0
                elif field == "daily_loss":
                    base = new.get("budget") or cap_equity      # budget is checked first (FIELDS order)
                    lo, hi = 1.0, max(base * 0.2, 1.0)
                else:
                    lo, hi = 1, 5
                    v = round(v)
                fixed = min(max(v, lo), hi)
                if fixed != v:
                    clamped.append(field)
                v = round(fixed, 2) if field != "max_positions" else int(fixed)
            new[field] = v
        if "pace" in changes:
            if changes["pace"] not in P.IDS:
                raise ValueError("pace must be calm, balanced or aggressive")
            new["pace"] = changes["pace"]
        with self._lock:
            old = dict(self._v)
        if live and not confirm:
            loosened = [f for f in FIELDS if f in changes and _looser(f, old.get(f), new.get(f))]
            if new["pace"] == "aggressive" and old.get("pace") != "aggressive":
                loosened.append("pace")
            if loosened:
                raise NeedsConfirm(", ".join(loosened))
        with self._lock:
            self._v = new
        self._save()
        return dict(new), clamped

    def _load(self) -> None:
        if not self.path or not self.path.exists():
            return
        try:
            saved = json.loads(self.path.read_text(encoding="utf-8"))
            for k in DEFAULTS:
                if k in saved:
                    self._v[k] = saved[k]
            if self._v.get("pace") not in P.IDS:
                self._v["pace"] = "balanced"
        except (OSError, ValueError):
            log.warning("could not read the bot settings; using the defaults", exc_info=True)

    def _save(self) -> None:
        if not self.path:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.all(), indent=1), encoding="utf-8")
            tmp.replace(self.path)
        except OSError:
            log.warning("could not save the bot settings", exc_info=True)


def limit_buy(settings: BotSettings | None, *, equity: float, invested: float, open_count: int,
              realized_today: float, stop_pct: float | None, fallback_stop_pct: float) -> tuple[str | None, float | None]:
    """The owner's limits for one new buy: (the gate that refuses it, or None;
    the most it may spend, or None for no extra cap). Pure, so it is easy to test."""
    if settings is None:
        return None, None
    v = settings.all()
    if v.get("daily_loss") is not None and realized_today <= -float(v["daily_loss"]):
        return "daily_loss", None
    if v.get("max_positions") is not None and open_count >= int(v["max_positions"]):
        return "cap", None
    caps = []
    budget = v.get("budget")
    if budget is not None:
        caps.append(float(budget) - max(invested, 0.0))
    if v.get("per_trade_pct") is not None:
        base = float(budget) if budget is not None else float(equity or 0)
        stop = stop_pct if stop_pct and stop_pct > 0 else fallback_stop_pct
        caps.append(base * float(v["per_trade_pct"]) / 100.0 / (stop / 100.0))
    if not caps:
        return None, None
    return None, max(min(caps), 0.0)
