package com.bofstudios.moneytree.engine

import kotlin.math.pow

/**
 * One fiscal year from a company's annual report (10-K or 20-F), in the
 * currency it reports in. Null means the filing did not state that figure.
 */
data class FiscalYear(
    /** Last day of the fiscal year, "2025-09-27". */
    val end: String,
    val revenue: Double? = null,
    val netIncome: Double? = null,
    val grossProfit: Double? = null,
    val operatingIncome: Double? = null,
    val equity: Double? = null,
    val debt: Double? = null,
    val operatingCashFlow: Double? = null,
    val capex: Double? = null,
    /** Diluted weighted-average shares — ordinary shares, not ADRs. */
    val shares: Double? = null,
    val interest: Double? = null,
    val cash: Double? = null,
) {
    val freeCashFlow: Double? get() = if (operatingCashFlow != null && capex != null) operatingCashFlow - capex else null
}

/** What a company has told the SEC about itself, a few years deep. */
data class Filings(
    val symbol: String,
    val name: String,
    /** "USD", "EUR", "DKK"… — every figure in [years] is in this currency. */
    val currency: String,
    /** Files 20-F/40-F: its New York shares may be ADRs worth more or less than one share. */
    val foreign: Boolean,
    /** An ETF or trust: a basket of companies with no income statement of its own. */
    val fund: Boolean,
    /** Oldest first. */
    val years: List<FiscalYear>,
    val fetchedAt: Long,
    /** The AI's three-line read of the business, if one was asked for. */
    val aiRead: String? = null,
)

/** Annual reports, from the SEC's free XBRL API on the phone. */
interface FilingsSource {
    /** Null when nothing could be found for the symbol. */
    suspend fun filings(symbol: String): Filings?
}

/** How many US dollars one unit of a currency buys. */
interface FxSource {
    suspend fun usdPer(currency: String): Double?
}

enum class CheckKind { BUSINESS, MOAT, MANAGEMENT, VALUE, RISK }

enum class Verdict { PASS, WATCH, FAIL, UNKNOWN }

/**
 * The answer after the five checks, in the spirit of "if the price is wrong,
 * it waits": a great business at a silly price is a WAIT, not a buy.
 */
enum class Decision { BUY_ZONE, WAIT, AVOID, UNKNOWN }

/** The numbers behind a check, named so each language can phrase them. */
enum class Metric {
    PROFIT_YEARS, REVENUE_GROWTH, GROSS_MARGIN, OPERATING_MARGIN, RETURN_ON_EQUITY,
    SHARE_CHANGE, DEBT_TO_PROFIT, INTEREST_COVER, PRICE, VALUE, PRICE_TO_VALUE,
    VS_200_DAY, DAILY_SWING, RED_FLAG, FUND,
}

data class Fact(val metric: Metric, val value: Double, val text: String? = null)

data class Check(val kind: CheckKind, val verdict: Verdict, val facts: List<Fact>) {
    val points: Double get() = when (verdict) { Verdict.PASS -> 1.0; Verdict.WATCH, Verdict.UNKNOWN -> 0.5; Verdict.FAIL -> 0.0 }
}

data class QualityReport(
    val symbol: String,
    val name: String,
    val fund: Boolean,
    val checks: List<Check>,
    val decision: Decision,
    /** 0 to 5: a pass is a point, a watch or an unknown half. */
    val score: Double,
    val price: Double?,
    /** The estimate of what one share (or ADR) is worth, in dollars. */
    val value: Double?,
    val fiscalYearEnd: String?,
    val computedAt: Long,
    val aiRead: String? = null,
) {
    fun check(kind: CheckKind): Check? = checks.firstOrNull { it.kind == kind }
    /** Price over value: under 1 is a discount, 1.4 means 40% above the estimate. */
    val priceToValue: Double? get() = if (price != null && value != null && value > 0) price / value else null
}

/**
 * The five questions a careful long-term investor asks, answered from the
 * company's own annual reports, today's price and the news:
 *
 *  1. BUSINESS   — does it reliably make money, and is it growing?
 *  2. MOAT       — are its margins and returns high enough that rivals clearly
 *                  cannot copy it cheaply?
 *  3. MANAGEMENT — does it buy back shares rather than print them, and earn
 *                  well on the owners' money without piling up debt?
 *  4. VALUE      — is the price below a conservative estimate of what the
 *                  business is worth (owner earnings, discounted at 10%)?
 *  5. RISK       — debt it can carry, interest it can pay, no red flags in the
 *                  news, and a price that does not swing wildly.
 *
 * Every threshold is a plain number written here, so a verdict can always be
 * traced back to the figure that caused it. Nothing is predicted.
 */
