package com.bofstudios.moneytree.ui

import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.bofstudios.moneytree.engine.Bar
import com.bofstudios.moneytree.engine.Indicators

/**
 * Candles with the two EMAs the strategy trades on, so what the monitor says
 * ("fast EMA crossed above slow") can be seen, not just read. Stop and target
 * lines are drawn when the bot holds the symbol.
 */
@Composable
fun CandleChart(
    bars: List<Bar>,
    modifier: Modifier = Modifier,
    stop: Double? = null,
    target: Double? = null,
) {
    if (bars.size < 2) {
        Text(tx("Not enough candles yet.", "Henüz yeterli mum yok."), color = MT.Text3, fontSize = 12.sp)
        return
    }
    val closes = remember(bars) { DoubleArray(bars.size) { bars[it].close } }
    val fast = remember(bars) { Indicators.ema(closes, 12) }
    val slow = remember(bars) { Indicators.ema(closes, 26) }
    // Candles draw in from the left once, so the chart reads as live.
    val reveal = remember(bars.firstOrNull()?.time, bars.size) { Animatable(0f) }
    LaunchedEffect(reveal) { reveal.animateTo(1f, tween(700)) }

    Column(modifier) {
        Canvas(Modifier.fillMaxWidth().height(200.dp)) {
            val lows = bars.map { it.low } + listOfNotNull(stop)
            val highs = bars.map { it.high } + listOfNotNull(target)
            val lo = lows.min(); val hi = highs.max()
            val span = (hi - lo).takeIf { it > 0 } ?: 1.0
            fun y(v: Double) = (size.height * (1 - (v - lo) / span)).toFloat()
            val step = size.width / bars.size
            val body = (step * 0.62f).coerceAtLeast(1f)
            val shown = (bars.size * reveal.value).toInt()

            for (i in 0 until shown) {
                val b = bars[i]
                val x = step * i + step / 2
                val up = b.close >= b.open
                val c = if (up) MT.Up else MT.Down
                drawLine(c, Offset(x, y(b.high)), Offset(x, y(b.low)), strokeWidth = 1.2f)
                val top = y(maxOf(b.open, b.close)); val bottom = y(minOf(b.open, b.close))
                drawRect(c, Offset(x - body / 2, top), Size(body, (bottom - top).coerceAtLeast(1f)))
            }

            fun line(values: DoubleArray, color: Color) {
                val path = Path()
                for (i in 0 until shown) {
                    val px = step * i + step / 2; val py = y(values[i])
                    if (i == 0) path.moveTo(px, py) else path.lineTo(px, py)
                }
                drawPath(path, color, style = Stroke(width = 2.2f))
            }
            line(fast, MT.Accent)
            line(slow, MT.Text2)

            val dash = PathEffect.dashPathEffect(floatArrayOf(10f, 8f))
            stop?.let { drawLine(MT.Down, Offset(0f, y(it)), Offset(size.width, y(it)), 1.5f, pathEffect = dash) }
            target?.let { drawLine(MT.Up, Offset(0f, y(it)), Offset(size.width, y(it)), 1.5f, pathEffect = dash) }
            val last = bars.last().close
            drawLine(MT.Text3, Offset(0f, y(last)), Offset(size.width, y(last)), 1f, pathEffect = dash)
        }
        Spacer(Modifier.height(8.dp))
        Row(verticalAlignment = Alignment.CenterVertically) {
            Legend(MT.Accent, "EMA 12")
            Legend(MT.Text2, "EMA 26")
            if (stop != null) Legend(MT.Down, "stop")
            if (target != null) Legend(MT.Up, tx("target", "hedef"))
        }
    }
}

@Composable
private fun Legend(color: Color, label: String) {
    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(end = 14.dp)) {
        Canvas(Modifier.width(14.dp).height(3.dp)) { drawRect(color) }
        Spacer(Modifier.width(6.dp))
        Text(label, color = MT.Text3, fontSize = 10.5.sp, fontWeight = FontWeight.Medium, fontFamily = MT.Mono)
    }
}
