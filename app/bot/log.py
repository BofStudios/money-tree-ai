"""agent.log: one numbered line per thing the engine really did.

The only way a line gets in is ``from_event``: the log subscribes to the
event bus and turns an event into at most one line. No event, no line.
Numbers never restart: the last one is read back from the file.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from collections import deque
from pathlib import Path

from app.bot.crew import ORDER_VERBS, RISK_VERBS, STEP_OWNER

log = logging.getLogger(__name__)

KEEP = 2000
MAX_BYTES = 5 * 1024 * 1024
QUIET_VERBS = ("scan", "note", "wait", "signal", "veto")
QUIET_S = 60
ACTED = ("signal", "order", "fill", "partial", "exit", "stop", "target", "veto", "pause", "lab", "learn", "thesis", "plan")
TABS = {"orders": ORDER_VERBS, "risk": RISK_VERBS}


def default_path() -> Path:
    from app.config import DATA_DIR

    return DATA_DIR / "bot" / "log.jsonl"


def _money(v) -> float | None:
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return None


def from_event(event: dict) -> dict | None:
    """The line for this event, without its number, or None."""
    kind = event.get("type")
    if kind == "step":
        step = event.get("step") if isinstance(event.get("step"), dict) else event
        state = step.get("state")
        if state not in ("done", "failed", "info"):
            return None          # still running: the line is written when it ends
        agent, verb = STEP_OWNER.get(step.get("kind") or "", ("orion", "note"))
        text = step.get("title") or ""
        if step.get("detail"):
            text = f"{text.rstrip('.:')}: {step['detail']}" if text else step["detail"]
        if not text:
            return None
        failed = state == "failed"
        level = "error" if failed else "warn" if step.get("kind") == "warn" else "info"
        return {"agent": agent, "verb": "error" if failed else verb, "text": text[:300], "symbol": None,
                "level": level, "ref": {"step": step.get("id")}, "money": None}
    if kind == "trade_opened":
        p = event.get("position") or {}
        symbol = p.get("symbol")
        qty, price = p.get("quantity", p.get("qty")), p.get("entry_price")
        return {"agent": "titan", "verb": "fill", "symbol": symbol, "level": "good",
                "text": f"{symbol} buy {qty:g} @ {price:,.2f} filled" if qty and price else f"{symbol} buy filled",
                "ref": {"position": symbol}, "money": None}
    if kind == "trade_closed":
        symbol = event.get("symbol")
        why = str(event.get("exit_reason") or "").lower()
        verb = "stop" if "stop" in why else "target" if ("target" in why or "profit" in why) else "exit"
        pnl, pct = _money(event.get("pnl")), _money(event.get("pnl_pct"))
        return {"agent": "luna", "verb": verb, "symbol": symbol,
                "level": "good" if (pnl or 0) > 0 else "bad" if (pnl or 0) < 0 else "info",
                "text": f"{symbol} closed ({event.get('exit_reason') or 'exit'})",
                "ref": {"trade": event.get("id")}, "money": {"pnl": pnl, "pct": pct}}
    if kind == "bot_plan":
        return {"agent": "orion", "verb": "plan", "symbol": None, "level": "info",
                "text": str(event.get("text") or "")[:300], "ref": {}, "money": None}
    if kind == "not_armed":
        return {"agent": "nova", "verb": "veto", "symbol": event.get("symbol"), "level": "warn",
                "text": "Real money is not armed: no order was sent", "ref": {"gate": "not_armed"}, "money": None}
    if kind == "error":
        return {"agent": "nova", "verb": "error", "symbol": None, "level": "error",
                "text": str(event.get("message") or event.get("error") or "error")[:300], "ref": {}, "money": None}
    return None


class AgentLog:
    def __init__(self, path: Path | None = None, events=None, now=time.time) -> None:
        self.path = path
        self.events = events
        self._now = now
        self._lock = threading.Lock()
        self._lines: deque[dict] = deque(maxlen=KEEP)
        self._quiet: dict[tuple, list] = {}
        self.head = 0
        self._load()
        if events is not None:
            events.subscribe(self._on_event)

    def _load(self) -> None:
        if not self.path or not self.path.exists():
            return
        try:
            for raw in self.path.read_text(encoding="utf-8").splitlines()[-KEEP:]:
                try:
                    line = json.loads(raw)
                except ValueError:
                    continue
                if isinstance(line, dict) and isinstance(line.get("n"), int):
                    self._lines.append(line)
                    self.head = max(self.head, line["n"])
        except OSError:
            log.warning("could not read the agent log", exc_info=True)

    def _on_event(self, event: dict) -> None:
        if event.get("type") == "bot_log":
            return
        try:
            line = from_event(event)
        except Exception:
            log.debug("agent log could not read an event", exc_info=True)
            return
        if line is None:
            return
        now = self._now()
        with self._lock:
            # The noise rule: the same agent saying the same kind of thing about the
            # same symbol within a minute is one line; the next one says how many.
            if line["verb"] in QUIET_VERBS:
                key = (line["agent"], line["verb"], line["symbol"], line["text"][:24])
                seen = self._quiet.get(key)
                if seen and now - seen[0] < QUIET_S:
                    seen[1] += 1
                    return
                if seen and seen[1]:
                    line["text"] = f"{line['text']} (×{seen[1] + 1})"
                self._quiet[key] = [now, 0]
            self.head += 1
            line = {"n": self.head, "at": int(now * 1000), **line}
            self._lines.append(line)
            self._append(line)
        if self.events is not None:
            self.events.publish("bot_log", {"line": line})

    def _append(self, line: dict) -> None:
        if not self.path:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.exists() and self.path.stat().st_size > MAX_BYTES:
                rows = self.path.read_text(encoding="utf-8").splitlines()
                self.path.write_text("\n".join(rows[len(rows) // 2:]) + "\n", encoding="utf-8")
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(line, ensure_ascii=False) + "\n")
        except OSError:
            log.debug("could not write the agent log", exc_info=True)

    def lines(self, after: int = 0, limit: int = 200, agent: str | None = None, tab: str | None = None,
              before: int | None = None) -> list[dict]:
        """after=n: the lines after n, oldest first (catching up). before=n: the
        `limit` lines just before n (scrolling back). Neither: the newest `limit`."""
        verbs = TABS.get(tab or "")
        with self._lock:
            rows = [l for l in self._lines
                    if l["n"] > after and (before is None or l["n"] < before)
                    and (not agent or l["agent"] == agent) and (verbs is None or l["verb"] in verbs)]
        limit = max(1, min(int(limit), 500))
        return rows[:limit] if after and before is None else rows[-limit:]

    def last_of(self, agent: str) -> dict | None:
        with self._lock:
            for line in reversed(self._lines):
                if line["agent"] == agent:
                    return line
        return None

    def count_today(self, agent: str, since_ms: int, acted: bool = False) -> int:
        with self._lock:
            return sum(1 for l in self._lines if l["agent"] == agent and l["at"] >= since_ms
                       and (not acted or l["verb"] in ACTED))

    def clear(self) -> None:
        with self._lock:
            self._lines.clear()
            if self.path:
                try:
                    self.path.unlink(missing_ok=True)
                except OSError:
                    pass
