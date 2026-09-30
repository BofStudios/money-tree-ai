package com.bofstudios.moneytree.engine

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** A broker whose market, account and history the test controls completely. */
class FakeBroker : Broker {
    var open = true
    var account = Account(100_000.0, 100_000.0, 100_000.0, 200_000.0, "USD", false)
    val positions = ArrayList<BrokerPosition>()
    val orders = ArrayList<BrokerOrder>()
    val bars = HashMap<String, List<Bar>>()
    val latest = HashMap<String, Double>()
    val closed = HashMap<String, List<BrokerOrder>>()
    var clockError: Exception? = null
    var buyError: Exception? = null

    val placed = ArrayList<Entry>()
    val cancelled = ArrayList<String>()
    val sold = ArrayList<String>()
    val moved = ArrayList<Pair<String, Double>>()

    override suspend fun clock(): MarketClock {
        clockError?.let { throw it }
        return MarketClock(open, 1_800_000_000_000L, 1_800_000_900_000L)
    }
    override suspend fun account() = account
    override suspend fun positions() = positions.toList()
    override suspend fun openOrders() = orders.toList()
    var barCalls = 0
    override suspend fun bars(symbol: String, timeframe: Timeframe, limit: Int): List<Bar> {
        barCalls += 1
        return bars[symbol].orEmpty()
    }
    override suspend fun latestPrice(symbol: String) = latest[symbol] ?: bars[symbol]?.lastOrNull()?.close
    override suspend fun news(symbol: String, limit: Int) = listOf(Headline("$symbol does a thing", "wire", ""))
    override suspend fun recentOrders(symbol: String, limit: Int) = closed[symbol].orEmpty()
    override suspend fun buyBracket(entry: Entry, clientId: String): BrokerOrder {
        buyError?.let { throw it }
        placed += entry
        return BrokerOrder("o${placed.size}", clientId, entry.symbol, "buy", "market", "accepted",
            entry.qty, null, null)
    }
    val fractionalBuys = ArrayList<Entry>()
    override suspend fun buyFractional(entry: Entry, clientId: String): BrokerOrder {
        fractionalBuys += entry
        return BrokerOrder("f${fractionalBuys.size}", clientId, entry.symbol, "buy", "market", "accepted",
            entry.qty, null, null)
    }
    val stops = ArrayList<Triple<String, Double, Double>>()
    override suspend fun sellStop(symbol: String, qty: Double, stopPrice: Double, clientId: String): BrokerOrder {
        stops += Triple(symbol, qty, stopPrice)
        val order = BrokerOrder("st${stops.size}", clientId, symbol, "sell", "stop", "new", qty, stopPrice, null)
        orders += order
        return order
    }
    override suspend fun cancelOrder(orderId: String) {
        cancelled += orderId
        orders.removeAll { o -> o.flatten().any { it.id == orderId } }
    }
    override suspend fun closePosition(symbol: String) { sold += symbol }
    override suspend fun moveStop(orderId: String, stopPrice: Double) { moved += orderId to stopPrice }
}

class RecordingNotifier : Notifier {
    val approvals = ArrayList<Proposal>()
    val closedTrades = ArrayList<TradeRecord>()
    var halts = 0
    val bought = ArrayList<Entry>()
    val researched = ArrayList<String>()
    val skipped = ArrayList<String>()
    val raised = ArrayList<Pair<String, Double>>()
    val summaries = ArrayList<Int>()
    val failures = ArrayList<Pair<String, String>>()
    override fun approvalNeeded(p: Proposal) { approvals += p }
    override fun orderPlaced(e: Entry) { bought += e }
    override fun positionClosed(t: TradeRecord) { closedTrades += t }
    override fun halted(message: String) { halts += 1 }
    override fun researching(symbol: String, line: String) { researched += symbol }
    override fun aiSkipped(symbol: String, why: String) { skipped += symbol }
    override fun stopRaised(symbol: String, from: Double?, to: Double, lockedIn: Double?) { raised += symbol to to }
    override fun dailySummary(trades: List<TradeRecord>, today: Double, equity: Double) { summaries += trades.size }
    override fun orderFailed(symbol: String, why: String) { failures += symbol to why }
}

