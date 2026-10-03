package com.bofstudios.moneytree.research

import com.bofstudios.moneytree.engine.BrainStore
import com.bofstudios.moneytree.engine.CompanyEvents
import com.bofstudios.moneytree.engine.EventsSource
import com.bofstudios.moneytree.engine.FilingEvent
import com.bofstudios.moneytree.engine.Filings
import com.bofstudios.moneytree.engine.FilingsSource
import com.bofstudios.moneytree.engine.FiscalYear
import com.bofstudios.moneytree.engine.Quality
import com.google.gson.stream.JsonReader
import com.google.gson.stream.JsonToken
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import java.io.Reader
import java.time.LocalDate
import java.time.temporal.ChronoUnit
import java.util.concurrent.TimeUnit
import kotlin.math.abs

/**
 * Company annual reports, straight from the SEC's free XBRL API — no key,
 * no account, nothing about the owner sent.
 *
 * Verified against the real API before this was written:
 *  - data.sec.gov answers a plain declared app name ([USER_AGENT]) and turns
 *    away generic HTTP-library agents;
 *  - a company file is 1–5 MB of JSON (≈300 KB gzipped, which OkHttp asks
 *    for), so it is streamed and only a dozen concepts are kept;
 *  - US companies report in "us-gaap", European ones (ASML aside) in
 *    "ifrs-full", often in euros or kroner — so both are read, with the unit;
 *  - an ETF such as SPY has a CIK but no company facts (404).
 */
