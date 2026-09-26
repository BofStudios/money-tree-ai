package com.bofstudios.moneytree.engine

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import java.util.UUID

data class HeldPosition(
    val position: BrokerPosition,
    val stop: Double?,
    val target: Double?,
    val stopOrderId: String?,
    /** False for anything the owner bought by hand: the bot leaves it alone. */
    val managed: Boolean,
)

data class EngineState(
    val marketOpen: Boolean? = null,
    val nextOpen: Long? = null,
    val nextClose: Long? = null,
    val account: Account? = null,
    val held: List<HeldPosition> = emptyList(),
    val snapshots: List<Snapshot> = emptyList(),
    val approvals: List<Proposal> = emptyList(),
    val suggestions: List<Proposal> = emptyList(),
    val lastScanAt: Long? = null,
    val haltReason: String? = null,
    val lastError: String? = null,
    val baselineEquity: Double? = null,
    /** Recent candles per symbol, for the phone's chart. */
    val bars: Map<String, List<Bar>> = emptyMap(),
)

data class ApprovalResult(val ok: Boolean, val message: String)

/**
 * The trading loop, running on the phone.
 *
 * One `cycle()` is one look at the market: clock, account, positions, bars,
 * analysis, then any trailing, selling or buying. Every one of those is a step
 * in the monitor, opened before the call and closed after it.
 *
 * Rules carried over from the desktop bot, unchanged: the EMA/RSI strategy,
 * ATR stops, risk-based sizing, the trailing stop, the daily loss limit, the
 * position cap, the cooldown, and the autonomy modes. Two things are new
 * because this runs on a phone:
 *  - every buy is a bracket order, so its stop and target are held at Alpaca
 *    and keep working when the phone is off or asleep;
 *  - the bot only manages positions it opened itself.
 */
