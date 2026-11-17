"""The pace (12.0): how eager Ultra is. It changes thresholds, never a safety gate.

            calm      balanced (9.0)   aggressive
  vote      6 of 8    5 of 8           4 of 8
  RSI(7)    <= 30     <= 35            <= 40
  dip       1.5 ATR   1.2 ATR          1.0 ATR
  a day     10        30               45
  all-in    off       at 6 of 8        at 6 of 8
  edge      always    your switch      your switch

Balanced reads the scalper's own constants when it is used, so it is exactly
today's rule (and the tests that patch those constants still work). Stop,
arming, the daily loss limit, the budget and every other gate are the same
in every pace. Each pace has its own Lab replay, shown next to the choice.
"""
from __future__ import annotations

from dataclasses import dataclass

IDS = ("calm", "balanced", "aggressive")


@dataclass(frozen=True)
class Pace:
    id: str
    conf_min: float
    rsi_max: float
    dip_atr: float
    max_entries: int
    all_in: bool
    edge_forced: bool

    def to_dict(self) -> dict:
        return {"id": self.id, "votes": round(self.conf_min * 8), "rsi_max": self.rsi_max, "dip_atr": self.dip_atr,
                "max_entries": self.max_entries, "all_in": self.all_in, "edge_forced": self.edge_forced}


def balanced() -> Pace:
    from app.engine import scalper as S

    return Pace("balanced", S.CONF_MIN, S.RSI_MAX, S.DIP_ATR, S.MAX_ENTRIES, True, False)


CALM = Pace("calm", 0.75, 30, 1.5, 10, False, True)
AGGRESSIVE = Pace("aggressive", 0.5, 40, 1.0, 45, True, False)


def get(pace_id: str | None) -> Pace:
    if pace_id == "calm":
        return CALM
    if pace_id == "aggressive":
        return AGGRESSIVE
    return balanced()


def widest_rsi() -> float:
    """The loosest RSI of all paces: the Lab's prefilter must not drop a minute any pace would take."""
    return max(CALM.rsi_max, balanced().rsi_max, AGGRESSIVE.rsi_max)
