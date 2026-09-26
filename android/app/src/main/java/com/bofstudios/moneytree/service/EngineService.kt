package com.bofstudios.moneytree.service

import android.app.Notification
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import com.bofstudios.moneytree.MoneyTreeApp
import com.bofstudios.moneytree.R
import com.bofstudios.moneytree.ai.GroqExplainer
import com.bofstudios.moneytree.broker.AlpacaBroker
import com.bofstudios.moneytree.data.Prefs
import com.bofstudios.moneytree.data.SecureStore
import com.bofstudios.moneytree.engine.Engine
import com.bofstudios.moneytree.engine.EngineState
import com.bofstudios.moneytree.engine.Entry
import com.bofstudios.moneytree.engine.Notifier
import com.bofstudios.moneytree.engine.Proposal
import com.bofstudios.moneytree.engine.StepKind
import com.bofstudios.moneytree.engine.TradeRecord
import com.bofstudios.moneytree.engine.Words
import com.bofstudios.moneytree.ui.MainActivity
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeoutOrNull
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * The trading loop as a foreground service: it keeps running with the app
 * closed and shows an ongoing notification, the way a music player does.
 *
 * What happens when the phone sleeps or dies: Android may slow the loop, and a
 * dead battery stops it. The positions it opened are still protected, because
 * each one's stop-loss and target were placed at Alpaca as a bracket order.
 */
class EngineService : Service() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    private var loop: Job? = null
    private lateinit var prefs: Prefs

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        prefs = Prefs(this)
        goForeground(ongoing(Hub.state.value))
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        goForeground(ongoing(Hub.state.value))
        when (intent?.action) {
            ACTION_STOP -> { stopBot(); return START_NOT_STICKY }
            ACTION_APPROVE -> intent.getStringExtra(EXTRA_ID)?.let { approve(it) }
            ACTION_SKIP -> intent.getStringExtra(EXTRA_ID)?.let { id ->
                Hub.engine?.skip(id)
                notifications().cancel(approvalNotificationId(id))
            }
            ACTION_SCAN -> Hub.wake.trySend(Unit)
            // Paper <-> real swaps the broker and its keys: rebuild the engine.
            ACTION_RESTART -> { loop?.cancel(); loop = null; Hub.engine = null }
        }
        startLoop()
        return START_STICKY
    }

    override fun onDestroy() {
        scope.cancel()
        Hub.engine = null
        Hub.running.value = false
        super.onDestroy()
    }

    // ------------------------------------------------------------------ loop

    private fun startLoop() {
        if (loop?.isActive == true) return
        val settings = prefs.settings(armed = false)
        val words = Words(settings.turkish)
        // Every start is disarmed. Real money needs a fresh Arm each time.
        Hub.armed.value = false

        val secure = SecureStore(this)
        val key = secure.get(if (settings.live) SecureStore.LIVE_KEY else SecureStore.PAPER_KEY)
        val secret = secure.get(if (settings.live) SecureStore.LIVE_SECRET else SecureStore.PAPER_SECRET)
        if (key == null || secret == null) {
            Hub.monitor.info(StepKind.WARN, noKeys(settings.turkish))
            stopBot()
            return
        }

        val engine = Engine(
            broker = AlpacaBroker(key, secret, live = settings.live),
            store = prefs,
            monitor = Hub.monitor,
            settings = { prefs.settings(Hub.armed.value) },
            notifier = AndroidNotifier(this) { prefs.settings(false).turkish },
            explainer = secure.get(SecureStore.GROQ_KEY)?.let { GroqExplainer(it) },
        )
        Hub.engine = engine
        Hub.running.value = true
        prefs.runWanted = true

        loop = scope.launch {
            launch {
                engine.state.collect {
                    Hub.state.value = it
                    notifications().notify(ONGOING_ID, ongoing(it))
                }
            }
            Hub.monitor.info(StepKind.INFO, words.started(settings))
            val power = getSystemService(Context.POWER_SERVICE) as PowerManager
            while (isActive) {
                // Hold the CPU awake for one look at the market, never longer.
                val lock = power.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "moneytree:cycle")
                lock.acquire(3 * 60_000L)
                val sleep = try { engine.cycle() } finally { if (lock.isHeld) lock.release() }
                withTimeoutOrNull(sleep) { Hub.wake.receive() }
            }
        }
    }

    private fun stopBot() {
        prefs.runWanted = false
        loop?.cancel()
        Hub.engine = null
        Hub.running.value = false
        Hub.armed.value = false
        ServiceCompat.stopForeground(this, ServiceCompat.STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    private fun approve(id: String) {
        val engine = Hub.engine ?: return
        scope.launch {
            val result = engine.approve(id)
            notifications().cancel(approvalNotificationId(id))
            notifications().notify(
                RESULT_ID,
                alert(if (result.ok) "✓" else "✕", result.message),
            )
        }
    }

    // --------------------------------------------------------- notifications

    private fun notifications() = getSystemService(NotificationManager::class.java)

    private fun goForeground(n: Notification) {
        val type = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE)
            ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE else 0
        ServiceCompat.startForeground(this, ONGOING_ID, n, type)
    }

    private fun ongoing(state: EngineState): Notification {
        val s = prefs.settings(Hub.armed.value)
        val w = Words(s.turkish)
        val time = SimpleDateFormat("HH:mm", Locale.getDefault())
        val title = buildString {
            append("Money Tree · ")
            append(if (s.live) (if (s.turkish) "GERÇEK" else "REAL") else "paper")
            append(" · ").append(w.autonomyName(s.autonomy))
        }
        val text = when {
            state.lastError != null -> (if (s.turkish) "Sorun: " else "Problem: ") + state.lastError
            state.marketOpen == false && state.nextOpen != null -> w.marketClosed(state.nextOpen!!)
            state.lastScanAt != null -> (if (s.turkish) "${s.watchlist.size} hisse izleniyor · son bakış " else
                "Watching ${s.watchlist.size} · last look ") + time.format(Date(state.lastScanAt!!))
            else -> if (s.turkish) "Başlıyor…" else "Starting…"
        }
        return NotificationCompat.Builder(this, MoneyTreeApp.CHANNEL_ENGINE)
            .setSmallIcon(R.drawable.ic_stat_tree)
            .setContentTitle(title)
            .setContentText(text)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setContentIntent(openApp(this))
            .addAction(0, if (s.turkish) "Durdur" else "Stop", serviceIntent(this, ACTION_STOP, null, 1))
            .build()
    }

    private fun alert(title: String, text: String): Notification =
        NotificationCompat.Builder(this, MoneyTreeApp.CHANNEL_ALERTS)
            .setSmallIcon(R.drawable.ic_stat_tree)
            .setContentTitle(title)
            .setContentText(text)
            .setStyle(NotificationCompat.BigTextStyle().bigText(text))
            .setAutoCancel(true)
            .setContentIntent(openApp(this))
            .build()

    private fun noKeys(tr: Boolean) =
        if (tr) "Alpaca anahtarı yok — Ayarlar'dan ekle" else "No Alpaca keys yet — add them in Settings"

    companion object {
        const val ACTION_STOP = "stop"
        const val ACTION_APPROVE = "approve"
        const val ACTION_SKIP = "skip"
        const val ACTION_SCAN = "scan"
        const val ACTION_RESTART = "restart"
        const val EXTRA_ID = "id"
        private const val ONGOING_ID = 1
        private const val RESULT_ID = 2

        fun start(context: Context) =
            ContextCompat.startForegroundService(context, Intent(context, EngineService::class.java))

        fun stop(context: Context) =
            ContextCompat.startForegroundService(context, Intent(context, EngineService::class.java).setAction(ACTION_STOP))

        fun restart(context: Context) =
            ContextCompat.startForegroundService(context, Intent(context, EngineService::class.java).setAction(ACTION_RESTART))

        fun scanNow(context: Context) {
            if (Hub.running.value) Hub.wake.trySend(Unit)
        }

        fun approvalNotificationId(id: String) = 1000 + (id.hashCode() and 0xfff)

        internal fun serviceIntent(context: Context, action: String, id: String?, code: Int): PendingIntent =
            PendingIntent.getForegroundService(
                context, code,
                Intent(context, EngineService::class.java).setAction(action).apply { id?.let { putExtra(EXTRA_ID, it) } },
                PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
            )

        internal fun openApp(context: Context): PendingIntent =
            PendingIntent.getActivity(
                context, 0,
                Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
                PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
            )
    }
}

