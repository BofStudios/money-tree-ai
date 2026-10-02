package com.bofstudios.moneytree.ai

import com.bofstudios.moneytree.engine.NewsItem
import com.bofstudios.moneytree.engine.Researcher
import com.bofstudios.moneytree.engine.Vet
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class AiCommitteeTest {
    private fun member(v: Vet?) = Researcher { _, _, _, _ -> v }
    private suspend fun vote(vararg votes: Vet?) =
        AiCommittee(votes.mapIndexed { i, v -> "m$i" to member(v) }).vet("AAA", "facts", listOf("h"), false)

    @Test fun eitherMemberCanStopABuy() = runTest {
        val v = vote(Vet(true, "fine"), Vet(false, "earnings tomorrow"))!!
        assertFalse(v.ok)
        assertTrue(v.note.contains("m1: earnings tomorrow"))
    }

    @Test fun bothOkLetsItThrough() = runTest {
        assertTrue(vote(Vet(true, ""), Vet(true, "routine"))!!.ok)
    }

    @Test fun aSilentMemberDoesNotVote() = runTest {
        assertTrue(vote(null, Vet(true, "ok"))!!.ok)
        assertNull(vote(null, null))
    }

    @Test fun headlineScoresAreReadByNumberAndClamped() {
        val items = listOf(NewsItem(10, "a", "", "", listOf("A"), 0), NewsItem(20, "b", "", "", listOf("B"), 0))
        val s = GroqExplainer.parseScores("<think>hmm</think>{\"scores\":[{\"n\":1,\"s\":0.5},{\"n\":2,\"s\":-3},{\"n\":9,\"s\":1}]}", items)
        assertEquals(mapOf(10L to 0.5, 20L to -1.0), s)
        assertTrue(GroqExplainer.parseScores("no json", items).isEmpty())
    }
}
