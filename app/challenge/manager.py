from __future__ import annotations

import logging
import math
import threading
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.common.events import EventBus
from app.config import ChallengeConfig, RiskConfig
from app.storage.models import ChallengeRow

log = logging.getLogger(__name__)

ACTIVE = "active"
WON = "won"
LOST = "lost"
STOPPED = "stopped"


@dataclass
class ChallengeState:
    """A snapshot of one run, safe to hand to the UI."""

    id: int
    stake: float
    target: float
    status: str
    realised_pnl: float
    unrealised_pnl: float
    peak_value: float
    trades: int
    wins: int
    started_at: datetime
    ended_at: datetime | None
    bust_floor: float

    @property
    def value(self) -> float:
        return self.stake + self.realised_pnl + self.unrealised_pnl

    @property
    def gain(self) -> float:
        return self.value - self.stake

    @property
    def gain_pct(self) -> float:
        return (self.gain / self.stake * 100) if self.stake else 0.0

    @property
    def progress_pct(self) -> float:
        """0 at the stake, 100 at the target. Clamped for the progress arc."""
        span = self.target - self.stake
        if span <= 0:
            return 100.0
        return max(min((self.value - self.stake) / span * 100, 100.0), 0.0)

    @property
    def is_active(self) -> bool:
        return self.status == ACTIVE

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "stake": round(self.stake, 2),
            "target": round(self.target, 2),
            "status": self.status,
            "value": round(self.value, 2),
            "gain": round(self.gain, 2),
            "gain_pct": round(self.gain_pct, 2),
            "progress_pct": round(self.progress_pct, 1),
            "realised_pnl": round(self.realised_pnl, 2),
            "unrealised_pnl": round(self.unrealised_pnl, 2),
            "peak_value": round(self.peak_value, 2),
            "bust_floor": round(self.bust_floor, 2),
            "trades": self.trades,
            "wins": self.wins,
            "losses": self.trades - self.wins,
            "win_rate": round(self.wins / self.trades * 100, 1) if self.trades else None,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "active": self.is_active,
        }


def winning_trades_needed(stake: float, target: float, take_profit_pct: float,
                          position_pct: float) -> int | None:
    """How many winning trades in a row it would take to get from stake to target.

    This is the honest headline number for a run like $5 → $10: with a 4% target
    and the whole bankroll on each trade it is about eighteen wins with no losses
    in between. Returns None if the maths cannot get there at all.
    """
    if stake <= 0 or target <= stake:
        return 0
    growth = 1 + (take_profit_pct / 100.0) * (position_pct / 100.0)
    if growth <= 1:
        return None
    return math.ceil(math.log(target / stake) / math.log(growth))


