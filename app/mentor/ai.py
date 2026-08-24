"""The mentor voice: turns bot state into real explanation, and holds a conversation.

This used to be Claude-only. It now speaks through whichever provider is
configured — including free ones that cost nothing to run — and it remembers
what the owner has told it across restarts.

Without any working provider every method returns None and the rule-based
narrator carries on alone, so this is always safe to leave switched off.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path

from app.config import MentorConfig
from app.mentor.memory import MentorMemory
from app.mentor.providers import build

log = logging.getLogger(__name__)

MIN_SECONDS_BETWEEN_COMMENTARY = 900  # cost guard: at most one market read per 15 min

# Answers are meant to be a few short paragraphs in a chat bubble, so this is
# deliberately small rather than the usual default.
ANSWER_TOKENS = 1500
COMMENTARY_TOKENS = 900

SYSTEM_PROMPT = """You are the mentor voice inside a personal algorithmic trading bot.
You explain what the bot is doing and why, to the one person who owns and runs it.

How the bot works, so you describe it accurately:
- It trades US stocks on a mechanical EMA-crossover strategy with an RSI filter.
- Stop distance is set from ATR (how much the symbol actually moves), not a flat
  percentage, and the take-profit is a fixed multiple of that stop distance.
- Position size is derived from risk: a fixed fraction of equity is put at risk per
  trade, and the share count falls out of the stop distance. A wider stop means fewer
  shares, not more money at risk.
- A trailing stop follows a winning trade once it is up by a set amount.
- Protections pause new entries: a cooldown after each trade, a halt after several
  stop-outs in a row, and a halt if the recent equity curve drops too far.
- There is a daily loss limit that disarms live trading, and live trading always
  starts disarmed.
- In paper mode the money is simulated. In signal mode the bot holds no money at all
  and the owner places trades themselves in Midas, which has no API.
- The owner may run a "challenge": a small stake with a target, traded on its own
  ring-fenced bankroll.
- A "catalyst" is a dated event the owner is trading around. The bot counts down to
  it and shows the real headlines, but never trades it automatically.

Hard rules for you:
- Only use numbers that appear in the state you are given. Never estimate, extrapolate,
  or invent a price, indicator value, or performance figure. If something is not in the
  state, say you do not have it.
- Never predict where a price will go. You explain the bot's mechanical logic and the
  measured present, not the future.
- You are not a financial adviser and this is not investment advice. Explain what the
  rules did and why; do not tell the owner what they personally ought to invest in, and
  do not encourage bigger positions or more risk.
- If the state shows the strategy losing money, say so plainly. Never spin results.
- Never describe simulated money as if it were real. If the mode is paper or signal,
  and the owner sounds like they think the balance is real, correct them.
- The owner is a beginner. Prefer plain words over jargon, and when you must use a term,
  explain it in the same breath.

Style: calm, concrete, conversational. Short paragraphs. Talk like a colleague looking
at the same screen, not like a marketing page. No hype, no emoji, no exclamation marks."""


class AIMentor:
    """Explains the bot, answers questions, and remembers the answers."""

    def __init__(
        self,
        config: MentorConfig,
        keys: dict[str, str] | None = None,
        memory_path: Path | str | None = None,
    ) -> None:
        self.config = config
        self._lock = threading.Lock()
        self._last_commentary_at = 0.0
        self.memory = MentorMemory(
            Path(memory_path or "data/mentor_memory.json"), config.memory_turns
        )

        self.provider = None
        if config.enabled:
            try:
                self.provider = build(config.provider, keys or {}, config.model)
            except Exception:
                log.exception("could not start the mentor; staying rule-based")

        if self.provider is not None and self.provider.available():
            log.info("mentor enabled: %s (%s)", self.provider.name, self.provider.model)
        else:
            log.info("mentor has no working provider; rule-based narration only")

    # ------------------------------------------------------------- introspect

    @property
    def available(self) -> bool:
        return self.provider is not None and self.provider.available()

    @property
    def backend(self) -> dict:
        """What the dashboard shows about who is actually answering."""
        if self.provider is None:
            return {"provider": None, "model": None, "available": False, "free": False}
        return {
            "provider": self.provider.name,
            "model": self.provider.model,
            "available": self.provider.available(),
            "free": self.provider.name != "anthropic",
        }

    # ------------------------------------------------------------------ public

    def answer(self, question: str, state: dict) -> str | None:
        """Reply to the owner, remembering what was already said."""
        if not self.available:
            return None

        # State goes in every turn because it moves between messages; the stored
        # history carries the thread of the conversation across restarts.
        turns = self.memory.turns() + [
            {"role": "user", "content": f"Current bot state:\n{_render(state)}\n\n{question}"}
        ]
        reply = self._send(turns, ANSWER_TOKENS)
        if reply is None:
            return None

        self.memory.record(question, reply)
        return reply

    def commentary(self, state: dict, force: bool = False) -> str | None:
        """A periodic read of the whole book. Rate limited to keep costs sane."""
        if not self.available:
            return None
        with self._lock:
            elapsed = time.monotonic() - self._last_commentary_at
            if not force and elapsed < MIN_SECONDS_BETWEEN_COMMENTARY:
                return None
            self._last_commentary_at = time.monotonic()

        return self._send(
            [{
                "role": "user",
                "content": (
                    f"Here is the bot's current state.\n\n{_render(state)}\n\n"
                    "In two or three short paragraphs, tell me what is going on right "
                    "now: what the watchlist looks like, what the open positions are "
                    "doing, and whether the strategy is behaving as designed. Be "
                    "specific about the numbers you can see."
                ),
            }],
            COMMENTARY_TOKENS,
        )

    def explain_trade(self, trade: dict, state: dict) -> str | None:
        if not self.available:
            return None
        return self._send(
            [{
                "role": "user",
                "content": (
                    f"State:\n{_render(state)}\n\nThe bot just closed this trade:\n"
                    f"{json.dumps(trade, indent=2, default=str)}\n\n"
                    "In one short paragraph, explain what happened and what the rules "
                    "did. If it was a loss, say so plainly and note which rule limited "
                    "the damage."
                ),
            }],
            600,
        )

    def reset(self) -> None:
        self.memory.clear_history()

    # --------------------------------------------------------------- internals

    def _send(self, messages: list[dict], max_tokens: int) -> str | None:
        # Facts are appended to the system prompt rather than the messages so they
        # keep their standing-context authority and survive history trimming.
        system = SYSTEM_PROMPT + self.memory.as_prompt()
        reply = self.provider.chat(system, messages, max_tokens)
        return reply.text if reply else None


def _render(state: dict) -> str:
    try:
        return json.dumps(state, indent=2, default=str)[:12000]
    except Exception:
        return str(state)[:12000]
