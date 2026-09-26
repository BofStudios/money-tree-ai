package com.bofstudios.moneytree.engine

/**
 * One candle. Times are epoch milliseconds, UTC.
 */
data class Bar(
    val time: Long,
    val open: Double,
    val high: Double,
    val low: Double,
    val close: Double,
    val volume: Double,
)

/**
 * The same three indicators the desktop bot uses, ported so that the phone and
 * the PC reach the same decision on the same candles.
 *
 * The desktop versions are pandas `ewm(adjust=False)` calls, and the details
 * that matter for parity are copied exactly:
 *  - an EMA starts at the first value, not at a simple average;
 *  - RSI and ATR stay NaN until `period` real observations exist, and RSI's
 *    first bar has no change, so it becomes valid one bar later than ATR;
 *  - a perfectly flat stretch gives RSI 50, not 0/0.
 * Tests pin these against values produced by the Python implementation.
 */
object Indicators {

    fun ema(values: DoubleArray, period: Int): DoubleArray {
        val out = DoubleArray(values.size) { Double.NaN }
        if (values.isEmpty()) return out
        val alpha = 2.0 / (period + 1)
        out[0] = values[0]
        for (i in 1 until values.size) {
            out[i] = alpha * values[i] + (1 - alpha) * out[i - 1]
        }
        return out
    }

    /** pandas `ewm(alpha=1/period, adjust=False, min_periods=period)` over a
     *  series whose leading entries may be NaN. */
    private fun wilder(values: DoubleArray, period: Int): DoubleArray {
        val out = DoubleArray(values.size) { Double.NaN }
        val alpha = 1.0 / period
        var mean = Double.NaN
        var seen = 0
        for (i in values.indices) {
            val x = values[i]
            if (x.isNaN()) continue
            mean = if (seen == 0) x else alpha * x + (1 - alpha) * mean
            seen += 1
            if (seen >= period) out[i] = mean
        }
        return out
    }

    fun rsi(closes: DoubleArray, period: Int = 14): DoubleArray {
        val n = closes.size
        val gain = DoubleArray(n) { Double.NaN }
        val loss = DoubleArray(n) { Double.NaN }
        for (i in 1 until n) {
            val delta = closes[i] - closes[i - 1]
            gain[i] = if (delta > 0) delta else 0.0
            loss[i] = if (delta < 0) -delta else 0.0
        }
        val avgGain = wilder(gain, period)
        val avgLoss = wilder(loss, period)
        return DoubleArray(n) { i ->
            val g = avgGain[i]
            val l = avgLoss[i]
            when {
                g.isNaN() || l.isNaN() -> Double.NaN
                g == 0.0 && l == 0.0 -> 50.0
                l == 0.0 -> 100.0
                else -> 100.0 - 100.0 / (1.0 + g / l)
            }
        }
    }

    fun atr(bars: List<Bar>, period: Int = 14): DoubleArray {
        val tr = DoubleArray(bars.size) { i ->
            val b = bars[i]
            if (i == 0) {
                b.high - b.low
            } else {
                val prev = bars[i - 1].close
                maxOf(b.high - b.low, kotlin.math.abs(b.high - prev), kotlin.math.abs(b.low - prev))
            }
        }
        return wilder(tr, period)
    }
}
