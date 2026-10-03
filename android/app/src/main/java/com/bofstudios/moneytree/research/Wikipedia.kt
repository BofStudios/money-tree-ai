package com.bofstudios.moneytree.research

import com.bofstudios.moneytree.engine.AttentionSource
import com.bofstudios.moneytree.engine.BrainStore
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONArray
import org.json.JSONObject
import java.net.URLEncoder
import java.time.LocalDate
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import java.util.concurrent.TimeUnit

/**
 * Attention, as alternative data: how many people read a company's Wikipedia
 * article each day (Wikimedia's free pageview API). A spike usually means
 * something happened before most headlines catch up — or simply that a stock
 * is crowded. Either way it is a fact about the crowd, not about the business.
 */
class Wikipedia(
    private val store: BrainStore? = null,
    private val http: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS).readTimeout(20, TimeUnit.SECONDS).build(),
) : AttentionSource {

    override suspend fun views(symbol: String, name: String): List<Int>? = withContext(Dispatchers.IO) {
        val title = title(symbol.uppercase(), name) ?: return@withContext null
        val end = LocalDate.now(ZoneOffset.UTC).minusDays(1)
        val start = end.minusDays(34)
        val fmt = DateTimeFormatter.BASIC_ISO_DATE
        val url = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/" +
            URLEncoder.encode(title, "UTF-8").replace("+", "_") + "/daily/${fmt.format(start)}/${fmt.format(end)}"
        runCatching {
            http.newCall(get(url)).execute().use { r ->
                if (!r.isSuccessful) return@use null
                val items = JSONObject(r.body?.string().orEmpty()).optJSONArray("items") ?: return@use null
                (0 until items.length()).map { items.getJSONObject(it).optInt("views") }
            }
        }.getOrNull()
    }

    /** The article for a company: the built-in list, the cache, or Wikipedia's own search. */
    private fun title(symbol: String, name: String): String? {
        KNOWN[symbol]?.let { return it }
        store?.read("wiki_$symbol")?.takeIf { it.isNotBlank() }?.let { return it }
        val query = name.replace(Regex("(?i)\\b(inc|corp|corporation|co|ltd|plc|holding|holdings|nv|sa|se|ag|a/s|the)\\b\\.?"), " ")
            .replace(Regex("[^A-Za-z0-9 &-]"), " ").trim().replace(Regex("\\s+"), " ")
        if (query.isEmpty()) return null
        val url = "https://en.wikipedia.org/w/api.php".toHttpUrl().newBuilder()
            .addQueryParameter("action", "opensearch").addQueryParameter("search", query)
            .addQueryParameter("limit", "1").addQueryParameter("namespace", "0").addQueryParameter("format", "json")
            .build().toString()
        val found = runCatching {
            http.newCall(get(url)).execute().use { r ->
                if (!r.isSuccessful) return@use null
                JSONArray(r.body?.string().orEmpty()).optJSONArray(1)?.optString(0)?.takeIf { it.isNotBlank() }
            }
        }.getOrNull() ?: return null
        store?.write("wiki_$symbol", found)
        return found
    }

    private fun get(url: String) = Request.Builder().url(url).header("User-Agent", SecEdgar.USER_AGENT).build()

    companion object {
        val KNOWN = mapOf(
            "AAPL" to "Apple Inc.", "MSFT" to "Microsoft", "NVDA" to "Nvidia", "AMZN" to "Amazon (company)",
            "GOOGL" to "Alphabet Inc.", "GOOG" to "Alphabet Inc.", "META" to "Meta Platforms", "TSLA" to "Tesla, Inc.",
            "SPY" to "SPDR S&P 500 ETF Trust", "ASML" to "ASML Holding", "SAP" to "SAP", "NVO" to "Novo Nordisk",
            "AZN" to "AstraZeneca", "SHEL" to "Shell plc", "TTE" to "TotalEnergies", "UL" to "Unilever",
        )
    }
}
