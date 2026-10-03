package com.bofstudios.moneytree.engine

import kotlin.math.abs

/** One 8-K a company filed with the SEC: a material event, by item number. */
data class FilingEvent(val symbol: String, val items: List<String>, val filedAt: Long, val accession: String)

/** What the SEC's filing index says about a company lately. */
data class CompanyEvents(
    val symbol: String,
    /** 8-Ks from the last 90 days, newest first. */
    val events: List<FilingEvent>,
    /** Form 4s (insider trades) filed in the last 30 days — activity, not direction. */
    val insiderFilings30d: Int,
    /** When its results have come out before (8-K item 2.02), newest first. */
    val resultsDates: List<Long>,
    val fetchedAt: Long,
) {
    /**
     * The next results date, estimated from the rhythm of past ones: the
     * average gap between the last few 8-K item 2.02 filings, added to the
     * latest. Null without a steady quarterly rhythm.
     */
    fun nextResults(): Long? {
        if (resultsDates.size < 3) return null
        val d = resultsDates.sortedDescending().take(5)
        val gaps = d.zipWithNext { a, b -> a - b }
        val avg = gaps.average()
        if (avg < 60 * DAY || avg > 120 * DAY) return null
        return (d.first() + avg).toLong()
    }

    companion object { const val DAY = 86_400_000L }
}

/** The SEC's filing index for a company: 8-Ks, Form 4 counts, results dates. */
interface EventsSource {
    suspend fun events(symbol: String): CompanyEvents?
}

/** Daily Wikipedia page views for a company: how much attention it gets. */
interface AttentionSource {
    /** Oldest first; null when the company's article cannot be found. */
    suspend fun views(symbol: String, name: String): List<Int>?
}

/** A stock the bot found in the news and added to what it watches, for a while. */
data class Discovery(val symbol: String, val name: String, val mentions: Int, val decision: Decision, val score: Double, val at: Long)

/** Alt data about one stock, for the screen and the AI. */
data class AltSignals(
    val symbol: String,
    /** Recent views over the usual: 1 = normal, 3 = three times the usual attention. */
    val attention: Double? = null,
    val insiderFilings30d: Int? = null,
    val lastEvent: FilingEvent? = null,
    val nextResults: Long? = null,
)

object EightK {
    /** What an 8-K item means, in plain English (the screen translates the important ones). */
    val ITEMS = mapOf(
        "1.01" to "a material agreement", "1.02" to "an agreement ended", "1.03" to "bankruptcy",
        "1.05" to "a cybersecurity incident", "2.01" to "an acquisition or sale completed",
        "2.02" to "results of operations (earnings)", "2.03" to "new debt", "2.05" to "restructuring costs",
        "2.06" to "an impairment", "3.01" to "a delisting notice", "3.02" to "unregistered share sales",
        "3.03" to "changed shareholder rights", "4.01" to "an auditor change", "4.02" to "past financials no longer reliable",
        "5.01" to "a change of control", "5.02" to "a director or officer change", "5.03" to "amended bylaws",
        "5.07" to "a shareholder vote", "7.01" to "a Reg FD disclosure", "8.01" to "other events",
    )

    fun flags(items: List<String>): List<RedFlagKind> = items.mapNotNull {
        when (it) {
            "1.03" -> RedFlagKind.BANKRUPTCY
            "3.01" -> RedFlagKind.DELISTING
            "4.02" -> RedFlagKind.ACCOUNTING
            "3.02" -> RedFlagKind.OFFERING
            "1.05" -> RedFlagKind.REGULATOR
            else -> null
        }
    }.distinct()

    fun topics(items: List<String>): Set<Topic> = items.mapNotNull {
        when (it) {
            "2.02" -> Topic.EARNINGS
            "5.02", "5.01" -> Topic.LEADERSHIP
            "1.01", "1.02", "2.01" -> Topic.DEALS
            "2.03", "3.02", "3.03" -> Topic.CAPITAL
            "1.03", "3.01", "4.01", "4.02" -> Topic.REGULATION
            else -> null
        }
    }.toSet()

    /** An 8-K, as an item on the news radar. Ids are negative so they never collide with the wire's. */
    fun asNews(e: FilingEvent, name: String): NewsItem {
        val what = e.items.filter { it != "9.01" }.mapNotNull { ITEMS[it] }.ifEmpty { listOf("a filing") }
        val headline = "SEC 8-K: $name reports ${what.joinToString(", ")}"
        val flags = flags(e.items)
        return NewsItem(
            id = -abs(e.accession.filter { it.isDigit() }.takeLast(15).toLongOrNull() ?: e.accession.hashCode().toLong()) - 1,
            headline = headline, summary = "", source = "SEC EDGAR", symbols = listOf(e.symbol), createdAt = e.filedAt,
            url = "", score = if (flags.any { it.severe }) -0.8 else 0.0, topics = topics(e.items), flags = flags,
        )
    }
}

/** Recent attention over the usual: the last two days against the 28 before them. */
fun attentionRatio(views: List<Int>): Double? {
    if (views.size < 10) return null
    val recent = views.takeLast(2).average()
    val base = views.dropLast(2).takeLast(28).average()
    return if (base > 0) recent / base else null
}
