package com.bofstudios.moneytree.broker

import com.bofstudios.moneytree.engine.Account
import com.bofstudios.moneytree.engine.Bar
import com.bofstudios.moneytree.engine.Broker
import com.bofstudios.moneytree.engine.BrokerError
import com.bofstudios.moneytree.engine.BrokerOrder
import com.bofstudios.moneytree.engine.BrokerPosition
import com.bofstudios.moneytree.engine.Entry
import com.bofstudios.moneytree.engine.Headline
import com.bofstudios.moneytree.engine.MarketClock
import com.bofstudios.moneytree.engine.Timeframe
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant
import java.time.OffsetDateTime
import java.time.format.DateTimeFormatter
import java.time.temporal.ChronoUnit
import java.util.Locale
import java.util.concurrent.TimeUnit

/**
 * Alpaca's REST API, translated and nothing else — no decisions live here.
 *
 * Three things verified against the real API before this was written:
 *  - money fields arrive as strings ("equity": "100000"), so every number is
 *    parsed from either form;
 *  - on the multi-symbol bars endpoint `limit` counts across all symbols, so a
 *    limit of 300 can return 300 bars of the first symbol and none of the rest.
 *    Bars are therefore requested one symbol at a time;
 *  - without an explicit `start` the bars endpoint defaults to today, which is
 *    empty on a weekend. A start date is always sent.
 *
 * The free data plan serves the IEX feed, which is sent explicitly.
 */
