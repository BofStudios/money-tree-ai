package com.bofstudios.moneytree.engine

import org.json.JSONArray
import org.json.JSONObject
import java.util.Locale
import java.util.Random
import kotlin.math.sqrt

/**
 * The strategy's tunable settings — what self-improvement changes. The owner's
 * risk (how much one stop-out may cost) is not in here and never changes.
 */
data class Genome(
    val fast: Int = 12,
    val slow: Int = 26,
    /** No entry with RSI at or above this. */
    val entryRsi: Double = 70.0,
    /** Exit once RSI runs past this. */
    val exitRsi: Double = 70.0,
    /** Stop distance in ATRs (still clamped by the risk settings' min and max). */
    val atrMultiple: Double = 1.5,
    /** Target distance as a multiple of the stop distance. */
    val rewardRisk: Double = 2.0,
) {
    fun strategy() = EmaRsiStrategy(fast, slow, 14, entryRsi, exitRsi)
    fun tune(c: RiskConfig) = c.copy(atrMultiple = atrMultiple, rewardRisk = rewardRisk)

    /** Keeps every gene inside sane bounds, so evolution can never wander somewhere silly. */
    fun clamped(): Genome {
        val f = fast.coerceIn(5, 20)
        return Genome(
            fast = f,
            slow = slow.coerceIn(maxOf(20, f + 6), 60),
            entryRsi = entryRsi.coerceIn(50.0, 80.0),
            exitRsi = exitRsi.coerceIn(60.0, 90.0),
            atrMultiple = atrMultiple.coerceIn(0.8, 3.0),
            rewardRisk = rewardRisk.coerceIn(1.2, 4.0),
        )
    }

    val label: String get() = String.format(Locale.US, "EMA %d/%d · RSI<%.0f · exit>%.0f · stop %.1f ATR · %.1f:1",
        fast, slow, entryRsi, exitRsi, atrMultiple, rewardRisk)

    companion object {
        /** The strategy Money Tree shipped with — always the fallback. */
        val DEFAULT = Genome()
    }
}

/** One stock's history, prepared once so thousands of strategies can replay it fast. */
class Series(val symbol: String, bars: List<Bar>) {
    val size = bars.size
    val open = DoubleArray(size) { bars[it].open }
    val high = DoubleArray(size) { bars[it].high }
    val low = DoubleArray(size) { bars[it].low }
    val close = DoubleArray(size) { bars[it].close }
    val rsi: DoubleArray = Indicators.rsi(close, 14)
    val atr: DoubleArray = Indicators.atr(bars, 14)
    private val emas = HashMap<Int, DoubleArray>()
    fun ema(period: Int): DoubleArray = synchronized(emas) { emas.getOrPut(period) { Indicators.ema(close, period) } }
}

/** Results of replaying one strategy, in R (one R = what the stop risks). */
data class Score(val trades: Int = 0, val sumR: Double = 0.0, val wins: Int = 0) {
    val expectancy: Double get() = if (trades > 0) sumR / trades else 0.0
    val winRate: Double get() = if (trades > 0) wins.toDouble() / trades else 0.0
    operator fun plus(o: Score) = Score(trades + o.trades, sumR + o.sumR, wins + o.wins)
}

/**
 * Replays a strategy over a stretch of candles, the way the live bot trades:
 * enter on the close of a crossover candle, stop and target from the ATR,
 * out at whichever of stop, target or sell signal comes first. Assumes the
 * worse when a candle touches both, fills a gap through the stop at the open,
 * and charges [COST_R] per trade for spread and slippage.
 */
object Replay {
    const val COST_R = 0.03

    fun run(g: Genome, s: Series, from: Int, to: Int, minStopPct: Double, maxStopPct: Double): Score {
        val f = s.ema(g.fast)
        val sl = s.ema(g.slow)
        val warm = maxOf(g.slow, 14) * 3
        var trades = 0; var sum = 0.0; var wins = 0
        var inTrade = false
        var entry = 0.0; var stop = 0.0; var target = 0.0; var risk = 1.0
        val end = minOf(to, s.size)
        var i = maxOf(from, warm, 1)
        while (i < end) {
            if (!inTrade) {
                if (f[i - 1] <= sl[i - 1] && f[i] > sl[i] && !s.rsi[i].isNaN() && s.rsi[i] < g.entryRsi && s.atr[i] > 0) {
                    entry = s.close[i]
                    val stopPct = (s.atr[i] * g.atrMultiple / entry * 100).coerceIn(minStopPct, maxStopPct) / 100
                    stop = entry * (1 - stopPct)
                    target = entry * (1 + stopPct * g.rewardRisk)
                    risk = entry - stop
                    inTrade = risk > 0
                }
            } else {
                val r = when {
                    s.low[i] <= stop -> (minOf(s.open[i], stop) - entry) / risk
                    s.high[i] >= target -> (target - entry) / risk
                    (f[i - 1] >= sl[i - 1] && f[i] < sl[i]) || s.rsi[i] > g.exitRsi -> (s.close[i] - entry) / risk
                    else -> null
                }
                if (r != null) {
                    trades++; sum += r - COST_R; if (r > 0) wins++
                    inTrade = false
                }
            }
            i++
        }
        if (inTrade && end > 0) {
            val r = (s.close[end - 1] - entry) / risk
            trades++; sum += r - COST_R; if (r > 0) wins++
        }
        return Score(trades, sum, wins)
    }
}

