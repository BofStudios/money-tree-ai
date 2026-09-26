package com.bofstudios.moneytree.engine

/**
 * Who pulls the trigger on a buy. Sells, stops and targets are automatic in
 * every mode — and on this app they sit at the broker, so they work even when
 * the phone does not.
 */
enum class Autonomy { FULL, SEMI, MANUAL }

/** How long a trade usually lasts, expressed as the candle size read. */
enum class Horizon(val timeframe: Timeframe) { SHORT(Timeframe.M15), MEDIUM(Timeframe.H1), LONG(Timeframe.D1) }

data class TradingSettings(
    val autonomy: Autonomy = Autonomy.FULL,
    val horizon: Horizon = Horizon.SHORT,
    val live: Boolean = false,
    /** Only ever true in memory; every start of the engine begins disarmed. */
    val armed: Boolean = false,
    val watchlist: List<String> = DEFAULT_WATCHLIST,
    val turkish: Boolean = false,
) {
    companion object {
        val DEFAULT_WATCHLIST = listOf("AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "SPY")
    }
}

enum class ProposalKind { APPROVAL, SUGGESTION }
enum class ProposalStatus { PENDING, APPROVED, SKIPPED, EXPIRED, FAILED }

data class Proposal(
    val id: String,
    val kind: ProposalKind,
    val entry: Entry,
    val createdAt: Long,
    val expiresAt: Long,
    val status: ProposalStatus = ProposalStatus.PENDING,
    val note: String = "",
)

/**
 * Buys waiting on the owner (semi) or ideas the bot will not act on (manual).
 * Thread-safe: the engine adds from its loop, the notification buttons and the
 * UI resolve from theirs.
 */
class ProposalBook(
    private val ttlMillis: Long = 15 * 60_000L,
    private val now: () -> Long = System::currentTimeMillis,
) {
    private val lock = Any()
    private var seq = 1
    private val pending = LinkedHashMap<String, Proposal>()
    private val history = ArrayList<Proposal>()

    /** Null when one is already live for the symbol — the same crossover is
     *  otherwise re-proposed on every scan until its bar closes. */
    fun add(kind: ProposalKind, entry: Entry): Proposal? = synchronized(lock) {
        if (pending.values.any { it.entry.symbol == entry.symbol }) return null
        val t = now()
        val p = Proposal(
            id = (if (kind == ProposalKind.APPROVAL) "ap-" else "sg-") + seq++,
            kind = kind, entry = entry, createdAt = t, expiresAt = t + ttlMillis,
        )
        pending[p.id] = p
        p
    }

    /** Removes a live approval so exactly one caller can act on it. */
    fun take(id: String): Proposal? = synchronized(lock) {
        val p = pending[id] ?: return null
        if (p.kind != ProposalKind.APPROVAL) return null
        pending.remove(id)
        if (now() >= p.expiresAt) {
            retire(p, ProposalStatus.EXPIRED, "")
            return null
        }
        p
    }

    fun finish(p: Proposal, status: ProposalStatus, note: String = "") = synchronized(lock) {
        pending.remove(p.id)
        retire(p, status, note)
    }

    fun skip(id: String): Proposal? = synchronized(lock) {
        val p = pending.remove(id) ?: return null
        retire(p, ProposalStatus.SKIPPED, "")
        p
    }

    fun expire(): List<Proposal> = synchronized(lock) {
        val t = now()
        val stale = pending.values.filter { t >= it.expiresAt }
        stale.forEach { pending.remove(it.id); retire(it, ProposalStatus.EXPIRED, "") }
        stale
    }

    fun clear(note: String) = synchronized(lock) {
        pending.values.toList().forEach { retire(it, ProposalStatus.SKIPPED, note) }
        pending.clear()
    }

    fun hasPendingFor(symbol: String): Boolean = synchronized(lock) {
        pending.values.any { it.entry.symbol == symbol }
    }

    fun pending(kind: ProposalKind? = null): List<Proposal> = synchronized(lock) {
        pending.values.filter { kind == null || it.kind == kind }.sortedByDescending { it.createdAt }
    }

    fun recent(limit: Int = 10): List<Proposal> = synchronized(lock) {
        history.takeLast(limit).reversed()
    }

    private fun retire(p: Proposal, status: ProposalStatus, note: String) {
        history.add(p.copy(status = status, note = note.ifEmpty { p.note }))
        while (history.size > 40) history.removeAt(0)
    }
}
