"""Which copy of the app this is, and what it is allowed to do.

personal  The owner's own copy: run from source, or an exe built with
          `scripts/build_exe.py --personal`. No licence key, Telegram on,
          ten strategy bots, and every limit is the owner's choice.
pro       The copy that is sold: `scripts/build_exe.py` without --personal.
          It needs a licence key. Nothing is pre-connected (no Telegram),
          and the safety limits below are fixed: the buyer can lower them
          in config.yaml, never raise them.

The owner's keys never ship with either build: they live in .env, the key
store and data/, which the build refuses to copy (scripts/build_exe.py).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from app import _build
from app.config import FROZEN


@dataclass(frozen=True)
class Limits:
    max_risk_per_trade_pct: float | None    # the money lost if the stop hits, % of equity
    max_daily_loss_pct: float | None        # the day's realised loss that disarms real money
    max_open_positions: int | None
    max_position_pct: float | None          # the most of the account in one stock
    max_bots: int                           # strategy bots in the swarm
    telegram: bool

    def to_dict(self) -> dict:
        return asdict(self)


LIMITS = {
    "personal": Limits(None, None, None, None, max_bots=10, telegram=True),
    "pro": Limits(1.0, 3.0, 5, 25.0, max_bots=4, telegram=False),
}

NAME = "personal" if (not FROZEN or _build.PERSONAL) else "pro"
PRO = NAME == "pro"


def limits() -> Limits:
    return LIMITS[NAME]


def clamp_risk(risk, limits_: Limits | None = None) -> list[str]:
    """Bring a RiskConfig inside the edition's limits. Returns what changed."""
    lim = limits_ or limits()
    changed = []
    for field, cap in (
        ("risk_per_trade_pct", lim.max_risk_per_trade_pct),
        ("max_daily_loss_pct", lim.max_daily_loss_pct),
        ("max_open_positions", lim.max_open_positions),
        ("max_position_pct", lim.max_position_pct),
    ):
        if cap is not None and getattr(risk, field) > cap:
            changed.append(f"{field} {getattr(risk, field)} -> {cap}")
            setattr(risk, field, cap)
    return changed
