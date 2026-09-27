package com.bofstudios.moneytree.ui

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.animateContentSize
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.bofstudios.moneytree.engine.EngineState
import com.bofstudios.moneytree.engine.Snapshot
import com.bofstudios.moneytree.engine.Step
import com.bofstudios.moneytree.engine.StepKind
import com.bofstudios.moneytree.engine.StepState
import com.bofstudios.moneytree.engine.TradingSettings
import com.bofstudios.moneytree.engine.Words
import com.bofstudios.moneytree.service.EngineService
import com.bofstudios.moneytree.service.Hub
import kotlinx.coroutines.delay
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * Watching the bot work, the way you watch an agent run its tools: one line
 * per step, a spinner while the real call is in flight, the result underneath,
 * newest at the bottom. Every row is a step the engine actually took — the
 * spinners, the "NVDA · 3/8" progress and the countdown are all backed by real
 * calls and the real schedule, never animated for effect.
 */
@Composable
fun LiveScreen(settings: TradingSettings) {
    val context = LocalContext.current
    val steps by Hub.steps.collectAsState()
    val state by Hub.state.collectAsState()
    val running by Hub.running.collectAsState()
    val nextLook by Hub.nextLookAt.collectAsState()
    val w = Words(LocalTurkish.current)
    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
    LaunchedEffect(Unit) { while (true) { delay(100); now = System.currentTimeMillis() } }
    var chart by rememberSaveable { mutableStateOf<String?>(null) }
    val busy = steps.any { it.state == StepState.RUNNING }

    Column(Modifier.fillMaxSize()) {
        // ------------------------------------------------------------ header
        Column(Modifier.padding(horizontal = 16.dp, vertical = 4.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Pulse(if (running) MT.Accent else MT.Text3, live = running && busy)
                Text(tx("Live", "Canlı"), fontSize = 22.sp, fontWeight = FontWeight.SemiBold)
                Spacer(Modifier.weight(1f))
                if (running) GhostButton(tx("Look now", "Şimdi bak"), { EngineService.scanNow(context) }, color = MT.Accent)
                else PrimaryButton(tx("Start", "Başlat"), { EngineService.start(context) })
            }
            Text(
                listOf(
                    tx("Watching ${settings.watchlist.size}", "${settings.watchlist.size} hisse izleniyor"),
                    w.tfName(settings.horizon.timeframe) + tx(" charts", " grafik"),
                    w.autonomyName(settings.autonomy),
                    if (settings.live) tx("real money", "gerçek para") else "paper",
                ).joinToString(" · "),
                color = MT.Text2, fontSize = 12.5.sp,
            )
            Text(
                when {
                    !running -> tx("Stopped — press Start to watch it work.", "Durdu — çalışmasını izlemek için Başlat'a bas.")
                    state.marketOpen == false -> tx("Market closed — it reviews the charts but trades nothing until the open.",
                        "Piyasa kapalı — grafikleri inceler ama açılışa kadar işlem yapmaz.")
                    state.marketOpen == true -> tx("Market open — it can trade.", "Piyasa açık — işlem yapabilir.")
                    else -> tx("Starting…", "Başlıyor…")
                },
                color = if (state.marketOpen == true && running) MT.Accent else MT.Text3, fontSize = 12.sp,
            )
        }

        // ------------------------------------------------------- looking at
        val symbols = (settings.watchlist + state.held.filter { it.managed }.map { it.position.symbol }).distinct()
        val bySymbol = state.snapshots.associateBy { it.symbol }
        Text(
            tx("Looking at", "Baktığı hisseler") + (state.focus?.let { tx(" · now: $it", " · şu an: $it") } ?: ""),
            color = MT.Text3, fontSize = 11.sp, fontWeight = FontWeight.SemiBold, letterSpacing = 1.sp,
            modifier = Modifier.padding(start = 16.dp, top = 12.dp, bottom = 8.dp),
        )
        LazyRow(
            contentPadding = PaddingValues(horizontal = 16.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            items(symbols, key = { it }) { sym ->
                SymbolChip(sym, bySymbol[sym], focused = state.focus == sym, open = chart == sym, w = w) {
                    chart = if (chart == sym) null else sym
                }
            }
        }
        AnimatedVisibility(chart != null, enter = expandVertically() + fadeIn(), exit = shrinkVertically()) {
            val sym = chart ?: return@AnimatedVisibility
            val held = state.held.firstOrNull { it.position.symbol == sym && it.managed }
            Card(Modifier.padding(start = 16.dp, end = 16.dp, top = 10.dp)) {
                Text(sym, fontFamily = MT.Mono, fontWeight = FontWeight.SemiBold)
                Spacer(Modifier.height(6.dp))
                CandleChart(state.bars[sym].orEmpty(), stop = held?.stop, target = held?.target)
            }
        }
        HorizontalDivider(color = MT.Line, modifier = Modifier.padding(top = 12.dp))

        // -------------------------------------------------------- transcript
        // Reversed so it sits at the bottom and follows new steps like a chat.
        LazyColumn(
            Modifier.weight(1f).fillMaxWidth(),
            reverseLayout = true,
            contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 12.dp, bottom = 130.dp),
        ) {
            item(key = "tail") { Tail(running, busy, nextLook, now, state) }
            items(steps.asReversed(), key = { it.id }) { TranscriptRow(it, now) }
            if (steps.isEmpty()) {
                item(key = "empty") {
                    Text(
                        tx("Nothing yet. Every step the bot takes appears here as it happens.",
                            "Henüz bir şey yok. Botun attığı her adım olduğu anda burada görünür."),
                        color = MT.Text3, fontSize = 13.sp, modifier = Modifier.padding(vertical = 20.dp),
                    )
                }
            }
        }
    }
}

