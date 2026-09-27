package com.bofstudios.moneytree.ui

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.animation.animateContentSize
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.spring
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.background
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
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ExitToApp
import androidx.compose.material.icons.automirrored.filled.List
import androidx.compose.material.icons.filled.AccountCircle
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.DateRange
import androidx.compose.material.icons.filled.Done
import androidx.compose.material.icons.filled.Email
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.KeyboardArrowUp
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.ShoppingCart
import androidx.compose.material.icons.filled.Star
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.bofstudios.moneytree.engine.EngineState
import com.bofstudios.moneytree.engine.Market
import com.bofstudios.moneytree.engine.Proposal
import com.bofstudios.moneytree.engine.Step
import com.bofstudios.moneytree.engine.StepKind
import com.bofstudios.moneytree.engine.StepState
import com.bofstudios.moneytree.engine.TradingSettings
import com.bofstudios.moneytree.engine.Words
import com.bofstudios.moneytree.service.EngineService
import com.bofstudios.moneytree.service.Hub
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * Home: whose money this is and how to move it (first, always), then what the
 * bot is doing. The full step-by-step view lives in the Live tab.
 */
@Composable
fun HomeScreen(
    settings: TradingSettings,
    toast: (String) -> Unit,
    onOpenLive: () -> Unit,
    onOpenMoney: (withdraw: Boolean) -> Unit,
    onPickMarket: (Market) -> Unit,
) {
    val steps by Hub.steps.collectAsState()
    val state by Hub.state.collectAsState()
    val running by Hub.running.collectAsState()
    val armed by Hub.armed.collectAsState()

    LazyColumn(
        Modifier.fillMaxSize(),
        contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 8.dp, bottom = 130.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item { MoneyCard(settings, onOpenMoney) }
        if (settings.market == null) item { MarketQuestion(onPickMarket) }
        item { StatusCard(state, settings, running, armed) }

        if (state.approvals.isNotEmpty() || state.suggestions.isNotEmpty()) {
            item { SectionTitle(if (state.approvals.isNotEmpty()) tx("Waiting for your OK", "Onayını bekliyor") else tx("Ideas (manual)", "Fikirler (manuel)")) }
            items(state.approvals, key = { it.id }) { ProposalCard(it, asking = true, settings, toast) }
            items(state.suggestions, key = { it.id }) { ProposalCard(it, asking = false, settings, toast) }
        }

        item { NowPanel(steps, running, onOpenLive) }
    }
}

