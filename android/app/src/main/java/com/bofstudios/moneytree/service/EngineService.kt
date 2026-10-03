package com.bofstudios.moneytree.service

import android.app.Notification
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.net.ConnectivityManager
import android.net.Network
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import com.bofstudios.moneytree.MoneyTreeApp
import com.bofstudios.moneytree.R
import com.bofstudios.moneytree.ai.AiCommittee
import com.bofstudios.moneytree.ai.GroqExplainer
import com.bofstudios.moneytree.broker.AlpacaBroker
import com.bofstudios.moneytree.data.BrainFiles
import com.bofstudios.moneytree.data.Prefs
import com.bofstudios.moneytree.data.SecureStore
import com.bofstudios.moneytree.engine.Brain
import com.bofstudios.moneytree.engine.Engine
import com.bofstudios.moneytree.research.Frankfurter
import com.bofstudios.moneytree.research.SecEdgar
import com.bofstudios.moneytree.research.Wikipedia
import com.bofstudios.moneytree.engine.TrainMode
import android.content.IntentFilter
import android.os.BatteryManager
import android.os.SystemClock
import kotlinx.coroutines.delay
import com.bofstudios.moneytree.engine.EngineState
import com.bofstudios.moneytree.engine.StepKind
import com.bofstudios.moneytree.engine.StepState
import com.bofstudios.moneytree.engine.Step
import com.bofstudios.moneytree.engine.Words
import com.bofstudios.moneytree.ui.MainActivity
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.distinctUntilChanged
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
 * Staying up around the clock on a phone takes three things beyond that:
 *  - while the market is open the CPU is held awake, because Android's Doze
 *    otherwise stretches a one-minute wait into many minutes with the screen
 *    off; while it is closed the CPU may sleep and an alarm wakes the loop
 *    just before the open;
 *  - a heartbeat alarm restarts the service if Android killed it, and a boot
 *    or app-update receiver brings it back after those;
 *  - when the network comes back after a failed look, it looks again at once.
 *
 * A restart that the owner did not start themselves always comes back with
 * real money disarmed, and says so on the lock screen.
 */
