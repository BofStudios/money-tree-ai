package com.bofstudios.moneytree.engine

import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** Stop means stop: nothing is bought once the owner pressed it, even mid-look. */
class EngineStopTest {
    private val broker = FakeBroker()
    private val store = MemoryStore()
    private val monitor = MemoryMonitor()
    private var allowed = true
    private var settings = TradingSettings(watchlist = listOf("AAA"))

    private fun engine() = Engine(broker, store, monitor, { settings }, allowed = { allowed }, now = { 1_000_000_000L }, pause = {})

    @Test fun aLookAlreadyUnderwayDoesNotBuyAfterStop() = runTest {
        broker.bars["AAA"] = Candles.crossUpOnLastBar()
        allowed = false
        engine().cycle()
        assertTrue(broker.placed.isEmpty())
        assertTrue(monitor.snapshot().any { it.kind == StepKind.WARN && it.title.contains("AAA") })
        assertTrue(store.orderLog().isEmpty())
    }

    @Test fun anApprovalAfterStopIsRefused() = runTest {
        settings = settings.copy(autonomy = Autonomy.SEMI)
        broker.bars["AAA"] = Candles.crossUpOnLastBar()
        val e = engine()
        e.cycle()
        val p = e.state.value.approvals.single()
        allowed = false
        assertFalse(e.approve(p.id).ok)
        assertTrue(broker.placed.isEmpty())
    }

    @Test fun stopWithdrawsUnfilledBuysButKeepsTheStops() = runTest {
        broker.orders += BrokerOrder("b1", "mt-abc", "AAA", "buy", "market", "new", 1.0, null, null)
        broker.orders += BrokerOrder("b2", "manual-1", "BBB", "buy", "limit", "new", 1.0, null, 10.0)
        broker.orders += BrokerOrder("s1", "mt-stop-1", "CCC", "sell", "stop", "new", 1.0, 9.0, null)
        assertEquals(1, engine().cancelPendingBuys())
        assertEquals(listOf("b1"), broker.cancelled)
    }

    @Test fun everyOrderItSendsIsLogged() = runTest {
        broker.bars["AAA"] = Candles.crossUpOnLastBar()
        engine().cycle()
        val log = store.orderLog().single()
        assertEquals("AAA", log.symbol)
        assertEquals("buy", log.side)
        assertEquals(broker.placed.single().qty, log.qty, 1e-9)
    }
}