/** Asked once, for anyone who set up before this question existed. */
@Composable
fun MarketQuestion(onPick: (Market) -> Unit) {
    Card(highlight = true) {
        Text(tx("Which market should I watch?", "Hangi piyasayı izleyeyim?"), fontWeight = FontWeight.SemiBold, fontSize = 16.sp)
        Spacer(Modifier.height(10.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Chip(tx("US", "ABD"), false, { onPick(Market.US) })
            Chip(tx("Europe", "Avrupa"), false, { onPick(Market.EUROPE) })
            Chip(tx("Both", "İkisi"), false, { onPick(Market.BOTH) })
        }
        Text(marketNote(), color = MT.Text3, fontSize = 12.sp, lineHeight = 17.sp, modifier = Modifier.padding(top = 10.dp))
    }
}

@Composable
fun marketNote() = tx(
    "Alpaca trades on US exchanges only. \"Europe\" means European companies also listed in New York — ASML, SAP, Novo Nordisk, AstraZeneca, Shell and more — plus a Europe ETF, in dollars, during US hours (about 16:30–23:00 Turkey time).",
    "Alpaca sadece ABD borsalarında işlem yapar. \"Avrupa\", New York'ta da işlem gören Avrupa şirketleri demek — ASML, SAP, Novo Nordisk, AstraZeneca, Shell ve dahası — artı bir Avrupa ETF'i; dolarla, ABD saatlerinde (Türkiye saatiyle yaklaşık 16:30–23:00).",
)

@Composable
private fun StatusCard(state: EngineState, settings: TradingSettings, running: Boolean, armed: Boolean) {
    val context = LocalContext.current
    val w = Words(LocalTurkish.current)
    val account = state.account
    val live = running && state.marketOpen == true && state.lastError == null

    Card(highlight = live, glow = live) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Pulse(
                color = when {
                    !running -> MT.Text3
                    state.lastError != null -> MT.Down
                    state.marketOpen == true -> MT.Accent
                    else -> MT.Text2
                },
                live = live,
            )
            Spacer(Modifier.width(6.dp))
            Text(
                when {
                    !running -> tx("Stopped", "Durdu")
                    state.lastError != null -> tx("Problem — retrying", "Sorun — yeniden deniyor")
                    state.marketOpen == true -> tx("Running · market open", "Çalışıyor · piyasa açık")
                    state.marketOpen == false -> tx("Running · market closed", "Çalışıyor · piyasa kapalı")
                    else -> tx("Starting…", "Başlıyor…")
                },
                Modifier.weight(1f), fontWeight = FontWeight.SemiBold, fontSize = 15.sp,
            )
            Tag(if (settings.live) (if (armed) tx("REAL · ARMED", "GERÇEK · DEVREDE") else tx("REAL", "GERÇEK")) else "PAPER",
                if (settings.live) MT.Down else MT.Accent)
        }

        Spacer(Modifier.height(14.dp))
        Text(
            if (settings.live) tx("Your real balance", "Gerçek bakiyen") else tx("Practice balance (Alpaca paper)", "Deneme bakiyesi (Alpaca paper)"),
            color = MT.Text3, fontSize = 11.sp, fontWeight = FontWeight.SemiBold,
        )
        AnimatedMoney(account?.equity, w::usd, Figure)

        if (account != null) {
            val today = account.equity - account.lastEquity
            Text("${w.signed(today)} ${tx("today", "bugün")}", color = today.tone(), fontFamily = MT.Mono, fontSize = 13.sp)
            state.baselineEquity?.let { base ->
                val since = account.equity - base
                Spacer(Modifier.height(10.dp))
                Row(
                    Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(MT.Surface2).padding(12.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(
                        if (since < 0) tx("Money Tree has lost you", "Money Tree sana kaybettirdi")
                        else tx("Money Tree has made you", "Money Tree sana kazandırdı"),
                        Modifier.weight(1f), color = MT.Text2, fontSize = 13.sp,
                    )
                    Text(w.signed(since), color = since.tone(), fontFamily = MT.Mono, fontWeight = FontWeight.SemiBold)
                }
                Text(
                    tx("Since you connected this account · ${w.usd(base)} then", "Bu hesabı bağladığından beri · o zaman ${w.usd(base)}"),
                    color = MT.Text3, fontSize = 11.sp, modifier = Modifier.padding(top = 4.dp),
                )
            }
        }

        state.haltReason?.let {
            Spacer(Modifier.height(10.dp))
            Text(it, color = MT.Down, fontSize = 12.5.sp)
        }

        Spacer(Modifier.height(12.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
            Tag(w.autonomyName(settings.autonomy))
            Tag(w.tfName(settings.horizon.timeframe))
            Spacer(Modifier.weight(1f))
            if (running) {
                GhostButton(tx("Look now", "Şimdi bak"), { EngineService.scanNow(context) }, color = MT.Accent)
            }
        }
        Spacer(Modifier.height(4.dp))
        if (running) {
            GhostButton(tx("Stop the bot", "Botu durdur"), { EngineService.stop(context) }, Modifier.fillMaxWidth())
        } else {
            PrimaryButton(tx("Start Money Tree", "Money Tree'yi başlat"), { EngineService.start(context) }, Modifier.fillMaxWidth())
        }
    }
}

@Composable
private fun ProposalCard(p: Proposal, asking: Boolean, settings: TradingSettings, toast: (String) -> Unit) {
    val w = Words(LocalTurkish.current)
    val scope = rememberCoroutineScope()
    var busy by remember { mutableStateOf(false) }
    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
    LaunchedEffect(p.id) { while (true) { delay(1000); now = System.currentTimeMillis() } }
    val e = p.entry

    Card(highlight = asking, modifier = Modifier.padding(bottom = 8.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Ticker(e.symbol)
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(
                    if (asking) tx("Buy ${e.qtyText} ${e.symbol} at about ${w.usd(e.price)}", "${e.symbol}: ${e.qtyText} adet al, yaklaşık ${w.usd(e.price)}")
                    else tx("Would buy ${e.qtyText} ${e.symbol} at ${w.usd(e.price)}", "${e.symbol}: ${e.qtyText} adet alırdım, ${w.usd(e.price)}"),
                    fontWeight = FontWeight.SemiBold, fontSize = 14.sp,
                )
                Text("Stop ${w.usd(e.stop)} · ${tx("target", "hedef")} ${w.usd(e.target)}",
                    color = MT.Text3, fontFamily = MT.Mono, fontSize = 11.sp)
                Text(e.reason, color = MT.Text3, fontSize = 11.5.sp)
            }
        }
        Spacer(Modifier.height(10.dp))
        Row(verticalAlignment = Alignment.CenterVertically) {
            if (asking) {
                val left = ((p.expiresAt - now) / 60_000).coerceAtLeast(0)
                Text(tx("lapses in $left min", "$left dk içinde düşer"), color = MT.Accent,
                    fontFamily = MT.Mono, fontSize = 11.sp, modifier = Modifier.weight(1f))
                GhostButton(tx("Skip", "Geç"), { Hub.engine?.skip(p.id) })
                PrimaryButton(tx("Approve", "Onayla"), enabled = !busy, onClick = {
                    val engine = Hub.engine ?: return@PrimaryButton
                    busy = true
                    scope.launch {
                        val r = engine.approve(p.id)
                        busy = false
                        toast(r.message)
                    }
                })
            } else {
                Spacer(Modifier.weight(1f))
                GhostButton(tx("Dismiss", "Kapat"), { Hub.engine?.skip(p.id) })
            }
        }
        if (asking && settings.live) {
            Text(tx("Real money. Re-checked against the live price when you tap.",
                "Gerçek para. Dokunduğunda güncel fiyatla tekrar kontrol edilir."),
                color = MT.Down, fontSize = 11.sp, modifier = Modifier.padding(top = 6.dp))
        }
    }
}

