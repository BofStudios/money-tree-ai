package com.bofstudios.moneytree.engine

import kotlin.math.floor

/**
 * The desktop bot's risk settings, same defaults (config/config.yaml).
 */
data class RiskConfig(
    val maxPositionPct: Double = 20.0,
    val maxDailyLossPct: Double = 5.0,
    val maxOpenPositions: Int = 3,
    val atrMultiple: Double = 1.5,
    val minStopPct: Double = 0.8,
    val maxStopPct: Double = 6.0,
    val rewardRisk: Double = 2.0,
    val riskPerTradePct: Double = 0.5,
    val trailActivatePct: Double = 2.0,
    val trailPct: Double = 1.0,
    val cooldownMinutes: Long = 30,
)

/** A buy the engine has sized and priced, before anyone decides to send it. */
data class Entry(
    val symbol: String,
    val qty: Double,
    val price: Double,
    val stop: Double,
    val target: Double,
    val reason: String,
    /** Fractional entries are plain market orders; their stop lives on the phone. */
    val fractional: Boolean = false,
) {
    val notional: Double get() = qty * price
    val riskCash: Double get() = qty * (price - stop)
    /** "7" for whole shares, "0.0412" for a fraction — never "7.0". */
    val qtyText: String get() = formatQty(qty)
}

fun formatQty(q: Double): String =
    if (q == kotlin.math.floor(q)) q.toLong().toString()
    else String.format(java.util.Locale.US, "%.4f", q).trimEnd('0').trimEnd('.')

/**
 * Sizing and protective levels, ported from `RiskManager`.
 *
 * One deliberate difference from the desktop bot: the share count is rounded
 * down to whole shares. Every entry here is a bracket order, so the stop-loss
 * and target live at Alpaca and keep working when the phone is off — and
 * Alpaca does not accept fractional quantities on bracket orders. A position
 * too small for one share is skipped and said so, rather than bought without
 * a broker-held stop.
 */
class Risk(val config: RiskConfig = RiskConfig()) {

    /** Stop distance as a percentage of price: ATR-scaled, clamped both ends. */
    fun stopDistancePct(price: Double, atr: Double): Double {
        val distance = if (!atr.isNaN() && atr > 0 && price > 0) {
            atr * config.atrMultiple / price * 100.0
        } else {
            config.minStopPct * 2
        }
        return distance.coerceIn(config.minStopPct, config.maxStopPct)
    }

    /**
     * Whole shares to buy so that a stop-out loses `riskPerTradePct` of equity,
     * capped by `maxPositionPct` and by the cash actually available.
     */
    fun shares(equity: Double, available: Double, price: Double, stopPct: Double): Int {
        if (price <= 0 || stopPct <= 0 || equity <= 0) return 0
        val spendable = minOf(equity * config.maxPositionPct / 100.0, available * (1 - FEE_BUFFER))
        val riskCash = equity * config.riskPerTradePct / 100.0
        val perShareRisk = price * stopPct / 100.0
        val allocation = minOf(riskCash / perShareRisk * price, spendable)
        return floor(allocation / price).toInt().coerceAtLeast(0)
    }

    /**
     * Fractional size for small accounts: the same risk rule, rounded down to
     * 1/10,000 of a share. Alpaca refuses orders under $1, so those are null.
     */
    fun fractionalShares(equity: Double, available: Double, price: Double, stopPct: Double): Double {
        if (price <= 0 || stopPct <= 0 || equity <= 0) return 0.0
        val spendable = minOf(equity * config.maxPositionPct / 100.0, available * (1 - FEE_BUFFER))
        val riskCash = equity * config.riskPerTradePct / 100.0
        val allocation = minOf(riskCash / (price * stopPct / 100.0) * price, spendable)
        return floor(allocation / price * 10_000) / 10_000
    }

    fun plan(
        symbol: String, reason: String, price: Double, atr: Double,
        equity: Double, available: Double, fractional: Boolean = false,
    ): Entry? {
        val stopPct = stopDistancePct(price, atr)
        val qty = if (fractional) {
            fractionalShares(equity, available, price, stopPct).takeIf { it * price >= MIN_FRACTIONAL_NOTIONAL }
        } else {
            shares(equity, available, price, stopPct).takeIf { it >= 1 }?.toDouble()
        } ?: return null
        val stopFraction = stopPct / 100.0
        return Entry(
            symbol = symbol,
            qty = qty,
            price = price,
            stop = price * (1 - stopFraction),
            target = price * (1 + stopFraction * config.rewardRisk),
            reason = reason,
            fractional = fractional,
        )
    }

    /**
     * A higher stop behind a winner, or null. Starts only once the trade is up
     * `trailActivatePct`, follows the price `trailPct` behind, never lowers.
     */
    fun trailingStop(entryPrice: Double, currentStop: Double?, price: Double): Double? {
        if (entryPrice <= 0) return null
        val gainPct = (price / entryPrice - 1) * 100
        if (gainPct < config.trailActivatePct) return null
        val candidate = price * (1 - config.trailPct / 100.0)
        if (currentStop != null && candidate <= currentStop) return null
        return candidate
    }

    /** Today's loss has reached the limit, measured against yesterday's close. */
    fun dailyLimitHit(equity: Double, lastEquity: Double): Boolean {
        if (lastEquity <= 0) return false
        return equity - lastEquity <= -(lastEquity * config.maxDailyLossPct / 100.0)
    }

    companion object {
        const val FEE_BUFFER = 0.005
        const val MIN_FRACTIONAL_NOTIONAL = 1.0
    }
}
