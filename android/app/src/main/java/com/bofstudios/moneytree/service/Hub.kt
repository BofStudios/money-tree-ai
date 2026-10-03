package com.bofstudios.moneytree.service

import com.bofstudios.moneytree.engine.Brain
import com.bofstudios.moneytree.engine.Engine
import com.bofstudios.moneytree.engine.EngineState
import com.bofstudios.moneytree.engine.MemoryMonitor
import com.bofstudios.moneytree.engine.Step
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.MutableStateFlow

/**
 * Where the background service and the screen meet. Both run in the same
 * process, so this is plain shared state: the service writes, the UI observes.
 */
object Hub {
    val steps = MutableStateFlow<List<Step>>(emptyList())
    val state = MutableStateFlow(EngineState())
    val running = MutableStateFlow(false)

    /**
     * Whether real-money trading is armed. Only ever held here, in memory —
     * never written to disk — so any restart of the app or phone disarms it.
     */
    val armed = MutableStateFlow(false)

    /** The AI monitor's feed. Lives here so it survives the service restarting. */
    val monitor = MemoryMonitor(cap = 300, onChange = { steps.value = it })

    /** "Look now" requests from the screen, e.g. after changing settings. */
    val wake = Channel<Unit>(Channel.CONFLATED)

    /** When the loop will next look at the market, while it is waiting. */
    val nextLookAt = MutableStateFlow<Long?>(null)

    @Volatile var engine: Engine? = null

    /** Self-improvement's live counters, refreshed about once a second while it trains. */
    val evolution = MutableStateFlow(com.bofstudios.moneytree.engine.EvolutionSnapshot())

    /** A newer release on GitHub: version name and APK link. */
    val update = MutableStateFlow<Pair<String, String>?>(null)

    /** The research desk of the running engine, for the screen's "forget" button. */
    @Volatile var brain: Brain? = null
}
