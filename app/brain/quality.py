"""The five checks a careful long-term investor asks, from the company's own filings.

  1. BUSINESS   — does it reliably make money, and is it growing?
  2. MOAT       — are margins and returns high enough that rivals clearly cannot copy it cheaply?
  3. MANAGEMENT — does it buy back shares rather than print them, earn well, keep debt sane?
  4. VALUE      — is the price below a conservative estimate of what it is worth?
  5. RISK       — debt it can carry, interest it can pay, no red flags, a sane daily swing.

Identical thresholds to the phone app. Every verdict traces to a number here.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np

from app.brain import text

DISCOUNT = 0.10
TERMINAL_GROWTH = 0.03
MAX_GROWTH = 0.15
GROWTH_HAIRCUT = 0.75

FUNDS = {
    "SPY", "VOO", "IVV", "QQQ", "QQQM", "DIA", "IWM", "VTI", "VT", "VEA", "VWO", "VGK", "EFA", "EEM",
    "IEFA", "IEMG", "SCHD", "VIG", "VUG", "VTV", "XLK", "XLF", "XLE", "XLV", "XLY", "XLP", "XLI",
    "XLU", "XLB", "XLRE", "XLC", "SMH", "SOXX", "ARKK", "GLD", "SLV", "TLT", "IEF", "SHY", "BND",
    "AGG", "HYG", "LQD", "EWG", "EWU", "EWJ", "FEZ", "EZU", "IEUR", "SPLG", "RSP", "MDY", "IJH", "IJR",
}

# Ordinary shares behind one New York share for the foreign companies we know.
SHARES_PER_LISTING = {
    "ASML": 1.0, "SAP": 1.0, "NVO": 1.0, "AZN": 0.5, "SHEL": 2.0, "TTE": 1.0,
    "UL": 1.0, "BP": 6.0, "HSBC": 5.0, "TSM": 5.0, "BABA": 8.0,
}

CHECKS = ["BUSINESS", "MOAT", "MANAGEMENT", "VALUE", "RISK"]


@dataclass
class FiscalYear:
    end: str
    revenue: float | None = None
    net_income: float | None = None
    gross_profit: float | None = None
    operating_income: float | None = None
    equity: float | None = None
    debt: float | None = None
    operating_cash_flow: float | None = None
    capex: float | None = None
    shares: float | None = None
    interest: float | None = None
    cash: float | None = None

    @property
    def free_cash_flow(self) -> float | None:
        if self.operating_cash_flow is None or self.capex is None:
            return None
        return self.operating_cash_flow - self.capex


@dataclass
class Filings:
    symbol: str
    name: str
    currency: str
    foreign: bool
    fund: bool
    years: list[FiscalYear]
    fetched_at: float
    ai_read: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Filings":
        years = [FiscalYear(**y) for y in d.get("years", [])]
        return Filings(d["symbol"], d.get("name", d["symbol"]), d.get("currency", "USD"), bool(d.get("foreign")),
                       bool(d.get("fund")), years, float(d.get("fetched_at", 0)), d.get("ai_read"))


@dataclass
class Check:
    kind: str
    verdict: str              # PASS / WATCH / FAIL / UNKNOWN
    facts: list[dict] = field(default_factory=list)   # {"metric": ..., "value": ..., "text": ...}

    @property
    def points(self) -> float:
        return {"PASS": 1.0, "WATCH": 0.5, "UNKNOWN": 0.5}.get(self.verdict, 0.0)


@dataclass
class Report:
    symbol: str
    name: str
    fund: bool
    checks: list[Check]
    decision: str             # BUY_ZONE / WAIT / AVOID / UNKNOWN
    score: float
    price: float | None
    value: float | None
    fiscal_year_end: str | None
    ai_read: str | None = None

    def check(self, kind: str) -> Check | None:
        return next((c for c in self.checks if c.kind == kind), None)

    @property
    def price_to_value(self) -> float | None:
        if self.price and self.value and self.value > 0:
            return self.price / self.value
        return None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["price_to_value"] = self.price_to_value
        return d


def _fact(metric: str, value: float, label: str | None = None) -> dict:
    return {"metric": metric, "value": float(value), "text": label}


def cagr(values: list[float]) -> float | None:
    if len(values) < 3:
        return None
    first, last = values[0], values[-1]
    if first <= 0 or last <= 0:
        return None
    return (last / first) ** (1.0 / (len(values) - 1)) - 1


def daily_swing(closes: np.ndarray, highs: np.ndarray, lows: np.ndarray) -> float | None:
    """Average true range of the last 14 days as a share of the price."""
    if len(closes) < 20:
        return None
    prev = np.concatenate([[closes[0]], closes[:-1]])
    tr = np.maximum(highs - lows, np.maximum(np.abs(highs - prev), np.abs(lows - prev)))
    atr = tr[-14:].mean()
    return float(atr / closes[-1]) if closes[-1] > 0 else None


def value_per_listing(f: Filings, usd_per: float | None, shares_per_listing: float | None, rev_growth: float | None) -> float | None:
    """Owner earnings (average of 3-year FCF and net income), grown at three
    quarters of past revenue growth (≤15%, halved after year five), 3% after
    ten years, discounted at 10%; plus net cash; per New York share in dollars."""
    y = f.years
    if not y or y[-1].net_income is None:
        return None
    ni = y[-1].net_income
    fcf = [r.free_cash_flow for r in y[-3:] if r.free_cash_flow is not None]
    owner = (sum(fcf) / len(fcf) + ni) / 2 if fcf else ni * 0.85
    shares = next((r.shares for r in reversed(y) if r.shares), None)
    if not shares or shares <= 0:
        return None
    fx = 1.0 if f.currency == "USD" else usd_per
    if fx is None:
        return None
    if shares_per_listing is not None:
        per = shares_per_listing
    elif f.foreign:
        return None
    else:
        per = 1.0
    g = min(max(rev_growth or 0.0, 0.0), MAX_GROWTH) * GROWTH_HAIRCUT
    flow = max(owner, 0.0)
    total = 0.0
    for year in range(1, 11):
        flow *= 1 + (g if year <= 5 else g / 2)
        total += flow / (1 + DISCOUNT) ** year
    total += flow * (1 + TERMINAL_GROWTH) / (DISCOUNT - TERMINAL_GROWTH) / (1 + DISCOUNT) ** 10
    cash = next((r.cash for r in reversed(y) if r.cash is not None), 0.0)
    debt = next((r.debt for r in reversed(y) if r.debt is not None), 0.0)
    return (total + cash - debt) / shares * per * fx


def _risk(filings: Filings | None, daily: dict | None, flags: list) -> Check:
    y = filings.years if filings else []
    last_ni = y[-1].net_income if y else None
    debt = next((r.debt for r in reversed(y) if r.debt is not None), None)
    debt_to_profit = debt / last_ni if debt is not None and last_ni and last_ni > 0 else None
    cover = next((r.operating_income / r.interest for r in reversed(y)
                  if r.operating_income is not None and r.interest), None)
    negative_equity = (y[-1].equity or 1.0) < 0 and (last_ni or 1.0) < 0 if y else False
    swing = daily_swing(daily["close"], daily["high"], daily["low"]) if daily else None
    has_severe = any(text.severe(f.kind) for f in flags)
    if has_severe or negative_equity or (debt_to_profit is not None and debt_to_profit > 6) \
            or (cover is not None and cover < 2.5) or (swing is not None and swing > 0.08):
        verdict = "FAIL"
    elif flags or (debt_to_profit is not None and debt_to_profit > 3) or (cover is not None and cover < 6) \
            or (swing is not None and swing > 0.045):
        verdict = "WATCH"
    elif filings is None and swing is None:
        verdict = "UNKNOWN"
    else:
        verdict = "PASS"
    facts = []
    if debt_to_profit is not None:
        facts.append(_fact("DEBT_TO_PROFIT", debt_to_profit))
    if cover is not None:
        facts.append(_fact("INTEREST_COVER", cover))
    if swing is not None:
        facts.append(_fact("DAILY_SWING", swing))
    facts += [_fact("RED_FLAG", 1.0, f.kind) for f in flags]
    return Check("RISK", verdict, facts)


def evaluate(symbol: str, filings: Filings | None, price: float | None, usd_per: float | None,
             daily: dict | None, flags: list) -> Report:
    """`daily` is {"close", "high", "low"} numpy arrays of daily candles, or None."""
    risk = _risk(filings, daily, flags)
    if filings is None or filings.fund:
        return _fund(symbol, filings, price, daily, risk)

    y = filings.years
    latest = y[-1] if y else None
    ni = [r.net_income for r in y if r.net_income is not None]
    revs = [r.revenue for r in y if r.revenue is not None]
    rev_growth = cagr(revs)
    profit_years = sum(1 for v in ni if v > 0)
    last3 = y[-3:]
    om = _avg([r.operating_income / r.revenue for r in last3 if r.operating_income is not None and r.revenue])
    gm = _avg([r.gross_profit / r.revenue for r in last3 if r.gross_profit is not None and r.revenue])
    roe = _avg([r.net_income / r.equity for r in last3 if r.net_income is not None and r.equity and r.equity > 0])
    shares = [r.shares for r in y if r.shares][-3:]
    share_change = (shares[-1] / shares[0]) ** (1.0 / (len(shares) - 1)) - 1 if len(shares) >= 2 and shares[0] > 0 else None
    last_ni = latest.net_income if latest else None
    debt = next((r.debt for r in reversed(y) if r.debt is not None), None)
    debt_to_profit = debt / last_ni if debt is not None and last_ni and last_ni > 0 else None

    if last_ni is None:
        business = "UNKNOWN"
    elif last_ni > 0 and profit_years >= len(ni) - 1 and (rev_growth or 0.0) >= 0:
        business = "PASS"
    elif last_ni <= 0 and profit_years * 2 < len(ni):
        business = "FAIL"
    else:
        business = "WATCH"

    if om is None and roe is None:
        moat = "UNKNOWN"
    elif (om or 0) >= 0.20 and (roe or 0) >= 0.15:
        moat = "PASS"
    elif (gm or 0) >= 0.40 and (om or 0) >= 0.15 and (roe or 0) >= 0.12:
        moat = "PASS"
    elif (om or 0) >= 0.10 or (roe or 0) >= 0.12:
        moat = "WATCH"
    else:
        moat = "FAIL"

    if share_change is None and roe is None:
        management = "UNKNOWN"
    elif (share_change or 0) > 0.03 or (roe is not None and roe < 0):
        management = "FAIL"
    elif (share_change or 0) <= 0.005 and (roe or 0) >= 0.12 and (debt_to_profit or 0) <= 3.0:
        management = "PASS"
    else:
        management = "WATCH"

    value = value_per_listing(filings, usd_per, SHARES_PER_LISTING.get(symbol), rev_growth)
    pv = price / value if price and value and value > 0 else None
    if price is None or value is None:
        value_verdict = "UNKNOWN"
    elif value <= 0:
        value_verdict = "FAIL"
    elif pv <= 1.0:
        value_verdict = "PASS"
    elif pv <= 1.5:
        value_verdict = "WATCH"
    else:
        value_verdict = "FAIL"

    checks = [
        Check("BUSINESS", business, [_fact("PROFIT_YEARS", profit_years, f"{profit_years}/{len(ni)}")]
              + ([_fact("REVENUE_GROWTH", rev_growth)] if rev_growth is not None else [])),
        Check("MOAT", moat, [f for f in (
            _fact("GROSS_MARGIN", gm) if gm is not None else None,
            _fact("OPERATING_MARGIN", om) if om is not None else None,
            _fact("RETURN_ON_EQUITY", roe) if roe is not None else None) if f]),
        Check("MANAGEMENT", management, [f for f in (
            _fact("SHARE_CHANGE", share_change) if share_change is not None else None,
            _fact("RETURN_ON_EQUITY", roe) if roe is not None else None,
            _fact("DEBT_TO_PROFIT", debt_to_profit) if debt_to_profit is not None else None) if f]),
        Check("VALUE", value_verdict, [f for f in (
            _fact("PRICE", price) if price is not None else None,
            _fact("VALUE", value) if value is not None else None,
            _fact("PRICE_TO_VALUE", pv) if pv is not None else None) if f]),
        risk,
    ]
    score = sum(c.points for c in checks)
    if all(c.verdict == "UNKNOWN" for c in checks):
        decision = "UNKNOWN"
    elif business == "FAIL" or risk.verdict == "FAIL" or score < 2.5:
        decision = "AVOID"
    elif value_verdict == "PASS" and score >= 4.0:
        decision = "BUY_ZONE"
    else:
        decision = "WAIT"
    return Report(symbol, filings.name, False, checks, decision, score, price, value,
                  latest.end if latest else None, filings.ai_read)


def _fund(symbol: str, f: Filings | None, price: float | None, daily: dict | None, risk: Check) -> Report:
    closes = daily["close"] if daily else np.array([])
    sma = float(closes[-200:].mean()) if len(closes) >= 200 else None
    last = price if price is not None else (float(closes[-1]) if len(closes) else None)
    vs = last / sma if sma and last else None
    if vs is None:
        value = "UNKNOWN"
    elif vs <= 1.0:
        value = "PASS"
    elif vs <= 1.10:
        value = "WATCH"
    else:
        value = "FAIL"
    na = [Check(k, "UNKNOWN", [_fact("FUND", 1.0)]) for k in ("BUSINESS", "MOAT", "MANAGEMENT")]
    checks = na + [Check("VALUE", value, [x for x in (_fact("PRICE", last) if last else None,
                                                       _fact("VS_200_DAY", vs) if vs else None) if x]), risk]
    is_fund = bool(f and f.fund) or symbol.upper() in FUNDS
    known = [c for c in checks if c.verdict != "UNKNOWN"]
    score = sum(c.points for c in known) / len(known) * 5 if known else 2.5
    if not is_fund and f is None:
        decision = "UNKNOWN"
    elif risk.verdict == "FAIL":
        decision = "AVOID"
    elif value == "PASS":
        decision = "BUY_ZONE"
    elif value == "UNKNOWN" and risk.verdict == "UNKNOWN":
        decision = "UNKNOWN"
    else:
        decision = "WAIT"
    return Report(symbol, f.name if f else symbol, is_fund, checks, decision, score, last, None, None, f.ai_read if f else None)


def _avg(v: list[float]) -> float | None:
    return sum(v) / len(v) if v else None