/** An AI whose verdict the test sets, counting how often it is asked. */
class FixedResearcher(var vet: Vet?) : Researcher {
    var calls = 0
    override suspend fun vet(symbol: String, facts: String, headlines: List<String>, turkish: Boolean): Vet? {
        calls += 1
        return vet
    }
}

class EngineTest {
    private val broker = FakeBroker()
    private val store = MemoryStore()
    private val monitor = MemoryMonitor()
    private val notifier = RecordingNotifier()
    private var settings = TradingSettings(watchlist = listOf("AAA"))
    private var clock = 1_000_000_000L

    private fun engine(researcher: Researcher? = null) = Engine(
        broker, store, monitor, { settings }, notifier = notifier, researcher = researcher,
        now = { clock }, pause = {},
    )

    private fun position(symbol: String, entry: Double, price: Double, qty: Double = 10.0) =
        BrokerPosition(symbol, qty, entry, price, (price - entry) * qty, price * qty)

    private fun steps(kind: StepKind) = monitor.snapshot().filter { it.kind == kind }

    // ------------------------------------------------------------ autonomy

    @Test fun fullAutoPlacesABracketAndRemembersItOwnsIt() = runTest {
        broker.bars["AAA"] = Candles.crossUpOnLastBar()
        engine().cycle()

        assertEquals(1, broker.placed.size)
        val e = broker.placed[0]
        assertTrue(e.qty >= 1)
        assertTrue(e.stop < e.price && e.price < e.target)
        assertTrue("AAA" in store.ownedSymbols())
        assertEquals(StepState.DONE, steps(StepKind.ORDER).single().state)
    }

    @Test fun semiAutoAsksInsteadOfBuying() = runTest {
        settings = settings.copy(autonomy = Autonomy.SEMI)
        broker.bars["AAA"] = Candles.crossUpOnLastBar()
        val engine = engine()
        engine.cycle()

        assertTrue(broker.placed.isEmpty())
        assertEquals(1, engine.state.value.approvals.size)
        assertEquals(1, notifier.approvals.size)
    }

    @Test fun manualNeverBuysAndHoldsNoApproval() = runTest {
        settings = settings.copy(autonomy = Autonomy.MANUAL)
        broker.bars["AAA"] = Candles.crossUpOnLastBar()
        val engine = engine()
        engine.cycle()

        assertTrue(broker.placed.isEmpty())
        assertTrue(engine.state.value.approvals.isEmpty())
        assertEquals(1, engine.state.value.suggestions.size)
    }

    @Test fun theSameSetupIsNotReProposedEveryScan() = runTest {
        settings = settings.copy(autonomy = Autonomy.SEMI)
        broker.bars["AAA"] = Candles.crossUpOnLastBar()
        val engine = engine()
        repeat(3) { engine.cycle() }

        assertEquals(1, engine.state.value.approvals.size)
        assertEquals(1, notifier.approvals.size)
    }

    // ------------------------------------------------------------ approving

    private suspend fun pendingApproval(engine: Engine): Proposal {
        settings = settings.copy(autonomy = Autonomy.SEMI)
        broker.bars["AAA"] = Candles.crossUpOnLastBar()
        engine.cycle()
        return engine.state.value.approvals.single()
    }

    @Test fun approvingBuysAtTheCurrentPrice() = runTest {
        val engine = engine()
        val p = pendingApproval(engine)
        broker.latest["AAA"] = p.entry.price * 1.005

        val result = engine.approve(p.id)

        assertTrue(result.message, result.ok)
        assertEquals(p.entry.price * 1.005, broker.placed.single().price, 1e-9)
        assertTrue(engine.state.value.approvals.isEmpty())
    }

    @Test fun anApprovalCanOnlyBeUsedOnce() = runTest {
        val engine = engine()
        val p = pendingApproval(engine)
        assertTrue(engine.approve(p.id).ok)
        assertFalse(engine.approve(p.id).ok)
        assertEquals(1, broker.placed.size)
    }