/** A strategy scored on the three windows: learn on the oldest 60%, check on the next 20%, prove on the newest 20%. */
data class Trial(val genome: Genome, val train: Score, val valid: Score? = null, val confirm: Score? = null) {
    /** The training score with a penalty for few trades: a lower bound, not a best case. */
    val fitness: Double get() = if (train.trades < MIN_TRADES) -1.0 + train.trades * 0.01 else train.expectancy - 1.0 / sqrt(train.trades.toDouble())

    companion object { const val MIN_TRADES = 12 }
}

data class Promotion(
    val version: Int,
    val at: Long,
    val from: Genome,
    val to: Genome,
    /** Expected R per trade on the windows it had never trained on, before and after. */
    val before: Double,
    val after: Double,
    val trades: Int,
    val rollback: Boolean = false,
)

data class EvolutionSnapshot(
    val ready: Boolean = false,
    val tested: Long = 0,
    val generations: Long = 0,
    val perSecond: Double = 0.0,
    val champion: Genome = Genome.DEFAULT,
    val version: Int = 1,
    val championTest: Score? = null,
    val defaultTest: Score? = null,
    val best: Trial? = null,
    val history: List<Promotion> = emptyList(),
    /** The best training fitness, one point per recent generation. */
    val trail: List<Double> = emptyList(),
    val symbols: Int = 0,
    val bars: Int = 0,
    val mode: TrainMode = TrainMode.WAITING,
    val dataAt: Long? = null,
)

enum class TrainMode { WAITING, FULL, LIGHT, OFF }

/**
 * Self-improvement, done carefully. A population of strategy settings is
 * bred, mutated and replayed over months of real candles, thousands per
 * minute. Most of that is noise-hunting, so the bar for actually changing how
 * the bot trades is high:
 *
 *  - candidates compete on the oldest 60% of history only;
 *  - the best one is then tried on the next 20%, which it never trained on,
 *    and must beat the current strategy there by [MARGIN] R per trade;
 *  - and it must also do at least as well on the newest 20% — a second
 *    unseen stretch — and make money there;
 *  - at most one change per [MIN_GAP], and every change is logged with its
 *    numbers;
 *  - each new day of data re-checks the current strategy against the
 *    original, and rolls back if it has fallen behind.
 *
 * It tunes the strategy's settings within fixed bounds. It never touches the
 * owner's risk per trade, position cap or daily loss limit.
 */
