package com.bofstudios.moneytree.engine

import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** The research desk between the signal and the order: what it holds back, and what it lets through smaller. */
class EngineBrainTest {
    private val broker = FakeBrokerWithNews()
    private val store = MemoryStore()
    private val monitor = MemoryMonitor()
    private val notifier = RecordingNotifier()
    private var settings = TradingSettings(watchlist = listOf("AAA"))
    private val clock = 1_000_000_000L
    private var filings: Filings? = Companies.great("AAA")

    private val source = object : FilingsSource {
        override suspend fun filings(symbol: String) = this@EngineBrainTest.filings?.copy(symbol = symbol)
    }

    private fun brain(store: BrainStore = MemoryBrainStore()) = Brain(store, filings = source, fx = null, now = { clock })

    private fun engine(brain: Brain) = Engine(
        broker, store, monitor, { settings }, notifier = notifier, brain = brain, now = { clock }, pause = {},
    )

    /** Daily candles rising gently, so the daily trend is up unless a test says otherwise. */
    private fun dailyUp() = Companies.daily((0 until 260).map { 50.0 + it * 0.1 })
    private fun dailyDown() = Companies.daily((0 until 260).map { 120.0 - it * 0.1 })

    private fun withSignal(daily: List<Bar> = dailyUp()) {
        broker.bars["AAA"] = Candles.crossUpOnLastBar()
        broker.daily["AAA"] = daily
    }

    @Test fun aGreatBusinessWithARisingDailyChartIsBought() = runTest {
        withSignal()
        engine(brain()).cycle()
        assertEquals(1, broker.placed.size)
        val research = monitor.snapshot().first { it.kind == StepKind.RESEARCH && it.title.contains("AAA") }
        assertTrue(research.lines.size >= 4)
    }

    @Test fun aCompanyThatFailsTheChecksIsHeldBack() = runTest {
        filings = Companies.poor()
        withSignal()
        engine(brain()).cycle()
        assertTrue(broker.placed.isEmpty())
        assertEquals(1, notifier.heldBack.size)
    }

    @Test fun theSameHeldBackCandleIsNotJudgedEveryMinute() = runTest {
        filings = Companies.poor()
        withSignal()
        val e = engine(brain())
        repeat(3) { e.cycle() }
        assertEquals(1, notifier.heldBack.size)
        assertEquals(1, monitor.snapshot().count { it.kind == StepKind.RESEARCH && it.title.contains("AAA") })
    }

    @Test fun offTheChecksNeverHoldABuyBack() = runTest {
        settings = settings.copy(qualityMode = QualityMode.OFF)
        filings = Companies.poor()
        withSignal(daily = dailyDown())
        engine(brain()).cycle()
        assertEquals(1, broker.placed.size)
    }

    @Test fun aFallingDailyChartHoldsBackInBalancedMode() = runTest {
        withSignal(daily = dailyDown())
        engine(brain()).cycle()
        assertTrue(broker.placed.isEmpty())
        assertTrue(notifier.heldBack.single().second.isNotBlank())
    }

    @Test fun strictModeOnlyBuysTheBuyZone() = runTest {
        settings = settings.copy(qualityMode = QualityMode.STRICT)
        // The fake candles trade near 100; make the value estimate far below that.
        filings = Companies.great().let { f -> f.copy(years = f.years.map { it.copy(shares = it.shares!! * 20) }) }
        withSignal()
        engine(brain()).cycle()
        assertTrue(broker.placed.isEmpty())
    }

    @Test fun aFreshRedFlagInTheNewsHoldsBack() = runTest {
        // Checks off, so it is the news gate (not the risk check reading the same flag) that speaks.
        settings = settings.copy(qualityMode = QualityMode.OFF)
        withSignal()
        broker.feed += NewsItem(1, "AAA prices secondary offering", "", "wire", listOf("AAA"), clock - 60_000L)
        engine(brain()).cycle()
        assertTrue(broker.placed.isEmpty())
        assertTrue(notifier.heldBack.single().second.contains("\"AAA prices secondary offering\""))
    }

    @Test fun theNewsCheckCanBeTurnedOff() = runTest {
        settings = settings.copy(newsCheck = false, qualityMode = QualityMode.OFF)
        withSignal()
        broker.feed += NewsItem(1, "AAA earnings preview: what to expect", "", "wire", listOf("AAA"), clock - 60_000L)
        engine(brain()).cycle()
        assertEquals(1, broker.placed.size)
    }