@Composable
private fun SymbolChip(symbol: String, snap: Snapshot?, focused: Boolean, open: Boolean, w: Words, onClick: () -> Unit) {
    Column(
        Modifier
            .clip(RoundedCornerShape(14.dp))
            .background(if (focused) MT.AccentSoft else MT.Surface)
            .border(1.dp, if (focused || open) MT.Accent else MT.Line, RoundedCornerShape(14.dp))
            .clickable(onClick = onClick)
            .padding(horizontal = 12.dp, vertical = 9.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(symbol, fontFamily = MT.Mono, fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
            if (focused) {
                Spacer(Modifier.width(6.dp))
                CircularProgressIndicator(Modifier.size(10.dp), color = MT.Accent, strokeWidth = 1.5.dp)
            }
        }
        if (snap != null && snap.ready) {
            Text(w.usd(snap.price), fontFamily = MT.Mono, fontSize = 11.5.sp, color = MT.Text2)
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(if (snap.trendUp) "▲" else "▼", color = if (snap.trendUp) MT.Up else MT.Down, fontSize = 10.sp)
                Spacer(Modifier.width(4.dp))
                Text("RSI ${"%.0f".format(snap.rsi)}", fontFamily = MT.Mono, fontSize = 10.5.sp, color = when {
                    snap.rsi >= 70 -> MT.Down; snap.rsi <= 30 -> MT.Up; else -> MT.Text3
                })
            }
        } else {
            Text("—", color = MT.Text3, fontFamily = MT.Mono, fontSize = 11.5.sp)
        }
    }
}

/** What happens after the last step: waiting for the next look, for real. */
@Composable
private fun Tail(running: Boolean, busy: Boolean, nextLook: Long?, now: Long, state: EngineState) {
    if (!running || busy) return
    val left = nextLook?.let { (it - now).coerceAtLeast(0) }
    Row(Modifier.padding(vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(16.dp), contentAlignment = Alignment.Center) {
            Box(Modifier.size(7.dp).clip(CircleShape).border(1.5.dp, MT.Text3, CircleShape))
        }
        Spacer(Modifier.width(10.dp))
        Text(
            when {
                left == null -> tx("Waiting…", "Bekliyor…")
                left > 3_600_000 && state.nextOpen != null -> tx("Resting until the open · next look ", "Açılışa kadar dinleniyor · sonraki bakış ") +
                    SimpleDateFormat("EEE HH:mm", Locale.getDefault()).format(Date(now + left))
                else -> tx("Waiting · next look in ", "Bekliyor · sonraki bakış ") + clock(left)
            },
            color = MT.Text3, fontSize = 13.sp,
        )
    }
}

private fun clock(ms: Long): String {
    val s = ms / 1000
    return if (s >= 3600) String.format(Locale.US, "%d:%02d:%02d", s / 3600, (s % 3600) / 60, s % 60)
    else String.format(Locale.US, "%d:%02d", s / 60, s % 60)
}

