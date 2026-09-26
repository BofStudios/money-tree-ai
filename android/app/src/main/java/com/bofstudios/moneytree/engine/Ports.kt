package com.bofstudios.moneytree.engine

/** A finished round trip, as it actually filled at the broker. */
data class TradeRecord(
    val symbol: String,
    val qty: Double,
    val entry: Double,
    val exit: Double,
    /** "stop-loss", "take-profit", "signal" or "closed". */
    val reason: String,
    val closedAt: Long,
) {
    val pnl: Double get() = (exit - entry) * qty
}

/**
 * What the engine needs to remember across restarts.
 *
 * Ownership matters most: the bot only ever sells, trails or reports on
 * positions it opened itself. Anything the owner bought by hand in the Alpaca
 * app is left completely alone.
 */
interface EngineStore {
    fun ownedSymbols(): Set<String>
    fun addOwned(symbol: String)
    fun removeOwned(symbol: String)
    /** Equity when the bot first saw the account — "made you / lost you" starts here. */
    fun baselineEquity(live: Boolean): Double?
    fun setBaselineEquity(live: Boolean, equity: Double)
    fun trades(): List<TradeRecord>
    fun addTrade(trade: TradeRecord)
}

/** Things worth putting on the lock screen. */
interface Notifier {
    fun approvalNeeded(p: Proposal)
    fun orderPlaced(e: Entry)
    fun positionClosed(t: TradeRecord)
    fun halted(message: String)
}

/** Optional plain-language explanation of a decision, from a language model. */
fun interface Explainer {
    suspend fun explain(facts: String, turkish: Boolean): String?
}

class MemoryStore : EngineStore {
    private val owned = LinkedHashSet<String>()
    private val baseline = HashMap<Boolean, Double>()
    private val trades = ArrayList<TradeRecord>()
    override fun ownedSymbols() = synchronized(this) { owned.toSet() }
    override fun addOwned(symbol: String) { synchronized(this) { owned.add(symbol) } }
    override fun removeOwned(symbol: String) { synchronized(this) { owned.remove(symbol) } }
    override fun baselineEquity(live: Boolean) = synchronized(this) { baseline[live] }
    override fun setBaselineEquity(live: Boolean, equity: Double) { synchronized(this) { baseline[live] = equity } }
    override fun trades() = synchronized(this) { trades.toList() }
    override fun addTrade(trade: TradeRecord) { synchronized(this) { trades.add(trade) } }
}

object SilentNotifier : Notifier {
    override fun approvalNeeded(p: Proposal) {}
    override fun orderPlaced(e: Entry) {}
    override fun positionClosed(t: TradeRecord) {}
    override fun halted(message: String) {}
}