class Engine(
    private val broker: Broker,
    private val store: EngineStore,
    private val monitor: Monitor,
    private val settings: () -> TradingSettings,
    private val strategy: EmaRsiStrategy = EmaRsiStrategy(),
    private val risk: Risk = Risk(),
    private val notifier: Notifier = SilentNotifier,
    private val explainer: Explainer? = null,
    private val now: () -> Long = System::currentTimeMillis,
    private val pause: suspend (Long) -> Unit = { delay(it) },
    val proposals: ProposalBook = ProposalBook(now = now),
) {
    private val _state = MutableStateFlow(EngineState())
    val state: StateFlow<EngineState> = _state.asStateFlow()

    private val mutex = Mutex()
    private val cooldownUntil = HashMap<String, Long>()
    private val exitReasons = HashMap<String, String>()
    private var lastCycleClosed = false

    /** One look at the market. Returns how long to wait before the next. */
    suspend fun cycle(): Long = mutex.withLock {
        val s = settings()
        val w = Words(s.turkish)
        try {
            expireProposals(w)
            // A closed market is looked at quietly after the first time, so a
            // weekend does not bury the feed under identical steps.
            val quiet = lastCycleClosed
            val clock = maybeStep(quiet, StepKind.CLOCK, w.checkingClock(), { broker.clock() }) {
                if (it.isOpen) w.marketOpen(it.nextClose) else w.marketClosed(it.nextOpen)
            }
            _state.update { it.copy(marketOpen = clock.isOpen, nextOpen = clock.nextOpen, nextClose = clock.nextClose) }

            val account = maybeStep(quiet, StepKind.ACCOUNT, w.readingAccount(), { broker.account() }) {
                w.accountSummary(it)
            }
            if (store.baselineEquity(s.live) == null && account.equity > 0) {
                store.setBaselineEquity(s.live, account.equity)
            }
            _state.update { it.copy(account = account, baselineEquity = store.baselineEquity(s.live)) }

            val (positions, orders) = maybeStep(
                quiet, StepKind.POSITIONS, w.checkingPositions(),
                { broker.positions() to broker.openOrders() },
            ) { w.positionsSummary(it.first.size, it.second.size) }
            val held = reconcile(positions, orders, w)

            if (!clock.isOpen) {
                if (!lastCycleClosed) monitor.info(StepKind.WAIT, w.waitingForOpen(clock.nextOpen))
                lastCycleClosed = true
                _state.update { it.copy(lastError = null) }
                return@withLock (clock.nextOpen - now()).coerceIn(MIN_SLEEP, CLOSED_MAX_SLEEP)
            }
            lastCycleClosed = false

            if (account.blocked) {
                monitor.info(StepKind.WARN, w.accountBlocked())
                return@withLock BLOCKED_SLEEP
            }

            val halt = if (risk.dailyLimitHit(account.equity, account.lastEquity)) {
                w.dailyHalt(account.equity - account.lastEquity, account.lastEquity * risk.config.maxDailyLossPct / 100)
            } else null
            if (halt != null && _state.value.haltReason == null) {
                monitor.info(StepKind.WARN, halt)
                notifier.halted(halt)
            }
            _state.update { it.copy(haltReason = halt) }

            // ------------------------------------------------------------ bars
            val symbols = (s.watchlist + held.filter { it.managed }.map { it.position.symbol }).distinct()
            val tf = s.horizon.timeframe
            val bars = monitor.step(StepKind.BARS, w.fetchingBars(symbols.size, tf), {
                symbols.associateWith { sym -> attempt { broker.bars(sym, tf, BAR_LIMIT) } ?: emptyList() }
            }, { w.barsSummary(it.count { e -> e.value.size >= strategy.warmupBars }, symbols.size) })

            // -------------------------------------------------------- analysis
            val heldBySymbol = held.associateBy { it.position.symbol }
            val signals = LinkedHashMap<String, Signal>()
            val snapshots = ArrayList<Snapshot>()
            val analysis = monitor.begin(StepKind.ANALYSE, w.analysing(symbols.size))
            val lines = ArrayList<String>()
            for (sym in symbols) {
                val b = bars[sym].orEmpty()
                val holding = heldBySymbol[sym]?.managed == true
                val signal = strategy.onBars(b, holding)
                val snap = strategy.snapshot(sym, b)
                signals[sym] = signal
                snapshots += snap
                lines += w.analysisLine(snap, signal)
            }
            analysis.done(
                w.analysisSummary(
                    signals.values.count { it.action == Action.BUY },
                    signals.values.count { it.action == Action.CLOSE },
                ),
                lines,
            )
            _state.update { it.copy(snapshots = snapshots, bars = bars.mapValues { e -> e.value.takeLast(CHART_BARS) }) }
            val price = snapshots.filter { it.ready }.associate { it.symbol to it.price }

            // ------------------------------------------------ manage what's held
            for (h in held.filter { it.managed }) {
                val sym = h.position.symbol
                val signal = signals[sym]
                if (signal?.action == Action.CLOSE) {
                    sell(sym, signal.reason, "signal", orders, w)
                    continue
                }
                val last = price[sym] ?: continue
                val guard = if (h.stopOrderId == null) store.guard(sym) else null
                // A fractional position has no bracket at Alpaca: this phone is
                // its stop-loss and target, checked on every look.
                if (guard != null) {
                    val (stop, target) = guard
                    if (last <= stop) { sell(sym, w.phoneStopHit(stop), "stop-loss", orders, w); continue }
                    if (last >= target) { sell(sym, w.phoneTargetHit(target), "take-profit", orders, w); continue }
                }
                val raised = risk.trailingStop(h.position.avgEntry, h.stop, last) ?: continue
                if (guard != null) {
                    store.setGuard(sym, raised, guard.second)
                    monitor.info(StepKind.TRAIL, w.raisingStop(sym, h.stop, raised), w.heldOnPhone())
                    continue
                }
                val id = h.stopOrderId ?: continue
                attempt {
                    monitor.step(StepKind.TRAIL, w.raisingStop(sym, h.stop, raised), { broker.moveStop(id, raised) })
                }
            }

            // ------------------------------------------------------------ buys
            val buys = signals.filter { it.value.action == Action.BUY && heldBySymbol[it.key] == null }
            if (buys.isNotEmpty()) {
                if (halt != null) {
                    // Already announced above; nothing new is opened today.
                } else {
                    val openBuys = orders.filter { it.side == "buy" }.map { it.symbol }.toSet()
                    var committed = held.count { it.managed } + proposals.pending(ProposalKind.APPROVAL).size + openBuys.size
                    for ((sym, signal) in buys) {
                        if (sym in openBuys || proposals.hasPendingFor(sym)) continue
                        val until = cooldownUntil[sym]
                        if (until != null && now() < until) { monitor.info(StepKind.INFO, w.cooling(sym)); continue }
                        if (committed >= risk.config.maxOpenPositions) {
                            monitor.info(StepKind.INFO, w.capReached(sym, risk.config.maxOpenPositions)); continue
                        }
                        val snap = snapshots.first { it.symbol == sym }
                        val available = minOf(account.cash, account.buyingPower)
                        val entry = risk.plan(sym, signal.reason, snap.price, snap.atr, account.equity, available, s.fractional)
                        if (entry == null) { monitor.info(StepKind.INFO, w.tooSmall(sym)); continue }
                        if (s.live && !s.armed) { monitor.info(StepKind.WARN, w.notArmed(sym)); continue }

                        val headlines = attempt {
                            monitor.step(StepKind.NEWS, w.readingNews(sym), { broker.news(sym, 3) },
                                { w.newsSummary(it.size) }, { list -> list.map { "${it.source}: ${it.headline}" } })
                        } ?: emptyList()

                        when (s.autonomy) {
                            Autonomy.FULL -> {
                                if (place(entry, w, headlines.map { "${it.source}: ${it.headline}" })) committed += 1
                            }
                            Autonomy.SEMI -> proposals.add(ProposalKind.APPROVAL, entry)?.let {
                                monitor.info(StepKind.APPROVAL, w.waitingApproval(entry), entry.reason)
                                notifier.approvalNeeded(it)
                                committed += 1
                            }
                            Autonomy.MANUAL -> proposals.add(ProposalKind.SUGGESTION, entry)?.let {
                                monitor.info(StepKind.INFO, w.suggestion(entry), entry.reason)
                            }
                        }
                    }
                }
            }

            publishProposals()
            _state.update { it.copy(lastScanAt = now(), lastError = null) }
            monitor.info(StepKind.WAIT, w.scanDone(held.count { it.managed }, (OPEN_SLEEP / 1000).toInt()))
            OPEN_SLEEP
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            _state.update { it.copy(lastError = e.message ?: e.javaClass.simpleName) }
            monitor.info(StepKind.WARN, w.cycleFailed(), e.message)
            lastCycleClosed = false
            ERROR_SLEEP
        }
    }

    /** The owner tapped Approve on a semi-auto buy. Re-checked against now. */
    suspend fun approve(id: String): ApprovalResult = mutex.withLock {
        val s = settings()
        val w = Words(s.turkish)
        val p = proposals.take(id) ?: return@withLock ApprovalResult(false, w.approveFailedExpired())
        val sym = p.entry.symbol

        fun fail(why: String): ApprovalResult {
            proposals.finish(p, ProposalStatus.FAILED, why)
            publishProposals()
            val message = w.didNotBuy(sym, why)
            monitor.info(StepKind.WARN, message)
            return ApprovalResult(false, message)
        }

        try {
            if (!broker.clock().isOpen) return@withLock fail(w.approveMarketClosed())
            if (s.live && !s.armed) return@withLock fail(w.approveNotArmed())
            val positions = broker.positions()
            if (positions.any { it.symbol == sym }) return@withLock fail(w.approveHeld(sym))
            val owned = store.ownedSymbols()
            val committed = positions.count { it.symbol in owned } + proposals.pending(ProposalKind.APPROVAL).size
            if (committed >= risk.config.maxOpenPositions) return@withLock fail(w.approveCap(risk.config.maxOpenPositions))

            val price = broker.latestPrice(sym) ?: return@withLock fail(w.approveNoPrice())
            val drift = kotlin.math.abs(price - p.entry.price) / p.entry.price * 100
            if (drift > Words.MAX_DRIFT_PCT) return@withLock fail(w.approveDrift(drift))
            if (price <= p.entry.stop) return@withLock fail(w.approveThroughStop())
            if (price >= p.entry.target) return@withLock fail(w.approveAtTarget())

            val entry = p.entry.copy(price = price)
            if (!place(entry, w, emptyList())) return@withLock fail(w.cycleFailed())
            proposals.finish(p, ProposalStatus.APPROVED)
            publishProposals()
            ApprovalResult(true, w.bought(entry))
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            fail(e.message ?: e.javaClass.simpleName)
        }
    }

    fun skip(id: String): Boolean {
        val done = proposals.skip(id) != null
        publishProposals()
        return done
    }

    /** Waiting requests were raised under the old rules; drop them on a change. */
    fun settingsChanged() {
        proposals.clear("settings changed")
        publishProposals()
    }

    // ------------------------------------------------------------- internals

    private suspend fun place(entry: Entry, w: Words, headlines: List<String>): Boolean {
        val order = attempt {
            val clientId = "mt-" + UUID.randomUUID().toString().take(24)
            if (entry.fractional) {
                monitor.step(StepKind.ORDER, w.placingFractional(entry),
                    { broker.buyFractional(entry, clientId) }, { w.fractionalAccepted(it.status) })
            } else {
                monitor.step(StepKind.ORDER, w.placingBracket(entry),
                    { broker.buyBracket(entry, clientId) }, { w.orderAccepted(it.status) })
            }
        } ?: return false
        store.addOwned(entry.symbol)
        if (entry.fractional) store.setGuard(entry.symbol, entry.stop, entry.target)
        notifier.orderPlaced(entry)

        val ai = explainer ?: return order.id.isNotEmpty()
        val facts = buildString {
            append("Bought ${entry.qtyText} ${entry.symbol} at about ${entry.price}. ")
            append("Rule that fired: ${entry.reason}. ")
            append("Stop-loss ${"%.2f".format(java.util.Locale.US, entry.stop)}, target ${"%.2f".format(java.util.Locale.US, entry.target)}. ")
            append("Money at risk if the stop fills: ${"%.2f".format(java.util.Locale.US, entry.riskCash)}. ")
            if (headlines.isNotEmpty()) append("Recent headlines: ${headlines.joinToString("; ")}.")
        }
        attempt {
            monitor.step(StepKind.AI, w.askingAi(), { ai.explain(facts, w.tr) }, { it })
        }
        return true
    }

    private suspend fun sell(symbol: String, reason: String, why: String, orders: List<BrokerOrder>, w: Words) {
        attempt {
            monitor.step(StepKind.SELL, w.selling(symbol, reason), {
                // The bracket's legs reserve the shares; cancel them or the sell is refused.
                orders.flatMap { it.flatten() }
                    .filter { it.symbol == symbol && it.side == "sell" }
                    .forEach { broker.cancelOrder(it.id) }
                // Cancels settle asynchronously; wait until the legs are gone.
                for (attempt in 0 until 10) {
                    val still = broker.openOrders().flatMap { o -> o.flatten() }
                        .any { it.symbol == symbol && it.side == "sell" }
                    if (!still) break
                    pause(500)
                }
                exitReasons[symbol] = why
                broker.closePosition(symbol)
            }, { w.sold() })
        }
    }

    /** Positions as the broker has them, plus what vanished since last time. */
    private suspend fun reconcile(positions: List<BrokerPosition>, orders: List<BrokerOrder>, w: Words): List<HeldPosition> {
        val owned = store.ownedSymbols()
        val bySymbol = positions.associateBy { it.symbol }
        val allOrders = orders.flatMap { it.flatten() }

        for (sym in owned) {
            if (sym in bySymbol) continue
            // A bracket that has not filled yet has an open buy and no position.
            if (allOrders.any { it.symbol == sym && it.side == "buy" }) continue
            store.removeOwned(sym)
            store.clearGuard(sym)
            cooldownUntil[sym] = now() + risk.config.cooldownMinutes * 60_000
            val trade = attempt { lastRoundTrip(sym) }
            if (trade != null) {
                store.addTrade(trade)
                notifier.positionClosed(trade)
                monitor.info(StepKind.SELL, w.closedAtBroker(trade), w.closedDetail(trade))
            }
            exitReasons.remove(sym)
        }

        val managed = store.ownedSymbols()
        val held = positions.map { p ->
            val sells = allOrders.filter { it.symbol == p.symbol && it.side == "sell" }
            val stopOrder = sells.firstOrNull { it.type.startsWith("stop") || it.type == "trailing_stop" }
            val targetOrder = sells.firstOrNull { it.type == "limit" }
            HeldPosition(
                position = p,
                stop = stopOrder?.stopPrice ?: store.guard(p.symbol)?.first,
                target = targetOrder?.limitPrice ?: store.guard(p.symbol)?.second,
                stopOrderId = stopOrder?.id,
                managed = p.symbol in managed,
            )
        }
        _state.update { it.copy(held = held) }
        return held
    }

    /** The most recent buy the bot made in `symbol` and the sell that closed it. */
    private suspend fun lastRoundTrip(symbol: String): TradeRecord? {
        val recent = broker.recentOrders(symbol, 20)
        val buy = recent.firstOrNull { it.side == "buy" && it.clientId.startsWith("mt-") && it.filledAvgPrice != null }
            ?: return null
        val sell = recent.flatMap { it.flatten() }
            .filter { it.side == "sell" && it.filledAvgPrice != null && it.filledAt >= buy.filledAt }
            .maxByOrNull { it.filledAt } ?: return null
        val reason = exitReasons[symbol] ?: when {
            sell.type.startsWith("stop") || sell.type == "trailing_stop" -> "stop-loss"
            sell.type == "limit" -> "take-profit"
            else -> "closed"
        }
        return TradeRecord(
            symbol = symbol,
            qty = if (sell.filledQty > 0) sell.filledQty else buy.filledQty,
            entry = buy.filledAvgPrice!!,
            exit = sell.filledAvgPrice!!,
            reason = reason,
            closedAt = sell.filledAt,
        )
    }

    private fun expireProposals(w: Words) {
        for (p in proposals.expire()) {
            if (p.kind == ProposalKind.APPROVAL) monitor.info(StepKind.INFO, w.approvalExpired(p.entry.symbol))
        }
        publishProposals()
    }

    private fun publishProposals() {
        _state.update {
            it.copy(
                approvals = proposals.pending(ProposalKind.APPROVAL),
                suggestions = proposals.pending(ProposalKind.SUGGESTION),
            )
        }
    }

    private suspend fun <T> maybeStep(
        quiet: Boolean, kind: StepKind, title: String,
        block: suspend () -> T, summary: (T) -> String?,
    ): T = if (quiet) block() else monitor.step(kind, title, block, summary)

    companion object {
        const val BAR_LIMIT = 300
        const val CHART_BARS = 90
        const val OPEN_SLEEP = 60_000L
        const val ERROR_SLEEP = 60_000L
        const val BLOCKED_SLEEP = 5 * 60_000L
        const val MIN_SLEEP = 60_000L
        const val CLOSED_MAX_SLEEP = 3 * 60 * 60_000L
    }
}

/**
 * Like runCatching, but never swallows cancellation: stopping the service must
 * stop the engine, not be mistaken for one failed network call.
 */
internal suspend fun <T> attempt(block: suspend () -> T): T? = try {
    block()
} catch (e: CancellationException) {
    throw e
} catch (e: Exception) {
    null
}