    @Test fun aPriceThatRanAwayIsRefused() = runTest {
        val engine = engine()
        val p = pendingApproval(engine)
        broker.latest["AAA"] = p.entry.price * 1.03

        val result = engine.approve(p.id)

        assertFalse(result.ok)
        assertTrue(broker.placed.isEmpty())
    }

    @Test fun aPriceAlreadyThroughTheStopIsRefused() = runTest {
        val engine = engine()
        val p = pendingApproval(engine)
        broker.latest["AAA"] = p.entry.stop - 0.01
        // Inside the drift limit only if the stop is close; force it by checking the rule order.
        val result = engine.approve(p.id)
        assertFalse(result.ok)
        assertTrue(broker.placed.isEmpty())
    }

    @Test fun nothingIsBoughtWhileTheMarketIsClosed() = runTest {
        val engine = engine()
        val p = pendingApproval(engine)
        broker.open = false
        assertFalse(engine.approve(p.id).ok)
        assertTrue(broker.placed.isEmpty())
    }

    @Test fun realMoneyNeedsArmingEvenWhenApproved() = runTest {
        val engine = engine()
        val p = pendingApproval(engine)
        settings = settings.copy(live = true, armed = false)
        assertFalse(engine.approve(p.id).ok)
        assertTrue(broker.placed.isEmpty())
    }

    @Test fun anExpiredRequestCannotBeApproved() = runTest {
        val engine = engine()
        val p = pendingApproval(engine)
        clock += 16 * 60_000
        assertFalse(engine.approve(p.id).ok)
        assertTrue(broker.placed.isEmpty())
    }

    // ---------------------------------------------------------- real money

    @Test fun liveAndUnarmedNeverBuysEvenOnFullAuto() = runTest {
        settings = settings.copy(live = true, armed = false)
        broker.bars["AAA"] = Candles.crossUpOnLastBar()
        engine().cycle()
        assertTrue(broker.placed.isEmpty())
    }

    @Test fun liveAndArmedBuys() = runTest {
        settings = settings.copy(live = true, armed = true)
        broker.bars["AAA"] = Candles.crossUpOnLastBar()
        engine().cycle()
        assertEquals(1, broker.placed.size)
    }

    @Test fun theDailyLossLimitStopsNewBuys() = runTest {
        broker.account = broker.account.copy(equity = 94_000.0, lastEquity = 100_000.0)
        broker.bars["AAA"] = Candles.crossUpOnLastBar()
        val engine = engine()
        engine.cycle()

        assertTrue(broker.placed.isEmpty())
        assertNotNull(engine.state.value.haltReason)
        assertEquals(1, notifier.halts)
    }

    // ------------------------------------------------------------ ownership

    @Test fun aPositionTheOwnerBoughtByHandIsNeverSold() = runTest {
        settings = settings.copy(watchlist = listOf("BBB"))
        broker.positions += position("BBB", 100.0, 90.0)
        broker.bars["BBB"] = Candles.crossDownOnLastBar()
        engine().cycle()

        assertTrue(broker.sold.isEmpty())
        assertTrue(broker.cancelled.isEmpty())
    }

    @Test fun anOwnedPositionIsSoldOnTheExitSignalAfterItsLegsAreCancelled() = runTest {
        settings = settings.copy(watchlist = listOf("BBB"))
        store.addOwned("BBB")
        broker.positions += position("BBB", 100.0, 90.0)
        broker.orders += BrokerOrder("p", "mt-1", "BBB", "buy", "market", "filled", 10.0, null, null,
            legs = listOf(
                BrokerOrder("t", "x", "BBB", "sell", "limit", "new", 10.0, null, 110.0),
                BrokerOrder("s", "y", "BBB", "sell", "stop", "new", 10.0, 95.0, null),
            ))
        broker.bars["BBB"] = Candles.crossDownOnLastBar()
        engine().cycle()

        assertTrue("legs cancelled first", broker.cancelled.containsAll(listOf("t", "s")))
        assertEquals(listOf("BBB"), broker.sold)
    }

