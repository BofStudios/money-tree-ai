package com.bofstudios.moneytree.engine

enum class Action { BUY, CLOSE, HOLD }

data class Signal(val action: Action, val reason: String)

/** What the monitor shows about one symbol after a scan. */
data class Snapshot(
    val symbol: String,
    val ready: Boolean,
    val bars: Int,
    val price: Double = Double.NaN,
    val fastEma: Double = Double.NaN,
    val slowEma: Double = Double.NaN,
    val rsi: Double = Double.NaN,
    val atr: Double = Double.NaN,
    val trendUp: Boolean = false,
) {
    val atrPct: Double get() = if (price > 0 && !atr.isNaN()) atr / price * 100 else Double.NaN
}

/**
 * EMA crossover with an RSI filter — the desktop bot's `EmaRsiStrategy`,
 * rule for rule.
 *
 * Entry: fast EMA crosses above slow EMA while RSI is below overbought.
 * Exit:  fast EMA crosses back below slow EMA, or RSI runs past overbought.
 */
class EmaRsiStrategy(
    val fast: Int = 12,
    val slow: Int = 26,
    val rsiPeriod: Int = 14,
    /** No entry with RSI at or above this. */
    val overbought: Double = 70.0,
    /** Exit once RSI runs past this; the same as [overbought] unless evolution tuned it. */
    val exitRsi: Double = overbought,
) {
    val warmupBars = maxOf(slow, rsiPeriod) * 3

    fun onBars(bars: List<Bar>, holding: Boolean): Signal {
        if (bars.size < warmupBars) return Signal(Action.HOLD, "warming up")

        val closes = DoubleArray(bars.size) { bars[it].close }
        val f = Indicators.ema(closes, fast)
        val s = Indicators.ema(closes, slow)
        val r = Indicators.rsi(closes, rsiPeriod)

        val last = bars.size - 1
        val rsiNow = r[last]
        if (rsiNow.isNaN()) return Signal(Action.HOLD, "indicators not ready")

        val crossedUp = f[last - 1] <= s[last - 1] && f[last] > s[last]
        val crossedDown = f[last - 1] >= s[last - 1] && f[last] < s[last]
        val rsiText = "%.0f".format(rsiNow)

        if (!holding) {
            if (crossedUp && rsiNow < overbought) {
                return Signal(Action.BUY, "EMA$fast crossed above EMA$slow, RSI $rsiText")
            }
            if (crossedUp) return Signal(Action.HOLD, "crossover skipped, RSI overbought at $rsiText")
            return Signal(Action.HOLD, "no entry signal")
        }

        if (crossedDown) return Signal(Action.CLOSE, "EMA$fast crossed below EMA$slow")
        if (rsiNow > exitRsi) return Signal(Action.CLOSE, "RSI overbought at $rsiText")
        return Signal(Action.HOLD, "holding position")
    }

    fun snapshot(symbol: String, bars: List<Bar>): Snapshot {
        if (bars.size < maxOf(slow, rsiPeriod) + 2) return Snapshot(symbol, false, bars.size)
        val closes = DoubleArray(bars.size) { bars[it].close }
        val last = bars.size - 1
        val f = Indicators.ema(closes, fast)[last]
        val s = Indicators.ema(closes, slow)[last]
        return Snapshot(
            symbol = symbol,
            ready = true,
            bars = bars.size,
            price = closes[last],
            fastEma = f,
            slowEma = s,
            rsi = Indicators.rsi(closes, rsiPeriod)[last],
            atr = Indicators.atr(bars, 14)[last],
            trendUp = f > s,
        )
    }
}
