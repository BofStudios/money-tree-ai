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
    override suspend fun bars(symbol: String, timeframe: Timeframe, limit: Int) = bars[symbol].orEmpty()
    override suspend fun latestPrice(symbol: String) = latest[symbol] ?: bars[symbol]?.lastOrNull()?.close
    override suspend fun news(symbol: String, limit: Int) = listOf(Headline("$symbol does a thing", "wire", ""))
    override suspend fun recentOrders(symbol: String, limit: Int) = closed[symbol].orEmpty()
    override suspend fun buyBracket(entry: Entry, clientId: String): BrokerOrder {
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
    override fun approvalNeeded(p: Proposal) { approvals += p }
    override fun orderPlaced(e: Entry) {}
    override fun positionClosed(t: TradeRecord) { closedTrades += t }
    override fun halted(message: String) { halts += 1 }
}

class EngineTest {
    private val broker = FakeBroker()
    private val store = MemoryStore()
    private val monitor = MemoryMonitor()
    private val notifier = RecordingNotifier()
    private var settings = TradingSettings(watchlist = listOf("AAA"))
    private var clock = 1_000_000_000L

    private fun engine() = Engine(
        broker, store, monitor, { settings }, notifier = notifier,
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
}
