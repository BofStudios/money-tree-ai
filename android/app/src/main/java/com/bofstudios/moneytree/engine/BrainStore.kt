package com.bofstudios.moneytree.engine

import org.json.JSONArray
import org.json.JSONObject

/**
 * Where the brain keeps what it read and learned between restarts: plain
 * named JSON documents. The phone stores them as files; tests keep them in
 * memory.
 */
interface BrainStore {
    fun read(name: String): String?
    fun write(name: String, text: String)
}

class MemoryBrainStore : BrainStore {
    private val docs = HashMap<String, String>()
    override fun read(name: String) = synchronized(this) { docs[name] }
    override fun write(name: String, text: String) { synchronized(this) { docs[name] = text } }
}

/** JSON for everything the brain persists. Unknown or broken documents read as empty. */
object BrainCodec {

    // -------------------------------------------------------------- filings
    fun filings(f: Filings): String = JSONObject()
        .put("symbol", f.symbol).put("name", f.name).put("currency", f.currency)
        .put("foreign", f.foreign).put("fund", f.fund).put("fetchedAt", f.fetchedAt)
        .put("aiRead", f.aiRead ?: JSONObject.NULL)
        .put("years", JSONArray().apply {
            f.years.forEach { y ->
                put(JSONObject().put("end", y.end)
                    .putN("revenue", y.revenue).putN("netIncome", y.netIncome).putN("grossProfit", y.grossProfit)
                    .putN("operatingIncome", y.operatingIncome).putN("equity", y.equity).putN("debt", y.debt)
                    .putN("ocf", y.operatingCashFlow).putN("capex", y.capex).putN("shares", y.shares)
                    .putN("interest", y.interest).putN("cash", y.cash))
            }
        }).toString()

    fun filings(text: String?): Filings? = text?.let {
        runCatching {
            val o = JSONObject(it)
            val ys = o.getJSONArray("years")
            Filings(
                symbol = o.getString("symbol"), name = o.optString("name"), currency = o.optString("currency", "USD"),
                foreign = o.optBoolean("foreign"), fund = o.optBoolean("fund"), fetchedAt = o.optLong("fetchedAt"),
                aiRead = o.optStringOrNull("aiRead"),
                years = (0 until ys.length()).map { i ->
                    val y = ys.getJSONObject(i)
                    FiscalYear(
                        end = y.getString("end"), revenue = y.n("revenue"), netIncome = y.n("netIncome"),
                        grossProfit = y.n("grossProfit"), operatingIncome = y.n("operatingIncome"), equity = y.n("equity"),
                        debt = y.n("debt"), operatingCashFlow = y.n("ocf"), capex = y.n("capex"), shares = y.n("shares"),
                        interest = y.n("interest"), cash = y.n("cash"),
                    )
                },
            )
        }.getOrNull()
    }

    // ----------------------------------------------------------------- news
    fun news(items: List<NewsItem>): String = JSONArray().apply {
        items.forEach { n ->
            put(JSONObject().put("id", n.id).put("h", n.headline).put("s", n.summary.take(400)).put("src", n.source)
                .put("sym", JSONArray(n.symbols)).put("t", n.createdAt).put("url", n.url)
                .putN("ai", n.aiScore))
        }
    }.toString()

    fun news(text: String?): List<NewsItem> = list(text) { o ->
        NewsItem(
            id = o.getLong("id"), headline = o.getString("h"), summary = o.optString("s"), source = o.optString("src"),
            symbols = o.getJSONArray("sym").let { a -> (0 until a.length()).map { a.getString(it) } },
            createdAt = o.getLong("t"), url = o.optString("url"), aiScore = o.n("ai"),
        )
    }

    // ------------------------------------------------------------- learning
    private fun features(f: Features): JSONObject = JSONObject()
        .put("sym", f.symbol).put("q", f.quality.name).putN("news", f.news).putN("rsi", f.rsi.takeUnless { it.isNaN() })
        .putN("stretch", f.stretch.takeUnless { it.isNaN() }).put("min", f.minuteOfSession ?: JSONObject.NULL)
        .put("daily", f.dailyUp ?: JSONObject.NULL)

