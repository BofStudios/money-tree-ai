package com.bofstudios.moneytree.engine

import kotlin.math.abs
import kotlin.math.pow

/** What the news is about, the way a desk would sort the wire. */
enum class Topic {
    EARNINGS, AI_CHIPS, CLOUD, PRODUCT, ANALYSTS, DEALS, CAPITAL, LEGAL, REGULATION, SUPPLY, MACRO, LEADERSHIP,
}

/**
 * Words in a headline that should stop a buy, or at least make it careful.
 * Severe ones mean "not now, whatever the chart says".
 */
enum class RedFlagKind(val severe: Boolean, val hours: Int) {
    HALT(true, 72),
    BANKRUPTCY(true, 72),
    FRAUD(true, 72),
    DELISTING(true, 72),
    OFFERING(true, 72),
    ACCOUNTING(true, 96),
    GUIDANCE_CUT(false, 48),
    EARNINGS_SOON(false, 36),
    REGULATOR(false, 48),
    RECALL(false, 48),
    ;

    /** Whether this flag alone keeps the bot from buying while it is fresh. */
    val blocksBuys: Boolean get() = severe || this == GUIDANCE_CUT || this == EARNINGS_SOON
}

data class RedFlag(val kind: RedFlagKind, val symbol: String, val at: Long, val headline: String)

data class NewsItem(
    val id: Long,
    val headline: String,
    val summary: String,
    val source: String,
    val symbols: List<String>,
    val createdAt: Long,
    val url: String = "",
    /** From the word list, −1 (bad) to +1 (good). */
    val score: Double = Sentiment.score(headline, summary),
    /** The AI's reading of the same item, when it has read it. */
    val aiScore: Double? = null,
    val topics: Set<Topic> = Topics.of(headline + " " + summary),
    val flags: List<RedFlagKind> = RedFlags.of(headline, summary),
) {
    /** The AI's score wins when there is one: it reads context a word list cannot. */
    val mood: Double get() = aiScore ?: score
    /** A round-up naming many companies says little about any one of them. */
    val roundup: Boolean get() = symbols.size > 4
}

/** Reads headlines for the AI, when it is connected: item id to a −1..+1 score. */
fun interface NewsScorer {
    suspend fun score(items: List<NewsItem>): Map<Long, Double>
}

/**
 * A finance word list, scored on the phone with no network: the headline
 * counts twice, the summary once, and "not", "no" or "fails to" flips the
 * next two words. Small and deliberately transparent — the screen highlights
 * exactly the words that moved the score.
 */