class Evolution(
    private val store: BrainStore,
    private val now: () -> Long = System::currentTimeMillis,
    seed: Long = System.nanoTime(),
) {
    private val lock = Any()
    private val rng = Random(seed)
    @Volatile var champion: Genome = Genome.DEFAULT; private set
    @Volatile var version: Int = 1; private set
    private var series: List<Series> = emptyList()
    private var minStop = 0.8
    private var maxStop = 6.0
    private var dataAt: Long? = null
    private val population = ArrayList<Trial>()
    private var tested = 0L
    private var generations = 0L
    private var rate = 0.0
    private val history = ArrayList<Promotion>()
    private val trail = ArrayDeque<Double>()
    private var lastPromotionAt = 0L
    private var championTest: Pair<Score, Score>? = null
    private var defaultTest: Pair<Score, Score>? = null
    @Volatile var mode: TrainMode = TrainMode.WAITING

    init { load() }

    val ready: Boolean get() = synchronized(lock) { series.isNotEmpty() }

    /**
     * New history to learn from (once a day). The current strategy is
     * re-checked against the original on the newest data, and rolled back if
     * it has fallen behind by more than the margin.
     */
    fun setData(data: List<Series>, minStopPct: Double, maxStopPct: Double): Promotion? = synchronized(lock) {
        series = data.filter { it.size >= 200 }
        minStop = minStopPct; maxStop = maxStopPct
        dataAt = now()
        population.clear()
        if (series.isEmpty()) return null
        val c = unseen(champion)
        val d = unseen(Genome.DEFAULT)
        championTest = c; defaultTest = d
        if (champion != Genome.DEFAULT && (c.first + c.second).expectancy < (d.first + d.second).expectancy - MARGIN) {
            val p = Promotion(version + 1, now(), champion, Genome.DEFAULT, (c.first + c.second).expectancy,
                (d.first + d.second).expectancy, (d.first + d.second).trades, rollback = true)
            adopt(p, d)
            return p
        }
        null
    }

    /** One generation: breed, replay on the training stretch, and maybe promote the best. */
    fun step(): Promotion? = synchronized(lock) {
        if (series.isEmpty()) return null
        val started = System.nanoTime()
        if (population.isEmpty()) {
            population += trial(champion)
            if (champion != Genome.DEFAULT) population += trial(Genome.DEFAULT)
            while (population.size < POPULATION) population += trial(randomGenome())
        }
        val parents = population.sortedByDescending { it.fitness }.take(PARENTS)
        val children = ArrayList<Trial>()
        repeat(POPULATION - IMMIGRANTS) {
            val a = parents[rng.nextInt(parents.size)].genome
            val b = parents[rng.nextInt(parents.size)].genome
            children += trial(mutate(if (rng.nextBoolean()) crossover(a, b) else a))
        }
        repeat(IMMIGRANTS) { children += trial(randomGenome()) }
        population.addAll(children)
        val kept = population.distinctBy { it.genome }.sortedByDescending { it.fitness }.take(POPULATION)
        population.clear(); population.addAll(kept)
        generations++
        trail.addLast(kept.first().fitness)
        while (trail.size > TRAIL) trail.removeFirst()
        val seconds = (System.nanoTime() - started) / 1e9
        if (seconds > 0) rate = rate * 0.8 + (children.size / seconds) * 0.2
        val promotion = consider(kept.first())
        if (generations % SAVE_EVERY == 0L || promotion != null) save()
        promotion
    }

    private fun consider(best: Trial): Promotion? {
        if (best.genome == champion || best.train.expectancy <= 0) return null
        if (now() - lastPromotionAt < MIN_GAP) return null
        val (v, c) = unseen(best.genome)
        val (cv, cc) = championTest ?: unseen(champion).also { championTest = it }
        val ok = v.trades >= MIN_VALID_TRADES && c.trades >= MIN_CONFIRM_TRADES &&
            v.expectancy >= cv.expectancy + MARGIN &&
            c.expectancy >= cc.expectancy && c.expectancy > 0
        if (!ok) return null
        val p = Promotion(version + 1, now(), champion, best.genome, (cv + cc).expectancy, (v + c).expectancy, (v + c).trades)
        adopt(p, v to c)
        return p
    }

    private fun adopt(p: Promotion, test: Pair<Score, Score>) {
        champion = p.to
        version = p.version
        championTest = test
        lastPromotionAt = p.at
        history.add(0, p)
        while (history.size > HISTORY) history.removeAt(history.size - 1)
        save()
    }

    /** Back to the strategy it shipped with; what it tested is kept. */
    fun reset() = synchronized(lock) {
        if (champion == Genome.DEFAULT) return@synchronized
        val d = if (series.isEmpty()) null else unseen(Genome.DEFAULT)
        adopt(Promotion(version + 1, now(), champion, Genome.DEFAULT, 0.0, d?.let { (it.first + it.second).expectancy } ?: 0.0, 0, rollback = true),
            d ?: (Score() to Score()))
        lastPromotionAt = now()
    }

    fun snapshot(): EvolutionSnapshot = synchronized(lock) {
        EvolutionSnapshot(
            ready = series.isNotEmpty(), tested = tested, generations = generations, perSecond = rate,
            champion = champion, version = version,
            championTest = championTest?.let { it.first + it.second },
            defaultTest = defaultTest?.let { it.first + it.second },
            best = population.maxByOrNull { it.fitness },
            history = history.toList(), trail = trail.toList(),
            symbols = series.size, bars = series.sumOf { it.size }, mode = mode, dataAt = dataAt,
        )
    }

    // ---------------------------------------------------------------- inner

    private fun trial(g: Genome): Trial {
        tested++
        var train = Score()
        for (s in series) train += Replay.run(g, s, 0, (s.size * 0.6).toInt(), minStop, maxStop)
        return Trial(g, train)
    }

    /** The two stretches a strategy never trained on: validation, then confirmation. */
    private fun unseen(g: Genome): Pair<Score, Score> {
        var v = Score(); var c = Score()
        for (s in series) {
            v += Replay.run(g, s, (s.size * 0.6).toInt(), (s.size * 0.8).toInt(), minStop, maxStop)
            c += Replay.run(g, s, (s.size * 0.8).toInt(), s.size, minStop, maxStop)
        }
        return v to c
    }

    private fun randomGenome(): Genome {
        val fast = 5 + rng.nextInt(16)
        return Genome(
            fast = fast,
            slow = maxOf(20, fast + 6) + rng.nextInt(61 - maxOf(20, fast + 6)),
            entryRsi = 50.0 + rng.nextDouble() * 30,
            exitRsi = 60.0 + rng.nextDouble() * 30,
            atrMultiple = 0.8 + rng.nextDouble() * 2.2,
            rewardRisk = 1.2 + rng.nextDouble() * 2.8,
        ).clamped()
    }

    private fun mutate(g: Genome): Genome {
        fun maybe(p: Double = 0.5) = rng.nextDouble() < p
        return Genome(
            fast = if (maybe()) g.fast + (rng.nextGaussian() * 2).toInt() else g.fast,
            slow = if (maybe()) g.slow + (rng.nextGaussian() * 4).toInt() else g.slow,
            entryRsi = if (maybe()) g.entryRsi + rng.nextGaussian() * 4 else g.entryRsi,
            exitRsi = if (maybe()) g.exitRsi + rng.nextGaussian() * 4 else g.exitRsi,
            atrMultiple = if (maybe()) g.atrMultiple + rng.nextGaussian() * 0.25 else g.atrMultiple,
            rewardRisk = if (maybe()) g.rewardRisk + rng.nextGaussian() * 0.3 else g.rewardRisk,
        ).clamped()
    }

    private fun crossover(a: Genome, b: Genome) = Genome(
        fast = if (rng.nextBoolean()) a.fast else b.fast,
        slow = if (rng.nextBoolean()) a.slow else b.slow,
        entryRsi = if (rng.nextBoolean()) a.entryRsi else b.entryRsi,
        exitRsi = if (rng.nextBoolean()) a.exitRsi else b.exitRsi,
        atrMultiple = if (rng.nextBoolean()) a.atrMultiple else b.atrMultiple,
        rewardRisk = if (rng.nextBoolean()) a.rewardRisk else b.rewardRisk,
    ).clamped()

    // ----------------------------------------------------------- persistence

    private fun save() {
        val o = JSONObject()
            .put("champion", genomeJson(champion)).put("version", version).put("tested", tested)
            .put("generations", generations).put("lastPromotionAt", lastPromotionAt)
            .put("history", JSONArray().apply {
                history.forEach { p ->
                    put(JSONObject().put("v", p.version).put("at", p.at).put("from", genomeJson(p.from)).put("to", genomeJson(p.to))
                        .put("b", p.before).put("a", p.after).put("n", p.trades).put("rb", p.rollback))
                }
            })
        store.write(DOC, o.toString())
    }

    private fun load() {
        val o = store.read(DOC)?.let { runCatching { JSONObject(it) }.getOrNull() } ?: return
        runCatching {
            champion = genome(o.getJSONObject("champion"))
            version = o.optInt("version", 1)
            tested = o.optLong("tested")
            generations = o.optLong("generations")
            lastPromotionAt = o.optLong("lastPromotionAt")
            val h = o.optJSONArray("history") ?: JSONArray()
            for (i in 0 until h.length()) {
                val p = h.getJSONObject(i)
                history += Promotion(p.getInt("v"), p.getLong("at"), genome(p.getJSONObject("from")), genome(p.getJSONObject("to")),
                    p.optDouble("b"), p.optDouble("a"), p.optInt("n"), p.optBoolean("rb"))
            }
        }.onFailure { champion = Genome.DEFAULT; version = 1 }
    }

    private fun genomeJson(g: Genome) = JSONObject().put("f", g.fast).put("s", g.slow).put("e", g.entryRsi)
        .put("x", g.exitRsi).put("a", g.atrMultiple).put("r", g.rewardRisk)

    private fun genome(o: JSONObject) = Genome(o.getInt("f"), o.getInt("s"), o.getDouble("e"), o.getDouble("x"),
        o.getDouble("a"), o.getDouble("r")).clamped()

    companion object {
        const val POPULATION = 24
        const val PARENTS = 8
        const val IMMIGRANTS = 4
        const val MARGIN = 0.08
        /** Fewer trades than this on the unseen stretches, and a "better" result is mostly luck. */
        const val MIN_VALID_TRADES = 15
        const val MIN_CONFIRM_TRADES = 10
        const val MIN_GAP = 30 * 60_000L
        const val HISTORY = 30
        const val TRAIL = 80
        const val SAVE_EVERY = 50L
        private const val DOC = "evolution"
    }
}