/** One step, drawn like an agent's tool call: bullet, title, ⎿ result. */
@Composable
private fun TranscriptRow(step: Step, now: Long) {
    var expanded by rememberSaveable(step.id) { mutableStateOf(false) }
    val time = remember(step.startedAt) { SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(Date(step.startedAt)) }
    val running = step.state == StepState.RUNNING

    Column(Modifier.fillMaxWidth().padding(vertical = 5.dp).animateContentSize()) {
        // A new look at the market starts with the clock: mark it.
        if (step.kind == StepKind.CLOCK) {
            Text("──  $time  ──", Modifier.fillMaxWidth().padding(top = 10.dp, bottom = 8.dp),
                color = MT.Text3, fontFamily = MT.Mono, fontSize = 10.5.sp, textAlign = TextAlign.Center)
        }
        Row(verticalAlignment = Alignment.Top) {
            Box(Modifier.size(width = 16.dp, height = 20.dp), contentAlignment = Alignment.Center) {
                if (running) CircularProgressIndicator(Modifier.size(11.dp), color = MT.Accent, strokeWidth = 1.8.dp)
                else Bullet(step)
            }
            Spacer(Modifier.width(10.dp))
            Column(Modifier.weight(1f)) {
                Row(verticalAlignment = Alignment.Top) {
                    Text(step.title, Modifier.weight(1f), fontSize = 14.sp, lineHeight = 19.sp,
                        fontWeight = if (running) FontWeight.SemiBold else FontWeight.Medium,
                        color = if (step.state == StepState.INFO) MT.Text2 else MT.Text)
                    Spacer(Modifier.width(8.dp))
                    Text(
                        when {
                            running -> seconds(now - step.startedAt)
                            step.state == StepState.INFO -> time.substring(0, 5)
                            step.endedAt != null -> seconds(step.endedAt - step.startedAt)
                            else -> ""
                        },
                        color = if (running) MT.Accent else MT.Text3, fontFamily = MT.Mono, fontSize = 11.sp,
                    )
                }
                step.detail?.let { detail ->
                    Row(Modifier.padding(top = 2.dp)) {
                        Text("⎿", color = MT.Text3, fontFamily = MT.Mono, fontSize = 12.sp)
                        Spacer(Modifier.width(6.dp))
                        Text(detail, fontFamily = MT.Mono, fontSize = 12.sp, lineHeight = 17.sp,
                            color = when {
                                step.state == StepState.FAILED -> MT.Down
                                running -> MT.Accent
                                else -> MT.Text2
                            })
                    }
                }
                if (step.lines.isNotEmpty()) {
                    val shown = if (expanded) step.lines else step.lines.take(PREVIEW_LINES)
                    Column(Modifier.padding(start = 18.dp, top = 4.dp)) {
                        shown.forEach { Text(it, color = MT.Text3, fontFamily = MT.Mono, fontSize = 11.sp, lineHeight = 16.sp) }
                        if (step.lines.size > PREVIEW_LINES) {
                            Text(
                                if (expanded) tx("show less", "daha az göster")
                                else tx("… +${step.lines.size - PREVIEW_LINES} more", "… +${step.lines.size - PREVIEW_LINES} daha"),
                                color = MT.Accent, fontFamily = MT.Mono, fontSize = 11.sp,
                                modifier = Modifier.clickable { expanded = !expanded }.padding(vertical = 3.dp),
                            )
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun Bullet(step: Step) {
    val color: Color = when {
        step.state == StepState.FAILED -> MT.Down
        step.kind == StepKind.WARN -> MT.Down
        step.kind == StepKind.ORDER || step.kind == StepKind.TRAIL -> MT.Up
        step.state == StepState.INFO -> MT.Text3
        else -> MT.Accent
    }
    if (step.state == StepState.INFO && step.kind != StepKind.WARN && step.kind != StepKind.APPROVAL) {
        Box(Modifier.size(7.dp).clip(CircleShape).border(1.5.dp, color, CircleShape))
    } else {
        Box(Modifier.size(8.dp).clip(CircleShape).background(color))
    }
}

private fun seconds(ms: Long): String =
    if (ms < 1000) "${ms}ms" else String.format(Locale.US, "%.1fs", ms / 1000.0)

private const val PREVIEW_LINES = 3
