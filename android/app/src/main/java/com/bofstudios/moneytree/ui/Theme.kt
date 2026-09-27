package com.bofstudios.moneytree.ui

import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.LocalContentColor
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableDoubleStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * Black and yellow. Yellow is identity and "live"; profit stays green and loss
 * red, because yellow reads as a warning and money should never be ambiguous.
 */
object MT {
    val Bg = Color(0xFF000000)
    val Surface = Color(0xFF0E0E0F)
    val Surface2 = Color(0xFF171718)
    val Line = Color(0x17FFFFFF)
    val Text = Color(0xFFFFFFFF)
    val Text2 = Color(0xFF8B8B90)
    val Text3 = Color(0xFF5A5A5F)
    val Accent = Color(0xFFFFD60A)
    val AccentSoft = Color(0x1FFFD60A)
    val Up = Color(0xFF32D583)
    val Down = Color(0xFFFF6B60)

    val Mono = FontFamily.Monospace
}

/** Every string on screen comes in both languages; this picks one. */
val LocalTurkish = staticCompositionLocalOf { false }

@Composable
fun tx(en: String, tr: String): String = if (LocalTurkish.current) tr else en

/** The same choice outside composition — inside click handlers and coroutines. */
fun pick(turkish: Boolean, en: String, tr: String): String = if (turkish) tr else en

@Composable
fun MoneyTreeTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = darkColorScheme(
            primary = MT.Accent, onPrimary = Color.Black,
            secondary = MT.Accent, onSecondary = Color.Black,
            background = MT.Bg, onBackground = MT.Text,
            surface = MT.Surface, onSurface = MT.Text,
            surfaceVariant = MT.Surface2, onSurfaceVariant = MT.Text2,
            error = MT.Down, outline = MT.Line,
        ),
    ) {
        // Material's Text takes its colour from LocalContentColor, which is
        // black unless a Surface sets it. Nothing here sits in a Surface, so
        // every Text without an explicit colour was drawn black on black —
        // the header, the status line, the Portfolio balance. Set it once here.
        CompositionLocalProvider(LocalContentColor provides MT.Text, content = content)
    }
}

@Composable
fun Card(
    modifier: Modifier = Modifier,
    highlight: Boolean = false,
    /** A soft yellow light in the top corner, for things that are live. */
    glow: Boolean = false,
    borderColor: Color? = null,
    padding: PaddingValues = PaddingValues(16.dp),
    content: @Composable ColumnScope.() -> Unit,
) {
    Column(
        modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(18.dp))
            .background(Brush.verticalGradient(listOf(MT.Surface2, MT.Surface)))
            .then(
                if (glow) Modifier.drawBehind {
                    drawCircle(
                        Brush.radialGradient(
                            listOf(MT.Accent.copy(alpha = 0.16f), Color.Transparent),
                            center = Offset(size.width, 0f), radius = size.width * 0.75f,
                        ),
                        radius = size.width * 0.75f, center = Offset(size.width, 0f),
                    )
                } else Modifier
            )
            .border(
                1.dp,
                borderColor ?: if (highlight) MT.Accent.copy(alpha = 0.5f) else MT.Line,
                RoundedCornerShape(18.dp),
            )
            .padding(padding),
        content = content,
    )
}

/**
 * A money figure that counts to its new value instead of snapping. Animates
 * a 0..1 progress and interpolates in Double, since a Float cannot hold
 * $100,000.00 to the cent.
 */
@Composable
fun AnimatedMoney(value: Double?, format: (Double) -> String, style: TextStyle, color: Color = MT.Text) {
    if (value == null || value.isNaN()) {
        Text("—", style = style, color = color)
        return
    }
    var from by remember { mutableDoubleStateOf(value) }
    var to by remember { mutableDoubleStateOf(value) }
    val progress = remember { Animatable(1f) }
    LaunchedEffect(value) {
        if (value != to) {
            from += (to - from) * progress.value
            to = value
            progress.snapTo(0f)
            progress.animateTo(1f, tween(900, easing = FastOutSlowInEasing))
        }
    }
    Text(format(from + (to - from) * progress.value), style = style, color = color)
}

@Composable
fun SectionTitle(text: String, modifier: Modifier = Modifier) {
    Text(
        text.uppercase(),
        modifier.padding(top = 22.dp, bottom = 10.dp),
        color = MT.Text3, fontSize = 11.sp, fontWeight = FontWeight.SemiBold, letterSpacing = 1.sp,
    )
}

/** A dot that breathes while something is live. */
@Composable
fun Pulse(color: Color, live: Boolean, size: Int = 9) {
    val t = rememberInfiniteTransition(label = "pulse")
    val s by t.animateFloat(1f, if (live) 2.2f else 1f,
        infiniteRepeatable(tween(1600), RepeatMode.Restart), label = "s")
    val a by t.animateFloat(0.6f, 0f, infiniteRepeatable(tween(1600), RepeatMode.Restart), label = "a")
    Box(contentAlignment = Alignment.Center, modifier = Modifier.size((size * 2.4).dp)) {
        if (live) Box(Modifier.size(size.dp).scale(s).alpha(a).clip(CircleShape).background(color))
        Box(Modifier.size(size.dp).clip(CircleShape).background(color))
    }
}

@Composable
fun Chip(text: String, selected: Boolean, onClick: () -> Unit, modifier: Modifier = Modifier) {
    Box(
        modifier
            .clip(RoundedCornerShape(20.dp))
            .background(if (selected) MT.Accent else MT.Surface2)
            .border(1.dp, if (selected) MT.Accent else MT.Line, RoundedCornerShape(20.dp))
            .clickable(onClick = onClick)
            .padding(horizontal = 14.dp, vertical = 9.dp),
    ) {
        Text(text, color = if (selected) Color.Black else MT.Text2,
            fontSize = 13.sp, fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Medium)
    }
}

@Composable
fun Tag(text: String, color: Color = MT.Accent) {
    Text(
        text,
        Modifier
            .clip(RoundedCornerShape(20.dp))
            .background(color.copy(alpha = 0.12f))
            .border(1.dp, color.copy(alpha = 0.35f), RoundedCornerShape(20.dp))
            .padding(horizontal = 9.dp, vertical = 4.dp),
        color = color, fontSize = 10.5.sp, fontFamily = MT.Mono, fontWeight = FontWeight.Medium,
    )
}

@Composable
fun PrimaryButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true) {
    androidx.compose.material3.Button(
        onClick, modifier, enabled = enabled,
        shape = RoundedCornerShape(12.dp),
        colors = ButtonDefaults.buttonColors(containerColor = MT.Accent, contentColor = Color.Black,
            disabledContainerColor = MT.Surface2, disabledContentColor = MT.Text3),
    ) { Text(text, fontWeight = FontWeight.SemiBold) }
}

@Composable
fun GhostButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier, color: Color = MT.Text2) {
    TextButton(onClick, modifier) { Text(text, color = color) }
}

@Composable
fun KeyValue(label: String, value: String, valueColor: Color = MT.Text) {
    Row(Modifier.fillMaxWidth().padding(vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(label, Modifier.weight(1f), color = MT.Text2, fontSize = 13.5.sp)
        Text(value, color = valueColor, fontFamily = MT.Mono, fontSize = 13.5.sp, fontWeight = FontWeight.Medium)
    }
}

val Figure = TextStyle(fontFamily = MT.Mono, fontWeight = FontWeight.SemiBold, fontSize = 34.sp, letterSpacing = (-1).sp)

fun Double.tone(): Color = when { this > 0 -> MT.Up; this < 0 -> MT.Down; else -> MT.Text2 }
