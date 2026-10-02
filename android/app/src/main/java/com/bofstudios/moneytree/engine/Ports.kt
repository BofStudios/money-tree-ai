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
    val pnlPct: Double get() = if (entry > 0) (exit / entry - 1) * 100 else 0.0
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
    /** Stop and target for a position with no broker-held bracket (fractional). */
    fun guard(symbol: String): Pair<Double, Double>?
    fun setGuard(symbol: String, stop: Double, target: Double)
    fun clearGuard(symbol: String)
    /** Every order the bot sent, so the owner can always see what it did and when. */
    fun logOrder(o: OrderLog) {}
    fun orderLog(): List<OrderLog> = emptyList()
}

/** One order Money Tree sent: "buy" with its size and price, or "sell" (a whole position). */
data class OrderLog(val symbol: String, val side: String, val qty: Double, val price: Double, val at: Long, val why: String)

/**
 * Things worth putting on the lock screen. The phone decides which of them
 * actually buzz, from the owner's notification level.
 */
interface Notifier {
    fun approvalNeeded(p: Proposal)
    /** "Just bought ..." */
    fun orderPlaced(e: Entry)
    /** "Just sold ..., this much profit / loss" — also when a stop fills at Alpaca. */
    fun positionClosed(t: TradeRecord)
    fun halted(message: String)
    /** A buy signal is being looked into: news, and the AI's check. */
    fun researching(symbol: String, line: String) {}
    /** The AI's plain-words note on a buy it just made. */
    fun explained(symbol: String, text: String) {}
    fun stopRaised(symbol: String, from: Double?, to: Double, lockedIn: Double?) {}
    fun aiSkipped(symbol: String, why: String) {}
    /** Alpaca refused a buy, with its reason (not enough buying power, market closed...). */
    fun orderFailed(symbol: String, why: String) {}
    /** Once, when the market closes after a session the bot watched. */
    fun dailySummary(trades: List<TradeRecord>, today: Double, equity: Double) {}
    /** The research held a buy back: the five checks, the news, the trend or what it learned. */
    fun heldBack(symbol: String, why: String) {}
    /** A new rule learned from results, or the AI's lesson from a closed trade. */
    fun learned(title: String, text: String) {}
}

/** Optional plain-language explanation of a decision, from a language model. */
fun interface Explainer {
    suspend fun explain(facts: String, turkish: Boolean): String?
}

/** The AI's answer on whether the news gives a reason not to buy right now. */
data class Vet(val ok: Boolean, val note: String)

/**
 * Reads the latest headlines before a buy. It can only call a buy off — never
 * start one — so a wrong answer costs a missed trade, not money. Headlines are
 * outside text; implementations must treat them as data, not instructions.
 */
fun interface Researcher {
    suspend fun vet(symbol: String, facts: String, headlines: List<String>, turkish: Boolean): Vet?
}

/** Something the AI said, kept for the home screen. */
data class AiNote(val symbol: String, val text: String, val at: Long)

class MemoryStore : EngineStore {
    private val owned = LinkedHashSet<String>()
    private val baseline = HashMap<Boolean, Double>()
    private val trades = ArrayList<TradeRecord>()
    private val guards = HashMap<String, Pair<Double, Double>>()
    private val orders = ArrayList<OrderLog>()
    override fun logOrder(o: OrderLog) { synchronized(this) { orders.add(o) } }
    override fun orderLog() = synchronized(this) { orders.toList() }
    override fun ownedSymbols() = synchronized(this) { owned.toSet() }
    override fun addOwned(symbol: String) { synchronized(this) { owned.add(symbol) } }
    override fun removeOwned(symbol: String) { synchronized(this) { owned.remove(symbol) } }
    override fun baselineEquity(live: Boolean) = synchronized(this) { baseline[live] }
    override fun setBaselineEquity(live: Boolean, equity: Double) { synchronized(this) { baseline[live] = equity } }
    override fun trades() = synchronized(this) { trades.toList() }
    override fun addTrade(trade: TradeRecord) { synchronized(this) { trades.add(trade) } }
    override fun guard(symbol: String) = synchronized(this) { guards[symbol] }
    override fun setGuard(symbol: String, stop: Double, target: Double) { synchronized(this) { guards[symbol] = stop to target } }
    override fun clearGuard(symbol: String) { synchronized(this) { guards.remove(symbol) } }
}

object SilentNotifier : Notifier {
    override fun approvalNeeded(p: Proposal) {}
    override fun orderPlaced(e: Entry) {}
    override fun positionClosed(t: TradeRecord) {}
    override fun halted(message: String) {}
}
