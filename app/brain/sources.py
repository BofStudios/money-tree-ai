"""Where the research desk reads from — all free, no account beyond Alpaca's keys.

  SEC (data.sec.gov)   annual reports (XBRL company facts) and the filing index
  Alpaca news          the watchlist's news, and the whole market's wire
  Wikimedia            daily page views: attention, as alternative data
  Frankfurter (ECB)    exchange rates for euro and krone reporters

Verified against the real services before this was written (2026-10): the SEC
answers a declared app name and turns away generic library agents; a company
file is 1–5 MB of JSON; an ETF has a CIK but no company facts (404).
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote

import requests

from app.brain.quality import Filings, FiscalYear, FUNDS

log = logging.getLogger(__name__)

USER_AGENT = "BofStudios MoneyTree-Desktop/3.0"
TIMEOUT = 30

KNOWN_CIKS = {
    "AAPL": 320193, "MSFT": 789019, "NVDA": 1045810, "AMZN": 1018724, "GOOGL": 1652044, "GOOG": 1652044,
    "META": 1326801, "TSLA": 1318605, "SPY": 884394, "ASML": 937966, "SAP": 1000184, "NVO": 353278,
    "AZN": 901832, "SHEL": 1306965, "TTE": 879764, "UL": 217410,
}

ANNUAL_FORMS = {"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}
FOREIGN_FORMS = {"20-F", "20-F/A", "40-F", "40-F/A"}
CONCEPTS = {
    "revenue": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet",
                "RevenueFromContractWithCustomerIncludingAssessedTax", "Revenue", "RevenueFromContractsWithCustomers"],
    "net_income": ["NetIncomeLoss", "ProfitLossAttributableToOwnersOfParent", "ProfitLoss"],
    "gross_profit": ["GrossProfit"],
    "cost_of_revenue": ["CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfSales"],
    "operating_income": ["OperatingIncomeLoss", "ProfitLossFromOperatingActivities"],
    "equity": ["StockholdersEquity", "EquityAttributableToOwnersOfParent",
               "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", "Equity"],
    "debt": ["LongTermDebtNoncurrent", "LongTermDebt", "LongtermBorrowings", "NoncurrentPortionOfNoncurrentBorrowings", "Borrowings"],
    "operating_cash_flow": ["NetCashProvidedByUsedInOperatingActivities", "CashFlowsFromUsedInOperatingActivities",
                            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment", "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
              "PurchaseOfPropertyPlantAndEquipmentIntangibleAssetsOtherThanGoodwillInvestmentPropertyAndOtherNoncurrentAssets",
              "PaymentsToAcquireProductiveAssets"],
    "shares": ["WeightedAverageNumberOfDilutedSharesOutstanding", "AdjustedWeightedAverageShares", "WeightedAverageShares"],
    "interest": ["InterestExpense", "InterestExpenseNonoperating", "FinanceCosts", "InterestExpenseDebt"],
    "cash": ["CashAndCashEquivalentsAtCarryingValue", "CashAndCashEquivalents"],
}
DURATIONS = {"revenue", "net_income", "gross_profit", "cost_of_revenue", "operating_income",
             "operating_cash_flow", "capex", "shares", "interest"}
FUND_WORDS = (" ETF", "TRUST", " FUND", "SPDR", "ISHARES", "VANGUARD", "INDEX")
MAX_YEARS = 6


def _session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    s.headers["Accept-Encoding"] = "gzip, deflate"
    return s


# ======================================================================= SEC

class SecClient:
    def __init__(self, cache: dict[str, str] | None = None) -> None:
        self._http = _session()
        self._lock = threading.Lock()
        self._last = 0.0
        self.ciks: dict[str, tuple[int, str]] = {}
        for k, v in (cache or {}).items():
            cik, _, name = v.partition("|")
            if cik.isdigit():
                self.ciks[k] = (int(cik), name)

    def _get(self, url: str, **params) -> requests.Response:
        # The SEC asks for at most ten requests a second; stay well under.
        with self._lock:
            wait = 0.15 - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
        return self._http.get(url, params=params or None, timeout=TIMEOUT)

    def cik(self, symbol: str) -> tuple[int, str] | None:
        symbol = symbol.upper()
        if symbol in self.ciks:
            return self.ciks[symbol]
        if symbol in KNOWN_CIKS:
            self.ciks[symbol] = (KNOWN_CIKS[symbol], symbol)
            return self.ciks[symbol]
        try:
            r = self._get("https://efts.sec.gov/LATEST/search-index", keysTyped=symbol.lower())
            if not r.ok:
                return None
            for h in r.json().get("hits", {}).get("hits", []):
                src = h.get("_source", {})
                tickers = [t.strip().upper() for t in src.get("tickers", "").split(",")]
                if symbol in tickers and str(h.get("_id", "")).isdigit():
                    found = (int(h["_id"]), src.get("entity", symbol).split(" (")[0].strip())
                    self.ciks[symbol] = found
                    return found
        except Exception as exc:
            log.info("SEC search for %s failed: %s", symbol, exc)
        return None

    def filings(self, symbol: str) -> Filings | None:
        found = self.cik(symbol)
        if not found:
            return None
        cik, entity = found
        r = self._get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json")
        if r.status_code == 404:
            if symbol.upper() in FUNDS or any(w in entity.upper() for w in FUND_WORDS):
                return Filings(symbol.upper(), entity, "USD", False, True, [], time.time())
            return None
        if not r.ok:
            return None
        return parse_facts(symbol.upper(), r.json(), time.time())

    def events(self, symbol: str) -> dict | None:
        found = self.cik(symbol)
        if not found:
            return None
        r = self._get(f"https://data.sec.gov/submissions/CIK{found[0]:010d}.json")
        if not r.ok:
            return None
        return parse_events(symbol.upper(), r.json(), time.time())


def parse_facts(symbol: str, doc: dict, now: float) -> Filings | None:
    """One row per fiscal year: annual filings only, flows that really span a
    year (10-Ks also carry quarters), the latest-filed figure per period."""
    facts = doc.get("facts", {})
    raws: dict[str, list[tuple[str, str | None, str, float, str, str]]] = {}
    foreign = False
    for taxonomy in ("us-gaap", "ifrs-full"):
        for concept, body in facts.get(taxonomy, {}).items():
            for unit, rows in body.get("units", {}).items():
                for row in rows:
                    form = row.get("form", "")
                    if form not in ANNUAL_FORMS or row.get("end") is None or not isinstance(row.get("val"), (int, float)):
                        continue
                    foreign = foreign or form in FOREIGN_FORMS
                    raws.setdefault(concept, []).append(
                        (unit, row.get("start"), row["end"], float(row["val"]), form, row.get("filed", "")))

    def series(key: str):
        best = None
        for priority, concept in enumerate(CONCEPTS[key]):
            by_unit: dict[str, dict[str, tuple]] = {}
            for unit, start, end, val, form, filed in raws.get(concept, []):
                if (key == "shares") != (unit == "shares"):
                    continue
                if key in DURATIONS:
                    if not start:
                        continue
                    try:
                        days = (date.fromisoformat(end) - date.fromisoformat(start)).days
                    except ValueError:
                        continue
                    if not 330 <= days <= 400:
                        continue
                prev = by_unit.setdefault(unit, {}).get(end)
                if prev is None or filed >= prev[1]:
                    by_unit[unit][end] = (val, filed)
            for unit, by_end in by_unit.items():
                if not by_end:
                    continue
                cand = (max(by_end), -priority, unit, {e: v[0] for e, v in by_end.items()})
                if best is None or cand[:2] > best[:2]:
                    best = cand
        return best

    s = {k: series(k) for k in CONCEPTS}
    spine = s["revenue"] or s["net_income"]
    if spine is None:
        return None
    ends = sorted(spine[3])[-MAX_YEARS:]

    def at(key: str, end: str):
        found = s.get(key)
        if not found:
            return None
        m = found[3]
        if end in m:
            return m[end]
        d = date.fromisoformat(end)
        for e, v in m.items():
            if abs((date.fromisoformat(e) - d).days) <= 7:
                return v
        return None

    years = []
    for e in ends:
        revenue = at("revenue", e)
        gross = at("gross_profit", e)
        if gross is None:
            cost = at("cost_of_revenue", e)
            gross = revenue - cost if revenue is not None and cost is not None else None
        years.append(FiscalYear(
            end=e, revenue=revenue, net_income=at("net_income", e), gross_profit=gross,
            operating_income=at("operating_income", e), equity=at("equity", e), debt=at("debt", e),
            operating_cash_flow=at("operating_cash_flow", e), capex=at("capex", e), shares=at("shares", e),
            interest=at("interest", e), cash=at("cash", e),
        ))
    return Filings(symbol, doc.get("entityName") or symbol, spine[2], foreign, False, years, now)


EIGHT_K = {
    "1.01": "a material agreement", "1.02": "an agreement ended", "1.03": "bankruptcy",
    "1.05": "a cybersecurity incident", "2.01": "an acquisition or sale completed",
    "2.02": "results of operations (earnings)", "2.03": "new debt", "2.05": "restructuring costs",
    "2.06": "an impairment", "3.01": "a delisting notice", "3.02": "unregistered share sales",
    "3.03": "changed shareholder rights", "4.01": "an auditor change", "4.02": "past financials no longer reliable",
    "5.01": "a change of control", "5.02": "a director or officer change", "5.03": "amended bylaws",
    "5.07": "a shareholder vote", "7.01": "a Reg FD disclosure", "8.01": "other events",
}
EIGHT_K_FLAGS = {"1.03": "BANKRUPTCY", "3.01": "DELISTING", "4.02": "ACCOUNTING", "3.02": "OFFERING", "1.05": "REGULATOR"}
EIGHT_K_TOPICS = {"2.02": "EARNINGS", "5.02": "LEADERSHIP", "5.01": "LEADERSHIP", "1.01": "DEALS", "1.02": "DEALS",
                  "2.01": "DEALS", "2.03": "CAPITAL", "3.02": "CAPITAL", "3.03": "CAPITAL",
                  "1.03": "REGULATION", "3.01": "REGULATION", "4.01": "REGULATION", "4.02": "REGULATION"}


def parse_events(symbol: str, doc: dict, now: float) -> dict | None:
    r = doc.get("filings", {}).get("recent")
    if not r or "form" not in r:
        return None
    events, results, insiders = [], [], 0
    for i, form in enumerate(r["form"]):
        at = _when((r.get("acceptanceDateTime") or [""] * (i + 1))[i]) or _day((r.get("filingDate") or [""] * (i + 1))[i])
        if at is None:
            continue
        if form in ("8-K", "8-K/A"):
            items = [x.strip() for x in (r.get("items") or [""] * (i + 1))[i].split(",") if x.strip()]
            if "2.02" in items:
                results.append(at)
            if now - at <= 90 * 86400:
                events.append({"items": items, "at": at, "accession": (r.get("accessionNumber") or [""] * (i + 1))[i]})
        elif form == "4" and now - at <= 30 * 86400:
            insiders += 1
    events.sort(key=lambda e: e["at"], reverse=True)
    results.sort(reverse=True)
    return {"symbol": symbol, "events": events, "insiders_30d": insiders, "results": results,
            "next_results": next_results(results), "fetched_at": now}


def next_results(dates: list[float]) -> float | None:
    """The next results date from the rhythm of past ones (8-K item 2.02)."""
    if len(dates) < 3:
        return None
    d = sorted(dates, reverse=True)[:5]
    gaps = [a - b for a, b in zip(d, d[1:])]
    avg = sum(gaps) / len(gaps)
    if not 60 * 86400 <= avg <= 120 * 86400:
        return None
    return d[0] + avg


def _when(s: str) -> float | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _day(s: str) -> float | None:
    try:
        return datetime.combine(date.fromisoformat(s), datetime.min.time(), tzinfo=timezone.utc).timestamp()
    except ValueError:
        return None


# ================================================================ Wikipedia

WIKI_TITLES = {
    "AAPL": "Apple Inc.", "MSFT": "Microsoft", "NVDA": "Nvidia", "AMZN": "Amazon (company)",
    "GOOGL": "Alphabet Inc.", "GOOG": "Alphabet Inc.", "META": "Meta Platforms", "TSLA": "Tesla, Inc.",
    "SPY": "SPDR S&P 500 ETF Trust", "ASML": "ASML Holding", "SAP": "SAP", "NVO": "Novo Nordisk",
    "AZN": "AstraZeneca", "SHEL": "Shell plc", "TTE": "TotalEnergies", "UL": "Unilever",
}


class Wikipedia:
    def __init__(self, titles: dict[str, str] | None = None) -> None:
        self._http = _session()
        self.titles = dict(titles or {})

    def title(self, symbol: str, name: str) -> str | None:
        if symbol in WIKI_TITLES:
            return WIKI_TITLES[symbol]
        if symbol in self.titles:
            return self.titles[symbol]
        import re
        query = re.sub(r"(?i)\b(inc|corp|corporation|co|ltd|plc|holding|holdings|nv|sa|se|ag|a/s|the)\b\.?", " ", name)
        query = re.sub(r"\s+", " ", re.sub(r"[^A-Za-z0-9 &-]", " ", query)).strip()
        if not query:
            return None
        try:
            r = self._http.get("https://en.wikipedia.org/w/api.php", timeout=TIMEOUT, params={
                "action": "opensearch", "search": query, "limit": 1, "namespace": 0, "format": "json"})
            found = r.json()[1][0] if r.ok and r.json()[1] else None
        except Exception:
            found = None
        if found:
            self.titles[symbol] = found
        return found

    def views(self, symbol: str, name: str) -> list[int] | None:
        title = self.title(symbol, name)
        if not title:
            return None
        end = date.today() - timedelta(days=1)
        start = end - timedelta(days=34)
        url = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/"
               f"{quote(title.replace(' ', '_'), safe='')}/daily/{start:%Y%m%d}/{end:%Y%m%d}")
        try:
            r = self._http.get(url, timeout=TIMEOUT)
            if not r.ok:
                return None
            return [int(i.get("views", 0)) for i in r.json().get("items", [])]
        except Exception:
            return None


def attention_ratio(views: list[int]) -> float | None:
    """The last two days against the 28 before them."""
    if len(views) < 10:
        return None
    recent = sum(views[-2:]) / 2
    base_list = views[:-2][-28:]
    base = sum(base_list) / len(base_list)
    return recent / base if base > 0 else None


# =================================================================== FX, news

def usd_per(currency: str) -> float | None:
    if currency == "USD":
        return 1.0
    try:
        r = _session().get("https://api.frankfurter.dev/v1/latest", params={"base": "USD", "symbols": currency}, timeout=TIMEOUT)
        rate = r.json().get("rates", {}).get(currency) if r.ok else None
        return 1.0 / rate if rate else None
    except Exception:
        return None


def make_asset_check(key: str, secret: str):
    """Whether Alpaca trades a symbol: tries the paper endpoint, then live (keys work on one)."""
    http = _session()
    headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
    bases = ["https://paper-api.alpaca.markets", "https://api.alpaca.markets"]

    def check(symbol: str) -> dict | None:
        for base in list(bases):
            r = http.get(f"{base}/v2/assets/{symbol.upper()}", headers=headers, timeout=TIMEOUT)
            if r.status_code in (401, 403):
                continue
            if not r.ok:
                return None
            if bases[0] != base:
                bases.remove(base)
                bases.insert(0, base)
            j = r.json()
            return {"tradable": bool(j.get("tradable")) and j.get("status") == "active",
                    "exchange": str(j.get("exchange", "")), "name": j.get("name", symbol),
                    "fractionable": bool(j.get("fractionable"))}
        return None
    return check


class AlpacaNews:
    """Alpaca's news REST API: per symbol, or the whole wire with no symbols."""

    def __init__(self, key: str, secret: str) -> None:
        self.key, self.secret = key, secret
        self._http = _session()

    @property
    def available(self) -> bool:
        return bool(self.key and self.secret)

    def fetch(self, symbols: list[str], since: float | None, limit: int = 50) -> list[dict]:
        if not self.available:
            return []
        params = {"limit": min(max(limit, 1), 50), "sort": "desc", "include_content": "false"}
        if symbols:
            params["symbols"] = ",".join(s.upper() for s in symbols)
        if since:
            params["start"] = datetime.fromtimestamp(since, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        r = self._http.get("https://data.alpaca.markets/v1beta1/news", params=params, timeout=TIMEOUT,
                           headers={"APCA-API-KEY-ID": self.key, "APCA-API-SECRET-KEY": self.secret})
        r.raise_for_status()
        return r.json().get("news", [])
