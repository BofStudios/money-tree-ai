package com.bofstudios.moneytree.data

import android.content.Context
import com.bofstudios.moneytree.engine.Autonomy
import com.bofstudios.moneytree.engine.EngineStore
import com.bofstudios.moneytree.engine.Horizon
import com.bofstudios.moneytree.engine.Market
import com.bofstudios.moneytree.engine.NotifyLevel
import com.bofstudios.moneytree.engine.OrderLog
import com.bofstudios.moneytree.engine.QualityMode
import com.bofstudios.moneytree.engine.RiskLevel
import com.bofstudios.moneytree.engine.TradeRecord
import com.bofstudios.moneytree.engine.TradingSettings
import org.json.JSONArray
import org.json.JSONObject
import java.util.Locale

/**
 * Plain settings and the engine's memory. Nothing secret lives here — keys are
 * in [SecureStore]. The armed state is deliberately absent: it only ever exists
 * in memory, so a restart always comes back disarmed.
 */
class Prefs(context: Context) : EngineStore {
    private val p = context.getSharedPreferences("moneytree", Context.MODE_PRIVATE)

    var onboarded: Boolean
        get() = p.getBoolean("onboarded", false)
        set(v) = p.edit().putBoolean("onboarded", v).apply()

    /**
     * Which set of setup questions the owner has answered. A version that asks
     * new ones bumps [SETUP_VERSION], and everyone is asked once more.
     */
    var setupVersion: Int
        get() = p.getInt("setup_version", if (onboarded) 1 else 0)
        set(v) = p.edit().putInt("setup_version", v).apply()

    /** Whether the 3.0 card introducing the five checks was answered on Home. */
    var brainIntroSeen: Boolean
        get() = p.getBoolean("brain_intro_seen", false)
        set(v) = p.edit().putBoolean("brain_intro_seen", v).apply()

    /** When GitHub was last asked for a newer version. */
    var updateCheckedAt: Long
        get() = p.getLong("update_checked_at", 0L)
        set(v) = p.edit().putLong("update_checked_at", v).apply()

    /** Whether the owner left the bot running — used to resume after a reboot. */
    var runWanted: Boolean
        get() = p.getBoolean("run_wanted", false)
        set(v) = p.edit().putBoolean("run_wanted", v).apply()

    fun settings(armed: Boolean): TradingSettings = TradingSettings(
        autonomy = runCatching { Autonomy.valueOf(p.getString("autonomy", "FULL")!!) }.getOrDefault(Autonomy.FULL),
        horizon = runCatching { Horizon.valueOf(p.getString("horizon", "SHORT")!!) }.getOrDefault(Horizon.SHORT),
        live = p.getBoolean("live", false),
        armed = armed,
        watchlist = p.getString("watchlist", null)?.split(",")?.map { it.trim().uppercase() }
            ?.filter { it.isNotEmpty() } ?: TradingSettings.DEFAULT_WATCHLIST,
        turkish = p.getString("language", null)?.let { it == "tr" }
            ?: (Locale.getDefault().language == "tr"),
        fractional = p.getBoolean("fractional", false),
        market = p.getString("market", null)?.let { runCatching { Market.valueOf(it) }.getOrNull() },
        riskLevel = runCatching { RiskLevel.valueOf(p.getString("risk_level", "CAREFUL")!!) }.getOrDefault(RiskLevel.CAREFUL),
        maxPositions = p.getInt("max_positions", 3).coerceIn(1, 5),
        dailyLossPct = p.getFloat("daily_loss_pct", 5f).toDouble().coerceIn(1.0, 20.0),
        usePct = p.getInt("use_pct", 100).coerceIn(10, 100),
        notify = runCatching { NotifyLevel.valueOf(p.getString("notify", "EVERYTHING")!!) }.getOrDefault(NotifyLevel.EVERYTHING),
        aiCheck = p.getBoolean("ai_check", true),
        qualityMode = runCatching { QualityMode.valueOf(p.getString("quality_mode", "BALANCED")!!) }.getOrDefault(QualityMode.BALANCED),
        newsCheck = p.getBoolean("news_check", true),
        learning = p.getBoolean("learning", true),
        selfImprove = p.getBoolean("self_improve", true),
        trainOnBattery = p.getBoolean("train_on_battery", false),
        discover = p.getBoolean("discover", true),
    )

