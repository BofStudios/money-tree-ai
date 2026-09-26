"""How much the bot is allowed to do on its own, and how far ahead it looks.

Two settings the owner chooses during onboarding, both of which change what
the bot actually does — they are not labels:

AUTONOMY — who pulls the trigger on a *buy*.

    full    the bot buys by itself.
    semi    the bot asks first. Every buy waits for an Approve tap, in the app
            or in Telegram, and expires if nobody answers.
    manual  the bot never buys. It shows what it would have done, and the
            owner decides what, if anything, to do about it.

    Sells are automatic in every mode, deliberately. A stop-loss that waits for
    a tap while the price keeps falling is not a stop-loss. Switching to manual
    therefore stops *new* positions; anything already open is still protected.

HORIZON — which candles the strategy reads.

    short   15-minute bars: trades last minutes to hours
    medium  1-hour bars:    trades last days
    long    daily bars:     trades last weeks

    The strategy is the same EMA/RSI crossover at every horizon; what changes
    is how much time one bar represents, and so how often it trades.
"""
from __future__ import annotations

import itertools
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from app.common.models import TradeIntent

AUTONOMY_MODES = ("manual", "semi", "full")
HORIZON_TIMEFRAMES = {"short": "15m", "medium": "1h", "long": "1d"}

# An approval request older than this is stale: the setup it described has
# probably changed, so it can no longer be accepted.
APPROVAL_MINUTES = 15
# Approving is refused if the price has moved further than this since the
# signal, because the stop and target were sized for the old price.
MAX_DRIFT_PCT = 1.5


def resolve_autonomy(preference: str | None, mode: str) -> str:
    """The owner's choice, or a safe default when they have not made one.

    Real money defaults to asking first; practice money defaults to letting the
    bot run, which is what the practice account is for.
    """
    if preference in AUTONOMY_MODES:
        return preference
    return "semi" if mode == "live" else "full"


def resolve_timeframe(horizon: str | None, fallback: str) -> str:
    return HORIZON_TIMEFRAMES.get(horizon or "", fallback)


@dataclass
class Proposal:
    """A buy the bot wants to make (semi) or would have made (manual)."""

    id: str
    kind: str  # "approval" | "suggestion"
    intent: TradeIntent
    expires_at: datetime
    status: str = "pending"  # pending | approved | skipped | expired | failed
    note: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def expired(self) -> bool:
        return self.status == "pending" and datetime.now(timezone.utc) >= self.expires_at

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "note": self.note,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            **self.intent.to_dict(),
        }


class ProposalBook:
    """Pending approvals and recent suggestions, safe to touch from any thread.

    The engine thread adds to it on every scan; the web server and Telegram
    resolve entries from their own threads.
    """

    def __init__(self, minutes: int = APPROVAL_MINUTES, history: int = 30) -> None:
        self._ttl = timedelta(minutes=minutes)
        self._history_size = history
        self._ids = itertools.count(1)
        self._lock = threading.Lock()
        self._pending: dict[str, Proposal] = {}
        self._history: list[Proposal] = []

    def add(self, kind: str, intent: TradeIntent) -> Proposal | None:
        """Record a proposal, or None if one for this symbol is still live.

        The strategy re-reads the same bar on every scan, so without this the
        same crossover would be proposed once a minute until the bar closes.
        """
        with self._lock:
            if any(p.intent.symbol == intent.symbol for p in self._pending.values()):
                return None
            proposal = Proposal(
                id=f"{'ap' if kind == 'approval' else 'sg'}-{next(self._ids)}",
                kind=kind,
                intent=intent,
                expires_at=datetime.now(timezone.utc) + self._ttl,
            )
            self._pending[proposal.id] = proposal
            return proposal

    def take(self, proposal_id: str) -> Proposal | None:
        """Remove a live approval so exactly one caller can act on it."""
        with self._lock:
            proposal = self._pending.get(proposal_id)
            if proposal is None or proposal.kind != "approval":
                return None
            if proposal.expired:
                self._retire(proposal, "expired")
                return None
            del self._pending[proposal_id]
            return proposal

    def finish(self, proposal: Proposal, status: str, note: str = "") -> None:
        with self._lock:
            self._pending.pop(proposal.id, None)
            self._retire(proposal, status, note)

    def skip(self, proposal_id: str) -> Proposal | None:
        with self._lock:
            proposal = self._pending.get(proposal_id)
            if proposal is None:
                return None
            self._retire(proposal, "skipped")
            return proposal

    def expire(self) -> list[Proposal]:
        with self._lock:
            stale = [p for p in self._pending.values() if p.expired]
            for proposal in stale:
                self._retire(proposal, "expired")
            return stale

    def has_pending_for(self, symbol: str) -> bool:
        with self._lock:
            return any(p.intent.symbol == symbol for p in self._pending.values())

    def pending(self, kind: str | None = None) -> list[Proposal]:
        with self._lock:
            items = [p for p in self._pending.values() if kind is None or p.kind == kind]
        return sorted(items, key=lambda p: p.created_at, reverse=True)

    def recent(self, limit: int = 10) -> list[Proposal]:
        with self._lock:
            return list(reversed(self._history[-limit:]))

    def clear_pending(self) -> None:
        with self._lock:
            for proposal in list(self._pending.values()):
                self._retire(proposal, "skipped", "mode changed")

    def _retire(self, proposal: Proposal, status: str, note: str = "") -> None:
        """Caller holds the lock."""
        self._pending.pop(proposal.id, None)
        proposal.status = status
        if note:
            proposal.note = note
        self._history.append(proposal)
        del self._history[: -self._history_size]