    @Test fun aPositionClosedAtTheBrokerBecomesATradeAndCoolsDown() = runTest {
        settings = settings.copy(watchlist = listOf("CCC"))
        store.addOwned("CCC")
        broker.closed["CCC"] = listOf(
            BrokerOrder("p", "mt-7", "CCC", "buy", "market", "filled", 10.0, null, null,
                filledAvgPrice = 100.0, filledQty = 10.0, filledAt = 1_000L,
                legs = listOf(
                    BrokerOrder("s", "y", "CCC", "sell", "stop", "filled", 10.0, 97.0, null,
                        filledAvgPrice = 96.9, filledQty = 10.0, filledAt = 2_000L),
                    BrokerOrder("t", "x", "CCC", "sell", "limit", "canceled", 10.0, null, 106.0),
                )),
        )
        broker.bars["CCC"] = Candles.crossUpOnLastBar()
        engine().cycle()

        val trade = store.trades().single()
        assertEquals("stop-loss", trade.reason)
        assertEquals(-31.0, trade.pnl, 1e-9)
        assertFalse("CCC" in store.ownedSymbols())
        assertEquals(1, notifier.closedTrades.size)
        // Freshly stopped out: the crossover is ignored during the cooldown.
        assertTrue(broker.placed.isEmpty())
    }

    @Test fun aWinnerHasItsBrokerStopRaised() = runTest {
        settings = settings.copy(watchlist = listOf("DDD"))
        store.addOwned("DDD")
        broker.positions += position("DDD", 100.0, 103.0)
        broker.orders += BrokerOrder("p", "mt-1", "DDD", "buy", "market", "filled", 10.0, null, null,
            legs = listOf(BrokerOrder("s1", "y", "DDD", "sell", "stop", "new", 10.0, 97.0, null)))
        broker.bars["DDD"] = Candles.of(List(120) { 103.0 })
        engine().cycle()

        val (id, stop) = broker.moved.single()
        assertEquals("s1", id)
        assertEquals(101.97, stop, 1e-9)
    }

    // -------------------------------------------------------- small account

    private val tenDollars = Account(10.0, 10.0, 10.0, 10.0, "USD", false)

    @Test fun tenDollarsBuysNothingWithWholeShares() = runTest {
        broker.account = tenDollars
        broker.bars["AAA"] = Candles.crossUpOnLastBar()
        engine().cycle()
        assertTrue(broker.placed.isEmpty())
        assertTrue(broker.fractionalBuys.isEmpty())
    }

    @Test fun tenDollarsBuysAFractionWhenSmallAccountModeIsOn() = runTest {
        settings = settings.copy(fractional = true)
        broker.account = tenDollars
        broker.bars["AAA"] = Candles.crossUpOnLastBar()
        engine().cycle()

        assertTrue(broker.placed.isEmpty())
        val e = broker.fractionalBuys.single()
        assertTrue("under one share", e.qty < 1.0)
        assertTrue("at least Alpaca's \$1 minimum", e.notional >= 1.0)
        assertTrue("capped at 20% of \$10", e.notional <= 2.0 + 1e-9)
        // No bracket at Alpaca, so this phone now holds the stop and target.
        assertEquals(e.stop to e.target, store.guard("AAA"))
    }

    @Test fun aPhoneHeldStopSellsWhenThePriceFallsThroughIt() = runTest {
        settings = settings.copy(watchlist = listOf("EEE"))
        store.addOwned("EEE")
        store.setGuard("EEE", 99.0, 110.0)
        broker.positions += position("EEE", 100.0, 98.0, qty = 0.02)
        broker.bars["EEE"] = Candles.of(List(120) { 98.0 })
        engine().cycle()

        assertEquals(listOf("EEE"), broker.sold)
    }

    @Test fun aPhoneHeldTargetSellsWhenReached() = runTest {
        settings = settings.copy(watchlist = listOf("EEE"))
        store.addOwned("EEE")
        store.setGuard("EEE", 90.0, 104.0)
        broker.positions += position("EEE", 100.0, 105.0, qty = 0.02)
        broker.bars["EEE"] = Candles.of(List(120) { 105.0 })
        engine().cycle()

        assertEquals(listOf("EEE"), broker.sold)
    }