object Sentiment {
    private val positive = mapOf(
        "beat" to 1.0, "beats" to 1.0, "tops" to 1.0, "topped" to 1.0, "surge" to 1.0, "surges" to 1.0, "surged" to 1.0,
        "soar" to 1.0, "soars" to 1.0, "soared" to 1.0, "jump" to 0.8, "jumps" to 0.8, "jumped" to 0.8, "rally" to 0.8,
        "rallies" to 0.8, "rallied" to 0.8, "record" to 0.6, "upgrade" to 1.0, "upgrades" to 1.0, "upgraded" to 1.0,
        "outperform" to 0.8, "outperforms" to 0.8, "raises" to 0.7, "raised" to 0.6, "strong" to 0.7, "stronger" to 0.7,
        "strongest" to 0.7, "growth" to 0.5, "grows" to 0.6, "grew" to 0.6, "gain" to 0.6, "gains" to 0.6, "gained" to 0.6,
        "rise" to 0.5, "rises" to 0.5, "rose" to 0.5, "rising" to 0.4, "higher" to 0.4, "bullish" to 0.9, "rebound" to 0.7,
        "rebounds" to 0.7, "boost" to 0.7, "boosts" to 0.7, "boosted" to 0.7, "wins" to 0.7, "won" to 0.5, "approval" to 0.8,
        "approves" to 0.8, "approved" to 0.8, "breakthrough" to 0.9, "exceeds" to 0.9, "exceeded" to 0.9, "accelerates" to 0.7,
        "accelerating" to 0.6, "expands" to 0.5, "expansion" to 0.4, "buyback" to 0.6, "upbeat" to 0.8, "optimistic" to 0.7,
        "robust" to 0.6, "solid" to 0.5, "momentum" to 0.4, "partnership" to 0.4, "launches" to 0.3, "profitable" to 0.6,
        "climbs" to 0.6, "climbed" to 0.6, "highs" to 0.5, "doubles" to 0.6, "dividend" to 0.3, "recovers" to 0.6,
    )
    private val negative = mapOf(
        "miss" to 1.0, "misses" to 1.0, "missed" to 1.0, "plunge" to 1.0, "plunges" to 1.0, "plunged" to 1.0,
        "slump" to 0.9, "slumps" to 0.9, "slumped" to 0.9, "tumble" to 0.9, "tumbles" to 0.9, "tumbled" to 0.9,
        "fall" to 0.6, "falls" to 0.6, "fell" to 0.6, "falling" to 0.6, "drop" to 0.6, "drops" to 0.6, "dropped" to 0.6,
        "sink" to 0.8, "sinks" to 0.8, "sank" to 0.8, "slide" to 0.6, "slides" to 0.6, "slid" to 0.6,
        "downgrade" to 1.0, "downgrades" to 1.0, "downgraded" to 1.0, "cut" to 0.6, "cuts" to 0.6, "lowers" to 0.7,
        "lowered" to 0.7, "weak" to 0.8, "weaker" to 0.8, "weakness" to 0.8, "warning" to 0.9, "warns" to 0.9, "warned" to 0.9,
        "lawsuit" to 0.8, "sues" to 0.7, "sued" to 0.7, "probe" to 0.7, "investigation" to 0.7, "fraud" to 1.0, "recall" to 0.8,
        "recalls" to 0.8, "layoffs" to 0.6, "halt" to 0.9, "halted" to 0.9, "delay" to 0.5, "delays" to 0.5, "delayed" to 0.5,
        "bankruptcy" to 1.0, "bankrupt" to 1.0, "default" to 0.9, "decline" to 0.6, "declines" to 0.6, "declined" to 0.6,
        "loss" to 0.6, "losses" to 0.6, "loses" to 0.6, "bearish" to 0.9, "selloff" to 0.8, "concern" to 0.5, "concerns" to 0.5,
        "fears" to 0.6, "worries" to 0.6, "antitrust" to 0.6, "fined" to 0.8, "penalty" to 0.7, "subpoena" to 0.8,
        "dilution" to 0.8, "crash" to 1.0, "crashes" to 1.0, "slowdown" to 0.7, "slowing" to 0.5, "underperform" to 0.8,
        "disappoints" to 0.9, "disappointing" to 0.9, "disappointed" to 0.8, "shortfall" to 0.8, "headwinds" to 0.6,
        "tariffs" to 0.4, "ban" to 0.6, "banned" to 0.7, "lawsuits" to 0.8, "slashes" to 0.9, "plummets" to 1.0,
        "plummeted" to 1.0, "retreats" to 0.5, "lows" to 0.5, "sell-off" to 0.8,
    )
    private val negators = setOf("not", "no", "never", "without", "fails", "failed", "fail")

    /** The words that moved a score, positive weights good, negative bad. */
    data class Hit(val word: String, val weight: Double)

    fun tokens(text: String): List<String> =
        text.lowercase().split(Regex("[^a-z0-9'-]+")).filter { it.isNotBlank() }

    fun hits(text: String): List<Hit> {
        val out = ArrayList<Hit>()
        var flip = 0
        for (t in tokens(text)) {
            if (t in negators) { flip = 2; continue }
            val w = positive[t]?.let { +it } ?: negative[t]?.let { -it }
            if (w != null) out += Hit(t, if (flip > 0) -w else w)
            if (flip > 0) flip--
        }
        return out
    }

    fun score(headline: String, summary: String = ""): Double {
        var pos = 0.0
        var neg = 0.0
        for ((text, weight) in listOf(headline to 2.0, summary to 1.0)) {
            for (h in hits(text)) if (h.weight > 0) pos += h.weight * weight else neg += -h.weight * weight
        }
        return (pos - neg) / (pos + neg + 1.0)
    }
}

