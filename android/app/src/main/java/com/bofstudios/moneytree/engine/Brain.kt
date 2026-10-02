package com.bofstudios.moneytree.engine

import java.util.Locale

/** How picky the five checks are about what may be bought. */
enum class QualityMode {
    /** Only stocks in the buy zone: a good business at a fair price, daily chart rising. */
    STRICT,
    /** Never a stock the checks call AVOID, never against a falling daily chart. */
    BALANCED,
    /** Charts only, as before 3.0. */
    OFF,
}

/** The AI's short read of what a business does and why customers stay. */
fun interface Analyst {
    suspend fun read(symbol: String, name: String, facts: String, turkish: Boolean): String?
}

/** The AI's lesson from a trade that just closed. */
fun interface Coach {
    suspend fun lesson(facts: String, turkish: Boolean): String?
}

/** Everything the research said about one buy signal, before any money moves. */
data class Research(
    val symbol: String,
    val report: QualityReport?,
    val qualityOk: Boolean,
    val dailyUp: Boolean?,
    val trendOk: Boolean,
    val mood: Double?,
    val newsCount: Int,
    val flags: List<RedFlag>,
    val newsOk: Boolean,
    val learned: LearnedVerdict,
    val learnedOk: Boolean,
    val features: Features,
    /** 0.5 to 1: how much of the normal size this buy gets. */
    val size: Double,
) {
    val ok: Boolean get() = qualityOk && trendOk && newsOk && learnedOk
}

/** What the screen shows of the brain. */
data class BrainSnapshot(
    val reports: Map<String, QualityReport> = emptyMap(),
    val radar: RadarSnapshot = RadarSnapshot(),
    val lessons: List<BucketStats> = emptyList(),
    val rules: List<BucketStats> = emptyList(),
    val shadowOpen: List<ShadowTrade> = emptyList(),
    val shadowRecent: List<ShadowTrade> = emptyList(),
    val shadowClosed: Int = 0,
    val shadowWins: Int = 0,
    val shadowAvgR: Double? = null,
    val realResults: Int = 0,
    val tradeLessons: List<AiNote> = emptyList(),
    val filingsAt: Long? = null,
)

/** What one look's tracking found: shadow trades opened and closed, rules newly learned. */
data class TrackResult(val opened: List<ShadowTrade>, val closed: List<ShadowTrade>, val newRules: List<BucketStats>)

/**
 * The research desk: annual reports, the news wire, daily charts and what
 * past signals taught. The engine asks it about every buy signal; it can only
 * say "not this one" or "smaller" — it never starts a trade.
 *
 * Network work (filings weekly, daily charts and exchange rates daily, news
 * every look) happens in [refresh] and [readNews]; everything else here is
 * arithmetic on what is already in memory.
 */
