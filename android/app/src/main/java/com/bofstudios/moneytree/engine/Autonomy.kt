package com.bofstudios.moneytree.engine

/**
 * Who pulls the trigger on a buy. Sells, stops and targets are automatic in
 * every mode — and on this app they sit at the broker, so they work even when
 * the phone does not.
 */
enum class Autonomy { FULL, SEMI, MANUAL }

/**
 * Which companies to watch. Alpaca trades on US exchanges only, so "Europe"
 * means European companies that are also listed in New York (ASML, SAP, Novo
 * Nordisk...) plus a Europe ETF — traded in dollars, during US market hours.
 */
enum class Market(val watchlist: List<String>) {
    US(listOf("AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "SPY")),
    EUROPE(listOf("ASML", "SAP", "NVO", "AZN", "SHEL", "TTE", "UL", "VGK")),
    BOTH(listOf("AAPL", "MSFT", "NVDA", "AMZN", "ASML", "SAP", "NVO", "SPY")),
}

/** How long a trade usually lasts, expressed as the candle size read. */
enum class Horizon(val timeframe: Timeframe) { SHORT(Timeframe.M15), MEDIUM(Timeframe.H1), LONG(Timeframe.D1) }

/**
 * How hard each trade leans. The stop is set the same way at every level; what
 * changes is how much of the account one stop-out may cost, and the ceiling on
 * one position.
 */
enum class RiskLevel(val riskPerTradePct: Double, val maxPositionPct: Double) {
    CAREFUL(0.5, 20.0),
    NORMAL(1.0, 33.0),
    BOLD(2.0, 50.0),
}

/** Which moments reach the lock screen. Approvals and halts always do. */
enum class NotifyLevel { EVERYTHING, TRADES, QUIET }

data class TradingSettings(
    val autonomy: Autonomy = Autonomy.FULL,
    val horizon: Horizon = Horizon.SHORT,
    val live: Boolean = false,
    /** Only ever true in memory; every start of the engine begins disarmed. */
    val armed: Boolean = false,
    val watchlist: List<String> = DEFAULT_WATCHLIST,
    val turkish: Boolean = false,
    /**
     * Small-account mode. Buys fractions of a share so $10 can trade, at a cost:
     * Alpaca takes no bracket order on fractions, so the stop and target are
     * watched by this phone instead of held at the broker. Off by default.
     */
    val fractional: Boolean = false,
    /** Null until the owner has been asked; the watchlist is what actually trades. */
    val market: Market? = null,
    val riskLevel: RiskLevel = RiskLevel.CAREFUL,
    /** At most this many positions open at once. */
    val maxPositions: Int = 3,
    /** No new buys for the rest of the day once the account is down this much. */
    val dailyLossPct: Double = 5.0,
    /** The share of the account the bot may put to work; the rest it never touches. */
    val usePct: Int = 100,
    val notify: NotifyLevel = NotifyLevel.EVERYTHING,
    /**
     * Before a buy, a language model reads the latest headlines and may call it
     * off on a clear red flag (earnings due, a halt, fraud...). It can only ever
     * stop a buy, never start one. Needs a Groq key; without one it is skipped.
     */
    val aiCheck: Boolean = true,
) {
    fun riskConfig(): RiskConfig = RiskConfig(
        maxPositionPct = riskLevel.maxPositionPct,
        riskPerTradePct = riskLevel.riskPerTradePct,
        maxDailyLossPct = dailyLossPct,
        maxOpenPositions = maxPositions.coerceIn(1, 5),
    )

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