    private fun features(o: JSONObject): Features = Features(
        symbol = o.getString("sym"),
        quality = runCatching { Decision.valueOf(o.getString("q")) }.getOrDefault(Decision.UNKNOWN),
        news = o.n("news"), rsi = o.n("rsi") ?: Double.NaN, stretch = o.n("stretch") ?: Double.NaN,
        minuteOfSession = if (o.isNull("min") || !o.has("min")) null else o.getInt("min"),
        dailyUp = if (o.isNull("daily") || !o.has("daily")) null else o.getBoolean("daily"),
    )

    fun shadows(list: List<ShadowTrade>): String = JSONArray().apply {
        list.forEach { t ->
            put(JSONObject().put("id", t.id).put("sym", t.symbol).put("at", t.openedAt).put("e", t.entry).put("st", t.stop)
                .put("tg", t.target).put("f", features(t.features)).put("b", t.bought)
                .put("c", t.closedAt ?: JSONObject.NULL).putN("r", t.r).put("x", t.exit ?: JSONObject.NULL))
        }
    }.toString()

    fun shadows(text: String?): List<ShadowTrade> = list(text) { o ->
        ShadowTrade(
            id = o.getString("id"), symbol = o.getString("sym"), openedAt = o.getLong("at"), entry = o.getDouble("e"),
            stop = o.getDouble("st"), target = o.getDouble("tg"), features = features(o.getJSONObject("f")),
            bought = o.optBoolean("b"), closedAt = if (o.isNull("c")) null else o.getLong("c"), r = o.n("r"),
            exit = o.optStringOrNull("x"),
        )
    }

    fun samples(list: List<Sample>): String = JSONArray().apply {
        list.forEach { s -> put(JSONObject().put("f", features(s.features)).put("r", s.r).put("real", s.real).put("at", s.at)) }
    }.toString()

    fun samples(text: String?): List<Sample> = list(text) { o ->
        Sample(features(o.getJSONObject("f")), o.getDouble("r"), o.optBoolean("real"), o.optLong("at"))
    }

    fun plans(list: Collection<EntryPlan>): String = JSONArray().apply {
        list.forEach { p -> put(JSONObject().put("sym", p.symbol).put("e", p.entry).put("st", p.stop).put("f", features(p.features)).put("at", p.at)) }
    }.toString()

    fun plans(text: String?): List<EntryPlan> = list(text) { o ->
        EntryPlan(o.getString("sym"), o.getDouble("e"), o.getDouble("st"), features(o.getJSONObject("f")), o.optLong("at"))
    }

    fun notes(list: List<AiNote>): String = JSONArray().apply {
        list.forEach { n -> put(JSONObject().put("sym", n.symbol).put("t", n.text).put("at", n.at)) }
    }.toString()

    fun notes(text: String?): List<AiNote> = list(text) { o -> AiNote(o.getString("sym"), o.getString("t"), o.optLong("at")) }

    // -------------------------------------------------------------- helpers
    private fun <T> list(text: String?, read: (JSONObject) -> T): List<T> {
        if (text.isNullOrBlank()) return emptyList()
        val arr = runCatching { JSONArray(text) }.getOrNull() ?: return emptyList()
        return (0 until arr.length()).mapNotNull { i -> runCatching { read(arr.getJSONObject(i)) }.getOrNull() }
    }

    private fun JSONObject.putN(key: String, v: Double?): JSONObject =
        put(key, if (v == null || v.isNaN() || v.isInfinite()) JSONObject.NULL else v)

    private fun JSONObject.n(key: String): Double? =
        if (!has(key) || isNull(key)) null else optDouble(key).takeUnless { it.isNaN() }

    private fun JSONObject.optStringOrNull(key: String): String? =
        if (!has(key) || isNull(key)) null else optString(key).takeIf { it.isNotEmpty() }
}