object Quality {
    /** What the owners' money must earn: the discount rate of the value estimate. */
    const val DISCOUNT = 0.10
    const val TERMINAL_GROWTH = 0.03
    const val MAX_GROWTH = 0.15
    /** Past growth is taken at three quarters: the future rarely repeats it in full. */
    const val GROWTH_HAIRCUT = 0.75

    fun evaluate(
        symbol: String,
        filings: Filings?,
        price: Double?,
        /** Dollars per unit of the reporting currency; 1 for USD. */
        usdPer: Double?,
        /** Ordinary shares behind one New York share; null when unknown. */
        sharesPerListing: Double?,
        daily: List<Bar>,
        flags: List<RedFlag>,
        now: Long,
    ): QualityReport {
        val risk = riskOf(filings, daily, flags)
        if (filings == null || filings.fund) return fund(symbol, filings, price, daily, risk, now)

        val y = filings.years
        val latest = y.lastOrNull()
        val ni = y.mapNotNull { it.netIncome }
        val revs = y.mapNotNull { it.revenue }
        val revGrowth = cagr(revs)
        val profitYears = ni.count { it > 0 }
        val last3 = y.takeLast(3)
        val om = avg(last3.mapNotNull { r -> ratio(r.operatingIncome, r.revenue) })
        val gm = avg(last3.mapNotNull { r -> ratio(r.grossProfit, r.revenue) })
        val roe = avg(last3.mapNotNull { r -> if (r.netIncome != null && r.equity != null && r.equity > 0) r.netIncome / r.equity else null })
        val shares = y.mapNotNull { it.shares }.takeLast(3)
        val shareChange = if (shares.size >= 2 && shares.first() > 0) (shares.last() / shares.first()).pow(1.0 / (shares.size - 1)) - 1 else null
        val lastNi = latest?.netIncome
        val debt = y.lastOrNull { it.debt != null }?.debt
        val debtToProfit = if (debt != null && lastNi != null && lastNi > 0) debt / lastNi else null
        val cover = y.lastOrNull { it.operatingIncome != null && it.interest != null && it.interest > 0 }
            ?.let { it.operatingIncome!! / it.interest!! }

        // ----------------------------------------------------------- business
        val business = when {
            lastNi == null -> Verdict.UNKNOWN
            lastNi > 0 && profitYears >= ni.size - 1 && (revGrowth ?: 0.0) >= 0 -> Verdict.PASS
            lastNi <= 0 && profitYears * 2 < ni.size -> Verdict.FAIL
            else -> Verdict.WATCH
        }
        // --------------------------------------------------------------- moat
        val moat = when {
            om == null && roe == null -> Verdict.UNKNOWN
            (om ?: 0.0) >= 0.20 && (roe ?: 0.0) >= 0.15 -> Verdict.PASS
            (gm ?: 0.0) >= 0.40 && (om ?: 0.0) >= 0.15 && (roe ?: 0.0) >= 0.12 -> Verdict.PASS
            (om ?: 0.0) >= 0.10 || (roe ?: 0.0) >= 0.12 -> Verdict.WATCH
            else -> Verdict.FAIL
        }
        // --------------------------------------------------------- management
        val management = when {
            shareChange == null && roe == null -> Verdict.UNKNOWN
            (shareChange ?: 0.0) > 0.03 || (roe != null && roe < 0) -> Verdict.FAIL
            (shareChange ?: 0.0) <= 0.005 && (roe ?: 0.0) >= 0.12 && (debtToProfit ?: 0.0) <= 3.0 -> Verdict.PASS
            else -> Verdict.WATCH
        }
        // -------------------------------------------------------------- value
        val value = valuePerListing(filings, usdPer, sharesPerListing, revGrowth)
        val pv = if (price != null && value != null && value > 0) price / value else null
        val valueVerdict = when {
            price == null || value == null -> Verdict.UNKNOWN
            value <= 0 -> Verdict.FAIL
            pv!! <= 1.0 -> Verdict.PASS
            pv <= 1.5 -> Verdict.WATCH
            else -> Verdict.FAIL
        }

        val checks = listOf(
            Check(CheckKind.BUSINESS, business, listOfNotNull(
                Fact(Metric.PROFIT_YEARS, profitYears.toDouble(), "$profitYears/${ni.size}"),
                revGrowth?.let { Fact(Metric.REVENUE_GROWTH, it) },
            )),
            Check(CheckKind.MOAT, moat, listOfNotNull(
                gm?.let { Fact(Metric.GROSS_MARGIN, it) },
                om?.let { Fact(Metric.OPERATING_MARGIN, it) },
                roe?.let { Fact(Metric.RETURN_ON_EQUITY, it) },
            )),
            Check(CheckKind.MANAGEMENT, management, listOfNotNull(
                shareChange?.let { Fact(Metric.SHARE_CHANGE, it) },
                roe?.let { Fact(Metric.RETURN_ON_EQUITY, it) },
                debtToProfit?.let { Fact(Metric.DEBT_TO_PROFIT, it) },
            )),
            Check(CheckKind.VALUE, valueVerdict, listOfNotNull(
                price?.let { Fact(Metric.PRICE, it) },
                value?.let { Fact(Metric.VALUE, it) },
                pv?.let { Fact(Metric.PRICE_TO_VALUE, it) },
            )),
            risk.copy(facts = listOfNotNull(
                debtToProfit?.let { Fact(Metric.DEBT_TO_PROFIT, it) },
                cover?.let { Fact(Metric.INTEREST_COVER, it) },
            ) + risk.facts),
        )
        val score = checks.sumOf { it.points }
        val decision = when {
            checks.all { it.verdict == Verdict.UNKNOWN } -> Decision.UNKNOWN
            business == Verdict.FAIL || risk.verdict == Verdict.FAIL || score < 2.5 -> Decision.AVOID
            valueVerdict == Verdict.PASS && score >= 4.0 -> Decision.BUY_ZONE
            else -> Decision.WAIT
        }
        return QualityReport(symbol, filings.name, false, checks, decision, score, price, value,
            latest?.end, now, filings.aiRead)
    }

