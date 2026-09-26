package com.bofstudios.moneytree.engine

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** Shared fixtures: synthetic candles shaped to produce a known crossover. */
internal object Candles {
    fun of(closes: List<Double>): List<Bar> =
        closes.mapIndexed { i, c -> Bar(i * 900_000L, c, c * 1.002, c * 0.998, c, 1_000.0) }

    /** Falls for a long while, then turns up, so the fast EMA crosses above the
     *  slow one on the very last bar. The slopes are chosen (checked against the
     *  Python strategy) so RSI is ~67 at the cross: a buy, not an overbought skip. */
    fun crossUpOnLastBar(): List<Bar> {
        val strategy = EmaRsiStrategy()
        val base = (0 until 100).map { 150.0 - it * 0.5 }.toMutableList()
        // Walk the price up one bar at a time until the crossover happens.
        var next = base.last()
        while (true) {
            next += 0.3
            val trial = base + next
            val closes = trial.toDoubleArray()
            val f = Indicators.ema(closes, 12)
            val s = Indicators.ema(closes, 26)
            val n = closes.size - 1
            base.add(next)
            if (f[n - 1] <= s[n - 1] && f[n] > s[n]) break
            check(base.size < 400)
        }
        check(strategy.onBars(of(base), holding = false).action == Action.BUY)
        return of(base)
    }

    fun crossDownOnLastBar(): List<Bar> {
        val base = (0 until 100).map { 100.0 + it * 0.5 }.toMutableList()
        var next = base.last()
        while (true) {
            next -= 0.3
            val closes = (base + next).toDoubleArray()
            val f = Indicators.ema(closes, 12)
            val s = Indicators.ema(closes, 26)
            val n = closes.size - 1
            base.add(next)
            if (f[n - 1] >= s[n - 1] && f[n] < s[n]) break
            check(base.size < 400)
        }
        return of(base)
    }
}

class StrategyTest {
    private val strategy = EmaRsiStrategy()

    @Test fun tooFewBarsIsWarmingUp() {
        val signal = strategy.onBars(Candles.of(List(20) { 100.0 }), holding = false)
        assertEquals(Action.HOLD, signal.action)
        assertEquals("warming up", signal.reason)
    }

    @Test fun anUpwardCrossoverBuys() {
        val signal = strategy.onBars(Candles.crossUpOnLastBar(), holding = false)
        assertEquals(Action.BUY, signal.action)
        assertTrue(signal.reason.startsWith("EMA12 crossed above EMA26"))
    }

    @Test fun theSameCrossoverDoesNotBuyAgainWhileHolding() {
        val signal = strategy.onBars(Candles.crossUpOnLastBar(), holding = true)
        assertTrue(signal.action != Action.BUY)
    }

    @Test fun aDownwardCrossoverSellsWhenHolding() {
        val signal = strategy.onBars(Candles.crossDownOnLastBar(), holding = true)
        assertEquals(Action.CLOSE, signal.action)
    }

    @Test fun aDownwardCrossoverDoesNothingWhenFlat() {
        assertEquals(Action.HOLD, strategy.onBars(Candles.crossDownOnLastBar(), holding = false).action)
    }
}

class RiskTest {
    private val risk = Risk()

    @Test fun stopDistanceScalesWithAtrAndIsClamped() {
        assertEquals(1.5, risk.stopDistancePct(100.0, 1.0), 1e-9)   // 1.0 * 1.5 / 100
        assertEquals(0.8, risk.stopDistancePct(100.0, 0.1), 1e-9)   // floor
        assertEquals(6.0, risk.stopDistancePct(100.0, 10.0), 1e-9)  // ceiling
    }

    @Test fun sizingRisksHalfAPercentOfEquity() {
        // $100k equity, 0.5% risk = $500; 2% stop on $100 = $2/share -> 250 shares
        // = $25k, over the 20% cap ($20k) -> 200 shares.
        assertEquals(200, risk.shares(100_000.0, 100_000.0, 100.0, 2.0))
        // A wider stop means fewer shares, not more money at risk.
        assertEquals(83, risk.shares(100_000.0, 100_000.0, 100.0, 6.0))
    }

    @Test fun sharesAreWholeBecauseBracketOrdersRequireIt() {
        // $1,000 account, $300 stock: the risk rule wants ~0.55 shares.
        assertEquals(0, risk.shares(1_000.0, 1_000.0, 300.0, 3.0))
        assertNull(risk.plan("NVDA", "x", 300.0, 6.0, 1_000.0, 1_000.0))
    }

    @Test fun cashAvailableCapsTheSize() {
        assertEquals(49, risk.shares(100_000.0, 5_000.0, 100.0, 2.0))
    }

    @Test fun targetIsTwoStopDistancesAway() {
        val e = risk.plan("AAPL", "x", 100.0, 2.0, 100_000.0, 100_000.0)
        assertNotNull(e)
        e!!
        assertEquals(97.0, e.stop, 1e-9)    // 2.0 * 1.5 = 3% stop
        assertEquals(106.0, e.target, 1e-9) // 2 x 3%
    }

    @Test fun trailingStartsOnlyAfterTheActivationGain() {
        assertNull(risk.trailingStop(100.0, 97.0, 101.5))           // up 1.5%, not yet
        assertEquals(101.97, risk.trailingStop(100.0, 97.0, 103.0)!!, 1e-9)
    }

    @Test fun trailingNeverLowersTheStop() {
        assertNull(risk.trailingStop(100.0, 102.5, 103.0))
    }

    @Test fun dailyLimitIsMeasuredFromYesterdaysClose() {
        assertTrue(risk.dailyLimitHit(94_900.0, 100_000.0))
        assertTrue(!risk.dailyLimitHit(95_100.0, 100_000.0))
    }
}
