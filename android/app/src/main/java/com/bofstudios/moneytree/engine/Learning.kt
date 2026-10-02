package com.bofstudios.moneytree.engine

import java.time.Instant
import java.time.ZoneId

/**
 * What the bot knew at the moment a buy signal fired. Each field becomes a
 * bucket ("RSI 60+", "bad news", "first hour") whose results are counted, so
 * the bot can learn which kinds of signal actually pay.
 */
data class Features(
    val symbol: String,
    val quality: Decision,
    /** Time-weighted news mood, null when there was no news. */
    val news: Double?,
    val rsi: Double,
    /** How far the price sits above the slow EMA, in ATRs. */
    val stretch: Double,
    /** Minutes since the 9:30 New York open; null on daily charts. */
    val minuteOfSession: Int?,
    /** The daily chart's direction: above its 50-day average. Null if unknown. */
    val dailyUp: Boolean?,
)

enum class FeatureKey { QUALITY, NEWS, RSI, STRETCH, SESSION, DAILY_TREND, SYMBOL }

/** One feature's bucket: (QUALITY, "WAIT"), (RSI, "60+")… */
data class Bucket(val key: FeatureKey, val value: String)

fun Features.buckets(): List<Bucket> = listOf(
    Bucket(FeatureKey.QUALITY, quality.name),
    Bucket(FeatureKey.NEWS, when {
        news == null -> "NONE"
        news <= -NewsRadar.GOOD_MOOD -> "BAD"
        news >= NewsRadar.GOOD_MOOD -> "GOOD"
        else -> "MIXED"
    }),
    Bucket(FeatureKey.RSI, when { rsi.isNaN() -> "?"; rsi < 45 -> "<45"; rsi < 60 -> "45-60"; else -> "60+" }),
    Bucket(FeatureKey.STRETCH, when { stretch.isNaN() -> "?"; stretch < 1.0 -> "NEAR"; stretch < 2.5 -> "EXTENDED"; else -> "FAR" }),
    Bucket(FeatureKey.SESSION, when {
        minuteOfSession == null -> "DAILY"
        minuteOfSession < 60 -> "OPEN"
        minuteOfSession >= 330 -> "CLOSE"
        else -> "MIDDAY"
    }),
    Bucket(FeatureKey.DAILY_TREND, when (dailyUp) { true -> "UP"; false -> "DOWN"; null -> "?" }),
    Bucket(FeatureKey.SYMBOL, symbol),
).filter { it.value != "?" }

/**
 * A buy signal followed "in the head": the bot notes the price, stop and
 * target it would have used — whether it actually bought or not — and later
 * reads the candles to see which came first. This is how it learns from
 * dozens of signals a week instead of the handful a $60 account can afford.
 *
 * Simplification, stated plainly: the trailing stop is not replayed, so a
 * shadow trade exits only at its stop, its target, the sell signal, or after
 * [ShadowBook.MAX_BARS] candles.
 */
data class ShadowTrade(
    val id: String,
    val symbol: String,
    /** Time of the candle the signal fired on. */
    val openedAt: Long,
    val entry: Double,
    val stop: Double,
    val target: Double,
    val features: Features,
    val bought: Boolean = false,
    val closedAt: Long? = null,
    /** Result in R: −1 is a full stop-out, +2 the target at 2:1. */
    val r: Double? = null,
    val exit: String? = null,
) {
    val open: Boolean get() = closedAt == null
    fun rAt(price: Double): Double = if (entry > stop) (price - entry) / (entry - stop) else 0.0
}

/** A finished result the learner counts. Real trades weigh double. */
data class Sample(val features: Features, val r: Double, val real: Boolean, val at: Long)

/** The plan behind a real buy, kept until it closes so its result can be counted in R. */
data class EntryPlan(val symbol: String, val entry: Double, val stop: Double, val features: Features, val at: Long)

class ShadowBook(private val strategy: EmaRsiStrategy) {
    private val lock = Any()
    private val trades = ArrayList<ShadowTrade>()

    fun restore(saved: List<ShadowTrade>) = synchronized(lock) { trades.clear(); trades.addAll(saved.takeLast(CAP)) }
    fun all(): List<ShadowTrade> = synchronized(lock) { trades.toList() }
    fun openTrades(): List<ShadowTrade> = synchronized(lock) { trades.filter { it.open } }

    /** Starts following a signal, once per candle and one open per symbol. */
    fun open(t: ShadowTrade): Boolean = synchronized(lock) {
        if (trades.any { it.symbol == t.symbol && (it.open || it.openedAt == t.openedAt) }) return false
        trades += t
        while (trades.size > CAP) trades.removeAt(trades.indexOfFirst { !it.open }.takeIf { it >= 0 } ?: 0)
        true
    }

    fun markBought(symbol: String) = synchronized(lock) {
        val i = trades.indexOfLast { it.symbol == symbol && it.open }
        if (i >= 0) trades[i] = trades[i].copy(bought = true)
    }

