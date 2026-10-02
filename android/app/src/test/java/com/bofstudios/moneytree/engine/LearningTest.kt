package com.bofstudios.moneytree.engine

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class LearningTest {
    private fun features(rsi: Double = 50.0, news: Double? = null, symbol: String = "AAA") =
        Features(symbol, Decision.WAIT, news, rsi, 0.5, 120, dailyUp = true)

    private fun bar(t: Long, low: Double, high: Double, close: Double) = Bar(t, close, high, low, close, 1.0)

    private fun shadow(symbol: String = "AAA") =
        ShadowTrade("s1", symbol, openedAt = 10, entry = 100.0, stop = 98.0, target = 104.0, features = features(symbol = symbol))

    // ------------------------------------------------------------- shadows

    @Test fun aShadowTradeClosesAtWhicheverCameFirst() {
        val book = ShadowBook(EmaRsiStrategy())
        book.open(shadow())
        // The candle the signal fired on (t=10) is not counted; t=20 touches the target.
        val closed = book.resolve(mapOf("AAA" to listOf(bar(10, 90.0, 110.0, 100.0), bar(20, 99.0, 104.5, 104.0))), rewardRisk = 2.0)
        assertEquals(1, closed.size)
        assertEquals(2.0, closed[0].r!!, 1e-9)
        assertEquals("take-profit", closed[0].exit)
    }

    @Test fun aCandleThatTouchesBothCountsAsTheStop() {
        val book = ShadowBook(EmaRsiStrategy())
        book.open(shadow())
        val closed = book.resolve(mapOf("AAA" to listOf(bar(20, 97.0, 105.0, 101.0))), rewardRisk = 2.0)
        assertEquals(-1.0, closed.single().r!!, 1e-9)
    }

    @Test fun aShadowTradeTimesOut() {
        val book = ShadowBook(EmaRsiStrategy())
        book.open(shadow())
        val bars = (1..ShadowBook.MAX_BARS).map { bar(10L + it, 99.5, 100.5, 101.0) }
        val closed = book.resolve(mapOf("AAA" to bars), rewardRisk = 2.0).single()
        assertEquals("time", closed.exit)
        assertEquals(0.5, closed.r!!, 1e-9) // (101 − 100) / (100 − 98)
    }

    @Test fun oneOpenShadowPerSymbolAndOnePerCandle() {
        val book = ShadowBook(EmaRsiStrategy())
        assertTrue(book.open(shadow()))
        assertFalse(book.open(shadow().copy(id = "s2", openedAt = 50)))
        assertTrue(book.open(shadow("BBB")))
    }

    // ------------------------------------------------------------- learner

    @Test fun aFewLossesTeachNothing() {
        val l = Learner()
        repeat(4) { l.add(Sample(features(rsi = 65.0), -1.0, real = false, at = 0)) }
        val v = l.verdict(features(rsi = 65.0))
        assertFalse(v.blocked)
        assertTrue(l.rules().isEmpty())
    }

    @Test fun aKindThatKeepsLosingBecomesARule() {
        val l = Learner()
        val learned = ArrayList<BucketStats>()
        repeat(12) { i -> learned += l.add(Sample(features(rsi = 65.0), if (i % 4 == 0) 2.0 else -1.0, real = false, at = 0)) }
        // 3 wins (+6R) and 9 losses (−9R) over 12: −0.25R raw, shrunk to −0.17R… not yet.
        assertTrue(l.rules().none { it.bucket == Bucket(FeatureKey.RSI, "60+") })
        repeat(6) { learned += l.add(Sample(features(rsi = 65.0), -1.0, real = false, at = 0)) }
        val rule = l.rules().first { it.bucket == Bucket(FeatureKey.RSI, "60+") }
        assertTrue(rule.shrunk <= Learner.BLOCK_AT)
        assertTrue(learned.any { it.bucket == rule.bucket })
        val v = l.verdict(features(rsi = 65.0))
        assertTrue(v.blocked)
        assertEquals(0.5, v.size, 1e-9)
        // A different kind of signal is not punished for it.
        val other = Learner().apply { repeat(20) { add(Sample(features(rsi = 40.0, symbol = "ZZZ"), 1.0, false, 0)) } }
        assertFalse(other.verdict(features(rsi = 40.0, symbol = "ZZZ")).blocked)
    }

    @Test fun realTradesWeighDouble() {
        val l = Learner()
        l.add(Sample(features(), -1.0, real = true, at = 0))
        assertEquals(2.0, l.stats().first { it.bucket.key == FeatureKey.RSI }.n, 1e-9)
    }

    @Test fun learningCanShrinkButNeverGrow() {
        val l = Learner()
        repeat(30) { l.add(Sample(features(), 2.0, false, 0)) }
        val v = l.verdict(features())
        assertFalse(v.blocked)
        assertEquals(1.0, v.size, 1e-9)
        assertTrue(v.edge!! > 0)
    }

    @Test fun bucketsSplitTheSessionAndTheNews() {
        val b = Features("AAA", Decision.BUY_ZONE, -0.4, 72.0, 3.0, 10, dailyUp = false).buckets().associate { it.key to it.value }
        assertEquals("OPEN", b[FeatureKey.SESSION])
        assertEquals("BAD", b[FeatureKey.NEWS])
        assertEquals("60+", b[FeatureKey.RSI])
        assertEquals("FAR", b[FeatureKey.STRETCH])
        assertEquals("DOWN", b[FeatureKey.DAILY_TREND])
    }

    @Test fun theSessionClockIsNewYorkTime() {
        // 2026-10-01 13:30 UTC is 09:30 in New York (EDT): minute zero.
        assertEquals(0, minuteOfSession(1_790_861_400_000L))
        assertEquals(null, minuteOfSession(1_790_861_400_000L - 60_000L))
    }
}