    @Test fun quantitiesPrintWithoutATrailingDecimal() {
        assertEquals("7", formatQty(7.0))
        assertEquals("0.0412", formatQty(0.0412))
        assertEquals("0.5", formatQty(0.5))
    }

    // --------------------------------------------------------- the monitor

    @Test fun aClosedMarketIsQuietAfterTheFirstLook() = runTest {
        broker.open = false
        val engine = engine()
        val sleep = engine.cycle()
        val afterFirst = monitor.snapshot().size
        engine.cycle()

        assertTrue(sleep >= 60_000)
        assertEquals(afterFirst, monitor.snapshot().size)
    }

    @Test fun aClosedMarketStillReviewsTheChartsButTradesNothing() = runTest {
        broker.open = false
        broker.bars["AAA"] = Candles.crossUpOnLastBar()   // a real buy signal
        val engine = engine()
        engine.cycle()

        assertTrue("charts were fetched", broker.barCalls > 0)
        assertTrue("analysis published", engine.state.value.snapshots.any { it.symbol == "AAA" && it.ready })
        assertTrue("nothing bought while closed", broker.placed.isEmpty() && broker.fractionalBuys.isEmpty())
        assertTrue(engine.state.value.approvals.isEmpty())
        val analysis = steps(StepKind.ANALYSE).single()
        assertTrue(analysis.detail!!.contains("not trading"))
    }

    @Test fun lookNowReviewsAgainWhileClosedButAQuietCycleDoesNot() = runTest {
        broker.open = false
        broker.bars["AAA"] = Candles.of(List(120) { 100.0 })
        val engine = engine()
        engine.cycle()
        val afterFirst = broker.barCalls

        engine.cycle()
        assertEquals("quiet cycle fetches nothing", afterFirst, broker.barCalls)

        engine.cycle(forceLook = true)
        assertTrue("Look now fetches again", broker.barCalls > afterFirst)
    }

    @Test fun aRunningStepShowsWhatItIsWorkingOn() {
        val handle = monitor.begin(StepKind.BARS, "Fetching")
        handle.progress("NVDA · 3/8")
        assertEquals("NVDA · 3/8", monitor.snapshot().single().detail)
        handle.done("8 of 8 ready")
        handle.progress("late update")
        assertEquals("a finished step is not rewritten", "8 of 8 ready", monitor.snapshot().single().detail)
    }

    @Test fun focusIsClearedAfterTheLook() = runTest {
        broker.bars["AAA"] = Candles.of(List(120) { 100.0 })
        val engine = engine()
        engine.cycle()
        assertEquals(null, engine.state.value.focus)
    }

    @Test fun everyNetworkStepIsClosedNotLeftSpinning() = runTest {
        broker.bars["AAA"] = Candles.crossUpOnLastBar()
        engine().cycle()
        assertTrue(monitor.snapshot().none { it.state == StepState.RUNNING })
    }

    @Test fun stoppingTheServiceStopsTheEngine() = runTest {
        broker.clockError = CancellationException("service stopped")
        var threw = false
        try { engine().cycle() } catch (e: CancellationException) { threw = true }
        assertTrue(threw)
    }

    @Test fun aFailingCallIsReportedAndRetried() = runTest {
        broker.clockError = IllegalStateException("network down")
        val engine = engine()
        val sleep = engine.cycle()
        assertEquals(Engine.ERROR_SLEEP, sleep)
        assertEquals("network down", engine.state.value.lastError)
        assertEquals(StepState.FAILED, steps(StepKind.CLOCK).single().state)
    }

    // ------------------------------------------------------------- research

    @Test fun aBuyIsResearchedThenAnnounced() = runTest {
        broker.bars["AAA"] = Candles.crossUpOnLastBar()
        engine().cycle()

        assertEquals(listOf("AAA"), notifier.researched)
        assertEquals(1, notifier.bought.size)
        assertEquals(StepState.DONE, steps(StepKind.NEWS).single().state)
    }