class SecEdgar(
    private val store: BrainStore? = null,
    private val http: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(20, TimeUnit.SECONDS).readTimeout(60, TimeUnit.SECONDS).build(),
    private val now: () -> Long = System::currentTimeMillis,
) : FilingsSource, EventsSource {
    private val ciks = HashMap<String, Pair<Long, String>>()

    /**
     * The company's filing index (data.sec.gov/submissions): 8-Ks with their
     * item numbers and acceptance times, Form 4 counts, and the dates results
     * came out. About 200 KB, a few times a day.
     */
    override suspend fun events(symbol: String): CompanyEvents? = withContext(Dispatchers.IO) {
        val sym = symbol.uppercase()
        val (cik, _) = cik(sym) ?: return@withContext null
        val url = "https://data.sec.gov/submissions/CIK%010d.json".format(cik)
        runCatching {
            http.newCall(get(url)).execute().use { r ->
                if (!r.isSuccessful) return@use null
                parseEvents(sym, JSONObject(r.body?.string().orEmpty()), now())
            }
        }.getOrNull()
    }

    override suspend fun filings(symbol: String): Filings? = withContext(Dispatchers.IO) {
        val sym = symbol.uppercase()
        val (cik, entity) = cik(sym) ?: return@withContext null
        val url = "https://data.sec.gov/api/xbrl/companyfacts/CIK%010d.json".format(cik)
        http.newCall(get(url)).execute().use { r ->
            when {
                r.code == 404 -> if (Quality.looksLikeFund(sym) || FUND_WORDS.any { it in entity.uppercase() }) {
                    Filings(sym, entity, "USD", foreign = false, fund = true, years = emptyList(), fetchedAt = now())
                } else null
                !r.isSuccessful -> null
                else -> r.body?.charStream()?.use { parse(sym, it, now()) }
            }
        }
    }

    /** CIK and entity name, from the built-in list, the cache, or the SEC's company search. */
    private fun cik(symbol: String): Pair<Long, String>? {
        ciks[symbol]?.let { return it }
        KNOWN[symbol]?.let { return (it to symbol).also { p -> ciks[symbol] = p } }
        store?.read("cik_$symbol")?.split("|", limit = 2)?.takeIf { it.size == 2 }?.let { parts ->
            parts[0].toLongOrNull()?.let { return (it to parts[1]).also { p -> ciks[symbol] = p } }
        }
        val url = "https://efts.sec.gov/LATEST/search-index".toHttpUrl().newBuilder()
            .addQueryParameter("keysTyped", symbol.lowercase()).build().toString()
        val found = runCatching {
            http.newCall(get(url)).execute().use { r ->
                if (!r.isSuccessful) return null
                val hits = JSONObject(r.body?.string().orEmpty()).optJSONObject("hits")?.optJSONArray("hits") ?: return null
                (0 until hits.length()).map { hits.getJSONObject(it) }.firstNotNullOfOrNull { h ->
                    val src = h.optJSONObject("_source") ?: return@firstNotNullOfOrNull null
                    val tickers = src.optString("tickers").split(",").map { it.trim().uppercase() }
                    if (symbol in tickers) h.optString("_id").toLongOrNull()?.let { it to src.optString("entity").substringBefore(" (").trim() } else null
                }
            }
        }.getOrNull() ?: return null
        ciks[symbol] = found
        store?.write("cik_$symbol", "${found.first}|${found.second}")
        return found
    }

    private fun get(url: String) = Request.Builder().url(url).header("User-Agent", USER_AGENT).build()

    companion object {
        const val USER_AGENT = "BofStudios MoneyTree-App/3.0"
        private val FUND_WORDS = listOf(" ETF", "TRUST", " FUND", "SPDR", "ISHARES", "VANGUARD", "INDEX")

        /** The default watchlists, so the first look needs no search. */
        val KNOWN = mapOf(
            "AAPL" to 320193L, "MSFT" to 789019L, "NVDA" to 1045810L, "AMZN" to 1018724L, "GOOGL" to 1652044L,
            "GOOG" to 1652044L, "META" to 1326801L, "TSLA" to 1318605L, "SPY" to 884394L, "ASML" to 937966L,
            "SAP" to 1000184L, "NVO" to 353278L, "AZN" to 901832L, "SHEL" to 1306965L, "TTE" to 879764L, "UL" to 217410L,
        )

        private val ANNUAL_FORMS = setOf("10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A")
        private val FOREIGN_FORMS = setOf("20-F", "20-F/A", "40-F", "40-F/A")

        /** Concepts per figure, best first; both taxonomies share most names. */
        private val CONCEPTS = linkedMapOf(
            "revenue" to listOf("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet",
                "RevenueFromContractWithCustomerIncludingAssessedTax", "Revenue", "RevenueFromContractsWithCustomers"),
            "netIncome" to listOf("NetIncomeLoss", "ProfitLossAttributableToOwnersOfParent", "ProfitLoss"),
            "grossProfit" to listOf("GrossProfit"),
            "costOfRevenue" to listOf("CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfSales"),
            "operatingIncome" to listOf("OperatingIncomeLoss", "ProfitLossFromOperatingActivities"),
            "equity" to listOf("StockholdersEquity", "EquityAttributableToOwnersOfParent",
                "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", "Equity"),
            "debt" to listOf("LongTermDebtNoncurrent", "LongTermDebt", "LongtermBorrowings",
                "NoncurrentPortionOfNoncurrentBorrowings", "Borrowings"),
            "ocf" to listOf("NetCashProvidedByUsedInOperatingActivities", "CashFlowsFromUsedInOperatingActivities",
                "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"),
            "capex" to listOf("PaymentsToAcquirePropertyPlantAndEquipment", "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
                "PurchaseOfPropertyPlantAndEquipmentIntangibleAssetsOtherThanGoodwillInvestmentPropertyAndOtherNoncurrentAssets",
                "PaymentsToAcquireProductiveAssets"),
            "shares" to listOf("WeightedAverageNumberOfDilutedSharesOutstanding", "AdjustedWeightedAverageShares", "WeightedAverageShares"),
            "interest" to listOf("InterestExpense", "InterestExpenseNonoperating", "FinanceCosts", "InterestExpenseDebt"),
            "cash" to listOf("CashAndCashEquivalentsAtCarryingValue", "CashAndCashEquivalents"),
        )
        /** Figures that cover a year (flows), rather than a balance on one day. */
        private val DURATIONS = setOf("revenue", "netIncome", "grossProfit", "costOfRevenue", "operatingIncome", "ocf", "capex", "shares", "interest")
        private val WANTED: Map<String, Int> = CONCEPTS.values.flatten().withIndex().associate { it.value to it.index }

        fun parseEvents(symbol: String, j: JSONObject, now: Long): CompanyEvents? {
            val r = j.optJSONObject("filings")?.optJSONObject("recent") ?: return null
            val form = r.optJSONArray("form") ?: return null
            val date = r.optJSONArray("filingDate")
            val accepted = r.optJSONArray("acceptanceDateTime")
            val items = r.optJSONArray("items")
            val acc = r.optJSONArray("accessionNumber")
            val events = ArrayList<FilingEvent>()
            val results = ArrayList<Long>()
            var insiders = 0
            for (i in 0 until form.length()) {
                val f = form.optString(i)
                val at = accepted?.optString(i)?.let { parseTime(it) }?.takeIf { it > 0 }
                    ?: date?.optString(i)?.let { parseDay(it) } ?: continue
                when (f) {
                    "8-K", "8-K/A" -> {
                        val its = items?.optString(i).orEmpty().split(",").map { it.trim() }.filter { it.isNotEmpty() }
                        if ("2.02" in its) results += at
                        if (now - at <= 90 * DAY) events += FilingEvent(symbol, its, at, acc?.optString(i).orEmpty())
                    }
                    "4" -> if (now - at <= 30 * DAY) insiders++
                }
            }
            return CompanyEvents(symbol, events.sortedByDescending { it.filedAt }, insiders, results.sortedDescending(), now)
        }

        private const val DAY = 86_400_000L
        private fun parseTime(s: String): Long = runCatching { java.time.Instant.parse(s).toEpochMilli() }.getOrDefault(0L)
        private fun parseDay(s: String): Long? = runCatching {
            LocalDate.parse(s).atStartOfDay(java.time.ZoneOffset.UTC).toInstant().toEpochMilli()
        }.getOrNull()

        private data class Raw(val concept: String, val unit: String, val start: String?, val end: String, val value: Double, val form: String, val filed: String)

        /**
         * Reads a company-facts document and keeps one row per fiscal year:
         * annual filings only, flows that really span a year (10-K files also
         * carry quarters), and the most recently filed figure for each period
         * — so restatements and stock splits are taken as later restated.
         */
        fun parse(symbol: String, source: Reader, now: Long): Filings? {
            val reader = JsonReader(source)
            var name = symbol
            val raws = ArrayList<Raw>()
            reader.beginObject()
            while (reader.hasNext()) {
                when (reader.nextName()) {
                    "entityName" -> name = reader.nextStringOrNull() ?: symbol
                    "facts" -> {
                        reader.beginObject()
                        while (reader.hasNext()) {
                            val taxonomy = reader.nextName()
                            if (taxonomy != "us-gaap" && taxonomy != "ifrs-full") { reader.skipValue(); continue }
                            reader.beginObject()
                            while (reader.hasNext()) {
                                val concept = reader.nextName()
                                if (concept !in WANTED) { reader.skipValue(); continue }
                                readConcept(reader, concept, raws)
                            }
                            reader.endObject()
                        }
                        reader.endObject()
                    }
                    else -> reader.skipValue()
                }
            }
            reader.endObject()
            return build(symbol, name, raws, now)
        }

        private fun readConcept(reader: JsonReader, concept: String, out: MutableList<Raw>) {
            reader.beginObject()
            while (reader.hasNext()) {
                if (reader.nextName() != "units") { reader.skipValue(); continue }
                reader.beginObject()
                while (reader.hasNext()) {
                    val unit = reader.nextName()
                    reader.beginArray()
                    while (reader.hasNext()) {
                        var start: String? = null; var end: String? = null; var value: Double? = null
                        var form = ""; var filed = ""
                        reader.beginObject()
                        while (reader.hasNext()) {
                            when (reader.nextName()) {
                                "start" -> start = reader.nextStringOrNull()
                                "end" -> end = reader.nextStringOrNull()
                                "val" -> value = if (reader.peek() == JsonToken.NUMBER) reader.nextDouble() else { reader.skipValue(); null }
                                "form" -> form = reader.nextStringOrNull().orEmpty()
                                "filed" -> filed = reader.nextStringOrNull().orEmpty()
                                else -> reader.skipValue()
                            }
                        }
                        reader.endObject()
                        if (end != null && value != null && form in ANNUAL_FORMS) out += Raw(concept, unit, start, end, value, form, filed)
                    }
                    reader.endArray()
                }
                reader.endObject()
            }
            reader.endObject()
        }

        private fun JsonReader.nextStringOrNull(): String? = if (peek() == JsonToken.NULL) { nextNull(); null } else nextString()

        private data class Series(val lastEnd: String, val priority: Int, val unit: String, val byEnd: Map<String, Double>)

        private fun series(key: String, raws: List<Raw>): Series? {
            var best: Series? = null
            for ((priority, concept) in CONCEPTS.getValue(key).withIndex()) {
                for ((unit, rows) in raws.filter { it.concept == concept }.groupBy { it.unit }) {
                    if ((key == "shares") != (unit == "shares")) continue
                    val byEnd = HashMap<String, Raw>()
                    for (r in rows) {
                        if (key in DURATIONS) {
                            val s = r.start ?: continue
                            val days = runCatching { ChronoUnit.DAYS.between(LocalDate.parse(s), LocalDate.parse(r.end)) }.getOrNull() ?: continue
                            if (days !in 330..400) continue
                        }
                        val prev = byEnd[r.end]
                        if (prev == null || r.filed >= prev.filed) byEnd[r.end] = r
                    }
                    if (byEnd.isEmpty()) continue
                    val candidate = Series(byEnd.keys.max(), priority, unit, byEnd.mapValues { it.value.value })
                    val b = best
                    if (b == null || candidate.lastEnd > b.lastEnd || (candidate.lastEnd == b.lastEnd && candidate.priority < b.priority)) best = candidate
                }
            }
            return best
        }

        private fun build(symbol: String, name: String, raws: List<Raw>, now: Long): Filings? {
            val s = CONCEPTS.keys.associateWith { series(it, raws) }
            val spine = s["revenue"] ?: s["netIncome"] ?: return null
            val ends = spine.byEnd.keys.sorted().takeLast(MAX_YEARS)
            fun at(key: String, end: String): Double? {
                val m = s[key]?.byEnd ?: return null
                m[end]?.let { return it }
                // 52/53-week years end on slightly different days across concepts.
                val d = LocalDate.parse(end)
                return m.entries.firstOrNull { abs(ChronoUnit.DAYS.between(LocalDate.parse(it.key), d)) <= 7 }?.value
            }
            val years = ends.map { e ->
                val revenue = at("revenue", e)
                val gross = at("grossProfit", e) ?: at("costOfRevenue", e)?.let { c -> revenue?.let { it - c } }
                FiscalYear(
                    end = e, revenue = revenue, netIncome = at("netIncome", e), grossProfit = gross,
                    operatingIncome = at("operatingIncome", e), equity = at("equity", e), debt = at("debt", e),
                    operatingCashFlow = at("ocf", e), capex = at("capex", e), shares = at("shares", e),
                    interest = at("interest", e), cash = at("cash", e),
                )
            }
            val foreign = raws.any { it.form in FOREIGN_FORMS }
            return Filings(symbol, name, spine.unit, foreign, fund = false, years = years, fetchedAt = now)
        }

        const val MAX_YEARS = 6
    }
}