/**
 * The top of the monitor: what the bot is doing this second, the way an agent
 * shows the tool it is running. The spinner and clock are tied to a real step
 * that is open right now; when nothing is running it says so.
 */
@Composable
private fun NowPanel(steps: List<Step>, running: Boolean, onOpenLive: () -> Unit) {
    val current = steps.lastOrNull { it.state == StepState.RUNNING }
    val latest = steps.lastOrNull()
    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
    LaunchedEffect(Unit) { while (true) { delay(200); now = System.currentTimeMillis() } }

    Card(highlight = current != null) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Pulse(if (current != null) MT.Accent else if (running) MT.Text2 else MT.Text3, live = current != null, size = 7)
            Text(tx("NOW", "ŞU AN"), color = MT.Text3, fontSize = 11.sp, fontWeight = FontWeight.SemiBold, letterSpacing = 1.sp)
            Spacer(Modifier.weight(1f))
            Text("${steps.size} ${tx("steps", "adım")}", color = MT.Text3, fontFamily = MT.Mono, fontSize = 11.sp)
        }
        Spacer(Modifier.height(10.dp))
        // The step itself is the animation's target, so a card fading out keeps
        // showing the step it was about, not the one replacing it.
        AnimatedContent(current ?: latest, contentKey = { it?.id }, transitionSpec = {
            (fadeIn(tween(220)) + slideInVertically(tween(260)) { it / 3 }) togetherWith fadeOut(tween(120))
        }, label = "now") { step ->
            Column {
                when {
                    step == null && running -> Text(tx("Starting…", "Başlıyor…"), fontSize = 15.sp)
                    step == null -> Text(tx("Idle. Start the bot and watch it work here.", "Boşta. Botu başlat, burada çalışmasını izle."),
                        color = MT.Text2, fontSize = 14.sp)
                    step.state == StepState.RUNNING -> {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            CircularProgressIndicator(Modifier.size(18.dp), color = MT.Accent, strokeWidth = 2.dp)
                            Spacer(Modifier.width(10.dp))
                            Text(step.title, fontWeight = FontWeight.SemiBold, fontSize = 15.sp, lineHeight = 20.sp)
                        }
                        Text(
                            String.format(Locale.US, "%.1fs", (now - step.startedAt) / 1000.0),
                            color = MT.Accent, fontFamily = MT.Mono, fontSize = 12.sp,
                            modifier = Modifier.padding(start = 28.dp, top = 4.dp),
                        )
                    }
                    else -> {
                        Text(step.title, fontWeight = FontWeight.Medium, fontSize = 15.sp, lineHeight = 20.sp)
                        Text(
                            tx("finished ", "bitti, ") + agoText(now - (step.endedAt ?: step.startedAt)),
                            color = MT.Text3, fontFamily = MT.Mono, fontSize = 11.5.sp, modifier = Modifier.padding(top = 4.dp),
                        )
                    }
                }
            }
        }
        Spacer(Modifier.height(14.dp))
        Row {
            Stat(steps.count { it.kind == StepKind.ANALYSE && it.state == StepState.DONE }, tx("scans", "tarama"), Modifier.weight(1f))
            Stat(steps.count { it.kind == StepKind.ORDER && it.state == StepState.DONE }, tx("orders", "emir"), Modifier.weight(1f))
            Stat(steps.count { it.state == StepState.FAILED || it.kind == StepKind.WARN }, tx("problems", "sorun"), Modifier.weight(1f),
                warn = true)
        }
        Spacer(Modifier.height(6.dp))
        GhostButton(tx("Watch it live →", "Canlı izle →"), onOpenLive, Modifier.fillMaxWidth(), color = MT.Accent)
    }
}

@Composable
private fun Stat(value: Int, label: String, modifier: Modifier, warn: Boolean = false) {
    Column(modifier) {
        Text(value.toString(), fontFamily = MT.Mono, fontWeight = FontWeight.SemiBold, fontSize = 18.sp,
            color = if (warn && value > 0) MT.Down else MT.Text)
        Text(label, color = MT.Text3, fontSize = 11.sp)
    }
}

@Composable
private fun agoText(ms: Long): String {
    val s = ms / 1000
    return when {
        s < 60 -> tx("${s}s ago", "$s sn önce")
        s < 3600 -> tx("${s / 60}m ago", "${s / 60} dk önce")
        else -> tx("${s / 3600}h ago", "${s / 3600} sa önce")
    }
}

@Composable
fun Ticker(symbol: String) {
    Box(
        Modifier.size(38.dp).clip(RoundedCornerShape(11.dp)).background(MT.Surface2),
        contentAlignment = Alignment.Center,
    ) { Text(symbol.take(2), fontFamily = MT.Mono, fontWeight = FontWeight.SemiBold, fontSize = 12.sp, color = MT.Text) }
}
