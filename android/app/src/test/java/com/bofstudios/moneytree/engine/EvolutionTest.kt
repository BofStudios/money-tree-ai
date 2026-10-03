package com.bofstudios.moneytree.engine

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class EvolutionTest {
    private fun bar(t: Long, o: Double, h: Double, l: Double, c: Double) = Bar(t, o, h, l, c, 1.0)

    /**
     * A market where every buy after a slow turn up is followed by a huge
     * jump: whatever the stop, the target is hit. So the strategy aiming for
     * the biggest target provably earns the most per trade.
     */
    private fun jumpy(cycles: Int = 22): List<Bar> {
        val out = ArrayList<Bar>()
        var p = 100.0
        var t = 0L
        fun add(next: Double) {
            out += bar(t, p, maxOf(p, next) * 1.001, minOf(p, next) * 0.999, next)
            p = next; t += 900_000L
        }
        // Zig-zags keep RSI moderate (about 37 falling, 63 rising), as real candles do.
        repeat(cycles) {
            repeat(30) { add(p - 0.6); add(p + 0.35) }
            repeat(25) { add(p + 0.6); add(p - 0.35) }
            add(p * 1.45)
            repeat(10) { add(p * 0.965) }
        }
        return out
    }

    // ---------------------------------------------------------------- replay

    @Test fun aReplayFindsTheTargetsInAJumpyMarket() {
        val g = Genome(fast = 10, slow = 30, entryRsi = 80.0, exitRsi = 90.0, atrMultiple = 1.5, rewardRisk = 2.0)
        val s = Series("X", jumpy(cycles = 6))
        val r = Replay.run(g, s, 0, s.size, 0.8, 6.0)
        assertTrue(r.trades >= 3)
        assertTrue("expectancy ${r.expectancy}", r.expectancy > 1.0)
        assertTrue(r.wins > 0)
    }

    @Test fun aGapThroughTheStopCostsMoreThanOneR() {
        val bars = ArrayList<Bar>()
        var p = 100.0
        var t = 0L
        for (i in 0 until 120) { val n = p - 0.3; bars += bar(t++, p, p + 0.1, n - 0.1, n); p = n }
        // Rise until the 5-bar average crosses the 20-bar one: that candle is the entry.
        while (true) {
            val n = p + 0.3; bars += bar(t++, p, n + 0.1, p - 0.1, n); p = n
            val c = DoubleArray(bars.size) { bars[it].close }
            val f = Indicators.ema(c, 5); val sl = Indicators.ema(c, 20); val k = c.size - 1
            if (f[k - 1] <= sl[k - 1] && f[k] > sl[k]) break
        }
        // The next candle opens 10% lower, far through any stop.
        bars += bar(t, p * 0.9, p * 0.9, p * 0.88, p * 0.89)
        val s = Series("X", bars)
        val r = Replay.run(Genome(fast = 5, slow = 20, entryRsi = 80.0, exitRsi = 99.0, atrMultiple = 1.0, rewardRisk = 4.0).clamped(), s, 0, s.size, 0.8, 6.0)
        assertEquals(1, r.trades)
        assertTrue("gap loss ${r.sumR}", r.sumR < -1.0 - Replay.COST_R)
    }

    @Test fun genesStayInsideTheirBounds() {
        val g = Genome(fast = 1, slow = 2, entryRsi = 10.0, exitRsi = 200.0, atrMultiple = 99.0, rewardRisk = 0.1).clamped()
        assertEquals(5, g.fast)
        assertTrue(g.slow >= g.fast + 6 && g.slow >= 20)
        assertEquals(50.0, g.entryRsi, 0.0)
        assertEquals(90.0, g.exitRsi, 0.0)
        assertEquals(3.0, g.atrMultiple, 0.0)
        assertEquals(1.2, g.rewardRisk, 0.0)
        assertEquals(Genome.DEFAULT.strategy().fast, EmaRsiStrategy().fast)
    }

    // ------------------------------------------------------------- evolution

    @Test fun itAdoptsWhatProvesBetterOnUnseenDataAndSaysWhy() {
        val evo = Evolution(MemoryBrainStore(), now = { 10_000_000_000L }, seed = 42)
        evo.setData(listOf(Series("A", jumpy(40)), Series("B", jumpy(36)), Series("C", jumpy(30))), 0.8, 6.0)
        var promoted: Promotion? = null
        repeat(80) { evo.step()?.let { promoted = it } }
        val p = assertNotNull(promoted).let { promoted!! }
        assertFalse(p.rollback)
        assertTrue("after ${p.after} before ${p.before}", p.after > p.before)
        assertTrue(evo.champion.rewardRisk > Genome.DEFAULT.rewardRisk)
        assertEquals(p.version, evo.version)
        assertTrue(evo.snapshot().tested >= 80L * (Evolution.POPULATION - Evolution.IMMIGRANTS))
    }

    @Test fun atMostOneChangePerHalfHour() {
        var clock = 10_000_000_000L
        val evo = Evolution(MemoryBrainStore(), now = { clock }, seed = 7)
        evo.setData(listOf(Series("A", jumpy())), 0.8, 6.0)
        val promotions = ArrayList<Promotion>()
        repeat(200) { evo.step()?.let { promotions += it } }
        assertTrue(promotions.size <= 1)
        clock += Evolution.MIN_GAP
        repeat(200) { evo.step()?.let { promotions += it } }
        assertTrue(promotions.size <= 2)
    }

    @Test fun noDataNoTraining() {
        val evo = Evolution(MemoryBrainStore(), seed = 1)
        assertFalse(evo.ready)
        assertNull(evo.step())
        assertEquals(Genome.DEFAULT, evo.champion)
    }

    @Test fun theChampionSurvivesARestart() {
        val store = MemoryBrainStore()
        val evo = Evolution(store, now = { 10_000_000_000L }, seed = 42)
        evo.setData(listOf(Series("A", jumpy(40)), Series("B", jumpy(36)), Series("C", jumpy(30))), 0.8, 6.0)
        repeat(80) { evo.step() }
        assertTrue(evo.version > 1)
        val again = Evolution(store, seed = 3)
        assertEquals(evo.champion, again.champion)
        assertEquals(evo.version, again.version)
        assertEquals(evo.snapshot().history.size, again.snapshot().history.size)
    }

    @Test fun aChampionThatFellBehindIsRolledBack() {
        val store = MemoryBrainStore()
        // A saved champion that never trades on this market (entries need RSI under 50 at a turn up).
        val bad = Genome(fast = 20, slow = 60, entryRsi = 50.0, exitRsi = 60.0, atrMultiple = 0.8, rewardRisk = 1.2)
        store.write("evolution", JSONObject().put("champion", JSONObject().put("f", bad.fast).put("s", bad.slow)
            .put("e", bad.entryRsi).put("x", bad.exitRsi).put("a", bad.atrMultiple).put("r", bad.rewardRisk)).put("version", 5).toString())
        val evo = Evolution(store, now = { 10_000_000_000L }, seed = 9)
        assertEquals(bad, evo.champion)
        val rollback = evo.setData(listOf(Series("A", jumpy())), 0.8, 6.0)
        assertNotNull(rollback)
        assertTrue(rollback!!.rollback)
        assertEquals(Genome.DEFAULT, evo.champion)
        assertEquals(6, evo.version)
    }

    @Test fun resetGoesBackToTheOriginal() {
        val evo = Evolution(MemoryBrainStore(), now = { 10_000_000_000L }, seed = 42)
        evo.setData(listOf(Series("A", jumpy(40)), Series("B", jumpy(36)), Series("C", jumpy(30))), 0.8, 6.0)
        repeat(80) { evo.step() }
        assertTrue(evo.champion != Genome.DEFAULT)
        evo.reset()
        assertEquals(Genome.DEFAULT, evo.champion)
        assertTrue(evo.snapshot().history.first().rollback)
    }
}
