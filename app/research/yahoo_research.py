"""Company research from Yahoo Finance, free and without an account.

Scale is the trap in this feed, and getting it wrong is a data-correctness bug
rather than a cosmetic one, so it is spelled out rather than inferred:

    fraction (x100 needed)   profitMargins, grossMargins, operatingMargins,
                             returnOnEquity, returnOnAssets, revenueGrowth,
                             earningsGrowth, payoutRatio
    already a percentage     dividendYield, fiveYearAvgDividendYield,
                             debtToEquity
    plain money / ratio      marketCap, totalCash, totalDebt, trailingPE, ...

Verified against AAPL and KO: Apple's 0.276 profit margin is 27.6%, while its
0.34 dividend yield is 0.34% — the same-looking numbers are on different
scales, so each field is converted explicitly below.
"""
from __future__ import annotations

import logging
import warnings
from datetime import datetime, timezone

from app.research.models import (
    Analysts,
    CompanyProfile,
    Dividend,
    Earnings,
    EarningsEvent,
    Holder,
    InsiderTrade,
    Ownership,
    PriceSnapshot,
    Provenance,
    Quality,
    StatementLine,
    Statements,
    Valuation,
    num,
    text,
    when,
)
from app.research.provider import ResearchProvider

log = logging.getLogger(__name__)

SOURCE = "Yahoo Finance"

# Rows lifted out of the raw statements, in the order a reader wants them.
INCOME_ROWS = [
    ("Total Revenue", "Revenue"),
    ("Gross Profit", "Gross profit"),
    ("Operating Income", "Operating income"),
    ("Net Income", "Net income"),
    ("Diluted EPS", "EPS (diluted)"),
]
BALANCE_ROWS = [
    ("Total Assets", "Total assets"),
    ("Total Liabilities Net Minority Interest", "Total liabilities"),
    ("Stockholders Equity", "Shareholder equity"),
    ("Cash And Cash Equivalents", "Cash"),
    ("Total Debt", "Total debt"),
]
CASHFLOW_ROWS = [
    ("Operating Cash Flow", "Operating cash flow"),
    ("Capital Expenditure", "Capital expenditure"),
    ("Free Cash Flow", "Free cash flow"),
]


def _pct(value) -> float | None:
    """A fraction from the feed, expressed as a percentage."""
    out = num(value)
    return None if out is None else out * 100.0


def _stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