class AlpacaBroker(
    private val keyId: String,
    private val secret: String,
    val live: Boolean,
    private val http: OkHttpClient = defaultClient(),
    private val tradingBase: String = if (live) LIVE else PAPER,
    private val dataBase: String = DATA,
) : Broker {

    override suspend fun clock(): MarketClock {
        val j = getObject(url(tradingBase, "/v2/clock"))
        return MarketClock(
            isOpen = j.optBoolean("is_open"),
            nextOpen = parseTime(j.optString("next_open")),
            nextClose = parseTime(j.optString("next_close")),
        )
    }

    override suspend fun account(): Account {
        val j = getObject(url(tradingBase, "/v2/account"))
        return Account(
            equity = j.num("equity"),
            lastEquity = j.num("last_equity"),
            cash = j.num("cash"),
            buyingPower = j.num("buying_power"),
            currency = j.optString("currency", "USD"),
            blocked = j.optBoolean("trading_blocked") || j.optBoolean("account_blocked") ||
                j.optString("status") != "ACTIVE",
        )
    }

    override suspend fun positions(): List<BrokerPosition> {
        val arr = getArray(url(tradingBase, "/v2/positions"))
        return (0 until arr.length()).map { i ->
            val p = arr.getJSONObject(i)
            BrokerPosition(
                symbol = p.optString("symbol"),
                qty = p.num("qty"),
                avgEntry = p.num("avg_entry_price"),
                currentPrice = p.num("current_price"),
                unrealizedPl = p.num("unrealized_pl"),
                marketValue = p.num("market_value"),
            )
        }
    }

    override suspend fun openOrders(): List<BrokerOrder> {
        val arr = getArray(
            url(tradingBase, "/v2/orders") { addQueryParameter("status", "open")
                addQueryParameter("nested", "true"); addQueryParameter("limit", "500") }
        )
        return (0 until arr.length()).map { parseOrder(arr.getJSONObject(it)) }
    }

    override suspend fun bars(symbol: String, timeframe: Timeframe, limit: Int): List<Bar> {
        val start = Instant.now().minus(timeframe.lookbackDays, ChronoUnit.DAYS)
            .truncatedTo(ChronoUnit.SECONDS)
        val j = getObject(
            url(dataBase, "/v2/stocks/${symbol.uppercase()}/bars") {
                addQueryParameter("timeframe", timeframe.alpaca)
                addQueryParameter("limit", limit.toString())
                addQueryParameter("start", DateTimeFormatter.ISO_INSTANT.format(start))
                addQueryParameter("feed", "iex")
                addQueryParameter("adjustment", "raw")
                // Newest first, so `limit` keeps the recent end; reversed below.
                addQueryParameter("sort", "desc")
            }
        )
        val arr = j.optJSONArray("bars") ?: return emptyList()
        return (0 until arr.length()).map { i ->
            val b = arr.getJSONObject(i)
            Bar(
                time = parseTime(b.optString("t")),
                open = b.num("o"), high = b.num("h"), low = b.num("l"),
                close = b.num("c"), volume = b.num("v"),
            )
        }.reversed()
    }

    override suspend fun latestPrice(symbol: String): Double? {
        val j = getObject(
            url(dataBase, "/v2/stocks/${symbol.uppercase()}/trades/latest") {
                addQueryParameter("feed", "iex")
            }
        )
        val price = j.optJSONObject("trade")?.num("p") ?: return null
        return price.takeIf { it > 0 && !it.isNaN() }
    }

    override suspend fun news(symbol: String, limit: Int): List<Headline> {
        val j = getObject(
            url(dataBase, "/v1beta1/news") {
                addQueryParameter("symbols", symbol.uppercase())
                addQueryParameter("limit", limit.toString())
            }
        )
        val arr = j.optJSONArray("news") ?: return emptyList()
        return (0 until arr.length()).map { i ->
            val n = arr.getJSONObject(i)
            Headline(n.optString("headline"), n.optString("source"), n.optString("created_at"))
        }
    }

    override suspend fun recentOrders(symbol: String, limit: Int): List<BrokerOrder> {
        val arr = getArray(
            url(tradingBase, "/v2/orders") {
                addQueryParameter("status", "closed")
                addQueryParameter("symbols", symbol.uppercase())
                addQueryParameter("limit", limit.toString())
                addQueryParameter("nested", "true")
                addQueryParameter("direction", "desc")
            }
        )
        return (0 until arr.length()).map { parseOrder(arr.getJSONObject(it)) }
    }

    override suspend fun buyBracket(entry: Entry, clientId: String): BrokerOrder {
        val body = bracketJson(entry, clientId)
        return parseOrder(send("POST", url(tradingBase, "/v2/orders"), body) as JSONObject)
    }

    override suspend fun cancelOrder(orderId: String) {
        send("DELETE", url(tradingBase, "/v2/orders/$orderId"), null)
    }

    override suspend fun closePosition(symbol: String) {
        send("DELETE", url(tradingBase, "/v2/positions/${symbol.uppercase()}"), null)
    }

    override suspend fun moveStop(orderId: String, stopPrice: Double) {
        val body = JSONObject().put("stop_price", price(stopPrice))
        send("PATCH", url(tradingBase, "/v2/orders/$orderId"), body)
    }

    // ------------------------------------------------------------------ http

    private fun url(base: String, path: String, build: HttpUrl.Builder.() -> Unit = {}): HttpUrl =
        (base + path).toHttpUrl().newBuilder().apply(build).build()

    private suspend fun getObject(url: HttpUrl): JSONObject = send("GET", url, null) as JSONObject
    private suspend fun getArray(url: HttpUrl): JSONArray = send("GET", url, null) as JSONArray

    private suspend fun send(method: String, url: HttpUrl, body: JSONObject?): Any =
        withContext(Dispatchers.IO) {
            val request = Request.Builder()
                .url(url)
                .header("APCA-API-KEY-ID", keyId)
                .header("APCA-API-SECRET-KEY", secret)
                .method(method, body?.toString()?.toRequestBody(JSON))
                .build()
            http.newCall(request).execute().use { response ->
                val text = response.body?.string().orEmpty()
                if (!response.isSuccessful) {
                    // Alpaca explains itself in {"message": ...}; pass that on as-is.
                    val message = runCatching { JSONObject(text).optString("message") }
                        .getOrNull().takeUnless { it.isNullOrBlank() }
                    throw BrokerError(message ?: "HTTP ${response.code}", response.code)
                }
                val trimmed = text.trim()
                when {
                    trimmed.startsWith("[") -> JSONArray(trimmed)
                    trimmed.startsWith("{") -> JSONObject(trimmed)
                    else -> JSONObject()
                }
            }
        }

    companion object {
        const val PAPER = "https://paper-api.alpaca.markets"
        const val LIVE = "https://api.alpaca.markets"
        const val DATA = "https://data.alpaca.markets"
        private val JSON = "application/json".toMediaType()

        fun defaultClient(): OkHttpClient = OkHttpClient.Builder()
            .connectTimeout(15, TimeUnit.SECONDS)
            .readTimeout(30, TimeUnit.SECONDS)
            .build()

        /**
         * The order Alpaca receives for a buy. GTC, not DAY: a DAY bracket's
         * stop-loss expires at the close and leaves the position unprotected
         * overnight.
         */
        fun bracketJson(entry: Entry, clientId: String): JSONObject = JSONObject()
            .put("symbol", entry.symbol.uppercase())
            .put("qty", entry.qty.toString())
            .put("side", "buy")
            .put("type", "market")
            .put("time_in_force", "gtc")
            .put("order_class", "bracket")
            .put("client_order_id", clientId)
            .put("take_profit", JSONObject().put("limit_price", price(entry.target)))
            .put("stop_loss", JSONObject().put("stop_price", price(entry.stop)))

        /** Always a dot, never a locale comma — this goes to an API. Stocks at or
         *  above $1 take two decimals; below $1, four. */
        fun price(value: Double): String =
            if (value >= 1.0) String.format(Locale.US, "%.2f", value)
            else String.format(Locale.US, "%.4f", value)

        fun parseTime(text: String): Long =
            if (text.isBlank()) 0L
            else runCatching { OffsetDateTime.parse(text).toInstant().toEpochMilli() }
                .getOrElse { runCatching { Instant.parse(text).toEpochMilli() }.getOrDefault(0L) }

        fun parseOrder(o: JSONObject): BrokerOrder {
            val legs = o.optJSONArray("legs")
            return BrokerOrder(
                id = o.optString("id"),
                clientId = o.optString("client_order_id"),
                symbol = o.optString("symbol"),
                side = o.optString("side"),
                type = o.optString("type"),
                status = o.optString("status"),
                qty = o.num("qty"),
                stopPrice = o.num("stop_price").takeUnless { it.isNaN() },
                limitPrice = o.num("limit_price").takeUnless { it.isNaN() },
                legs = if (legs == null) emptyList()
                else (0 until legs.length()).map { parseOrder(legs.getJSONObject(it)) },
                filledAvgPrice = o.num("filled_avg_price").takeUnless { it.isNaN() },
                filledQty = o.num("filled_qty").takeUnless { it.isNaN() } ?: 0.0,
                filledAt = parseTime(o.optString("filled_at").takeUnless { it == "null" } ?: ""),
            )
        }
    }
}

/** Alpaca sends numbers as strings, numbers, or null depending on the field. */
internal fun JSONObject.num(key: String): Double {
    if (!has(key) || isNull(key)) return Double.NaN
    return when (val v = get(key)) {
        is Number -> v.toDouble()
        is String -> v.toDoubleOrNull() ?: Double.NaN
        else -> Double.NaN
    }
}
