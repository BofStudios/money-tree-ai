package com.bofstudios.moneytree.service

import android.app.NotificationManager
import android.content.Context
import androidx.core.app.NotificationCompat
import com.bofstudios.moneytree.MoneyTreeApp
import com.bofstudios.moneytree.R
import com.bofstudios.moneytree.engine.Entry
import com.bofstudios.moneytree.engine.Notifier
import com.bofstudios.moneytree.engine.NotifyLevel
import com.bofstudios.moneytree.engine.Proposal
import com.bofstudios.moneytree.engine.TradeRecord
import com.bofstudios.moneytree.engine.TradingSettings
import com.bofstudios.moneytree.engine.Words

/**
 * Puts the bot's moments on the lock screen, filtered by the owner's level:
 *
 *  - EVERYTHING: buys, sells, the day's summary, plus silent notes on what it
 *    is researching, stops it raised and buys the AI called off;
 *  - TRADES: buys, sells and the summary only;
 *  - QUIET: nothing but approvals and warnings.
 *
 * Approvals and warnings (the daily loss limit) always come through.
 */
class AndroidNotifier(private val context: Context, private val settings: () -> TradingSettings) : Notifier {
    private val nm = context.getSystemService(NotificationManager::class.java)
    private var seq = 20_000
    /** The last buy per symbol, so the AI's note can be added to the same notification. */
    private val buys = HashMap<String, Pair<String, String>>()

    private fun words() = Words(settings().turkish)
    private fun level() = settings().notify

    override fun approvalNeeded(p: Proposal) {
        val w = words()
        val e = p.entry
        val text = w.waitingApproval(e) + "\nStop ${w.usd(e.stop)} · " +
            (if (w.tr) "Hedef " else "Target ") + w.usd(e.target) + "\n" + e.reason
        val code = EngineService.approvalNotificationId(p.id)
        nm.notify(code, NotificationCompat.Builder(context, MoneyTreeApp.CHANNEL_ALERTS)
            .setSmallIcon(R.drawable.ic_stat_tree)
            .setContentTitle(if (w.tr) "${e.symbol} alınsın mı?" else "Buy ${e.symbol}?")
            .setContentText(w.waitingApproval(e))
            .setStyle(NotificationCompat.BigTextStyle().bigText(text))
            .setTimeoutAfter(p.expiresAt - System.currentTimeMillis())
            .setContentIntent(EngineService.openApp(context))
            .addAction(0, if (w.tr) "Onayla" else "Approve",
                EngineService.serviceIntent(context, EngineService.ACTION_APPROVE, p.id, code))
            .addAction(0, if (w.tr) "Geç" else "Skip",
                EngineService.serviceIntent(context, EngineService.ACTION_SKIP, p.id, code + 1))
            .build())
    }

    override fun orderPlaced(e: Entry) {
        if (level() == NotifyLevel.QUIET) return
        val w = words()
        val title = w.justBoughtTitle(e)
        val text = w.justBoughtText(e)
        buys[e.symbol] = title to text
        post(MoneyTreeApp.CHANNEL_TRADES, buyId(e.symbol), title, text)
    }

    override fun explained(symbol: String, text: String) {
        if (level() == NotifyLevel.QUIET) return
        val (title, body) = buys[symbol] ?: return
        // Same id: the buy notification gains the AI's note instead of buzzing twice.
        post(MoneyTreeApp.CHANNEL_TRADES, buyId(symbol), title, "$body\n\n🤖 $text", silent = true)
    }

    override fun positionClosed(t: TradeRecord) {
        if (level() == NotifyLevel.QUIET) return
        val w = words()
        post(MoneyTreeApp.CHANNEL_TRADES, seq++, w.justSoldTitle(t), w.justSoldText(t))
    }

    override fun halted(message: String) = post(MoneyTreeApp.CHANNEL_ALERTS, seq++, "Money Tree", message)

    override fun researching(symbol: String, line: String) {
        if (level() != NotifyLevel.EVERYTHING) return
        post(MoneyTreeApp.CHANNEL_ACTIVITY, researchId(symbol), words().researchingTitle(symbol), line, silent = true)
    }

    override fun stopRaised(symbol: String, from: Double?, to: Double, lockedIn: Double?) {
        if (level() != NotifyLevel.EVERYTHING) return
        val w = words()
        post(MoneyTreeApp.CHANNEL_ACTIVITY, stopId(symbol), w.stopRaisedTitle(symbol, to), w.stopRaisedText(from, lockedIn), silent = true)
    }

    override fun aiSkipped(symbol: String, why: String) {
        if (level() != NotifyLevel.EVERYTHING) return
        post(MoneyTreeApp.CHANNEL_ACTIVITY, researchId(symbol), words().aiSkipped(symbol), why, silent = true)
    }

    override fun heldBack(symbol: String, why: String) {
        if (level() != NotifyLevel.EVERYTHING) return
        post(MoneyTreeApp.CHANNEL_ACTIVITY, researchId(symbol), words().heldBack(symbol), why, silent = true)
    }

    override fun learned(title: String, text: String) {
        if (level() == NotifyLevel.QUIET) return
        post(MoneyTreeApp.CHANNEL_ACTIVITY, LEARNED_ID + (seq++ % 50), "🧠 $title", text, silent = true)
    }

    override fun briefing(title: String, text: String) {
        if (level() == NotifyLevel.QUIET) return
        post(MoneyTreeApp.CHANNEL_TRADES, BRIEFING_ID, "☀ $title", text, silent = true)
    }

    override fun orderFailed(symbol: String, why: String) {
        if (level() == NotifyLevel.QUIET) return
        post(MoneyTreeApp.CHANNEL_TRADES, seq++, words().orderFailedTitle(symbol), why)
    }

    override fun dailySummary(trades: List<TradeRecord>, today: Double, equity: Double) {
        if (level() == NotifyLevel.QUIET) return
        val w = words()
        post(MoneyTreeApp.CHANNEL_TRADES, SUMMARY_ID, w.dailySummaryTitle(trades.size, today), w.dailySummaryDetail(trades, equity))
    }

    private fun post(channel: String, id: Int, title: String, text: String, silent: Boolean = false) {
        nm.notify(id, NotificationCompat.Builder(context, channel)
            .setSmallIcon(R.drawable.ic_stat_tree)
            .setContentTitle(title)
            .setContentText(text.lineSequence().first())
            .setStyle(NotificationCompat.BigTextStyle().bigText(text))
            .setAutoCancel(true)
            .setSilent(silent)
            .setContentIntent(EngineService.openApp(context))
            .build())
    }

    private fun buyId(symbol: String) = 10_000 + (symbol.hashCode() and 0x3ff)
    private fun researchId(symbol: String) = 11_000 + (symbol.hashCode() and 0x3ff)
    private fun stopId(symbol: String) = 12_000 + (symbol.hashCode() and 0x3ff)

    companion object {
        // Approvals use 1000–5095 (EngineService.approvalNotificationId).
        private const val SUMMARY_ID = 9_000
        private const val LEARNED_ID = 13_000
        private const val BRIEFING_ID = 9_001
    }
}