    @Test fun whatItLearnedHoldsBackALosingKindOfSignal() = runTest {
        withSignal()
        val b = brain()
        // Twenty earlier signals on AAA in the same setup, nearly all stopped out.
        val f = Features("AAA", Decision.BUY_ZONE, null, 60.0, 1.0, null, dailyUp = true)
        repeat(20) { b.learner.add(Sample(f, -1.0, real = false, at = 0)) }
        engine(b).cycle()
        assertTrue(broker.placed.isEmpty())
        assertTrue(notifier.heldBack.isNotEmpty())
    }

    @Test fun learningOffKeepsCountingButNeverHoldsBack() = runTest {
        settings = settings.copy(learning = false)
        withSignal()
        val b = brain()
        val f = Features("AAA", Decision.BUY_ZONE, null, 60.0, 1.0, null, dailyUp = true)
        repeat(20) { b.learner.add(Sample(f, -1.0, real = false, at = 0)) }
        engine(b).cycle()
        assertEquals(1, broker.placed.size)
    }

    @Test fun aGoodBusinessAtAHighPriceGetsASmallerSize() = runTest {
        withSignal()
        engine(brain()).cycle()
        val full = broker.placed.single().qty

        val broker2 = FakeBrokerWithNews().apply { bars["AAA"] = Candles.crossUpOnLastBar(); daily["AAA"] = dailyUp() }
        filings = Companies.great().let { f -> f.copy(years = f.years.map { it.copy(shares = it.shares!! * 20) }) }
        val b2 = Brain(MemoryBrainStore(), filings = source, now = { clock })
        Engine(broker2, MemoryStore(), MemoryMonitor(), { settings }, notifier = RecordingNotifier(), brain = b2, now = { clock }, pause = {}).cycle()
        val smaller = broker2.placed.single().qty
        assertTrue("$smaller < $full", smaller < full)
    }

    @Test fun everyBuySignalIsFollowedInItsHead() = runTest {
        filings = Companies.poor()
        withSignal()
        val b = brain()
        engine(b).cycle()
        // Held back, but still followed, so the bot learns whether holding back was right.
        assertEquals(1, b.shadows.openTrades().size)
        assertFalse(b.shadows.openTrades().single().bought)
    }

    @Test fun aRealBuyIsRememberedAndItsCloseIsCountedDouble() = runTest {
        withSignal()
        val b = brain()
        val e = engine(b)
        e.cycle()
        val entry = broker.placed.single()
        assertTrue(b.shadows.openTrades().single().bought)
        // The bracket filled at the stop at Alpaca: the position is gone at the next look.
        broker.closed["AAA"] = listOf(
            BrokerOrder("b", "mt-1", "AAA", "buy", "market", "filled", entry.qty, null, null, filledAvgPrice = entry.price, filledQty = entry.qty, filledAt = 10),
            BrokerOrder("s", "x", "AAA", "sell", "stop", "filled", entry.qty, entry.stop, null, filledAvgPrice = entry.stop, filledQty = entry.qty, filledAt = 20),
        )
        e.cycle()
        val real = b.learner.all().single { it.real }
        assertEquals(-1.0, real.r, 1e-6)
    }

    @Test fun theBrainIsPublishedForTheScreen() = runTest {
        withSignal()
        val e = engine(brain())
        e.cycle()
        val snap = e.state.value.brain
        assertEquals(Decision.BUY_ZONE, snap.reports.getValue("AAA").decision)
        assertTrue(snap.shadowOpen.isNotEmpty())
    }

    @Test fun whatItLearnedSurvivesARestart() = runTest {
        withSignal()
        val disk = MemoryBrainStore()
        engine(brain(disk)).cycle()
        val again = brain(disk)
        assertEquals(1, again.shadows.all().size)
        assertTrue(again.radar.all().isEmpty())
    }
}

/** The fake broker with a news wire and daily candles. */
open class FakeBrokerWithNews : FakeBroker() {
    val feed = ArrayList<NewsItem>()
    val daily = HashMap<String, List<Bar>>()
    override suspend fun newsFeed(symbols: List<String>, since: Long?, limit: Int) =
        feed.filter { n -> n.symbols.any { it in symbols } && (since == null || n.createdAt >= since) }.sortedByDescending { it.createdAt }
    override suspend fun bars(symbol: String, timeframe: Timeframe, limit: Int): List<Bar> =
        if (timeframe == Timeframe.D1) daily[symbol].orEmpty() else super.bars(symbol, timeframe, limit)
}
