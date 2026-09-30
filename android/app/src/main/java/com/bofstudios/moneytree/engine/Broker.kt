package com.bofstudios.moneytree.engine

/**
 * Everything the engine needs from a brokerage, and nothing more.
 *
 * The engine only ever talks to this interface, so the rules can be tested on
 * a laptop against a fake broker, and the real one (Alpaca) stays a thin
 * translation layer with no decisions in it.
 */
interface Broker {
    suspend fun clock(): MarketClock
    suspend fun account(): Account
    suspend fun positions(): List<BrokerPosition>
    /** Open orders, with bracket legs nested under their parent. */
    suspend fun openOrders(): List<BrokerOrder>
    /** Most recent `limit` bars, oldest first. */
    suspend fun bars(symbol: String, timeframe: Timeframe, limit: Int): List<Bar>
    suspend fun latestPrice(symbol: String): Double?
    suspend fun news(symbol: String, limit: Int): List<Headline>
    /** Recently closed orders for one symbol, newest first, legs nested. */
    suspend fun recentOrders(symbol: String, limit: Int): List<BrokerOrder>

    /** Market buy with a broker-held stop-loss and take-profit (GTC). */
    suspend fun buyBracket(entry: Entry, clientId: String): BrokerOrder
    /** Plain market buy of a fractional quantity (DAY). */
    suspend fun buyFractional(entry: Entry, clientId: String): BrokerOrder
    /**
     * A stop sell held at the broker. Alpaca takes these on fractional
     * quantities, but only as DAY orders, so one is placed each trading day.
     */
    suspend fun sellStop(symbol: String, qty: Double, stopPrice: Double, clientId: String): BrokerOrder
    suspend fun cancelOrder(orderId: String)
    /** Market sell of the whole position. Cancel its open orders first. */
    suspend fun closePosition(symbol: String)
    suspend fun moveStop(orderId: String, stopPrice: Double)
}

class BrokerError(message: String, val status: Int = 0) : Exception(message)

enum class Timeframe(val alpaca: String, val minutes: Long, val lookbackDays: Long) {
    M15("15Min", 15, 30),
    H1("1Hour", 60, 90),
    D1("1Day", 1440, 700),
}

data class MarketClock(
    val isOpen: Boolean,
    val nextOpen: Long,
    val nextClose: Long,
)

data class Account(
    val equity: Double,
    /** Equity at the previous market close — the base for today's P&L. */
    val lastEquity: Double,
    val cash: Double,
    val buyingPower: Double,
    val currency: String,
    val blocked: Boolean,
)

data class BrokerPosition(
    val symbol: String,
    val qty: Double,
    val avgEntry: Double,
    val currentPrice: Double,
    val unrealizedPl: Double,
    val marketValue: Double,
)

data class BrokerOrder(
    val id: String,
    val clientId: String,
    val symbol: String,
    val side: String,
    val type: String,
    val status: String,
    val qty: Double,
    val stopPrice: Double?,
    val limitPrice: Double?,
    val legs: List<BrokerOrder> = emptyList(),
    val filledAvgPrice: Double? = null,
    val filledQty: Double = 0.0,
    val filledAt: Long = 0L,
) {
    /** Every order in this tree, parent first. */
    fun flatten(): List<BrokerOrder> = listOf(this) + legs.flatMap { it.flatten() }
}

data class Headline(
    val headline: String,
    val source: String,
    val createdAt: String,
)