class Brain(
    private val store: BrainStore,
    private val filings: FilingsSource? = null,
    private val fx: FxSource? = null,
    private val scorer: NewsScorer? = null,
    private val analyst: Analyst? = null,
    private val coach: Coach? = null,
    strategy: EmaRsiStrategy = EmaRsiStrategy(),
    private val now: () -> Long = System::currentTimeMillis,
) {
    val radar = NewsRadar(now)
    val shadows = ShadowBook(strategy)
    val learner = Learner()

    private val lock = Any()
    private val filed = HashMap<String, Filings>()
    private val missedAt = HashMap<String, Long>()
    private val daily = HashMap<String, List<Bar>>()
    private val dailyAt = HashMap<String, Long>()
    private val rates = HashMap<String, Double>()
    private var ratesAt = 0L
    private val reports = LinkedHashMap<String, QualityReport>()
    private val plans = HashMap<String, EntryPlan>()
    private val tradeLessons = ArrayList<AiNote>()
    private var lastScoredAt = 0L

    init {
        radar.restore(BrainCodec.news(store.read(NEWS)))
        shadows.restore(BrainCodec.shadows(store.read(SHADOWS)))
        learner.restore(BrainCodec.samples(store.read(SAMPLES)))
        BrainCodec.plans(store.read(PLANS)).forEach { plans[it.symbol] = it }
        tradeLessons.addAll(BrainCodec.notes(store.read(LESSONS)))
    }

    /** Loads what was saved last time, so the screen has reports before the first network call. */
    fun warmUp(symbols: List<String>) {
        for (s in symbols) if (s !in filed) BrainCodec.filings(store.read(filingsKey(s)))?.let { filed[s] = it }
        evaluate(symbols, emptyMap())
    }

    // ------------------------------------------------------------ refreshing

    /**
     * Annual reports once a week, daily charts once a New York day, exchange
     * rates twice a day. Each is a visible step while it runs; when nothing is
     * due this costs nothing.
     */
    suspend fun refresh(symbols: List<String>, broker: Broker, monitor: Monitor, w: Words) {
        val t = now()
        val source = filings
        if (source != null) {
            for (s in symbols) if (s !in filed) BrainCodec.filings(store.read(filingsKey(s)))?.let { filed[s] = it }
            val due = symbols.filter { s ->
                val f = filed[s]
                if (f == null) (missedAt[s] ?: 0L) < t - DAY else t - f.fetchedAt > WEEK
            }
            if (due.isNotEmpty()) {
                val step = monitor.begin(StepKind.RESEARCH, w.readingFilings(due.size))
                val lines = ArrayList<String>()
                for ((i, s) in due.withIndex()) {
                    step.progress("$s · ${i + 1}/${due.size}")
                    val f = attempt { source.filings(s) }
                    if (f == null) { missedAt[s] = t; lines += w.filingsMissing(s); continue }
                    // A fresh fetch keeps last month's AI read rather than paying for a new one.
                    val kept = f.copy(aiRead = filed[s]?.aiRead)
                    filed[s] = kept
                    store.write(filingsKey(s), BrainCodec.filings(kept))
                    lines += w.filingsLine(kept)
                }
                step.done(w.filingsSummary(due.count { it in filed }, due.size), lines)
            }
            analyst?.let { ai ->
                val unread = symbols.mapNotNull { filed[it] }.filter { !it.fund && it.years.isNotEmpty() && it.aiRead == null }
                for (f in unread.take(MAX_READS_PER_LOOK)) {
                    val read = attempt {
                        monitor.step(StepKind.AI, w.aiReadingBusiness(f.name), { ai.read(f.symbol, f.name, businessFacts(f), w.tr) }, { it })
                    } ?: continue
                    val updated = f.copy(aiRead = read.trim())
                    filed[f.symbol] = updated
                    store.write(filingsKey(f.symbol), BrainCodec.filings(updated))
                }
            }
        }

        val today = startOfNyDay(t)
        val dueDaily = symbols.filter { (dailyAt[it] ?: 0L) < today }
        if (dueDaily.isNotEmpty()) {
            val step = monitor.begin(StepKind.BARS, w.fetchingDaily(dueDaily.size))
            for ((i, s) in dueDaily.withIndex()) {
                step.progress("$s · ${i + 1}/${dueDaily.size}")
                val bars = attempt { broker.bars(s, Timeframe.D1, DAILY_BARS) }
                if (bars != null && bars.isNotEmpty()) { synchronized(lock) { daily[s] = bars }; dailyAt[s] = t }
            }
            step.done(w.dailyChartsSummary(dueDaily.count { (dailyAt[it] ?: 0L) >= today }, dueDaily.size))
        }

        val fxSource = fx
        val currencies = symbols.mapNotNull { filed[it]?.currency }.filter { it != "USD" }.toSet()
        if (fxSource != null && currencies.isNotEmpty() && (t - ratesAt > 12 * HOUR || currencies.any { it !in rates })) {
            attempt {
                monitor.step(StepKind.RESEARCH, w.readingFx(currencies), {
                    currencies.forEach { c -> fxSource.usdPer(c)?.let { rates[c] = it } }
                }, { w.fxSummary(rates.filterKeys { it in currencies }) })
            }
            ratesAt = t
        }
    }

    /**
     * Pulls whatever the wire has that is new. Shown in the feed only when
     * something new arrived (or the owner asked for a look), so a quiet
     * minute does not add a quiet line.
     */
    suspend fun readNews(symbols: List<String>, broker: Broker, monitor: Monitor, w: Words, verbose: Boolean) {
        if (symbols.isEmpty()) return
        val since = radar.latestAt()?.minus(60_000L) ?: (now() - 48 * HOUR)
        val fresh = attempt { broker.newsFeed(symbols, since, NEWS_PAGE) } ?: run {
            if (verbose) monitor.info(StepKind.NEWS, w.newsWireFailed())
            return
        }
        val before = radar.all().map { it.id }.toSet()
        val added = radar.ingest(fresh)
        if (added > 0 || verbose) {
            val newOnes = fresh.filter { it.id !in before }
            monitor.info(StepKind.NEWS, w.newsWire(added, radar.all().size), null,
                newOnes.take(6).map { "${it.mood.moodText()}  ${it.symbols.take(3).joinToString(",")}  ${it.headline.take(90)}" })
        }
        val ai = scorer
        if (ai != null && now() - lastScoredAt >= SCORE_EVERY) {
            val unscored = radar.unscored(SCORE_BATCH)
            if (unscored.isNotEmpty()) {
                lastScoredAt = now()
                attempt {
                    monitor.step(StepKind.AI, w.aiReadingHeadlines(unscored.size), { ai.score(unscored) }, { w.aiScored(it.size) })
                }?.let { radar.applyScores(it) }
            }
        }
        if (added > 0 || ai != null) store.write(NEWS, BrainCodec.news(radar.all()))
    }

    // ---------------------------------------------------------- the checks

    /** Re-scores the five checks against current prices. No network. */
    fun evaluate(symbols: List<String>, prices: Map<String, Double>) {
        val t = now()
        val next = LinkedHashMap<String, QualityReport>()
        for (s in symbols) {
            val f = filed[s]
            val bars = synchronized(lock) { daily[s].orEmpty() }
            val price = prices[s] ?: bars.lastOrNull()?.close
            val usdPer = f?.currency?.let { if (it == "USD") 1.0 else rates[it] }
            next[s] = Quality.evaluate(s, f, price, usdPer, Quality.SHARES_PER_LISTING[s], bars, radar.flags(s), t)
        }
        synchronized(lock) { reports.clear(); reports.putAll(next) }
    }

    fun report(symbol: String): QualityReport? = synchronized(lock) { reports[symbol] }

    fun dailyUp(symbol: String): Boolean? {
        val bars = synchronized(lock) { daily[symbol].orEmpty() }
        if (bars.size < 50) return null
        return bars.last().close > bars.takeLast(50).map { it.close }.average()
    }

    fun features(symbol: String, snap: Snapshot, bars: List<Bar>, intraday: Boolean): Features = Features(
        symbol = symbol,
        quality = report(symbol)?.decision ?: Decision.UNKNOWN,
        news = radar.mood(symbol),
        rsi = snap.rsi,
        stretch = if (snap.atr > 0) (snap.price - snap.slowEma) / snap.atr else Double.NaN,
        minuteOfSession = if (intraday) bars.lastOrNull()?.let { minuteOfSession(it.time) } else null,
        dailyUp = dailyUp(symbol),
    )

    /**
     * The four gates every buy signal passes before it may be sized, in the
     * order the owner sees them: the five checks, the daily trend, the news,
     * and what past signals of this kind returned.
     */
    fun research(symbol: String, snap: Snapshot, bars: List<Bar>, s: TradingSettings): Research {
        val report = report(symbol)
        val f = features(symbol, snap, bars, intraday = s.horizon.timeframe != Timeframe.D1)
        val qualityOk = when (s.qualityMode) {
            QualityMode.OFF -> true
            QualityMode.BALANCED -> report?.decision != Decision.AVOID
            QualityMode.STRICT -> report?.decision == Decision.BUY_ZONE
        }
        val trendOk = s.qualityMode == QualityMode.OFF || f.dailyUp != false
        val flags = radar.flags(symbol)
        val count = radar.count(symbol)
        val mood = f.news
        val newsOk = !s.newsCheck ||
            (flags.none { it.kind.blocksBuys } && !(mood != null && mood <= NewsRadar.BAD_MOOD && count >= 2))
        val learned = if (s.learning) learner.verdict(f) else LearnedVerdict(false, null, emptyList(), 1.0)
        val qualitySize = when {
            s.qualityMode == QualityMode.OFF -> 1.0
            report?.decision == Decision.BUY_ZONE -> 1.0
            else -> 0.75
        }
        val newsSize = if (s.newsCheck && mood != null && mood < -NewsRadar.GOOD_MOOD) 0.75 else 1.0
        val size = (qualitySize * newsSize * learned.size).coerceIn(0.5, 1.0)
        return Research(symbol, report, qualityOk, f.dailyUp, trendOk, mood, count, flags, newsOk,
            learned, !learned.blocked, f, size)
    }

    /**
     * What the AI committee is told about a stock, in plain English. The
     * headlines go separately, quoted, so their text is never mistaken for
     * the bot's own words.
     */
    fun dossier(r: Research): String = buildString {
        val us = Locale.US
        r.report?.let { q ->
            append("Five checks (from SEC annual reports): ")
            append(q.checks.joinToString("; ") { c -> "${c.kind} ${c.verdict}" + factsText(c) })
            append(". Decision ${q.decision}, ${String.format(us, "%.1f", q.score)}/5. ")
        }
        r.dailyUp?.let { append(if (it) "Daily chart above its 50-day average. " else "Daily chart below its 50-day average. ") }
        append("News: ${r.newsCount} items in 24h")
        r.mood?.let { append(", time-weighted mood ${it.moodText()} (−1 bad, +1 good)") }
        append(". ")
        if (r.flags.isNotEmpty()) append("Fresh flags: ${r.flags.joinToString { it.kind.name }}. ")
        if (r.learned.evidence.isNotEmpty()) {
            append("What past signals like this returned: ")
            append(r.learned.evidence.take(3).joinToString("; ") { b ->
                "${b.bucket.key} ${b.bucket.value}: ${String.format(us, "%.0f", b.n)} results, " +
                    "${String.format(us, "%.0f", b.winRate * 100)}% won, avg ${String.format(us, "%+.2f", b.avgR)}R"
            })
            append(". ")
        }
    }

    // -------------------------------------------------------------- learning

    /**
     * Follows every buy signal in the head (bought or not), closes the ones
     * whose stop, target or sell signal has come, and counts the results.
     */
    fun track(
        signals: Map<String, Signal>, snapshots: List<Snapshot>, bars: Map<String, List<Bar>>,
        risk: Risk, s: TradingSettings,
    ): TrackResult {
        val opened = ArrayList<ShadowTrade>()
        val intraday = s.horizon.timeframe != Timeframe.D1
        for ((sym, signal) in signals) {
            if (signal.action != Action.BUY) continue
            val snap = snapshots.firstOrNull { it.symbol == sym && it.ready } ?: continue
            val b = bars[sym].orEmpty()
            val last = b.lastOrNull() ?: continue
            val stopPct = risk.stopDistancePct(snap.price, snap.atr) / 100.0
            val t = ShadowTrade(
                id = "sh-$sym-${last.time}", symbol = sym, openedAt = last.time, entry = snap.price,
                stop = snap.price * (1 - stopPct), target = snap.price * (1 + stopPct * risk.config.rewardRisk),
                features = features(sym, snap, b, intraday),
            )
            if (shadows.open(t)) opened += t
        }
        val closed = shadows.resolve(bars, risk.config.rewardRisk)
        val newRules = ArrayList<BucketStats>()
        for (c in closed) newRules += learner.add(Sample(c.features, c.r ?: 0.0, real = false, at = c.closedAt ?: now()))
        if (opened.isNotEmpty() || closed.isNotEmpty()) {
            store.write(SHADOWS, BrainCodec.shadows(shadows.all()))
            if (closed.isNotEmpty()) store.write(SAMPLES, BrainCodec.samples(learner.all()))
        }
        return TrackResult(opened, closed, newRules.distinctBy { it.bucket })
    }

    fun bought(entry: Entry, f: Features) {
        synchronized(lock) { plans[entry.symbol] = EntryPlan(entry.symbol, entry.price, entry.stop, f, now()) }
        shadows.markBought(entry.symbol)
        store.write(PLANS, BrainCodec.plans(synchronized(lock) { plans.values.toList() }))
        store.write(SHADOWS, BrainCodec.shadows(shadows.all()))
    }

    /** A real trade closed: count it (double weight) and ask the coach for its lesson. */
    suspend fun closed(t: TradeRecord, monitor: Monitor, w: Words): Pair<List<BucketStats>, AiNote?> {
        val plan = synchronized(lock) { plans.remove(t.symbol) } ?: return emptyList<BucketStats>() to null
        store.write(PLANS, BrainCodec.plans(synchronized(lock) { plans.values.toList() }))
        val riskPerShare = t.entry - plan.stop
        val r = if (riskPerShare > 0) (t.exit - t.entry) / riskPerShare else 0.0
        val rules = learner.add(Sample(plan.features, r, real = true, at = t.closedAt))
        store.write(SAMPLES, BrainCodec.samples(learner.all()))
        val ai = coach ?: return rules to null
        val us = Locale.US
        val facts = "Trade on ${t.symbol}: bought at ${String.format(us, "%.2f", t.entry)}, stop was ${String.format(us, "%.2f", plan.stop)}, " +
            "sold at ${String.format(us, "%.2f", t.exit)} (${t.reason}), result ${String.format(us, "%+.2f", t.pnl)} USD = ${String.format(us, "%+.2f", r)}R. " +
            "At the buy: checks ${plan.features.quality}, news mood ${plan.features.news?.moodText() ?: "none"}, " +
            "RSI ${String.format(us, "%.0f", plan.features.rsi)}, ${String.format(us, "%.1f", plan.features.stretch)} ATRs above the slow EMA, " +
            "daily chart ${when (plan.features.dailyUp) { true -> "rising"; false -> "falling"; null -> "unknown" }}."
        val text = attempt { monitor.step(StepKind.AI, w.aiLesson(t.symbol), { ai.lesson(facts, w.tr) }, { it }) } ?: return rules to null
        val note = AiNote(t.symbol, text.trim(), now())
        synchronized(lock) {
            tradeLessons.add(0, note)
            while (tradeLessons.size > MAX_LESSONS) tradeLessons.removeAt(tradeLessons.size - 1)
        }
        store.write(LESSONS, BrainCodec.notes(synchronized(lock) { tradeLessons.toList() }))
        return rules to note
    }

    fun forget() {
        learner.clear()
        shadows.clear()
        synchronized(lock) { tradeLessons.clear() }
        store.write(SAMPLES, "[]"); store.write(SHADOWS, "[]"); store.write(LESSONS, "[]")
    }

    fun snapshot(symbols: List<String>): BrainSnapshot {
        val all = shadows.all()
        val done = all.filter { !it.open }
        return BrainSnapshot(
            reports = synchronized(lock) { reports.filterKeys { it in symbols } },
            radar = radar.snapshot(symbols),
            lessons = learner.lessons().take(12),
            rules = learner.rules(),
            shadowOpen = all.filter { it.open }.sortedByDescending { it.openedAt },
            shadowRecent = done.sortedByDescending { it.closedAt }.take(12),
            shadowClosed = done.size,
            shadowWins = done.count { (it.r ?: 0.0) > 0 },
            shadowAvgR = done.mapNotNull { it.r }.takeIf { it.isNotEmpty() }?.average(),
            realResults = learner.all().count { it.real },
            tradeLessons = synchronized(lock) { tradeLessons.toList() },
            filingsAt = filed.values.maxOfOrNull { it.fetchedAt },
        )
    }

    private fun factsText(c: Check): String {
        val us = Locale.US
        val parts = c.facts.mapNotNull { f ->
            when (f.metric) {
                Metric.PROFIT_YEARS -> "profitable ${f.text} years"
                Metric.REVENUE_GROWTH -> "revenue ${String.format(us, "%+.1f", f.value * 100)}%/yr"
                Metric.GROSS_MARGIN -> "gross margin ${String.format(us, "%.0f", f.value * 100)}%"
                Metric.OPERATING_MARGIN -> "operating margin ${String.format(us, "%.0f", f.value * 100)}%"
                Metric.RETURN_ON_EQUITY -> "ROE ${String.format(us, "%.0f", f.value * 100)}%"
                Metric.SHARE_CHANGE -> "shares ${String.format(us, "%+.1f", f.value * 100)}%/yr"
                Metric.DEBT_TO_PROFIT -> "debt ${String.format(us, "%.1f", f.value)}x yearly profit"
                Metric.INTEREST_COVER -> "interest covered ${String.format(us, "%.0f", f.value)}x"
                Metric.PRICE -> "price ${String.format(us, "%.2f", f.value)}"
                Metric.VALUE -> "value estimate ${String.format(us, "%.2f", f.value)}"
                Metric.PRICE_TO_VALUE -> "price/value ${String.format(us, "%.2f", f.value)}"
                Metric.VS_200_DAY -> "price/200-day avg ${String.format(us, "%.2f", f.value)}"
                Metric.DAILY_SWING -> "daily swing ${String.format(us, "%.1f", f.value * 100)}%"
                Metric.RED_FLAG -> "flag ${f.text}"
                Metric.FUND -> null
            }
        }
        return if (parts.isEmpty()) "" else " (" + parts.joinToString(", ") + ")"
    }

    private fun businessFacts(f: Filings): String {
        val y = f.years.lastOrNull() ?: return f.name
        val us = Locale.US
        fun b(v: Double?) = v?.let { String.format(us, "%.1f", it / 1e9) + "bn " + f.currency } ?: "n/a"
        return "${f.name} (${f.symbol}). Latest fiscal year ending ${y.end}: revenue ${b(y.revenue)}, " +
            "operating income ${b(y.operatingIncome)}, net income ${b(y.netIncome)}."
    }

    companion object {
        const val HOUR = 3_600_000L
        const val DAY = 24 * HOUR
        const val WEEK = 7 * DAY
        const val DAILY_BARS = 260
        const val NEWS_PAGE = 50
        const val SCORE_EVERY = 5 * 60_000L
        const val SCORE_BATCH = 20
        const val MAX_READS_PER_LOOK = 3
        const val MAX_LESSONS = 20

        private const val NEWS = "news"
        private const val SHADOWS = "shadows"
        private const val SAMPLES = "samples"
        private const val PLANS = "plans"
        private const val LESSONS = "lessons"
        private fun filingsKey(symbol: String) = "filings_$symbol"
    }
}
