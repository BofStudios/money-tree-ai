"""What the mentor still knows after the app has been closed and reopened.

Two separate things live here, and the difference matters:

    facts    things the owner told it to remember, kept forever until removed
    history  the recent back-and-forth, trimmed to the last few turns

Chat APIs are stateless, so both are re-sent on every call. Facts go into the
system prompt (they are standing context), history goes into the messages (it is
the conversation). Everything is written to one JSON file so a restart, a crash,
or a rebuild of the exe does not wipe what the owner has taught it.
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

MAX_FACTS = 60
MAX_FACT_CHARS = 400


class MentorMemory:
    """Facts and conversation, persisted to disk."""

    def __init__(self, path: Path, keep_turns: int = 12) -> None:
        self.path = Path(path)
        self.keep_turns = keep_turns
        self._lock = threading.Lock()
        self._facts: list[dict] = []
        self._history: list[dict] = []
        self._load()

    # ------------------------------------------------------------------ disk

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            # A half-written file should not stop the app from starting.
            log.exception("could not read mentor memory; starting empty")
            return
        self._facts = [f for f in data.get("facts", []) if isinstance(f, dict) and f.get("text")]
        self._history = [
            m for m in data.get("history", [])
            if isinstance(m, dict) and m.get("role") in ("user", "assistant") and m.get("content")
        ]

    def _save(self) -> None:
        """Write through a temporary file so an interrupted save cannot corrupt it."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps({"facts": self._facts, "history": self._history}, indent=2),
                encoding="utf-8",
            )
            tmp.replace(self.path)
        except Exception:
            log.exception("could not save mentor memory")

    # ----------------------------------------------------------------- facts

    def remember(self, text: str) -> dict:
        text = " ".join(str(text).split())[:MAX_FACT_CHARS]
        if not text:
            raise ValueError("nothing to remember")

        with self._lock:
            # Saying the same thing twice should not make two entries.
            for fact in self._facts:
                if fact["text"].lower() == text.lower():
                    return dict(fact)
            fact = {"text": text, "added_at": datetime.now(timezone.utc).isoformat()}
            self._facts.append(fact)
            del self._facts[:-MAX_FACTS]
            self._save()
        return dict(fact)

    def forget(self, index: int) -> bool:
        with self._lock:
            if not 0 <= index < len(self._facts):
                return False
            self._facts.pop(index)
            self._save()
        return True

    def facts(self) -> list[dict]:
        with self._lock:
            return [dict(f) for f in self._facts]

    def as_prompt(self) -> str:
        """The facts as a block to append to the system prompt."""
        with self._lock:
            if not self._facts:
                return ""
            lines = "\n".join(f"- {f['text']}" for f in self._facts)
        return (
            "\n\nThings the owner has told you to remember. Treat these as standing "
            "context and let them shape your answers:\n" + lines
        )

    # --------------------------------------------------------------- history

    def turns(self) -> list[dict]:
        with self._lock:
            return [dict(m) for m in self._history]

    def record(self, question: str, answer: str) -> None:
        with self._lock:
            self._history.append({"role": "user", "content": question})
            self._history.append({"role": "assistant", "content": answer})
            keep = self.keep_turns * 2
            if keep:
                del self._history[:-keep]
            self._save()

    def clear_history(self) -> None:
        with self._lock:
            self._history.clear()
            self._save()

    def wipe(self) -> None:
        """Forget everything, facts included."""
        with self._lock:
            self._facts.clear()
            self._history.clear()
            self._save()