    @Test fun theAiCanCallABuyOffOnARedFlag() = runTest {
        broker.bars["AAA"] = Candles.crossUpOnLastBar()
        val ai = FixedResearcher(Vet(false, "earnings tomorrow"))
        engine(ai).cycle()

        assertTrue(broker.placed.isEmpty())
        assertEquals(listOf("AAA"), notifier.skipped)
        assertEquals(1, ai.calls)
    }

    @Test fun aStockTheAiPassedOnIsLeftAloneForAnHour() = runTest {
        broker.bars["AAA"] = Candles.crossUpOnLastBar()
        val ai = FixedResearcher(Vet(false, "trading halt"))
        val engine = engine(ai)
        engine.cycle()
        engine.cycle()
        assertEquals("not asked again while cooling down", 1, ai.calls)

        ai.vet = Vet(true, "")
        clock += Engine.AI_SKIP_COOLDOWN + 1
        engine.cycle()
        assertEquals(1, broker.placed.size)
    }

    @Test fun anOkFromTheAiLetsTheRulesBuy() = runTest {
        broker.bars["AAA"] = Candles.crossUpOnLastBar()
        engine(FixedResearcher(Vet(true, "nothing unusual"))).cycle()
        assertEquals(1, broker.placed.size)
    }

    @Test fun anAiThatDoesNotAnswerNeverBlocksABuy() = runTest {
        broker.bars["AAA"] = Candles.crossUpOnLastBar()
        engine(FixedResearcher(null)).cycle()
        assertEquals(1, broker.placed.size)
    }

    @Test fun withTheCheckOffTheAiIsNotAsked() = runTest {
        settings = settings.copy(aiCheck = false)
        broker.bars["AAA"] = Candles.crossUpOnLastBar()
        val ai = FixedResearcher(Vet(false, "would have skipped"))
        engine(ai).cycle()
        assertEquals(0, ai.calls)
        assertEquals(1, broker.placed.size)
    }

    // ------------------------------------------------------------ risk levels

    @Test fun aBolderLevelRisksMoreOnTheSameSignal() {
        fun qty(level: RiskLevel) = Risk(TradingSettings(riskLevel = level).riskConfig())
            .plan("AAA", "x", 100.0, 2.0, 10_000.0, 10_000.0)!!.qty
        assertTrue(qty(RiskLevel.CAREFUL) < qty(RiskLevel.NORMAL))
        assertTrue(qty(RiskLevel.NORMAL) < qty(RiskLevel.BOLD))
    }

    @Test fun theOwnersPositionCapIsTheOneUsed() = runTest {
        settings = settings.copy(watchlist = listOf("AAA", "BBB"), maxPositions = 1)
        broker.bars["AAA"] = Candles.crossUpOnLastBar()
        broker.bars["BBB"] = Candles.crossUpOnLastBar()
        engine().cycle()
        assertEquals(1, broker.placed.size)
    }

    @Test fun theBotOnlyUsesItsShareOfTheAccount() = runTest {
        settings = settings.copy(usePct = 25, riskLevel = RiskLevel.BOLD)
        broker.account = Account(1_000.0, 1_000.0, 1_000.0, 1_000.0, "USD", false)
        broker.bars["AAA"] = Candles.crossUpOnLastBar()
        val engine = engine()
        engine.cycle()

        val e = broker.placed.single()
        // A quarter of $1,000 is $250; Bold caps one position at half of that.
        assertTrue("${e.notional}", e.notional <= 125.0 + 1e-9)
        assertEquals(250.0, engine.state.value.budget!!, 1e-9)
    }

    @Test fun inSmallAccountModeAWholeShareStillWinsWhenItFits() = runTest {
        settings = settings.copy(fractional = true)
        broker.bars["AAA"] = Candles.crossUpOnLastBar()
        engine().cycle()

        assertEquals("bracket, stop at Alpaca", 1, broker.placed.size)
        assertTrue(broker.fractionalBuys.isEmpty())
        assertEquals(null, store.guard("AAA"))
    }

    // ------------------------------------------------ fractional stops at Alpaca

