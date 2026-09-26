package com.bofstudios.moneytree.broker

import com.bofstudios.moneytree.engine.Autonomy
import com.bofstudios.moneytree.engine.EmaRsiStrategy
import com.bofstudios.moneytree.engine.Engine
import com.bofstudios.moneytree.engine.MemoryMonitor
import com.bofstudios.moneytree.engine.MemoryStore
import com.bofstudios.moneytree.engine.StepState
import com.bofstudios.moneytree.engine.Timeframe
import com.bofstudios.moneytree.engine.TradingSettings
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test

/**
 * Talks to the real Alpaca *paper* API, read-only. Skipped unless
 * ALPACA_PAPER_KEY and ALPACA_PAPER_SECRET are set in the environment, so it
 * never runs by accident and never needs keys in the repository.
 *
 * Nothing here places an order: the engine run uses manual mode, which cannot
 * buy, and the checks below are all reads.
 */
class AlpacaLiveReadTest {
    private val key = System.getenv("ALPACA_PAPER_KEY").orEmpty()
    private val secret = System.getenv("ALPACA_PAPER_SECRET").orEmpty()

    private fun broker(): AlpacaBroker {
        assumeTrue("no paper keys in the environment", key.isNotEmpty() && secret.isNotEmpty())
        return AlpacaBroker(key, secret, live = false)
    }

    @Test fun readsTheAccountClockAndBook() = runBlocking {
        val b = broker()
        val clock = b.clock()
        assertTrue(clock.nextOpen > 0 && clock.nextClose > 0)
        val account = b.account()
        assertTrue("equity parsed from a string", account.equity > 0)
        assertEquals("USD", account.currency)
        b.positions()
        b.openOrders()
        println("clock open=${clock.isOpen} equity=${account.equity} lastEquity=${account.lastEquity}")
    }

    @Test fun barsComeBackPerSymbolOldestFirstAndEnoughForTheStrategy() = runBlocking {
        val b = broker()
        val strategy = EmaRsiStrategy()
        for (tf in Timeframe.entries) {
            for (sym in listOf("AAPL", "MSFT")) {
                val bars = b.bars(sym, tf, 300)
                assertTrue("$sym $tf returned ${bars.size} bars", bars.size >= strategy.warmupBars)
                assertTrue("$sym $tf oldest first", bars.first().time < bars.last().time)
                assertTrue(bars.all { it.close > 0 && it.high >= it.low })
                println("$sym ${tf.alpaca}: ${bars.size} bars, last close ${bars.last().close}")
            }
        }
    }

    @Test fun latestPriceAndNewsAndHistory() = runBlocking {
        val b = broker()
        val price = b.latestPrice("AAPL")
        assertTrue("latest price $price", price != null && price > 0)
        val news = b.news("NVDA", 3)
        assertTrue(news.all { it.headline.isNotBlank() })
        b.recentOrders("AAPL", 5)
        println("AAPL latest $price, ${news.size} NVDA headlines")
    }

    @Test fun oneEngineCycleAgainstTheRealApi() = runBlocking {
        val monitor = MemoryMonitor()
        val engine = Engine(
            broker = broker(), store = MemoryStore(), monitor = monitor,
            settings = { TradingSettings(autonomy = Autonomy.MANUAL, watchlist = listOf("AAPL", "MSFT", "NVDA")) },
        )
        val sleep = engine.cycle()
        val steps = monitor.snapshot()
        steps.forEach { println("[${it.state}] ${it.kind} ${it.title} — ${it.detail ?: ""}") }
        assertTrue("no step left spinning", steps.none { it.state == StepState.RUNNING })
        assertTrue("no step failed", steps.none { it.state == StepState.FAILED })
        assertTrue(sleep >= 60_000)
        assertTrue(engine.state.value.account != null)
    }
}
