package com.bofstudios.moneytree.engine

import com.bofstudios.moneytree.research.SecEdgar
import com.bofstudios.moneytree.service.UpdateCheck
import kotlinx.coroutines.test.runTest
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class AltDataTest {
    private val day = 86_400_000L

    @Test fun theNextResultsDateFollowsTheQuarterlyRhythm() {
        val last = 200 * day
        val e = CompanyEvents("AAA", emptyList(), 0, listOf(last, last - 91 * day, last - 182 * day, last - 273 * day), 0)
        assertEquals(last + 91 * day, e.nextResults())
        // No steady rhythm, no guess.
        assertNull(CompanyEvents("AAA", emptyList(), 0, listOf(last, last - 10 * day, last - 20 * day), 0).nextResults())
        assertNull(CompanyEvents("AAA", emptyList(), 0, listOf(last), 0).nextResults())
    }

    @Test fun attentionIsTheLastTwoDaysOverTheUsual() {
        assertEquals(3.0, attentionRatio(List(28) { 100 } + listOf(300, 300))!!, 1e-9)
        assertNull(attentionRatio(listOf(1, 2, 3)))
    }

    @Test fun eightKsBecomeNewsWithTheRightFlags() {
        val bankrupt = EightK.asNews(FilingEvent("AAA", listOf("1.03", "9.01"), 5L, "0001-26-000001"), "Aaa Corp")
        assertTrue(bankrupt.id < 0)
        assertEquals(listOf(RedFlagKind.BANKRUPTCY), bankrupt.flags)
        assertTrue(bankrupt.headline.contains("bankruptcy"))
        val results = EightK.asNews(FilingEvent("AAA", listOf("2.02", "9.01"), 5L, "0001-26-000002"), "Aaa Corp")
        assertTrue(results.flags.isEmpty())
        assertTrue(Topic.EARNINGS in results.topics)
        assertEquals(listOf(RedFlagKind.ACCOUNTING), EightK.flags(listOf("4.02")))
    }

    @Test fun theSecFilingIndexIsReadIntoEvents() {
        val now = java.time.Instant.parse("2026-10-02T12:00:00Z").toEpochMilli()
        val j = JSONObject("""{"filings":{"recent":{
            "form":["4","8-K","4","8-K","10-Q","8-K","8-K","8-K"],
            "filingDate":["2026-10-01","2026-09-20","2026-08-01","2026-07-30","2026-07-31","2026-04-30","2026-01-29","2025-10-30"],
            "acceptanceDateTime":["2026-10-01T20:00:00.000Z","2026-09-20T20:00:00.000Z","2026-08-01T20:00:00.000Z","2026-07-30T20:30:00.000Z","","2026-04-30T20:30:00.000Z","2026-01-29T21:30:00.000Z","2025-10-30T20:30:00.000Z"],
            "items":["","5.02","","2.02,9.01","","2.02,9.01","2.02,9.01","2.02,9.01"],
            "accessionNumber":["a","b","c","d","e","f","g","h"]}}}""")
        val e = SecEdgar.parseEvents("AAA", j, now)!!
        assertEquals(1, e.insiderFilings30d) // the August one is older than 30 days
        assertEquals(listOf("5.02"), e.events.first().items)
        assertEquals(4, e.resultsDates.size)
        val next = assertNotNull(e.nextResults()).let { e.nextResults()!! }
        assertTrue(java.time.Instant.ofEpochMilli(next).toString().startsWith("2026-10-2"))
    }

    @Test fun theWholeWireShowsWhatIsHot() {
        val radar = NewsRadar { 100 * day }
        val items = (1..5).map { NewsItem(it.toLong(), "XYZ beats estimates", "", "wire", listOf("XYZ"), 100 * day - it * 60_000L) } +
            NewsItem(9, "Five stocks to watch", "", "wire", listOf("A", "B", "C", "D", "E"), 100 * day) +
            (10..12).map { NewsItem(it.toLong(), "AAA news", "", "wire", listOf("AAA"), 100 * day) }
        radar.ingestWire(items)
        val hot = radar.hot(exclude = setOf("AAA"))
        assertEquals(listOf("XYZ"), hot.map { it.symbol })
        assertEquals(5, hot.single().mentions)
        assertTrue(hot.single().mood > 0)
    }

    @Test fun updatesCompareVersionsNumerically() {
        assertTrue(UpdateCheck.isNewer("4.0.0", "3.0.0"))
        assertTrue(UpdateCheck.isNewer("3.10.0", "3.9.1"))
        assertFalse(UpdateCheck.isNewer("3.0.0", "3.0.0"))
        assertFalse(UpdateCheck.isNewer("2.9", "3.0.0"))
    }

    // ------------------------------------------------------------- discovery

    @Test fun aHotStockThatPassesTheChecksIsWatchedForADayOrThree() = runTest {
        val clock = 1_000_000_000_000L
        val broker = DiscoveryBroker(clock)
        val source = object : FilingsSource { override suspend fun filings(symbol: String) = Companies.great(symbol) }
        val brain = Brain(MemoryBrainStore(), filings = source, now = { clock })
        brain.radar.ingestWire((1..6).map { NewsItem(it.toLong(), "HOT wins big contract", "", "wire", listOf("HOT"), clock - it * 60_000L) } +
            (7..12).map { NewsItem(it.toLong(), "OTC soars", "", "wire", listOf("OTC"), clock - it * 60_000L) })
        val s = TradingSettings(watchlist = listOf("AAA"))
        val out = brain.refresh(listOf("AAA"), broker, MemoryMonitor(), Words(false), s)
        assertEquals(listOf("HOT"), out.discovered.map { it.symbol })
        assertEquals(listOf("HOT"), brain.discoveredSymbols(s))
        assertTrue(brain.discoveredSymbols(s.copy(discover = false)).isEmpty())
    }
}

/** A broker that knows two hot stocks: one listed and liquid, one over the counter. */
class DiscoveryBroker(private val clock: Long) : FakeBroker() {
    override suspend fun asset(symbol: String) = when (symbol) {
        "HOT" -> AssetInfo("HOT", "Hot Inc", "NASDAQ", tradable = true, fractionable = true, active = true)
        "OTC" -> AssetInfo("OTC", "Otc Co", "OTC", tradable = false, fractionable = false, active = true)
        else -> null
    }
    override suspend fun latestPrice(symbol: String) = if (symbol == "HOT") 50.0 else 2.0
    override suspend fun bars(symbol: String, timeframe: Timeframe, limit: Int) =
        if (timeframe == Timeframe.D1) Companies.daily((0 until 260).map { 40.0 + it * 0.05 }) else emptyList()
}