object Topics {
    // Whole words and phrases only: "chip" must not match "Chipotle".
    private val words = mapOf(
        Topic.EARNINGS to listOf("earnings", "results", "estimates", "sales", "quarter", "quarterly", "eps", "revenue", "guidance", "outlook", "forecast", "profit", "profits"),
        Topic.AI_CHIPS to listOf("ai", "artificial intelligence", "gpu", "gpus", "chip", "chips", "chipmaker", "semiconductor", "semiconductors", "data center", "data centers"),
        Topic.CLOUD to listOf("cloud", "azure", "aws", "enterprise", "saas", "software", "subscription", "subscriptions"),
        Topic.PRODUCT to listOf("launch", "launches", "unveil", "unveils", "release", "releases", "iphone", "product", "products", "device", "vehicle", "feature"),
        Topic.ANALYSTS to listOf("upgrade", "upgrades", "downgrade", "downgrades", "price target", "analyst", "analysts", "rating", "overweight", "underweight", "outperform"),
        Topic.DEALS to listOf("acquire", "acquires", "acquisition", "merger", "deal", "stake", "partnership", "invest", "invests", "buyout", "takeover"),
        Topic.CAPITAL to listOf("buyback", "dividend", "offering", "bond", "bonds", "notes", "stock split", "repurchase", "debt"),
        Topic.LEGAL to listOf("lawsuit", "lawsuits", "sued", "sues", "court", "settlement", "verdict", "litigation", "judge", "jury"),
        Topic.REGULATION to listOf("antitrust", "regulator", "regulators", "ftc", "doj", "european commission", "sec", "probe", "investigation", "fine", "fined"),
        Topic.SUPPLY to listOf("supply", "supply chain", "shortage", "factory", "production", "export", "exports", "tariff", "tariffs", "inventory"),
        Topic.MACRO to listOf("fed", "federal reserve", "inflation", "interest rate", "interest rates", "jobs report", "cpi", "economy", "recession", "treasury"),
        Topic.LEADERSHIP to listOf("ceo", "cfo", "chief executive", "steps down", "resigns", "appoints", "board", "founder"),
    )

    fun of(text: String): Set<Topic> {
        val t = " " + text.lowercase().replace(Regex("[^a-z0-9]+"), " ") + " "
        return words.filter { (_, list) -> list.any { " $it " in t } }.keys
    }
}

object RedFlags {
    private val patterns = linkedMapOf(
        RedFlagKind.HALT to listOf("trading halt", "halts trading", "trading halted", "halted trading"),
        RedFlagKind.BANKRUPTCY to listOf("bankruptcy", "chapter 11", "insolvency", "insolvent"),
        RedFlagKind.FRAUD to listOf("accused of fraud", "fraud charges", "securities fraud", "fraud allegations", "accounting fraud",
            "charged with fraud", "accounting irregular", "restates earnings", "restatement", "sec charges", "charged by the sec"),
        RedFlagKind.DELISTING to listOf("delist"),
        RedFlagKind.OFFERING to listOf("public offering", "secondary offering", "stock offering", "share offering",
            "at-the-market offering", "prices offering", "dilutive offering"),
        RedFlagKind.GUIDANCE_CUT to listOf("cuts guidance", "lowers guidance", "lowered guidance", "cut its guidance",
            "slashes forecast", "cuts forecast", "lowers outlook", "cuts outlook", "profit warning", "warns on profit", "cuts full-year"),
        RedFlagKind.EARNINGS_SOON to listOf("earnings preview", "ahead of earnings", "earnings on deck", "to report earnings",
            "earnings tomorrow", "reports after the bell", "reports before the bell", "what to expect from", "earnings scheduled"),
        RedFlagKind.REGULATOR to listOf("antitrust", "subpoena", "regulators probe", "opens probe", "launches probe",
            "under investigation", "opens investigation", "launches investigation"),
        RedFlagKind.RECALL to listOf("recall"),
    )

