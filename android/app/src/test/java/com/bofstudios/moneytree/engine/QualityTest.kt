package com.bofstudios.moneytree.engine

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** Companies built by hand, so each verdict can be traced to the figure that caused it. */
internal object Companies {
    /** Growing, very profitable, buying back shares, little debt. Worth roughly $100 a share. */
    fun great(symbol: String = "GRT", currency: String = "USD", foreign: Boolean = false) = Filings(
        symbol, "Great Co", currency, foreign, fund = false, fetchedAt = 0L,
        years = (0 until 6).map { i ->
            val k = 1.08.let { g -> Math.pow(g, i.toDouble()) }
            FiscalYear(
                end = "${2020 + i}-12-31", revenue = 100e9 * k, netIncome = 25e9 * k, grossProfit = 60e9 * k,
                operatingIncome = 32e9 * k, equity = 80e9, debt = 20e9, operatingCashFlow = 30e9 * k, capex = 5e9 * k,
                shares = 5e9 * (1 - 0.01 * i), interest = 1e9, cash = 30e9,
            )
        },
    )

    /** Losing money most years, shrinking, deep in debt. */
    fun poor() = Filings(
        "BAD", "Bad Co", "USD", false, fund = false, fetchedAt = 0L,
        years = (0 until 5).map { i ->
            FiscalYear(
                end = "${2021 + i}-12-31", revenue = 10e9 * (1 - 0.05 * i), netIncome = if (i == 1) 0.2e9 else -1e9,
                grossProfit = 1.5e9, operatingIncome = -0.5e9, equity = 2e9, debt = 15e9, operatingCashFlow = -0.2e9,
                capex = 0.5e9, shares = 1e9 * (1 + 0.06 * i), interest = 1.2e9, cash = 1e9,
            )
        },
    )

    fun daily(closes: List<Double>): List<Bar> = closes.mapIndexed { i, c -> Bar(i * 86_400_000L, c, c * 1.01, c * 0.99, c, 1e6) }
}

class QualityTest {
    private fun great(price: Double, flags: List<RedFlag> = emptyList()) =
        Quality.evaluate("GRT", Companies.great(), price, 1.0, null, emptyList(), flags, 0L)

    @Test fun aGreatBusinessAtAFairPriceIsInTheBuyZone() {
        val r = great(price = 50.0)
        assertEquals(Decision.BUY_ZONE, r.decision)
        CheckKind.entries.filter { it != CheckKind.RISK }.forEach { assertEquals(it.name, Verdict.PASS, r.check(it)!!.verdict) }
        assertTrue(r.score >= 4.5)
    }

    @Test fun ifThePriceIsWrongItWaits() {
        val value = great(price = 50.0).value!!
        val r = great(price = value * 2)
        assertEquals(Verdict.FAIL, r.check(CheckKind.VALUE)!!.verdict)
        assertEquals(Decision.WAIT, r.decision)
        assertEquals(2.0, r.priceToValue!!, 1e-9)
    }

    @Test fun aLittleAboveValueIsAWatchNotAFail() {
        val value = great(price = 50.0).value!!
        assertEquals(Verdict.WATCH, great(price = value * 1.3).check(CheckKind.VALUE)!!.verdict)
    }

    @Test fun aLossMakingIndebtedCompanyIsAvoided() {
        val r = Quality.evaluate("BAD", Companies.poor(), 5.0, 1.0, null, emptyList(), emptyList(), 0L)
        assertEquals(Verdict.FAIL, r.check(CheckKind.BUSINESS)!!.verdict)
        assertEquals(Verdict.FAIL, r.check(CheckKind.MANAGEMENT)!!.verdict) // 6% a year dilution
        assertEquals(Decision.AVOID, r.decision)
    }

    @Test fun aSevereRedFlagFailsRiskAndAvoidsEvenAGreatBusiness() {
        val r = great(price = 50.0, flags = listOf(RedFlag(RedFlagKind.OFFERING, "GRT", 0L, "Great Co prices offering")))
        assertEquals(Verdict.FAIL, r.check(CheckKind.RISK)!!.verdict)
        assertEquals(Decision.AVOID, r.decision)
    }

    @Test fun aMildFlagOnlyAsksForCare() {
        val r = great(price = 50.0, flags = listOf(RedFlag(RedFlagKind.REGULATOR, "GRT", 0L, "EU opens probe")))
        assertEquals(Verdict.WATCH, r.check(CheckKind.RISK)!!.verdict)
    }

    @Test fun theValueEstimateIsConservativeAndCurrencyAware() {
        val usd = Quality.valuePerListing(Companies.great(), 1.0, null, 0.08)!!
        // Owner earnings ≈ 33bn on ≈4.75bn shares: a few dollars a share times a sensible multiple.
        assertTrue("value $usd", usd in 60.0..200.0)
        val eur = Quality.valuePerListing(Companies.great(currency = "EUR"), 1.10, null, 0.08)!!
        assertEquals(usd * 1.10, eur, 1e-6)
        // No exchange rate: no figure, rather than a figure in the wrong currency.
        assertNull(Quality.valuePerListing(Companies.great(currency = "EUR"), null, null, 0.08))
    }

    @Test fun anAdrOfUnknownSizeGetsNoValueButAKnownOneIsScaled() {
        val foreign = Companies.great(foreign = true)
        assertNull(Quality.valuePerListing(foreign, 1.0, null, 0.08))
        val one = Quality.valuePerListing(foreign, 1.0, 1.0, 0.08)!!
        assertEquals(one * 2, Quality.valuePerListing(foreign, 1.0, 2.0, 0.08)!!, 1e-6)
        assertEquals(Verdict.UNKNOWN, Quality.evaluate("X", foreign, 50.0, 1.0, null, emptyList(), emptyList(), 0L).check(CheckKind.VALUE)!!.verdict)
    }

    @Test fun aFundIsJudgedOnItsTrendNotItsBusiness() {
        val calm = Companies.daily((0 until 220).map { 100.0 + it * 0.05 })
        val r = Quality.evaluate("SPY", null, calm.last().close, null, null, calm, emptyList(), 0L)
        assertTrue(r.fund)
        assertEquals(Verdict.UNKNOWN, r.check(CheckKind.BUSINESS)!!.verdict)
        assertNotNull(r.check(CheckKind.VALUE)!!.facts.firstOrNull { it.metric == Metric.VS_200_DAY })
        // 5% above its 200-day average: a watch, so it waits.
        assertEquals(Decision.WAIT, r.decision)
        val dip = Quality.evaluate("SPY", null, calm.takeLast(200).map { it.close }.average() * 0.97, null, null, calm, emptyList(), 0L)
        assertEquals(Decision.BUY_ZONE, dip.decision)
    }

    @Test fun anUnknownStockWithNoDataSaysSo() {
        val r = Quality.evaluate("ZZZZ", null, 10.0, null, null, emptyList(), emptyList(), 0L)
        assertEquals(Decision.UNKNOWN, r.decision)
    }

    @Test fun growthNeedsThreeYearsAndPositiveEnds() {
        assertNull(Quality.cagr(listOf(1.0, 2.0)))
        assertNull(Quality.cagr(listOf(-1.0, 1.0, 2.0)))
        assertEquals(0.1, Quality.cagr(listOf(100.0, 110.0, 121.0))!!, 1e-9)
    }
}