class EngineService : Service() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    private var loop: Job? = null
    private lateinit var prefs: Prefs
    private var networkCallback: ConnectivityManager.NetworkCallback? = null
    private var sessionLock: PowerManager.WakeLock? = null
    private var trainLock: PowerManager.WakeLock? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        prefs = Prefs(this)
        goForeground(ongoing(Hub.state.value, Hub.steps.value))
        watchNetwork()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        goForeground(ongoing(Hub.state.value, Hub.steps.value))
        // No intent means Android restarted the service after killing it.
        val auto = intent == null || intent.getStringExtra(EXTRA_SOURCE) == SOURCE_AUTO
        val action = intent?.action
        if (action == ACTION_STOP) { stopBot(); return START_NOT_STICKY }
        // Stop means stop. A button on an old notification (Approve, Skip, Look
        // now) or an automatic restart must never bring back a bot the owner
        // stopped: only Start in the app does. Before 3.0 these fell through to
        // starting the loop again.
        if (!prefs.runWanted && (action != null || auto)) {
            intent?.getStringExtra(EXTRA_ID)?.let { notifications().cancel(approvalNotificationId(it)) }
            if (loop?.isActive != true) {
                ServiceCompat.stopForeground(this, ServiceCompat.STOP_FOREGROUND_REMOVE)
                stopSelf()
            }
            return START_NOT_STICKY
        }
        when (action) {
            ACTION_APPROVE -> intent.getStringExtra(EXTRA_ID)?.let { approve(it) }
            ACTION_SKIP -> intent.getStringExtra(EXTRA_ID)?.let { id ->
                Hub.engine?.skip(id)
                notifications().cancel(approvalNotificationId(id))
            }
            ACTION_SCAN -> Hub.wake.trySend(Unit)
            // Paper <-> real swaps the broker and its keys: rebuild the engine.
            ACTION_RESTART -> { loop?.cancel(); loop = null; Hub.engine = null }
        }
        startLoop(auto)
        Alarms.scheduleHeartbeat(this)
        return START_STICKY
    }

    override fun onDestroy() {
        networkCallback?.let { cb -> runCatching { getSystemService(ConnectivityManager::class.java).unregisterNetworkCallback(cb) } }
        releaseSession()
        scope.cancel()
        Hub.engine = null
        Hub.brain = null
        Hub.running.value = false
        super.onDestroy()
    }

    // ------------------------------------------------------------------ loop

    private fun startLoop(auto: Boolean) {
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

        val groq = secure.get(SecureStore.GROQ_KEY)
        val ai = groq?.let { GroqExplainer(it) }
        // Two different models vote on every buy; either can stop it.
        val committee = groq?.let { AiCommittee(listOf("gpt-oss" to GroqExplainer(it, GroqExplainer.BIG), "qwen" to GroqExplainer(it, GroqExplainer.SECOND))) }
        val brainFiles = BrainFiles(java.io.File(filesDir, "brain"))
        val sec = SecEdgar(brainFiles)
        val brain = Brain(
            store = brainFiles,
            filings = sec,
            fx = Frankfurter(),
            scorer = groq?.let { GroqExplainer(it, GroqExplainer.SMALL) },
            analyst = ai,
            coach = ai,
            events = sec,
            attention = Wikipedia(brainFiles),
        )
        val engine = Engine(
            broker = AlpacaBroker(key, secret, live = settings.live),
            store = prefs,
            monitor = Hub.monitor,
            settings = { prefs.settings(Hub.armed.value) },
            notifier = AndroidNotifier(this) { prefs.settings(false) },
            explainer = ai,
            researcher = committee,
            brain = brain,
            // Checked right before every order is sent: once Stop is pressed,
            // a look that is already halfway through cannot buy.
            allowed = { Hub.running.value && prefs.runWanted },
        )
        Hub.engine = engine
        Hub.brain = brain
        Hub.running.value = true
        prefs.runWanted = true

        if (auto && settings.live) {
            // It came back on its own: say that real money is paused until the owner arms it.
            notifications().notify(REARM_ID, alert(words.restartedDisarmedTitle(), words.restartedDisarmedText()))
        }

        loop = scope.launch {
            launch {
                engine.state.collect { Hub.state.value = it }
            }
            launch(Dispatchers.Default) { train(brain, engine) }
            launch {
                // The ongoing notification says what the bot is doing right now.
                combine(Hub.state, Hub.steps) { state, steps -> ongoingText(state, steps) }
                    .distinctUntilChanged()
                    .collect { notifications().notify(ONGOING_ID, ongoing(Hub.state.value, Hub.steps.value)) }
            }
            Hub.monitor.info(StepKind.INFO, words.started(settings))
            val power = getSystemService(Context.POWER_SERVICE) as PowerManager
            // The first look after starting is always a full one: the owner just
            // pressed Start and should see the bot actually work.
            var asked = true
            while (isActive) {
                Hub.nextLookAt.value = null
                // Hold the CPU awake for one look at the market, never longer.
                val lock = power.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "moneytree:cycle")
                lock.acquire(3 * 60_000L)
                val sleep = try { engine.cycle(forceLook = asked) } finally { if (lock.isHeld) lock.release() }
                val state = engine.state.value
                val openSoon = state.nextOpen?.let { it - System.currentTimeMillis() < OPEN_EARLY_MS } == true
                if (state.marketOpen == true || openSoon) {
                    holdSession(power)
                } else {
                    releaseSession()
                    // Sleep freely, but be woken a few minutes before the open.
                    state.nextOpen?.let { open -> Alarms.scheduleOpen(this@EngineService, open - OPEN_EARLY_MS + 60_000L) }
                }
                // The real time of the next look, for the Live tab's countdown.
                Hub.nextLookAt.value = System.currentTimeMillis() + sleep
                asked = withTimeoutOrNull(sleep) { Hub.wake.receive() } != null
            }
        }
    }

    /**
     * Self-improvement, around the clock: one generation after another of
     * strategy settings bred and replayed on months of candles. On the charger
     * (or when the owner allows it on battery) it runs at about 80% of one
     * core and keeps the CPU awake to do it; on battery it takes about a
     * tenth of that and lets the phone sleep.
     */
    private suspend fun train(brain: Brain, engine: Engine) {
        val power = getSystemService(Context.POWER_SERVICE) as PowerManager
        var lastPublish = 0L
        var charging = false
        var checkedAt = 0L
        try {
            while (true) {
                val s = prefs.settings(false)
                val evo = brain.evolution
                if (!s.selfImprove || !evo.ready) {
                    evo.mode = if (!s.selfImprove) TrainMode.OFF else TrainMode.WAITING
                    releaseTrain()
                    Hub.evolution.value = evo.snapshot()
                    delay(15_000)
                    continue
                }
                if (SystemClock.elapsedRealtime() - checkedAt > 10_000) { charging = isCharging(); checkedAt = SystemClock.elapsedRealtime() }
                val full = charging || s.trainOnBattery
                evo.mode = if (full) TrainMode.FULL else TrainMode.LIGHT
                if (full) holdTrain(power) else releaseTrain()
                val started = SystemClock.elapsedRealtime()
                brain.train()?.let { engine.announce(it) }
                val took = SystemClock.elapsedRealtime() - started
                if (SystemClock.elapsedRealtime() - lastPublish > 1000) {
                    Hub.evolution.value = evo.snapshot()
                    lastPublish = SystemClock.elapsedRealtime()
                }
                delay(if (full) took / 4 + 1 else took * 9 + 50)
            }
        } finally {
            releaseTrain()
        }
    }

    private fun isCharging(): Boolean =
        (registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))?.getIntExtra(BatteryManager.EXTRA_PLUGGED, 0) ?: 0) != 0

    private fun holdTrain(power: PowerManager) {
        val lock = trainLock
        if (lock != null && lock.isHeld) return
        trainLock = power.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "moneytree:train").apply { acquire(TRAIN_LOCK_MS) }
    }

    private fun releaseTrain() {
        trainLock?.let { if (it.isHeld) it.release() }
        trainLock = null
    }

    /** Keeps the CPU awake through the trading session, so one-minute looks stay one minute. */
    private fun holdSession(power: PowerManager) {
        if (sessionLock?.isHeld == true) return
        sessionLock = power.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "moneytree:session").apply {
            // A US session is 6.5 hours; the timeout is only a safety net.
            acquire(SESSION_MAX_MS)
        }
    }

    private fun releaseSession() {
        sessionLock?.let { if (it.isHeld) it.release() }
        sessionLock = null
    }

    private fun watchNetwork() {
        val cm = getSystemService(ConnectivityManager::class.java) ?: return
        val callback = object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: Network) {
                // Back online after a failed look: look again now, not in a minute.
                if (Hub.running.value && Hub.state.value.lastError != null) Hub.wake.trySend(Unit)
            }
        }
        runCatching { cm.registerDefaultNetworkCallback(callback) }.onSuccess { networkCallback = callback }
    }

    private fun stopBot() {
        // First, the two switches the engine checks right before any order.
        prefs.runWanted = false
        Hub.running.value = false
        Hub.armed.value = false
        val engine = Hub.engine
        Alarms.cancelAll(this)
        releaseSession()
        Hub.nextLookAt.value = null
        loop?.cancel()
        // Buys waiting for an OK die with the bot…
        engine?.state?.value?.approvals?.forEach { notifications().cancel(approvalNotificationId(it.id)) }
        engine?.settingsChanged()
        // …and a buy already sent to Alpaca but not filled yet is withdrawn.
        // Stops protecting what it holds stay where they are.
        engine?.let { e -> cleanup.launch { withTimeoutOrNull(30_000L) { e.cancelPendingBuys() } } }
        Hub.engine = null
        Hub.brain = null
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

    /** One line for the ongoing notification: the step in flight, else the state. */
    private fun ongoingText(state: EngineState, steps: List<Step>): String {
        val s = prefs.settings(Hub.armed.value)
        val w = Words(s.turkish)
        val running = steps.lastOrNull { it.state == StepState.RUNNING }
        if (running != null) {
            return (if (s.turkish) "Şu an: " else "Now: ") + running.title + (running.detail?.let { " · $it" } ?: "")
        }
        val time = SimpleDateFormat("HH:mm", Locale.getDefault())
        return when {
            state.lastError != null -> (if (s.turkish) "Sorun: " else "Problem: ") + state.lastError
            state.marketOpen == false && state.nextOpen != null -> w.marketClosed(state.nextOpen)
            state.lastScanAt != null -> (if (s.turkish) "${s.watchlist.size} hisse izleniyor · son bakış " else
                "Watching ${s.watchlist.size} · last look ") + time.format(Date(state.lastScanAt))
            else -> if (s.turkish) "Başlıyor…" else "Starting…"
        }
    }

    private fun ongoing(state: EngineState, steps: List<Step>): Notification {
        val s = prefs.settings(Hub.armed.value)
        val w = Words(s.turkish)
        val title = buildString {
            append("Money Tree · ")
            append(if (s.live) (if (Hub.armed.value) (if (s.turkish) "GERÇEK · devrede" else "REAL · armed")
                else (if (s.turkish) "GERÇEK · beklemede" else "REAL · paused")) else "paper")
            append(" · ").append(w.autonomyName(s.autonomy))
        }
        val account = state.account
        val sub = account?.let {
            w.usd(it.equity) + " · " + w.signed(it.equity - it.lastEquity) + (if (s.turkish) " bugün" else " today")
        }
        return NotificationCompat.Builder(this, MoneyTreeApp.CHANNEL_ENGINE)
            .setSmallIcon(R.drawable.ic_stat_tree)
            .setContentTitle(title)
            .setContentText(ongoingText(state, steps))
            .apply { sub?.let { setSubText(it) } }
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setSilent(true)
            .setContentIntent(openApp(this))
            .addAction(0, if (s.turkish) "Şimdi bak" else "Look now", serviceIntent(this, ACTION_SCAN, null, 3))
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
        const val EXTRA_SOURCE = "source"
        const val SOURCE_AUTO = "auto"
        private const val ONGOING_ID = 1
        private const val RESULT_ID = 2
        private const val REARM_ID = 3
        const val STOPPED_ID = 4
        /** How long before the open the CPU is held awake, so the first look is on time. */
        private const val OPEN_EARLY_MS = 10 * 60_000L
        private const val SESSION_MAX_MS = 8 * 60 * 60_000L
        /** Re-taken while training continues; only a safety net if something hangs. */
        private const val TRAIN_LOCK_MS = 30 * 60_000L

        /** Outlives the service, so Stop can finish withdrawing orders after it is gone. */
        private val cleanup = CoroutineScope(SupervisorJob() + Dispatchers.IO)

        /** Started by the owner, from the app. */
        fun start(context: Context) =
            ContextCompat.startForegroundService(context, Intent(context, EngineService::class.java))

        /**
         * Started by the system — boot, an app update, the heartbeat. Android may
         * refuse to start a foreground service from the background; then the
         * owner gets a notification to start it with one tap.
         */
        fun startAuto(context: Context) {
            try {
                ContextCompat.startForegroundService(
                    context, Intent(context, EngineService::class.java).putExtra(EXTRA_SOURCE, SOURCE_AUTO),
                )
            } catch (e: Exception) {
                val w = Words(Prefs(context).settings(false).turkish)
                context.getSystemService(NotificationManager::class.java).notify(
                    STOPPED_ID,
                    NotificationCompat.Builder(context, MoneyTreeApp.CHANNEL_ALERTS)
                        .setSmallIcon(R.drawable.ic_stat_tree)
                        .setContentTitle(w.stoppedTitle())
                        .setContentText(w.stoppedText())
                        .setStyle(NotificationCompat.BigTextStyle().bigText(w.stoppedText()))
                        .setAutoCancel(true)
                        .setContentIntent(openApp(context))
                        .build(),
                )
            }
        }

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
