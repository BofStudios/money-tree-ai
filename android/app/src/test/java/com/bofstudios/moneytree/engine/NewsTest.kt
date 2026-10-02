package com.bofstudios.moneytree.engine

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class NewsTest {
    private val hour = 3_600_000L
    private var clock = 100 * hour
    private fun item(id: Long, headline: String, vararg symbols: String, hoursAgo: Double = 0.0, ai: Double? = null) =
        NewsItem(id, headline, "", "wire", symbols.toList(), clock - (hoursAgo * hour).toLong(), aiScore = ai)

    // ------------------------------------------------------------- the words

    @Test fun goodAndBadHeadlinesScoreTheRightWay() {
        assertTrue(Sentiment.score("Apple beats estimates, shares surge to a record") > 0.5)
        assertTrue(Sentiment.score("Tesla misses on deliveries, stock plunges") < -0.5)
        assertEquals(0.0, Sentiment.score("Microsoft to hold annual meeting on Tuesday"), 1e-9)
    }

    @Test fun aNegationFlipsTheNextWords() {
        assertTrue(Sentiment.score("Regulators approved the merger") > 0)
        assertTrue(Sentiment.score("Regulators have not approved the merger") < 0)
    }

    @Test fun topicsMatchWholeWordsOnly() {
        assertTrue(Topic.AI_CHIPS in Topics.of("Nvidia's new chips sell out"))
        assertFalse(Topic.AI_CHIPS in Topics.of("Chipotle raises prices"))
        assertTrue(Topic.EARNINGS in Topics.of("Q3 earnings beat; guidance raised"))
    }

    @Test fun redFlagsAreSpecific() {
        assertTrue(RedFlagKind.OFFERING in RedFlags.of("XYZ prices \$500 million public offering"))
        assertTrue(RedFlagKind.EARNINGS_SOON in RedFlags.of("Apple earnings preview: what to expect"))
        // Selling fraud-detection software is not an allegation of fraud.
        assertFalse(RedFlagKind.FRAUD in RedFlags.of("Visa launches AI fraud detection for banks"))
        assertTrue(RedFlagKind.FRAUD in RedFlags.of("Company accused of fraud by short seller"))
    }

    // ------------------------------------------------------------- the radar

    @Test fun recentNewsCountsMoreThanOld() {
        val radar = NewsRadar { clock }
        radar.ingest(listOf(
            item(1, "AAA beats estimates, shares surge", "AAA", hoursAgo = 30.0),
            item(2, "AAA plunges after guidance miss", "AAA", hoursAgo = 0.5),
        ))
        assertTrue(radar.mood("AAA")!! < 0)
        assertNull(radar.mood("BBB"))
    }

    @Test fun anAiScoreOverridesTheWordListAndSurvivesUpdates() {
        val radar = NewsRadar { clock }
        radar.ingest(listOf(item(1, "AAA holds event", "AAA")))
        radar.applyScores(mapOf(1L to 0.8))
        assertEquals(0.8, radar.mood("AAA")!!, 1e-9)
        // The wire sends the same story again (an update): it is not new, and keeps the AI's reading.
        assertEquals(0, radar.ingest(listOf(item(1, "AAA holds event (updated)", "AAA"))))
        assertEquals(0.8, radar.all().single().mood, 1e-9)
        assertTrue(radar.unscored(10).isEmpty())
    }

    @Test fun flagsExpireAndRoundupsRaiseNone() {
        val radar = NewsRadar { clock }
        radar.ingest(listOf(
            item(1, "AAA earnings preview: what to expect", "AAA", hoursAgo = 2.0),
            item(2, "BBB prices secondary offering", "BBB", hoursAgo = 100.0),
            item(3, "Five stocks with a public offering this week", "C1", "C2", "C3", "C4", "C5"),
        ))
        assertEquals(listOf(RedFlagKind.EARNINGS_SOON), radar.flags("AAA").map { it.kind })
        assertTrue(radar.flags("BBB").isEmpty()) // 100 hours old: past its 72
        assertTrue(radar.flags("C1").isEmpty())
        clock += 40 * hour
        assertTrue(radar.flags("AAA").isEmpty()) // earnings flags last 36 hours
    }

    @Test fun theSnapshotHasAMoodTimelineAndTopics() {
        val radar = NewsRadar { clock }
        radar.ingest(listOf(
            item(1, "AAA beats estimates on strong cloud demand", "AAA", hoursAgo = 1.5),
            item(2, "BBB earnings disappoint", "BBB", hoursAgo = 0.2),
        ))
        val snap = radar.snapshot(listOf("AAA", "BBB", "CCC"))
        assertEquals(24, snap.timeline.size)
        assertNotNull(snap.timeline.last())
        assertNotNull(snap.market)
        assertEquals(Topic.EARNINGS, snap.topics.first().topic)
        assertEquals(0, snap.moods.getValue("CCC").count24h)
    }

    @Test fun aWeekOfNewsIsKeptAndNoMore() {
        val radar = NewsRadar { clock }
        radar.ingest(listOf(item(1, "old", "AAA", hoursAgo = 8 * 24.0), item(2, "new", "AAA")))
        assertEquals(listOf(2L), radar.all().map { it.id })
    }
}
