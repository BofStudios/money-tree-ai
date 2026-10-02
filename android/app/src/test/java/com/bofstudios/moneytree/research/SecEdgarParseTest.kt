package com.bofstudios.moneytree.research

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.StringReader

/**
 * A company-facts document cut down to the shapes the real API sends (checked
 * against Apple's and ASML's): quarters inside a 10-K, a restated year, a
 * concept that only appears in old filings, and taxonomies that are skipped.
 */
class SecEdgarParseTest {
    private fun fact(start: String?, end: String, v: Double, form: String = "10-K", filed: String = "2026-01-30") =
        """{"start":${start?.let { "\"$it\"" } ?: "null"},"end":"$end","val":$v,"accn":"x","fy":2025,"fp":"FY","form":"$form","filed":"$filed"}"""

    private val us = """
    {"cik":1,"entityName":"Test Corp","facts":{
      "dei":{"EntityCommonStockSharesOutstanding":{"units":{"shares":[${fact(null, "2025-12-31", 9e9)}]}}},
      "us-gaap":{
        "AccountsPayableCurrent":{"label":"x","units":{"USD":[${fact(null, "2025-12-31", 1.0)}]}},
        "Revenues":{"label":"old","units":{"USD":[${fact("2017-01-01", "2017-12-31", 50.0)}]}},
        "RevenueFromContractWithCustomerExcludingAssessedTax":{"label":"rev","units":{"USD":[
          ${fact("2023-01-01", "2023-12-31", 100.0, filed = "2024-02-01")},
          ${fact("2024-01-01", "2024-12-31", 110.0, filed = "2025-02-01")},
          ${fact("2025-10-01", "2025-12-31", 31.0)},
          ${fact("2025-01-01", "2025-12-31", 121.0)},
          ${fact("2024-01-01", "2024-12-31", 111.0, filed = "2026-01-30")}
        ]}},
        "NetIncomeLoss":{"units":{"USD":[${fact("2024-01-01", "2024-12-31", 20.0)}, ${fact("2025-01-01", "2025-12-31", 24.0)}]}},
        "CostOfRevenue":{"units":{"USD":[${fact("2025-01-01", "2025-12-31", 50.0)}]}},
        "StockholdersEquity":{"units":{"USD":[${fact(null, "2025-12-31", 80.0)}, ${fact(null, "2025-06-30", 70.0, form = "10-Q")}]}},
        "WeightedAverageNumberOfDilutedSharesOutstanding":{"units":{"shares":[${fact("2025-01-01", "2025-12-31", 10.0)}]}},
        "LongTermDebtNoncurrent":{"units":{"USD":[${fact(null, "2025-12-31", 30.0)}]}}
      }}}
    """.trimIndent()

    @Test fun keepsOneRowPerFiscalYearFromAnnualFilingsOnly() {
        val f = SecEdgar.parse("TST", StringReader(us), 7L)!!
        assertEquals("Test Corp", f.name)
        assertEquals("USD", f.currency)
        assertFalse(f.foreign)
        // The 2017 "Revenues" concept is older than the current one: the newer concept wins.
        assertEquals(listOf("2023-12-31", "2024-12-31", "2025-12-31"), f.years.map { it.end })
        val last = f.years.last()
        assertEquals(121.0, last.revenue!!, 1e-9) // the full year, not the quarter inside the 10-K
        assertEquals(111.0, f.years[1].revenue!!, 1e-9) // the later restatement wins
        assertEquals(71.0, last.grossProfit!!, 1e-9) // revenue − cost of revenue
        assertEquals(80.0, last.equity!!, 1e-9) // the 10-Q balance is ignored
        assertEquals(10.0, last.shares!!, 1e-9)
        assertEquals(30.0, last.debt!!, 1e-9)
        assertNull(f.years.first().netIncome)
        assertEquals(7L, f.fetchedAt)
    }

    @Test fun readsIfrsInItsOwnCurrencyAndMarksForeignFilers() {
        val ifrs = """
        {"entityName":"Euro SE","facts":{"ifrs-full":{
          "Revenue":{"units":{"EUR":[${fact("2024-01-01", "2024-12-31", 30.0, form = "20-F")}, ${fact("2025-01-01", "2025-12-31", 33.0, form = "20-F")}]}},
          "ProfitLossAttributableToOwnersOfParent":{"units":{"EUR":[${fact("2025-01-01", "2025-12-31", 9.0, form = "20-F")}]}},
          "AdjustedWeightedAverageShares":{"units":{"shares":[${fact("2025-01-01", "2025-12-31", 3.0, form = "20-F")}]}}
        }}}
        """.trimIndent()
        val f = SecEdgar.parse("EUR", StringReader(ifrs), 0L)!!
        assertEquals("EUR", f.currency)
        assertTrue(f.foreign)
        assertEquals(9.0, f.years.last().netIncome!!, 1e-9)
        assertEquals(3.0, f.years.last().shares!!, 1e-9)
    }

    @Test fun aDocumentWithoutRevenueOrProfitIsNothing() {
        assertNull(SecEdgar.parse("X", StringReader("""{"entityName":"X","facts":{"us-gaap":{}}}"""), 0L))
    }
}