    /**
     * Walks each open shadow trade forward through the candles that came
     * after it, and closes it at whichever of stop, target or sell signal
     * came first. A candle that touched both the stop and the target counts
     * as the stop: when in doubt, assume the worse.
     */
    fun resolve(bars: Map<String, List<Bar>>, rewardRisk: Double): List<ShadowTrade> = synchronized(lock) {
        val closed = ArrayList<ShadowTrade>()
        for ((i, t) in trades.withIndex()) {
            if (!t.open) continue
            val b = bars[t.symbol] ?: continue
            val start = b.indexOfFirst { it.time > t.openedAt }
            if (start < 0) continue
            var done: ShadowTrade? = null
            for (j in start until b.size) {
                val bar = b[j]
                done = when {
                    bar.low <= t.stop -> t.copy(closedAt = bar.time, r = -1.0, exit = "stop-loss")
                    bar.high >= t.target -> t.copy(closedAt = bar.time, r = rewardRisk, exit = "take-profit")
                    strategy.onBars(b.subList(0, j + 1), holding = true).action == Action.CLOSE ->
                        t.copy(closedAt = bar.time, r = t.rAt(bar.close), exit = "signal")
                    j - start + 1 >= MAX_BARS -> t.copy(closedAt = bar.time, r = t.rAt(bar.close), exit = "time")
                    else -> null
                }
                if (done != null) break
            }
            if (done != null) { trades[i] = done; closed += done }
        }
        closed
    }

    fun clear() = synchronized(lock) { trades.clear() }

    companion object {
        const val CAP = 400
        const val MAX_BARS = 40
    }
}

/** How one bucket has done. */
data class BucketStats(val bucket: Bucket, val n: Double, val wins: Double, val sumR: Double) {
    /** The average result pulled toward zero until there is enough evidence. */
    val shrunk: Double get() = sumR / (n + Learner.PRIOR)
    val winRate: Double get() = if (n > 0) wins / n else 0.0
    val avgR: Double get() = if (n > 0) sumR / n else 0.0
}

data class LearnedVerdict(
    val blocked: Boolean,
    /** Average of the trusted buckets' shrunk results, in R. */
    val edge: Double?,
    /** The buckets that spoke, worst first. */
    val evidence: List<BucketStats>,
    /** A size multiplier from 0.5 to 1: learning can shrink a trade, never grow it. */
    val size: Double,
)

/**
 * Learning, kept honest:
 *  - every result is counted per bucket, and each bucket's average is
 *    shrunk toward zero ([PRIOR] phantom break-even trades), so three lucky
 *    losses do not become a "rule";
 *  - a bucket only blocks once it has [MIN_EVIDENCE] results and a shrunk
 *    average of [BLOCK_AT] R or worse;
 *  - it can only ever block a buy or make it smaller — never add one, never
 *    make one bigger than the owner's risk setting.
 */
class Learner {
    private val lock = Any()
    private val samples = ArrayList<Sample>()

    fun restore(saved: List<Sample>) = synchronized(lock) { samples.clear(); samples.addAll(saved.takeLast(CAP)) }
    fun all(): List<Sample> = synchronized(lock) { samples.toList() }

    /** Adds a result; returns the rules that just became active because of it. */
    fun add(s: Sample): List<BucketStats> = synchronized(lock) {
        val before = rules().map { it.bucket }.toSet()
        samples += s
        while (samples.size > CAP) samples.removeAt(0)
        rules().filter { it.bucket !in before }
    }

    fun clear() = synchronized(lock) { samples.clear() }

    fun stats(): List<BucketStats> = synchronized(lock) {
        val map = LinkedHashMap<Bucket, DoubleArray>()
        for (s in samples) {
            val w = if (s.real) 2.0 else 1.0
            for (b in s.features.buckets()) {
                val a = map.getOrPut(b) { DoubleArray(3) }
                a[0] += w
                if (s.r > 0) a[1] += w
                a[2] += s.r * w
            }
        }
        map.map { (b, a) -> BucketStats(b, a[0], a[1], a[2]) }
    }

    /** The buckets that currently block buys. */
    fun rules(): List<BucketStats> = stats().filter { it.n >= MIN_EVIDENCE && it.shrunk <= BLOCK_AT }.sortedBy { it.shrunk }

    fun verdict(f: Features): LearnedVerdict {
        val all = stats().associateBy { it.bucket }
        val mine = f.buckets().mapNotNull { all[it] }.filter { it.n >= 3 }
        if (mine.isEmpty()) return LearnedVerdict(false, null, emptyList(), 1.0)
        val edge = mine.map { it.shrunk }.average()
        val blockers = mine.filter { it.n >= MIN_EVIDENCE && it.shrunk <= BLOCK_AT }
        val blocked = blockers.isNotEmpty() && edge < 0
        val size = when {
            edge <= -0.15 -> 0.5
            edge < 0 -> 0.75
            else -> 1.0
        }
        return LearnedVerdict(blocked, edge, mine.sortedBy { it.shrunk }, size)
    }

    /** Buckets with enough results to say something, strongest finding first. */
    fun lessons(): List<BucketStats> =
        stats().filter { it.n >= 5 && it.bucket.key != FeatureKey.SYMBOL || it.n >= 8 }
            .sortedByDescending { kotlin.math.abs(it.shrunk) * kotlin.math.sqrt(it.n) }

    companion object {
        const val PRIOR = 6.0
        const val MIN_EVIDENCE = 10.0
        const val BLOCK_AT = -0.25
        const val CAP = 800
    }
}

/** Minutes since the 9:30 New York open for a candle time; null outside the session. */
fun minuteOfSession(epoch: Long): Int? {
    val t = Instant.ofEpochMilli(epoch).atZone(ZoneId.of("America/New_York"))
    val m = t.hour * 60 + t.minute - (9 * 60 + 30)
    return m.takeIf { it in 0 until 390 }
}