    /**
     * Owner earnings — the average of free cash flow (three-year mean) and
     * net income, since heavy growth spending makes cash flow alone look
     * poor — grown for ten years at three quarters of past revenue growth
     * (capped at 15%, halved after year five), then at 3% forever, all
     * discounted at 10%. Net cash is added, debt taken off. Divided by the
     * diluted share count and turned into dollars per New York share.
     */
    fun valuePerListing(f: Filings, usdPer: Double?, sharesPerListing: Double?, revGrowth: Double?): Double? {
        val y = f.years
        val ni = y.lastOrNull()?.netIncome ?: return null
        val fcf = y.takeLast(3).mapNotNull { it.freeCashFlow }
        val owner = if (fcf.isNotEmpty()) (fcf.average() + ni) / 2 else ni * 0.85
        val shares = y.lastOrNull { it.shares != null }?.shares?.takeIf { it > 0 } ?: return null
        val fx = if (f.currency == "USD") 1.0 else usdPer ?: return null
        val perListing = when {
            sharesPerListing != null -> sharesPerListing
            f.foreign -> return null // an ADR of unknown size: no honest per-share figure
            else -> 1.0
        }
        val g = (revGrowth ?: 0.0).coerceIn(0.0, MAX_GROWTH) * GROWTH_HAIRCUT
        var flow = owner.coerceAtLeast(0.0)
        var total = 0.0
        for (year in 1..10) {
            flow *= 1 + if (year <= 5) g else g / 2
            total += flow / (1 + DISCOUNT).pow(year)
        }
        total += flow * (1 + TERMINAL_GROWTH) / (DISCOUNT - TERMINAL_GROWTH) / (1 + DISCOUNT).pow(10)
        val cash = y.lastOrNull { it.cash != null }?.cash ?: 0.0
        val debt = y.lastOrNull { it.debt != null }?.debt ?: 0.0
        return (total + cash - debt) / shares * perListing * fx
    }

    /** Debt, interest, the news and how hard the price swings. */
    private fun riskOf(filings: Filings?, daily: List<Bar>, flags: List<RedFlag>): Check {
        val y = filings?.years.orEmpty()
        val lastNi = y.lastOrNull()?.netIncome
        val debt = y.lastOrNull { it.debt != null }?.debt
        val debtToProfit = if (debt != null && lastNi != null && lastNi > 0) debt / lastNi else null
        val cover = y.lastOrNull { it.operatingIncome != null && it.interest != null && it.interest > 0 }
            ?.let { it.operatingIncome!! / it.interest!! }
        val negativeEquity = (y.lastOrNull()?.equity ?: 1.0) < 0 && (lastNi ?: 1.0) < 0
        val swing = dailySwing(daily)
        val severe = flags.any { it.kind.severe }
        val verdict = when {
            severe || negativeEquity -> Verdict.FAIL
            debtToProfit != null && debtToProfit > 6 -> Verdict.FAIL
            cover != null && cover < 2.5 -> Verdict.FAIL
            swing != null && swing > 0.08 -> Verdict.FAIL
            flags.isNotEmpty() -> Verdict.WATCH
            debtToProfit != null && debtToProfit > 3 -> Verdict.WATCH
            cover != null && cover < 6 -> Verdict.WATCH
            swing != null && swing > 0.045 -> Verdict.WATCH
            filings == null && swing == null -> Verdict.UNKNOWN
            else -> Verdict.PASS
        }
        return Check(CheckKind.RISK, verdict, listOfNotNull(
            swing?.let { Fact(Metric.DAILY_SWING, it) },
        ) + flags.map { Fact(Metric.RED_FLAG, 1.0, it.kind.name) })
    }

