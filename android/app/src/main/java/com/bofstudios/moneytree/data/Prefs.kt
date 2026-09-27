package com.bofstudios.moneytree.data

import android.content.Context
import com.bofstudios.moneytree.engine.Autonomy
import com.bofstudios.moneytree.engine.EngineStore
import com.bofstudios.moneytree.engine.Horizon
import com.bofstudios.moneytree.engine.Market
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

    private fun guardKey(symbol: String) = "guard_${if (p.getBoolean("live", false)) "live" else "paper"}_$symbol"

    /** Paper and live keep separate books so practice never mixes with real. */
    private fun ownedKey() = if (p.getBoolean("live", false)) "owned_live" else "owned_paper"
    private fun tradesKey() = if (p.getBoolean("live", false)) "trades_live" else "trades_paper"
}