/** Puts approvals, fills and halts on the lock screen. */
class AndroidNotifier(private val context: Context, private val turkish: () -> Boolean) : Notifier {
    private val nm = context.getSystemService(NotificationManager::class.java)
    private var seq = 5000

    override fun approvalNeeded(p: Proposal) {
        val w = Words(turkish())
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
        val w = Words(turkish())
        post(if (w.tr) "${e.qtyText} ${e.symbol} alındı" else "Bought ${e.qtyText} ${e.symbol}",
            "~${w.usd(e.price)} · stop ${w.usd(e.stop)} · " + (if (w.tr) "hedef " else "target ") + w.usd(e.target))
    }

    override fun positionClosed(t: TradeRecord) {
        val w = Words(turkish())
        post(w.closedAtBroker(t), w.closedDetail(t))
    }

    override fun halted(message: String) = post("Money Tree", message)

    private fun post(title: String, text: String) {
        nm.notify(seq++, NotificationCompat.Builder(context, MoneyTreeApp.CHANNEL_ALERTS)
            .setSmallIcon(R.drawable.ic_stat_tree)
            .setContentTitle(title)
            .setContentText(text)
            .setStyle(NotificationCompat.BigTextStyle().bigText(text))
            .setAutoCancel(true)
            .setContentIntent(EngineService.openApp(context))
            .build())
    }
}

/** Brings the bot back after a reboot, if it was running before. */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == Intent.ACTION_BOOT_COMPLETED && Prefs(context).runWanted) {
            EngineService.start(context)
        }
    }
}
