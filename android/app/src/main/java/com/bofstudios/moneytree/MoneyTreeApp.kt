package com.bofstudios.moneytree

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.os.Build

class MoneyTreeApp : Application() {
    override fun onCreate() {
        super.onCreate()
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

    companion object {
        const val CHANNEL_ENGINE = "engine"
        const val CHANNEL_ALERTS = "alerts"
    }
}