class ChallengeManager:
    """Owns the lifecycle of a run and the bankroll it trades.

    Only one challenge is active at a time. While it is active the engine sizes
    from the challenge bankroll instead of the whole account, so a $5 run really
    does risk $5 and nothing more.
    """

    def __init__(
        self,
        config: ChallengeConfig,
        risk: RiskConfig,
        session_factory: sessionmaker[Session],
        events: EventBus,
        mode: str,
    ) -> None:
        self.config = config
        self.risk = risk
        self.mode = mode
        self.events = events
        self._session_factory = session_factory
        self._lock = threading.RLock()
        self._unrealised = 0.0

    # ------------------------------------------------------------------ queries

    def active(self) -> ChallengeState | None:
        with self._session_factory() as session:
            row = session.scalar(
                select(ChallengeRow).where(
                    ChallengeRow.mode == self.mode, ChallengeRow.status == ACTIVE
                )
            )
        return self._to_state(row) if row else None

    def history(self, limit: int = 20) -> list[dict]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(ChallengeRow)
                .where(ChallengeRow.mode == self.mode, ChallengeRow.status != ACTIVE)
                .order_by(ChallengeRow.started_at.desc())
                .limit(limit)
            ).all()
        return [self._to_state(r).to_dict() for r in rows]

    def bankroll(self) -> float | None:
        """Money the engine may deploy, or None when no run is active."""
        state = self.active()
        return max(state.value, 0.0) if state else None

    def odds(self, stake: float, target: float) -> dict:
        """The honest arithmetic behind a proposed run."""
        needed = winning_trades_needed(
            stake, target, self.risk.take_profit_pct, self.config.position_pct
        )
        return {
            "winning_trades_needed": needed,
            "take_profit_pct": self.risk.take_profit_pct,
            "stop_loss_pct": self.risk.stop_loss_pct,
            "position_pct": self.config.position_pct,
            "bust_floor": round(stake * (1 - self.config.bust_drawdown_pct / 100.0), 2),
        }

    # -------------------------------------------------------------- lifecycle

    def start(self, stake: float, target: float) -> ChallengeState:
        if stake <= 0:
            raise ValueError("stake must be positive")
        if target <= stake:
            raise ValueError("target must be above the stake")
        if self.active() is not None:
            raise ValueError("a challenge is already running")

        row = ChallengeRow(
            mode=self.mode,
            stake=stake,
            target=target,
            status=ACTIVE,
            realised_pnl=0.0,
            peak_value=stake,
            trades=0,
            wins=0,
            started_at=datetime.now(timezone.utc),
        )
        with self._lock, self._session_factory() as session:
            session.add(row)
            session.commit()
            session.refresh(row)

        self._unrealised = 0.0
        state = self._to_state(row)
        log.info("challenge %s started: %.2f -> %.2f", row.id, stake, target)
        self.events.publish("challenge", {"challenge": state.to_dict(), "event": "started"})
        return state

    def stop(self, reason: str = "stopped by you") -> ChallengeState | None:
        return self._finish(STOPPED, reason)

    def record_trade(self, pnl: float) -> ChallengeState | None:
        """Fold a closed trade into the run and end it if it is decided."""
        with self._lock:
            row_id = self._active_id()
            if row_id is None:
                return None
            with self._session_factory() as session:
                row = session.get(ChallengeRow, row_id)
                row.realised_pnl += pnl
                row.trades += 1
                if pnl > 0:
                    row.wins += 1
                value = row.stake + row.realised_pnl
                row.peak_value = max(row.peak_value, value)
                session.commit()
                session.refresh(row)

            self._unrealised = 0.0
            state = self._to_state(row)

        if state.value >= state.target:
            return self._finish(WON, "target reached") or state
        if state.value <= state.bust_floor:
            return self._finish(LOST, "bankroll fell through the floor") or state

        self.events.publish("challenge", {"challenge": state.to_dict(), "event": "trade"})
        return state

    def mark_unrealised(self, unrealised: float) -> None:
        """Open-position P&L, so the dial moves between closes."""
        with self._lock:
            self._unrealised = unrealised

    # ---------------------------------------------------------------- internals

    def _finish(self, status: str, reason: str) -> ChallengeState | None:
        with self._lock:
            row_id = self._active_id()
            if row_id is None:
                return None
            with self._session_factory() as session:
                row = session.get(ChallengeRow, row_id)
                row.status = status
                row.ended_at = datetime.now(timezone.utc)
                session.commit()
                session.refresh(row)
            self._unrealised = 0.0
            state = self._to_state(row)

        log.info("challenge %s ended (%s): %s", state.id, status, reason)
        self.events.publish(
            "challenge",
            {"challenge": state.to_dict(), "event": status, "reason": reason},
        )
        return state

    def _active_id(self) -> int | None:
        with self._session_factory() as session:
            return session.scalar(
                select(ChallengeRow.id).where(
                    ChallengeRow.mode == self.mode, ChallengeRow.status == ACTIVE
                )
            )

    def _to_state(self, row: ChallengeRow) -> ChallengeState:
        return ChallengeState(
            id=row.id,
            stake=row.stake,
            target=row.target,
            status=row.status,
            realised_pnl=row.realised_pnl,
            unrealised_pnl=self._unrealised if row.status == ACTIVE else 0.0,
            peak_value=row.peak_value,
            trades=row.trades,
            wins=row.wins,
            started_at=row.started_at,
            ended_at=row.ended_at,
            bust_floor=row.stake * (1 - self.config.bust_drawdown_pct / 100.0),
        )