    fun save(s: TradingSettings) {
        p.edit()
            .putString("autonomy", s.autonomy.name)
            .putString("horizon", s.horizon.name)
            .putBoolean("live", s.live)
            .putString("watchlist", s.watchlist.joinToString(","))
            .putString("language", if (s.turkish) "tr" else "en")
            .putBoolean("fractional", s.fractional)
            .putString("market", s.market?.name)
            .putString("risk_level", s.riskLevel.name)
            .putInt("max_positions", s.maxPositions)
            .putFloat("daily_loss_pct", s.dailyLossPct.toFloat())
            .putInt("use_pct", s.usePct)
            .putString("notify", s.notify.name)
            .putBoolean("ai_check", s.aiCheck)
            .putString("quality_mode", s.qualityMode.name)
            .putBoolean("news_check", s.newsCheck)
            .putBoolean("learning", s.learning)
            .putBoolean("self_improve", s.selfImprove)
            .putBoolean("train_on_battery", s.trainOnBattery)
            .putBoolean("discover", s.discover)
            .apply()
    }

    // ---------------------------------------------------------- EngineStore

    override fun ownedSymbols(): Set<String> = p.getStringSet(ownedKey(), emptySet())!!.toSet()

    override fun addOwned(symbol: String) = synchronized(this) {
        p.edit().putStringSet(ownedKey(), ownedSymbols() + symbol).apply()
    }

    override fun removeOwned(symbol: String) = synchronized(this) {
        p.edit().putStringSet(ownedKey(), ownedSymbols() - symbol).apply()
    }

    override fun baselineEquity(live: Boolean): Double? =
        p.getString("baseline_${if (live) "live" else "paper"}", null)?.toDoubleOrNull()

    override fun setBaselineEquity(live: Boolean, equity: Double) {
        p.edit().putString("baseline_${if (live) "live" else "paper"}", equity.toString()).apply()
    }

    override fun trades(): List<TradeRecord> {
        val arr = JSONArray(p.getString(tradesKey(), "[]"))
        return (0 until arr.length()).map {
            val o = arr.getJSONObject(it)
            TradeRecord(o.getString("s"), o.getDouble("q"), o.getDouble("e"), o.getDouble("x"),
                o.getString("r"), o.getLong("t"))
        }
    }

    override fun addTrade(trade: TradeRecord) = synchronized(this) {
        val kept = (trades() + trade).takeLast(100)
        val arr = JSONArray()
        kept.forEach {
            arr.put(JSONObject().put("s", it.symbol).put("q", it.qty).put("e", it.entry)
                .put("x", it.exit).put("r", it.reason).put("t", it.closedAt))
        }
        p.edit().putString(tradesKey(), arr.toString()).apply()
    }

    override fun guard(symbol: String): Pair<Double, Double>? {
        val raw = p.getString(guardKey(symbol), null) ?: return null
        val parts = raw.split("|").mapNotNull { it.toDoubleOrNull() }
        return if (parts.size == 2) parts[0] to parts[1] else null
    }

    override fun setGuard(symbol: String, stop: Double, target: Double) {
        p.edit().putString(guardKey(symbol), "$stop|$target").apply()
    }

    override fun clearGuard(symbol: String) {
        p.edit().remove(guardKey(symbol)).apply()
    }

    override fun logOrder(o: OrderLog) = synchronized(this) {
        val kept = (orderLog() + o).takeLast(100)
        val arr = JSONArray()
        kept.forEach {
            arr.put(JSONObject().put("s", it.symbol).put("d", it.side).put("q", it.qty).put("p", it.price)
                .put("t", it.at).put("w", it.why))
        }
        p.edit().putString(ordersKey(), arr.toString()).apply()
    }

    override fun orderLog(): List<OrderLog> {
        val arr = runCatching { JSONArray(p.getString(ordersKey(), "[]")) }.getOrElse { JSONArray() }
        return (0 until arr.length()).mapNotNull { i ->
            runCatching {
                val o = arr.getJSONObject(i)
                OrderLog(o.getString("s"), o.getString("d"), o.optDouble("q"), o.optDouble("p"), o.getLong("t"), o.optString("w"))
            }.getOrNull()
        }
    }

    private fun ordersKey() = if (p.getBoolean("live", false)) "orders_live" else "orders_paper"

    private fun guardKey(symbol: String) = "guard_${if (p.getBoolean("live", false)) "live" else "paper"}_$symbol"

    /** Paper and live keep separate books so practice never mixes with real. */
    private fun ownedKey() = if (p.getBoolean("live", false)) "owned_live" else "owned_paper"
    private fun tradesKey() = if (p.getBoolean("live", false)) "trades_live" else "trades_paper"
}

/** 2: risk level, positions, daily limit, budget, notifications, AI check, background. */
const val SETUP_VERSION = 2