    fun of(headline: String, summary: String = ""): List<RedFlagKind> {
        val text = (headline + " " + summary).lowercase()
        return patterns.filter { (_, list) -> list.any { it in text } }.keys.toList()
    }
}

/** What the screen shows of the news, computed once per look. */
data class RadarSnapshot(
    val items: List<NewsItem> = emptyList(),
    /** Per symbol: time-weighted mood over 48 hours and how many items in 24. */
    val moods: Map<String, SymbolMood> = emptyMap(),
    val market: Double? = null,
    /** 24 hourly averages, oldest first; null where the hour had no news. */
    val timeline: List<Double?> = emptyList(),
    val topics: List<TopicCount> = emptyList(),
    val flags: List<RedFlag> = emptyList(),
    val aiRead: Int = 0,
    /** The whole market's wire: the most talked-about stocks of the last 24 hours. */
    val hot: List<HotStock> = emptyList(),
    val wireSize: Int = 0,
)

data class HotStock(val symbol: String, val mentions: Int, val mood: Double)

data class SymbolMood(val symbol: String, val mood: Double?, val count24h: Int)
data class TopicCount(val topic: Topic, val count: Int, val mood: Double)

/**
 * The wire, read continuously: every look pulls whatever is new for the
 * watchlist, scores it, tags it, and keeps a week of it. Recent items count
 * more (a six-hour half-life), and round-ups that name many companies count
 * half, so one "stocks to watch" list cannot swing a stock's mood.
 */
class NewsRadar(private val now: () -> Long) {
    private val lock = Any()
    private val items = LinkedHashMap<Long, NewsItem>()
    /** Everything else on the wire, for a day: what the whole market is talking about. */
    private val wire = LinkedHashMap<Long, NewsItem>()

    /** Whole-market items: kept a day, used to find what is hot. Returns how many were new. */
    fun ingestWire(fresh: List<NewsItem>): Int = synchronized(lock) {
        var added = 0
        for (n in fresh) if (wire.put(n.id, n) == null) added++
        val cutoff = now() - 24 * HOUR
        wire.values.removeAll { it.createdAt < cutoff }
        if (wire.size > WIRE_CAP) wire.values.sortedBy { it.createdAt }.take(wire.size - WIRE_CAP).forEach { wire.remove(it.id) }
        added
    }

    /** The stocks the whole wire mentions most in a day, round-ups left out. */
    fun hot(exclude: Set<String> = emptySet(), min: Int = 3): List<HotStock> = synchronized(lock) {
        val by = HashMap<String, MutableList<NewsItem>>()
        for (n in (wire.values + items.values).distinctBy { it.id }) {
            if (n.roundup || now() - n.createdAt > 24 * HOUR) continue
            for (s in n.symbols) if (s !in exclude) by.getOrPut(s) { ArrayList() } += n
        }
        by.filter { it.value.size >= min }
            .map { (s, list) -> HotStock(s, list.size, list.map { it.mood }.average()) }
            .sortedByDescending { it.mentions }
    }

    fun wireLatestAt(): Long? = synchronized(lock) { wire.values.maxOfOrNull { it.createdAt } }

    /** Adds what is new, replacing updated items; returns how many were new. */
    fun ingest(fresh: List<NewsItem>): Int = synchronized(lock) {
        var added = 0
        for (n in fresh) {
            val old = items[n.id]
            if (old == null) added++
            // An update keeps the AI's earlier reading unless it re-reads it.
            items[n.id] = if (old?.aiScore != null && n.aiScore == null) n.copy(aiScore = old.aiScore) else n
        }
        prune()
        added
    }

    fun restore(saved: List<NewsItem>) = synchronized(lock) { saved.forEach { items[it.id] = it }; prune() }

    fun all(): List<NewsItem> = synchronized(lock) { items.values.sortedByDescending { it.createdAt } }

    fun latestAt(): Long? = synchronized(lock) { items.values.maxOfOrNull { it.createdAt } }

