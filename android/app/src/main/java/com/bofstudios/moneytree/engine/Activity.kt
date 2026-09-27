package com.bofstudios.moneytree.engine

/**
 * The AI monitor's feed: one entry per thing the engine actually did.
 *
 * Each step is opened *before* the work starts and closed when it finishes, so
 * the screen shows a spinner for the length of the real network call — there
 * is no animated progress that is not backed by an actual operation. A step
 * that failed says so and keeps its error.
 */
enum class StepKind { CLOCK, ACCOUNT, POSITIONS, BARS, ANALYSE, NEWS, ORDER, TRAIL, SELL, AI, APPROVAL, WAIT, WARN, INFO }

enum class StepState { RUNNING, DONE, FAILED, INFO }

data class Step(
    val id: Long,
    val kind: StepKind,
    val title: String,
    val state: StepState,
    val startedAt: Long,
    val endedAt: Long? = null,
    val detail: String? = null,
    val lines: List<String> = emptyList(),
)

/** Where the engine reports what it is doing. */
interface Monitor {
    fun begin(kind: StepKind, title: String): StepHandle
    fun info(kind: StepKind, title: String, detail: String? = null, lines: List<String> = emptyList())
}

interface StepHandle {
    fun done(detail: String? = null, lines: List<String> = emptyList())
    fun fail(detail: String)
    /** Update what a still-running step is doing, e.g. which symbol is in flight. */
    fun progress(detail: String) {}
}

/** Runs `block` inside a step: DONE on success, FAILED (and rethrown) on error. */
suspend fun <T> Monitor.step(
    kind: StepKind,
    title: String,
    block: suspend () -> T,
    summary: (T) -> String? = { null },
    lines: (T) -> List<String> = { emptyList() },
): T {
    val handle = begin(kind, title)
    return try {
        val result = block()
        handle.done(summary(result), lines(result))
        result
    } catch (e: Exception) {
        // Stopping the bot mid-step is not an error worth a message.
        handle.fail(if (e is kotlinx.coroutines.CancellationException) "—" else e.message ?: e.javaClass.simpleName)
        throw e
    }
}

/** An in-memory feed, capped, newest last. The Android layer wraps this. */
class MemoryMonitor(
    private val cap: Int = 250,
    private val now: () -> Long = System::currentTimeMillis,
    private val onChange: (List<Step>) -> Unit = {},
) : Monitor {
    private val lock = Any()
    private var nextId = 1L
    private val steps = ArrayList<Step>()

    fun snapshot(): List<Step> = synchronized(lock) { steps.toList() }

    override fun begin(kind: StepKind, title: String): StepHandle {
        val id = add(Step(0, kind, title, StepState.RUNNING, now()))
        return object : StepHandle {
            override fun done(detail: String?, lines: List<String>) =
                update(id) { it.copy(state = StepState.DONE, endedAt = now(), detail = detail, lines = lines) }

            override fun fail(detail: String) =
                update(id) { it.copy(state = StepState.FAILED, endedAt = now(), detail = detail) }

            override fun progress(detail: String) =
                update(id) { if (it.state == StepState.RUNNING) it.copy(detail = detail) else it }
        }
    }

    override fun info(kind: StepKind, title: String, detail: String?, lines: List<String>) {
        add(Step(0, kind, title, StepState.INFO, now(), now(), detail, lines))
    }

    private fun add(step: Step): Long {
        val out: List<Step>
        val id: Long
        synchronized(lock) {
            id = nextId++
            steps.add(step.copy(id = id))
            while (steps.size > cap) steps.removeAt(0)
            out = steps.toList()
        }
        onChange(out)
        return id
    }

    private fun update(id: Long, change: (Step) -> Step) {
        val out: List<Step>
        synchronized(lock) {
            val i = steps.indexOfFirst { it.id == id }
            if (i < 0) return
            steps[i] = change(steps[i])
            out = steps.toList()
        }
        onChange(out)
    }
}
