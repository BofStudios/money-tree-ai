package com.bofstudios.moneytree.ai

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class GroqVerdictTest {
    @Test fun anOkLetsTheBuyThrough() {
        val v = GroqExplainer.parseVet("{\"verdict\":\"OK\",\"reason\":\"routine news\"}")!!
        assertTrue(v.ok)
        assertEquals("routine news", v.note)
    }

    @Test fun aSkipCarriesItsReason() {
        val v = GroqExplainer.parseVet("Here you go: {\"verdict\": \"skip\", \"reason\": \"Earnings are due tomorrow.\"} ")!!
        assertFalse(v.ok)
        assertEquals("Earnings are due tomorrow.", v.note)
    }

    @Test fun anythingUnreadableIsNoVerdictNotASkip() {
        assertNull(GroqExplainer.parseVet("I think it's fine"))
        assertNull(GroqExplainer.parseVet("{\"verdict\":\"MAYBE\"}"))
        assertNull(GroqExplainer.parseVet("{ broken"))
    }
}
