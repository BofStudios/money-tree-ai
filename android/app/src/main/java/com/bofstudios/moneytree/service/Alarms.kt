package com.bofstudios.moneytree.service

import android.app.AlarmManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.PowerManager
import com.bofstudios.moneytree.data.Prefs

/**
 * Two alarms keep the bot up without holding the phone awake all night.
 *
 *  - The heartbeat, every half hour: if Android killed the service, it starts
 *    it again. It is re-armed each time it fires.
 *  - The open alarm, a few minutes before the US market opens: wakes the loop
 *    so the first look of the day is on time even after a night in Doze.
 *
 * Both use setAndAllowWhileIdle, which fires in Doze without the exact-alarm
 * permission; Android may shift it by a few minutes, which is fine here.
 */
object Alarms {
    private const val HEARTBEAT = "com.bofstudios.moneytree.HEARTBEAT"
    private const val OPEN = "com.bofstudios.moneytree.OPEN"
    private const val HEARTBEAT_MS = 30 * 60_000L

    fun scheduleHeartbeat(context: Context) =
        set(context, HEARTBEAT, System.currentTimeMillis() + HEARTBEAT_MS, 11)

    fun scheduleOpen(context: Context, at: Long) =
        set(context, OPEN, at.coerceAtLeast(System.currentTimeMillis() + 60_000L), 12)

    fun cancelAll(context: Context) {
        val am = context.getSystemService(AlarmManager::class.java) ?: return
        am.cancel(pending(context, HEARTBEAT, 11))
        am.cancel(pending(context, OPEN, 12))
    }

    private fun set(context: Context, action: String, at: Long, code: Int) {
        val am = context.getSystemService(AlarmManager::class.java) ?: return
        runCatching { am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at, pending(context, action, code)) }
    }

    private fun pending(context: Context, action: String, code: Int): PendingIntent =
        PendingIntent.getBroadcast(
            context, code,
            Intent(context, AlarmReceiver::class.java).setAction(action),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )

    internal fun isOpenAlarm(intent: Intent) = intent.action == OPEN
}

/** Restarts a killed service, or wakes a sleeping loop before the open. */
class AlarmReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val prefs = Prefs(context)
        if (!prefs.runWanted) return
        // Keep the CPU up long enough for the loop to take its own wake lock.
        context.getSystemService(PowerManager::class.java)
            ?.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "moneytree:alarm")?.acquire(60_000L)
        if (!Hub.running.value) {
            EngineService.startAuto(context)
        } else if (Alarms.isOpenAlarm(intent)) {
            Hub.wake.trySend(Unit)
        }
        Alarms.scheduleHeartbeat(context)
    }
}

/** Brings the bot back after a reboot or an app update, if it was running before. */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val relevant = intent.action == Intent.ACTION_BOOT_COMPLETED ||
            intent.action == Intent.ACTION_MY_PACKAGE_REPLACED
        if (relevant && Prefs(context).runWanted) EngineService.startAuto(context)
    }
}