    @Test fun aFractionalPositionGetsTodaysStopAtAlpaca() = runTest {
        settings = settings.copy(watchlist = listOf("EEE"))
        store.addOwned("EEE")
        store.setGuard("EEE", 95.0, 110.0)
        broker.positions += position("EEE", 100.0, 100.0, qty = 0.05)
        broker.bars["EEE"] = Candles.of(List(120) { 100.0 })
        engine().cycle()

        assertEquals(Triple("EEE", 0.05, 95.0), broker.stops.single())
        assertTrue(broker.sold.isEmpty())
    }

    @Test fun withTheStopAtAlpacaThePhoneDoesNotRaceIt() = runTest {
        settings = settings.copy(watchlist = listOf("EEE"))
        store.addOwned("EEE")
        store.setGuard("EEE", 99.0, 110.0)
        broker.positions += position("EEE", 100.0, 98.0, qty = 0.05)
        broker.orders += BrokerOrder("st", "mt-stop-1", "EEE", "sell", "stop", "new", 0.05, 99.0, null)
        broker.bars["EEE"] = Candles.of(List(120) { 98.0 })
        engine().cycle()

        assertTrue("Alpaca sells at the stop, not the phone", broker.sold.isEmpty())
        assertTrue("no second stop", broker.stops.isEmpty())
    }

    @Test fun aFractionalTrailMovesTheAlpacaStopAndRemembersIt() = runTest {
        settings = settings.copy(watchlist = listOf("EEE"))
        store.addOwned("EEE")
        store.setGuard("EEE", 97.0, 110.0)
        broker.positions += position("EEE", 100.0, 103.0, qty = 0.05)
        broker.orders += BrokerOrder("st1", "mt-stop-1", "EEE", "sell", "stop", "new", 0.05, 97.0, null)
        broker.bars["EEE"] = Candles.of(List(120) { 103.0 })
        engine().cycle()

        assertEquals("st1" to 101.97, broker.moved.single().let { it.first to Math.round(it.second * 100) / 100.0 })
        assertEquals(101.97, store.guard("EEE")!!.first, 1e-9)
        assertEquals("EEE", notifier.raised.single().first)
    }

    @Test fun aStopBelowThePriceIsNeverPlacedAbove() = runTest {
        settings = settings.copy(watchlist = listOf("EEE"))
        store.addOwned("EEE")
        store.setGuard("EEE", 99.0, 110.0)
        broker.positions += position("EEE", 100.0, 98.0, qty = 0.05)
        broker.bars["EEE"] = Candles.of(List(120) { 98.0 })
        engine().cycle()

        // Already through the stop with nothing at Alpaca: the phone sells now
        // rather than sending a stop order Alpaca would refuse.
        assertEquals(listOf("EEE"), broker.sold)
        assertTrue(broker.stops.isEmpty())
    }

    // --------------------------------------------------------- daily summary

    @Test fun theDayEndsWithOneSummary() = runTest {
        broker.bars["AAA"] = Candles.of(List(120) { 100.0 })
        val engine = engine()
        engine.cycle()
        broker.open = false
        engine.cycle()
        engine.cycle()
        assertEquals(1, notifier.summaries.size)
    }

    @Test fun noSummaryWithoutASessionWatched() = runTest {
        broker.open = false
        engine().cycle()
        assertTrue(notifier.summaries.isEmpty())
    }

    @Test fun aRefusedOrderIsReportedToTheOwner() = runTest {
        broker.buyError = BrokerError("insufficient buying power", 403)
        broker.bars["AAA"] = Candles.crossUpOnLastBar()
        engine().cycle()

        assertEquals("AAA" to "insufficient buying power", notifier.failures.single())
        assertEquals(StepState.FAILED, steps(StepKind.ORDER).single().state)
        assertFalse("AAA" in store.ownedSymbols())
    }

    @Test fun aStockTheAiPassedOnSaysSoNotThatItClosed() = runTest {
        broker.bars["AAA"] = Candles.crossUpOnLastBar()
        val engine = engine(FixedResearcher(Vet(false, "halt")))
        engine.cycle()
        engine.cycle()
        assertTrue(monitor.snapshot().any { it.title.contains("AI passed") })
        assertTrue(monitor.snapshot().none { it.title.contains("cooling") })
    }
}
