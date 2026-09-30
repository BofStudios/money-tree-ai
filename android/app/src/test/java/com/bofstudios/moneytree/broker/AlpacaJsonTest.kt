package com.bofstudios.moneytree.broker

import com.bofstudios.moneytree.engine.Entry
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.util.Locale

class AlpacaJsonTest {

    private val entry = Entry("nvda", 7.0, 218.36, 211.9049, 231.2651, "test")

    @Test fun aBuyIsAGoodTillCancelledBracket() {
        val j = AlpacaBroker.bracketJson(entry, "mt-1")
        assertEquals("NVDA", j.getString("symbol"))
        assertEquals("7", j.getString("qty"))
        assertEquals("buy", j.getString("side"))
        assertEquals("market", j.getString("type"))
        assertEquals("bracket", j.getString("order_class"))
        // DAY would let the stop expire at the close and leave the position bare overnight.
        assertEquals("gtc", j.getString("time_in_force"))
        assertEquals("211.90", j.getJSONObject("stop_loss").getString("stop_price"))
        assertEquals("231.27", j.getJSONObject("take_profit").getString("limit_price"))
    }

    @Test fun pricesUseADotEvenOnATurkishPhone() {
        val previous = Locale.getDefault()
        try {
            Locale.setDefault(Locale.forLanguageTag("tr-TR"))
            assertEquals("211.90", AlpacaBroker.price(211.9049))
            val j = AlpacaBroker.bracketJson(entry, "mt-1")
            assertTrue(!j.toString().contains("211,90"))
        } finally {
            Locale.setDefault(previous)
        }
    }

    @Test fun subDollarPricesKeepFourDecimals() {
        assertEquals("0.4567", AlpacaBroker.price(0.45671))
    }

    @Test fun moneyParsesFromStringsNumbersAndNull() {
        val j = JSONObject("""{"a":"100000","b":12.5,"c":null,"d":"oops"}""")
        assertEquals(100000.0, j.num("a"), 0.0)
        assertEquals(12.5, j.num("b"), 0.0)
        assertTrue(j.num("c").isNaN())
        assertTrue(j.num("d").isNaN())
        assertTrue(j.num("missing").isNaN())
    }

    @Test fun bracketLegsAreParsedAndFlattened() {
        val o = AlpacaBroker.parseOrder(JSONObject("""
            {"id":"p","client_order_id":"mt-9","symbol":"NVDA","side":"buy","type":"market",
             "status":"filled","qty":"7","filled_avg_price":"218.40","filled_qty":"7",
             "filled_at":"2026-09-28T14:31:00Z","stop_price":null,"limit_price":null,
             "legs":[
               {"id":"t","client_order_id":"x","symbol":"NVDA","side":"sell","type":"limit",
                "status":"new","qty":"7","limit_price":"231.27","stop_price":null},
               {"id":"s","client_order_id":"y","symbol":"NVDA","side":"sell","type":"stop",
                "status":"new","qty":"7","stop_price":"211.90","limit_price":null}]}
        """.trimIndent()))
        assertEquals(3, o.flatten().size)
        assertEquals(218.40, o.filledAvgPrice!!, 1e-9)
        val stop = o.flatten().first { it.type == "stop" }
        assertEquals(211.90, stop.stopPrice!!, 1e-9)
        assertNull(stop.limitPrice)
        assertTrue(o.filledAt > 0)
    }

    @Test fun clockTimesParseWithTheirOffset() {
        val t = AlpacaBroker.parseTime("2026-09-28T09:30:00-04:00")
        assertEquals(AlpacaBroker.parseTime("2026-09-28T13:30:00Z"), t)
    }

    @Test fun aFractionalStopIsADaySellStop() {
        val j = AlpacaBroker.sellStopJson("nvda", 0.0412, 175.104, "mt-stop-1")
        assertEquals("NVDA", j.getString("symbol"))
        assertEquals("0.0412", j.getString("qty"))
        assertEquals("sell", j.getString("side"))
        assertEquals("stop", j.getString("type"))
        // Alpaca only takes day orders on fractions.
        assertEquals("day", j.getString("time_in_force"))
        assertEquals("175.10", j.getString("stop_price"))
    }

    @Test fun aSellNeverAsksForMoreSharesThanAreHeld() {
        assertEquals("0.0412", AlpacaBroker.sellQty(0.0412))
        assertEquals("0.123456789", AlpacaBroker.sellQty(0.1234567899))
        assertEquals("3", AlpacaBroker.sellQty(3.0))
    }
}