    fun unscored(limit: Int): List<NewsItem> = synchronized(lock) {
        items.values.filter { it.aiScore == null }.sortedByDescending { it.createdAt }.take(limit)
    }

    fun applyScores(scores: Map<Long, Double>) = synchronized(lock) {
        for ((id, s) in scores) items[id]?.let { items[id] = it.copy(aiScore = s.coerceIn(-1.0, 1.0)) }
    }

    fun mood(symbol: String, hours: Int = 48): Double? {
        val t = now()
        var sum = 0.0
        var weights = 0.0
        for (n in all()) {
            if (symbol !in n.symbols) continue
            val age = (t - n.createdAt).coerceAtLeast(0) / HOUR.toDouble()
            if (age > hours) continue
            val w = 0.5.pow(age / HALF_LIFE_HOURS) * (if (n.roundup) 0.5 else 1.0)
            sum += w * n.mood
            weights += w
        }
        return if (weights > 0) sum / weights else null
    }

    fun count(symbol: String, hours: Int = 24): Int {
        val since = now() - hours * HOUR
        return all().count { symbol in it.symbols && it.createdAt >= since }
    }

    /** Flags still fresh enough to matter, for one symbol or all. */
    fun flags(symbol: String? = null): List<RedFlag> {
        val t = now()
        val out = ArrayList<RedFlag>()
        for (n in all()) {
            if (n.roundup) continue
            for (k in n.flags) {
                if (t - n.createdAt > k.hours * HOUR) continue
                for (s in n.symbols) if (symbol == null || s == symbol) out += RedFlag(k, s, n.createdAt, n.headline)
            }
        }
        return out.distinctBy { Triple(it.kind, it.symbol, it.headline) }
    }

    fun snapshot(symbols: List<String>): RadarSnapshot {
        val t = now()
        val all = all()
        val day = all.filter { t - it.createdAt <= 24 * HOUR }
        val timeline = (23 downTo 0).map { h ->
            val from = t - (h + 1) * HOUR
            val to = t - h * HOUR
            all.filter { it.createdAt in from until to }.map { it.mood }.takeIf { it.isNotEmpty() }?.average()
        }
        val marketItems = all.filter { t - it.createdAt <= 12 * HOUR }
        val market = if (marketItems.isEmpty()) null else {
            var s = 0.0; var w = 0.0
            for (n in marketItems) {
                val ww = 0.5.pow(((t - n.createdAt) / HOUR.toDouble()) / HALF_LIFE_HOURS)
                s += ww * n.mood; w += ww
            }
            s / w
        }
        val topics = Topic.entries.mapNotNull { topic ->
            val with = day.filter { topic in it.topics }
            if (with.isEmpty()) null else TopicCount(topic, with.size, with.map { it.mood }.average())
        }.sortedByDescending { it.count }
        return RadarSnapshot(
            items = all.take(SHOWN),
            moods = symbols.associateWith { SymbolMood(it, mood(it), count(it)) },
            market = market,
            timeline = timeline,
            topics = topics,
            flags = flags(),
            aiRead = all.count { it.aiScore != null },
            hot = hot(symbols.toSet()).take(10),
            wireSize = synchronized(lock) { wire.size },
        )
    }

    private fun prune() {
        val cutoff = now() - KEEP_DAYS * 24 * HOUR
        items.values.removeAll { it.createdAt < cutoff }
        if (items.size > CAP) {
            items.values.sortedBy { it.createdAt }.take(items.size - CAP).forEach { items.remove(it.id) }
        }
    }

    companion object {
        const val HOUR = 3_600_000L
        const val HALF_LIFE_HOURS = 6.0
        const val KEEP_DAYS = 7
        const val CAP = 400
        const val WIRE_CAP = 1500
        const val SHOWN = 60

        /** Below this a stock's mood counts as bad news. */
        const val BAD_MOOD = -0.35
        const val GOOD_MOOD = 0.15
    }
}

/** −0.18 → "−0.18"; for logs and the AI's brief. */
fun Double.moodText(): String = (if (this >= 0) "+" else "−") + String.format(java.util.Locale.US, "%.2f", abs(this))