class YahooResearch(ResearchProvider):
    """Free company data. Delayed, and honest about being delayed."""

    name = "yahoo"

    def __init__(self) -> None:
        # Imported lazily so the rest of the app still starts if yfinance is
        # missing or broken; every method then degrades to None.
        self._yf = None
        try:
            import yfinance as yf

            self._yf = yf
        except Exception:
            log.exception("yfinance unavailable; company research disabled")

    # ---------------------------------------------------------------- helpers

    def _ticker(self, symbol: str):
        if self._yf is None:
            return None
        try:
            return self._yf.Ticker(symbol.upper())
        except Exception:
            log.exception("could not open ticker %s", symbol)
            return None

    def _info(self, symbol: str) -> dict:
        ticker = self._ticker(symbol)
        if ticker is None:
            return {}
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                return ticker.info or {}
        except Exception:
            log.warning("no info for %s", symbol, exc_info=True)
            return {}

    def _prov(self, as_of: str | None = None) -> Provenance:
        return Provenance(source=SOURCE, as_of=as_of or _stamp(), delayed=True)

    # ---------------------------------------------------------------- profile

    def profile(self, symbol: str) -> CompanyProfile | None:
        info = self._info(symbol)
        if not info:
            return None
        return CompanyProfile(
            symbol=symbol.upper(),
            name=text(info.get("longName") or info.get("shortName")),
            sector=text(info.get("sector")),
            industry=text(info.get("industry")),
            country=text(info.get("country")),
            employees=num(info.get("fullTimeEmployees")),
            website=text(info.get("website")),
            summary=text(info.get("longBusinessSummary")),
            currency=text(info.get("currency")),
            exchange=text(info.get("fullExchangeName") or info.get("exchange")),
            provenance=self._prov(),
        )

    # ------------------------------------------------------------------ price

    def price(self, symbol: str) -> PriceSnapshot | None:
        info = self._info(symbol)
        if not info:
            return None

        price = num(info.get("currentPrice") or info.get("regularMarketPrice"))
        previous = num(info.get("previousClose") or info.get("regularMarketPreviousClose"))
        high52 = num(info.get("fiftyTwoWeekHigh"))
        low52 = num(info.get("fiftyTwoWeekLow"))
        volume = num(info.get("volume") or info.get("regularMarketVolume"))
        avg_volume = num(info.get("averageVolume"))

        change = change_pct = None
        if price is not None and previous:
            change = price - previous
            change_pct = (change / previous) * 100.0

        # Distance from the yearly extremes: the cheapest way to say whether a
        # price is near its ceiling or scraping its floor.
        from_high = ((price - high52) / high52 * 100.0) if price and high52 else None
        from_low = ((price - low52) / low52 * 100.0) if price and low52 else None
        rel_volume = (volume / avg_volume) if volume and avg_volume else None

        return PriceSnapshot(
            price=price,
            previous_close=previous,
            change=change,
            change_pct=change_pct,
            day_high=num(info.get("dayHigh")),
            day_low=num(info.get("dayLow")),
            week52_high=high52,
            week52_low=low52,
            from_52w_high_pct=from_high,
            from_52w_low_pct=from_low,
            volume=volume,
            average_volume=avg_volume,
            relative_volume=rel_volume,
            market_cap=num(info.get("marketCap")),
            beta=num(info.get("beta")),
            provenance=self._prov(),
        )

    # -------------------------------------------------------------- valuation

    def valuation(self, symbol: str) -> Valuation | None:
        info = self._info(symbol)
        if not info:
            return None

        market_cap = num(info.get("marketCap"))
        fcf = num(info.get("freeCashflow"))
        fcf_yield = (fcf / market_cap * 100.0) if fcf and market_cap else None

        return Valuation(
            pe=num(info.get("trailingPE")),
            forward_pe=num(info.get("forwardPE")),
            peg=num(info.get("pegRatio") or info.get("trailingPegRatio")),
            price_to_sales=num(info.get("priceToSalesTrailing12Months")),
            price_to_book=num(info.get("priceToBook")),
            ev_to_ebitda=num(info.get("enterpriseToEbitda")),
            ev_to_revenue=num(info.get("enterpriseToRevenue")),
            eps=num(info.get("trailingEps")),
            forward_eps=num(info.get("forwardEps")),
            fcf_yield_pct=fcf_yield,
            # Already a percentage in this feed — do not multiply.
            dividend_yield_pct=num(info.get("dividendYield")),
            provenance=self._prov(),
        )

    # ---------------------------------------------------------------- quality

    def quality(self, symbol: str) -> Quality | None:
        info = self._info(symbol)
        if not info:
            return None

        cash = num(info.get("totalCash"))
        debt = num(info.get("totalDebt"))
        net_debt = (debt - cash) if debt is not None and cash is not None else None

        return Quality(
            revenue=num(info.get("totalRevenue")),
            revenue_growth_pct=_pct(info.get("revenueGrowth")),
            earnings_growth_pct=_pct(info.get("earningsGrowth")),
            gross_margin_pct=_pct(info.get("grossMargins")),
            operating_margin_pct=_pct(info.get("operatingMargins")),
            net_margin_pct=_pct(info.get("profitMargins")),
            return_on_equity_pct=_pct(info.get("returnOnEquity")),
            return_on_assets_pct=_pct(info.get("returnOnAssets")),
            free_cash_flow=num(info.get("freeCashflow")),
            operating_cash_flow=num(info.get("operatingCashflow")),
            total_cash=cash,
            total_debt=debt,
            net_debt=net_debt,
            # Already expressed as a percentage of equity in this feed.
            debt_to_equity=num(info.get("debtToEquity")),
            current_ratio=num(info.get("currentRatio")),
            provenance=self._prov(),
        )

    # ------------------------------------------------------------- statements

    def statements(self, symbol: str) -> Statements | None:
        ticker = self._ticker(symbol)
        if ticker is None:
            return None

        annual = self._read_statements(ticker, quarterly=False)
        quarterly = self._read_statements(ticker, quarterly=True)
        if not annual and not quarterly:
            return None
        return Statements(annual=annual, quarterly=quarterly, provenance=self._prov())

    def _read_statements(self, ticker, quarterly: bool) -> list[StatementLine]:
        sources = (
            [
                (ticker, "quarterly_income_stmt", INCOME_ROWS),
                (ticker, "quarterly_balance_sheet", BALANCE_ROWS),
                (ticker, "quarterly_cashflow", CASHFLOW_ROWS),
            ]
            if quarterly
            else [
                (ticker, "income_stmt", INCOME_ROWS),
                (ticker, "balance_sheet", BALANCE_ROWS),
                (ticker, "cashflow", CASHFLOW_ROWS),
            ]
        )

        lines: list[StatementLine] = []
        for obj, attr, wanted in sources:
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    frame = getattr(obj, attr)
            except Exception:
                continue
            if frame is None or getattr(frame, "empty", True):
                continue

            # Columns are reporting periods, newest first. Five is enough to
            # show a trend without turning the table into a spreadsheet.
            periods = [when(c) for c in list(frame.columns)[:5]]
            for row_key, label in wanted:
                if row_key not in frame.index:
                    continue
                values = [num(v) for v in list(frame.loc[row_key])[:5]]
                if all(v is None for v in values):
                    continue
                lines.append(StatementLine(label=label, periods=periods, values=values))
        return lines

    # --------------------------------------------------------------- earnings

    def earnings(self, symbol: str) -> Earnings | None:
        ticker = self._ticker(symbol)
        if ticker is None:
            return None

        history: list[EarningsEvent] = []
        beats = misses = 0
        next_date = None
        now = datetime.now(timezone.utc)

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                frame = ticker.earnings_dates
        except Exception:
            frame = None

        if frame is not None and not getattr(frame, "empty", True):
            for stamp, row in frame.iterrows():
                estimate = num(row.get("EPS Estimate"))
                actual = num(row.get("Reported EPS"))
                surprise = num(row.get("Surprise(%)"))

                # A row with no reported figure is a scheduled future report.
                if actual is None:
                    try:
                        upcoming = stamp.to_pydatetime()
                        if upcoming > now and (next_date is None or when(stamp) < next_date):
                            next_date = when(stamp)
                    except Exception:
                        pass
                    continue

                if surprise is not None:
                    if surprise > 0:
                        beats += 1
                    elif surprise < 0:
                        misses += 1
                history.append(
                    EarningsEvent(
                        date=when(stamp),
                        eps_estimate=estimate,
                        eps_actual=actual,
                        surprise_pct=surprise,
                    )
                )

        if next_date is None:
            next_date = self._calendar_date(ticker)

        if not history and next_date is None:
            return None
        return Earnings(
            next_date=next_date,
            history=history[:8],
            beats=beats or None,
            misses=misses or None,
            provenance=self._prov(),
        )

    def _calendar_date(self, ticker) -> str | None:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                calendar = ticker.calendar
        except Exception:
            return None
        if not isinstance(calendar, dict):
            return None
        dates = calendar.get("Earnings Date")
        if isinstance(dates, (list, tuple)) and dates:
            return when(dates[0])
        return when(dates)

    # --------------------------------------------------------------- analysts

    def analysts(self, symbol: str) -> Analysts | None:
        info = self._info(symbol)
        ticker = self._ticker(symbol)
        if not info and ticker is None:
            return None

        strong_buy = buy = hold = sell = strong_sell = None
        if ticker is not None:
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    frame = ticker.recommendations
                if frame is not None and not getattr(frame, "empty", True):
                    latest = frame.iloc[0]
                    strong_buy = num(latest.get("strongBuy"))
                    buy = num(latest.get("buy"))
                    hold = num(latest.get("hold"))
                    sell = num(latest.get("sell"))
                    strong_sell = num(latest.get("strongSell"))
            except Exception:
                log.debug("no recommendation split for %s", symbol, exc_info=True)

        out = Analysts(
            consensus=text(info.get("recommendationKey")),
            analyst_count=num(info.get("numberOfAnalystOpinions")),
            target_mean=num(info.get("targetMeanPrice")),
            target_high=num(info.get("targetHighPrice")),
            target_low=num(info.get("targetLowPrice")),
            strong_buy=strong_buy,
            buy=buy,
            hold=hold,
            sell=sell,
            strong_sell=strong_sell,
            provenance=self._prov(),
        )
        empty = all(
            getattr(out, f) is None
            for f in ("consensus", "target_mean", "strong_buy", "buy", "hold")
        )
        return None if empty else out

    # -------------------------------------------------------------- ownership

    def ownership(self, symbol: str) -> Ownership | None:
        ticker = self._ticker(symbol)
        if ticker is None:
            return None
        info = self._info(symbol)

        holders: list[Holder] = []
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                frame = ticker.institutional_holders
            if frame is not None and not getattr(frame, "empty", True):
                for _, row in frame.head(8).iterrows():
                    holders.append(
                        Holder(
                            name=text(row.get("Holder")),
                            # pctHeld arrives as a fraction of shares outstanding.
                            pct_held=_pct(row.get("pctHeld")),
                            shares=num(row.get("Shares")),
                            reported=when(row.get("Date Reported")),
                        )
                    )
        except Exception:
            log.debug("no institutional holders for %s", symbol, exc_info=True)

        trades: list[InsiderTrade] = []
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                frame = ticker.insider_transactions
            if frame is not None and not getattr(frame, "empty", True):
                for _, row in frame.head(10).iterrows():
                    trades.append(
                        InsiderTrade(
                            person=text(row.get("Insider")),
                            action=text(row.get("Text") or row.get("Transaction")),
                            shares=num(row.get("Shares")),
                            value=num(row.get("Value")),
                            date=when(row.get("Start Date") or row.get("Date")),
                        )
                    )
        except Exception:
            log.debug("no insider transactions for %s", symbol, exc_info=True)

        if not holders and not trades and not info:
            return None
        return Ownership(
            insider_pct=_pct(info.get("heldPercentInsiders")),
            institution_pct=_pct(info.get("heldPercentInstitutions")),
            top_holders=holders,
            insider_trades=trades,
            provenance=self._prov(),
        )

    # --------------------------------------------------------------- dividend

    def dividend(self, symbol: str) -> Dividend | None:
        info = self._info(symbol)
        if not info:
            return None
        # Already a percentage here, unlike the margin fields.
        yield_pct = num(info.get("dividendYield"))
        rate = num(info.get("dividendRate"))
        if yield_pct is None and rate is None:
            return None

        history: list[dict] = []
        ticker = self._ticker(symbol)
        if ticker is not None:
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    series = ticker.dividends
                if series is not None and len(series):
                    for stamp, value in list(series.items())[-12:]:
                        amount = num(value)
                        if amount is not None:
                            history.append({"date": when(stamp), "amount": amount})
            except Exception:
                log.debug("no dividend history for %s", symbol, exc_info=True)

        return Dividend(
            yield_pct=yield_pct,
            rate=rate,
            payout_ratio_pct=_pct(info.get("payoutRatio")),
            five_year_avg_yield_pct=num(info.get("fiveYearAvgDividendYield")),
            ex_date=when(info.get("exDividendDate")),
            history=history,
            provenance=self._prov(),
        )

    # ----------------------------------------------------------------- search

    def search(self, query: str, limit: int = 8) -> list[dict]:
        query = (query or "").strip()
        if not query or self._yf is None:
            return []
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                found = self._yf.Search(query, max_results=limit)
            quotes = getattr(found, "quotes", None) or []
        except Exception:
            log.debug("search failed for %r", query, exc_info=True)
            return []

        out = []
        for q in quotes[:limit]:
            symbol = text(q.get("symbol"))
            if not symbol:
                continue
            out.append(
                {
                    "symbol": symbol,
                    "name": text(q.get("longname") or q.get("shortname")),
                    "exchange": text(q.get("exchDisp") or q.get("exchange")),
                    "type": text(q.get("quoteType")),
                }
            )
        return out
