package com.bofstudios.moneytree

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.os.Build

class MoneyTreeApp : Application() {
    override fun onCreate() {
        super.onCreate()
        recordCrashes()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val nm = getSystemService(NotificationManager::class.java)
            nm.createNotificationChannel(
                NotificationChannel(CHANNEL_ENGINE, "Money Tree running", NotificationManager.IMPORTANCE_LOW)
                    .apply { description = "The always-on notification while the bot is watching the market." }
            )
            nm.createNotificationChannel(
                NotificationChannel(CHANNEL_ALERTS, "Trades and approvals", NotificationManager.IMPORTANCE_HIGH)
                    .apply { description = "Buys waiting for your OK, orders placed, positions closed." }
            )
        }
    }

    /**
     * Nobody has run this app on a real phone before the owner does, so a crash
     * must not vanish: the stack trace is kept and shown on the next launch,
     * ready to copy and send back. It never leaves the phone on its own.
     */
    private fun recordCrashes() {
        val previous = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { thread, error ->
            runCatching {
                val trace = android.util.Log.getStackTraceString(error).take(6000)
                val info = "Money Tree ${BuildConfig.VERSION_NAME} · Android ${Build.VERSION.RELEASE} " +
                    "(API ${Build.VERSION.SDK_INT}) · ${Build.MANUFACTURER} ${Build.MODEL}\n" +
                    "thread: ${thread.name}\n\n$trace"
                // commit(), not apply(): the process is about to die.
                getSharedPreferences("crash", MODE_PRIVATE).edit().putString("last", info).commit()
            }
            previous?.uncaughtException(thread, error)
        }
    }

    companion object {
        fun lastCrash(context: android.content.Context): String? =
            context.getSharedPreferences("crash", MODE_PRIVATE).getString("last", null)

        fun clearCrash(context: android.content.Context) =
            context.getSharedPreferences("crash", MODE_PRIVATE).edit().remove("last").apply()

        const val CHANNEL_ENGINE = "engine"
        const val CHANNEL_ALERTS = "alerts"
    }
}
