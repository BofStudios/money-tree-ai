"""Typed shapes for company research.

Two rules run through every dataclass here:

1. **A missing number is None, never a placeholder.** No zeros standing in for
   "unknown", no invented estimates. The dashboard renders None as "not
   available" and the AI is told, in its prompt, that it may not reason about a
   field it cannot see.
2. **Every block carries its own provenance.** `source` says who supplied it
   and `as_of` says when — because "revenue grew 8%" means nothing without
   knowing whether that is this quarter or two years stale.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any


def num(value: Any) -> float | None:
    """Coerce a provider value to a real float, or None.

    Providers hand back numpy scalars, strings, NaN and infinity more or less
    interchangeably. Anything that is not a finite number becomes None so it
    cannot be mistaken for data further down.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def text(value: Any) -> str | None:
    if value is None:
        return None
    out = str(value).strip()
    return out or None


def when(value: Any) -> str | None:
    """Normalise a provider timestamp to an ISO date string, or None."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.utcfromtimestamp(float(value)).date().isoformat()
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    parsed = getattr(value, "to_pydatetime", None)
    if callable(parsed):
        try:
            return parsed().date().isoformat()
        except Exception:
            return None
    return text(value)


@dataclass
class Provenance:
    """Who said it and when. Attached to every block the UI renders."""

    source: str
    as_of: str | None = None
    delayed: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


# ------------------------------------------------------------------- profile


@dataclass
class CompanyProfile:
    symbol: str
    name: str | None = None
    sector: str | None = None
    industry: str | None = None
    country: str | None = None
    employees: float | None = None
    website: str | None = None
    summary: str | None = None
    currency: str | None = None
    exchange: str | None = None
    provenance: Provenance | None = None

    def to_dict(self) -> dict:
        out = asdict(self)
        out["provenance"] = self.provenance.to_dict() if self.provenance else None
        return out


# --------------------------------------------------------------------- price


@dataclass
class PriceSnapshot:
    price: float | None = None
    previous_close: float | None = None
    change: float | None = None
    change_pct: float | None = None
    day_high: float | None = None
    day_low: float | None = None
    week52_high: float | None = None
    week52_low: float | None = None
    from_52w_high_pct: float | None = None
    from_52w_low_pct: float | None = None
    volume: float | None = None
    average_volume: float | None = None
    relative_volume: float | None = None
    market_cap: float | None = None
    beta: float | None = None
    provenance: Provenance | None = None

    def to_dict(self) -> dict:
        out = asdict(self)
        out["provenance"] = self.provenance.to_dict() if self.provenance else None
        return out


# ----------------------------------------------------------------- valuation


@dataclass
class Valuation:
    pe: float | None = None
    forward_pe: float | None = None
    peg: float | None = None
    price_to_sales: float | None = None
    price_to_book: float | None = None
    ev_to_ebitda: float | None = None
    ev_to_revenue: float | None = None
    eps: float | None = None
    forward_eps: float | None = None
    fcf_yield_pct: float | None = None
    dividend_yield_pct: float | None = None
    provenance: Provenance | None = None

    def to_dict(self) -> dict:
        out = asdict(self)
        out["provenance"] = self.provenance.to_dict() if self.provenance else None
        return out


# ------------------------------------------------------------------- quality


@dataclass
class Quality:
    """Profitability, growth and balance-sheet strength in one block."""

    revenue: float | None = None
    revenue_growth_pct: float | None = None
    earnings_growth_pct: float | None = None
    gross_margin_pct: float | None = None
    operating_margin_pct: float | None = None
    net_margin_pct: float | None = None
    return_on_equity_pct: float | None = None
    return_on_assets_pct: float | None = None
    free_cash_flow: float | None = None
    operating_cash_flow: float | None = None
    total_cash: float | None = None
    total_debt: float | None = None
    net_debt: float | None = None
    debt_to_equity: float | None = None
    current_ratio: float | None = None
    provenance: Provenance | None = None

    def to_dict(self) -> dict:
        out = asdict(self)
        out["provenance"] = self.provenance.to_dict() if self.provenance else None
        return out


# ---------------------------------------------------------------- statements


@dataclass
class StatementLine:
    """One metric across several reporting periods, newest first."""

    label: str
    periods: list[str] = field(default_factory=list)
    values: list[float | None] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Statements:
    annual: list[StatementLine] = field(default_factory=list)
    quarterly: list[StatementLine] = field(default_factory=list)
    provenance: Provenance | None = None

    def to_dict(self) -> dict:
        return {
            "annual": [line.to_dict() for line in self.annual],
            "quarterly": [line.to_dict() for line in self.quarterly],
            "provenance": self.provenance.to_dict() if self.provenance else None,
        }


# ------------------------------------------------------------------ earnings


@dataclass
class EarningsEvent:
    date: str | None = None
    eps_estimate: float | None = None
    eps_actual: float | None = None
    surprise_pct: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Earnings:
    next_date: str | None = None
    history: list[EarningsEvent] = field(default_factory=list)
    beats: int | None = None
    misses: int | None = None
    provenance: Provenance | None = None

    def to_dict(self) -> dict:
        return {
            "next_date": self.next_date,
            "history": [e.to_dict() for e in self.history],
            "beats": self.beats,
            "misses": self.misses,
            "provenance": self.provenance.to_dict() if self.provenance else None,
        }


# ------------------------------------------------------------------ analysts


@dataclass
class Analysts:
    consensus: str | None = None
    analyst_count: float | None = None
    target_mean: float | None = None
    target_high: float | None = None
    target_low: float | None = None
    strong_buy: float | None = None
    buy: float | None = None
    hold: float | None = None
    sell: float | None = None
    strong_sell: float | None = None
    provenance: Provenance | None = None

    def to_dict(self) -> dict:
        out = asdict(self)
        out["provenance"] = self.provenance.to_dict() if self.provenance else None
        return out


# ----------------------------------------------------------------- ownership


@dataclass
class Holder:
    name: str | None = None
    pct_held: float | None = None
    shares: float | None = None
    reported: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class InsiderTrade:
    person: str | None = None
    action: str | None = None
    shares: float | None = None
    value: float | None = None
    date: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Ownership:
    insider_pct: float | None = None
    institution_pct: float | None = None
    top_holders: list[Holder] = field(default_factory=list)
    insider_trades: list[InsiderTrade] = field(default_factory=list)
    provenance: Provenance | None = None

    def to_dict(self) -> dict:
        return {
            "insider_pct": self.insider_pct,
            "institution_pct": self.institution_pct,
            "top_holders": [h.to_dict() for h in self.top_holders],
            "insider_trades": [t.to_dict() for t in self.insider_trades],
            "provenance": self.provenance.to_dict() if self.provenance else None,
        }


# ------------------------------------------------------------------ dividend


@dataclass
class Dividend:
    yield_pct: float | None = None
    rate: float | None = None
    payout_ratio_pct: float | None = None
    five_year_avg_yield_pct: float | None = None
    ex_date: str | None = None
    history: list[dict] = field(default_factory=list)
    provenance: Provenance | None = None

    def to_dict(self) -> dict:
        out = asdict(self)
        out["provenance"] = self.provenance.to_dict() if self.provenance else None
        return out