    /**
     * An ETF has no income statement: the business, moat and management
     * questions do not apply. Value becomes "how far above its own 200-day
     * average is it", and risk is the news and the swing.
     */
    private fun fund(symbol: String, f: Filings?, price: Double?, daily: List<Bar>, risk: Check, now: Long): QualityReport {
        val sma = if (daily.size >= 200) daily.takeLast(200).map { it.close }.average() else null
        val last = price ?: daily.lastOrNull()?.close
        val vs = if (sma != null && last != null && sma > 0) last / sma else null
        val value = when {
            vs == null -> Verdict.UNKNOWN
            vs <= 1.0 -> Verdict.PASS
            vs <= 1.10 -> Verdict.WATCH
            else -> Verdict.FAIL
        }
        val na = { k: CheckKind -> Check(k, Verdict.UNKNOWN, listOf(Fact(Metric.FUND, 1.0))) }
        val checks = listOf(
            na(CheckKind.BUSINESS), na(CheckKind.MOAT), na(CheckKind.MANAGEMENT),
            Check(CheckKind.VALUE, value, listOfNotNull(last?.let { Fact(Metric.PRICE, it) }, vs?.let { Fact(Metric.VS_200_DAY, it) })),
            risk,
        )
        val isFund = f?.fund == true || looksLikeFund(symbol)
        val known = checks.filter { it.verdict != Verdict.UNKNOWN }
        val score = if (known.isEmpty()) 2.5 else known.sumOf { it.points } / known.size * 5
        val decision = when {
            !isFund && f == null -> Decision.UNKNOWN
            risk.verdict == Verdict.FAIL -> Decision.AVOID
            value == Verdict.PASS -> Decision.BUY_ZONE
            value == Verdict.UNKNOWN && risk.verdict == Verdict.UNKNOWN -> Decision.UNKNOWN
            else -> Decision.WAIT
        }
        return QualityReport(symbol, f?.name ?: symbol, isFund, checks, decision, score, last, null, null, now, f?.aiRead)
    }

    /** Average true range of the last 14 days, as a share of the price. */
    fun dailySwing(daily: List<Bar>): Double? {
        if (daily.size < 20) return null
        val atr = Indicators.atr(daily, 14).last()
        val close = daily.last().close
        return if (!atr.isNaN() && close > 0) atr / close else null
    }

    /** Compound yearly growth from the first figure to the last; needs three. */
    fun cagr(values: List<Double>): Double? {
        if (values.size < 3) return null
        val first = values.first(); val last = values.last()
        if (first <= 0 || last <= 0) return null
        return (last / first).pow(1.0 / (values.size - 1)) - 1
    }

    private fun ratio(a: Double?, b: Double?): Double? = if (a != null && b != null && b != 0.0) a / b else null
    private fun avg(v: List<Double>): Double? = if (v.isEmpty()) null else v.average()

    /** Well-known funds, so they are judged as funds even before the SEC answers. */
    fun looksLikeFund(symbol: String): Boolean = symbol.uppercase() in FUNDS

    val FUNDS = setOf(
        "SPY", "VOO", "IVV", "QQQ", "QQQM", "DIA", "IWM", "VTI", "VT", "VEA", "VWO", "VGK", "EFA", "EEM",
        "IEFA", "IEMG", "SCHD", "VIG", "VUG", "VTV", "XLK", "XLF", "XLE", "XLV", "XLY", "XLP", "XLI",
        "XLU", "XLB", "XLRE", "XLC", "SMH", "SOXX", "ARKK", "GLD", "SLV", "TLT", "IEF", "SHY", "BND",
        "AGG", "HYG", "LQD", "EWG", "EWU", "EWJ", "FEZ", "EZU", "IEUR", "SPLG", "RSP", "MDY", "IJH", "IJR",
    )

    /**
     * Ordinary shares behind one New York-listed share of the foreign
     * companies Money Tree knows. A 20-F filer missing here gets no value
     * estimate rather than a wrong one.
     */
    val SHARES_PER_LISTING = mapOf(
        "ASML" to 1.0, "SAP" to 1.0, "NVO" to 1.0, "AZN" to 0.5, "SHEL" to 2.0, "TTE" to 1.0,
        "UL" to 1.0, "BP" to 6.0, "HSBC" to 5.0, "TSM" to 5.0, "BABA" to 8.0,
    )
}
