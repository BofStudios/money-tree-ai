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
import com.bofstudios.moneytree.engine.AiNote
import com.bofstudios.moneytree.engine.BrainSnapshot
import com.bofstudios.moneytree.engine.Decision
import com.bofstudios.moneytree.engine.QualityMode
import com.bofstudios.moneytree.engine.QualityReport
import com.bofstudios.moneytree.engine.moodText
import com.bofstudios.moneytree.engine.EngineState
import com.bofstudios.moneytree.engine.HeldPosition
import com.bofstudios.moneytree.engine.TradeRecord
import com.bofstudios.moneytree.engine.formatQty
import com.bofstudios.moneytree.engine.startOfNyDay
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
    requestArm: () -> Unit,
    trades: () -> List<TradeRecord>,
    onOpenBrain: () -> Unit,
    brainIntro: Boolean,
    onBrainIntro: (QualityMode) -> Unit,
) {
    val steps by Hub.steps.collectAsState()
    val state by Hub.state.collectAsState()
    val running by Hub.running.collectAsState()
    val armed by Hub.armed.collectAsState()
    val update by Hub.update.collectAsState()
    // Re-read the journal whenever the feed moves; closes are announced there.
    val journal = remember(steps.size) { trades() }

    LazyColumn(
        Modifier.fillMaxSize(),
        contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 8.dp, bottom = 130.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item { MoneyCard(settings, onOpenMoney) }
        update?.let { u -> item { UpdateCard(u.first, u.second) } }
        if (settings.live && !armed && running) item { ArmBanner(requestArm) }
        if (running) item { BackgroundWarning() }
        if (settings.market == null) item { MarketQuestion(onPickMarket) }
        item { StatusCard(state, settings, running, armed, toast) }
        if (brainIntro) item { BrainIntro(onBrainIntro) }
        item { BrainCard(state.brain, onOpenBrain) }

        if (state.approvals.isNotEmpty() || state.suggestions.isNotEmpty()) {
            item { SectionTitle(if (state.approvals.isNotEmpty()) tx("Waiting for your OK", "Onayını bekliyor") else tx("Ideas (manual)", "Fikirler (manuel)")) }
            items(state.approvals, key = { it.id }) { ProposalCard(it, asking = true, settings, toast) }
            items(state.suggestions, key = { it.id }) { ProposalCard(it, asking = false, settings, toast) }
        }

        val mine = state.held.filter { it.managed }
        if (mine.isNotEmpty()) item { PositionsCard(mine) }
        item { TodayCard(journal) }
        if (state.notes.isNotEmpty()) item { NotesCard(state.notes) }
        item { NowPanel(steps, running, onOpenLive) }
    }
}

/** A newer version is out on GitHub: one tap to download it (Android asks before installing). */
@Composable
private fun UpdateCard(version: String, url: String) {
    val context = LocalContext.current
    Card(highlight = true, glow = true) {
        Text(tx("NEW VERSION", "YENİ SÜRÜM"), color = MT.Accent, fontSize = 11.sp, fontWeight = FontWeight.SemiBold, letterSpacing = 1.sp)
        Text(tx("Money Tree $version is ready", "Money Tree $version hazır"), fontWeight = FontWeight.SemiBold, fontSize = 17.sp,
            modifier = Modifier.padding(top = 4.dp))
        Text(tx("It installs over this one and keeps your keys and settings.", "Bunun üstüne kurulur, anahtarların ve ayarların kalır."),
            color = MT.Text2, fontSize = 13.sp, modifier = Modifier.padding(vertical = 6.dp))
        PrimaryButton(tx("Download", "İndir"), {
            context.startActivity(android.content.Intent(android.content.Intent.ACTION_VIEW, android.net.Uri.parse(url)))
        }, Modifier.fillMaxWidth())
    }
}

/** Once, for anyone who set up before 3.0: what is new, and how picky to be. */
@Composable
private fun BrainIntro(onPick: (QualityMode) -> Unit) {
    val w = Words(LocalTurkish.current)
    Card(highlight = true, glow = true) {
        Text(tx("NEW IN 3.0", "3.0'DA YENİ"), color = MT.Accent, fontSize = 11.sp, fontWeight = FontWeight.SemiBold, letterSpacing = 1.sp)
        Text(tx("It thinks before it buys", "Almadan önce düşünüyor"), fontWeight = FontWeight.SemiBold, fontSize = 18.sp, modifier = Modifier.padding(top = 4.dp))
        Text(tx("Five checks from each company's annual reports (business, moat, management, value, risk), a live news radar, two AI models voting on every buy, and it learns from every signal it follows.",
            "Her şirketin yıllık raporlarından 5 kontrol (işletme, kale, yönetim, değer, risk), canlı haber radarı, her alımda oy veren iki AI modeli — ve takip ettiği her sinyalden öğreniyor."),
            color = MT.Text2, fontSize = 13.sp, lineHeight = 18.sp, modifier = Modifier.padding(top = 6.dp))
        Text(tx("How picky should it be?", "Ne kadar seçici olsun?"), fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 12.dp, bottom = 8.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Chip(w.qualityModeName(QualityMode.STRICT), false, { onPick(QualityMode.STRICT) })
            Chip(w.qualityModeName(QualityMode.BALANCED) + " ★", true, { onPick(QualityMode.BALANCED) })
        }
        Spacer(Modifier.height(8.dp))
        Chip(w.qualityModeName(QualityMode.OFF), false, { onPick(QualityMode.OFF) })
        Text(tx("★ recommended. You can change it any time in Settings.", "★ önerilen. İstediğin zaman Ayarlar'dan değiştirebilirsin."),
            color = MT.Text3, fontSize = 11.5.sp, modifier = Modifier.padding(top = 8.dp))
    }
}

/** The research desk in one card: the market's mood, the best pick, what it has learned. */
@Composable
private fun BrainCard(b: BrainSnapshot, onOpen: () -> Unit) {
    val w = Words(LocalTurkish.current)
    val order = listOf(Decision.BUY_ZONE, Decision.WAIT, Decision.UNKNOWN, Decision.AVOID)
    val best = b.reports.values.sortedWith(compareBy<QualityReport> { order.indexOf(it.decision) }.thenByDescending { it.score }).firstOrNull()
    Card(Modifier.clickable(onClick = onOpen), glow = best?.decision == Decision.BUY_ZONE) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(tx("BRAIN", "BEYİN"), Modifier.weight(1f), color = MT.Text3, fontSize = 11.sp, fontWeight = FontWeight.SemiBold, letterSpacing = 1.sp)
            Text(tx("Open →", "Aç →"), color = MT.Accent, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
        }
        if (best == null && b.radar.market == null) {
            Text(tx("Reads the annual reports and the news once the bot runs.", "Bot çalışınca yıllık raporları ve haberleri okur."),
                color = MT.Text3, fontSize = 13.sp, modifier = Modifier.padding(top = 6.dp))
            return@Card
        }
        best?.let { r ->
            Row(Modifier.padding(top = 10.dp), verticalAlignment = Alignment.CenterVertically) {
                Ticker(r.symbol)
                Spacer(Modifier.width(10.dp))
                Column(Modifier.weight(1f)) {
                    Text(tx("Best right now", "Şu an en iyisi"), color = MT.Text3, fontSize = 11.sp)
                    Text("${r.symbol} · ${w.decisionName(r.decision)}", fontWeight = FontWeight.SemiBold, color = decisionColor(r.decision))
                }
                Text(String.format(Locale.US, "%.1f/5", r.score), fontFamily = MT.Mono, fontWeight = FontWeight.SemiBold)
            }
        }
        val counts = b.reports.values.groupingBy { it.decision }.eachCount()
        if (counts.isNotEmpty()) {
            Text(
                listOf(Decision.BUY_ZONE, Decision.WAIT, Decision.AVOID).filter { (counts[it] ?: 0) > 0 }
                    .joinToString(" · ") { "${counts[it]} ${w.decisionName(it).lowercase()}" },
                color = MT.Text2, fontSize = 12.5.sp, modifier = Modifier.padding(top = 8.dp),
            )
        }
        Row(Modifier.padding(top = 6.dp), verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(7.dp).clip(CircleShape).background(moodColor(b.radar.market)))
            Spacer(Modifier.width(6.dp))
            Text(tx("Market mood ", "Piyasa havası ") + (b.radar.market?.let { w.moodName(it) + " " + it.moodText() } ?: "—"),
                color = MT.Text3, fontSize = 12.sp)
        }
        val evo by Hub.evolution.collectAsState()
        val e = if (evo.tested > 0) evo else b.evolution
        if (e.tested > 0) {
            Text(
                tx("Strategy v${e.version} · ${String.format(Locale.US, "%,d", e.tested)} strategies tested", "Strateji v${e.version} · ${String.format(Locale.US, "%,d", e.tested)} strateji denendi"),
                color = MT.Accent, fontSize = 12.sp, fontFamily = MT.Mono, modifier = Modifier.padding(top = 4.dp),
            )
        }
        Text(
            tx("${b.shadowClosed + b.shadowOpen.size} signals followed · ${b.rules.size} rule(s) learned", "${b.shadowClosed + b.shadowOpen.size} sinyal takip edildi · ${b.rules.size} kural öğrenildi") +
                (if (b.radar.flags.isNotEmpty()) tx(" · ⚑ ${b.radar.flags.size} red flag(s)", " · ⚑ ${b.radar.flags.size} kırmızı bayrak") else ""),
            color = MT.Text3, fontSize = 12.sp, modifier = Modifier.padding(top = 4.dp),
        )
    }
}

/** Shown only while Android may still pause the bot with the screen off. */
@Composable
private fun BackgroundWarning() {
    val context = LocalContext.current
    val power = context.getSystemService(android.os.PowerManager::class.java)
    if (power.isIgnoringBatteryOptimizations(context.packageName)) return
    Card(borderColor = MT.Accent.copy(alpha = 0.5f)) {
        Text(tx("Android may pause the bot", "Android botu durdurabilir"), fontWeight = FontWeight.SemiBold, color = MT.Accent)
        Text(tx("Battery saving is on for Money Tree, so it can stop looking while the screen is off. Allow background running to keep it up around the clock.",
            "Money Tree için pil tasarrufu açık; ekran kapalıyken bakmayı bırakabilir. Gece gündüz çalışsın diye arka planda çalışmaya izin ver."),
            color = MT.Text2, fontSize = 13.sp, lineHeight = 18.sp, modifier = Modifier.padding(vertical = 6.dp))
        BatteryPermission()
    }
}

/** Real money, bot running, not armed: say it plainly and make arming one tap. */
@Composable
private fun ArmBanner(requestArm: () -> Unit) {
    Card(borderColor = MT.Down.copy(alpha = 0.6f)) {
        Text(tx("Real money is paused", "Gerçek para beklemede"), fontWeight = FontWeight.SemiBold, color = MT.Down)
        Text(tx("The bot is watching and managing what it holds, but will not buy until you arm it. Every restart pauses it again.",
            "Bot izliyor ve elindekileri yönetiyor ama sen devreye alana kadar almayacak. Her yeniden başlatma tekrar bekletir."),
            color = MT.Text2, fontSize = 13.sp, lineHeight = 18.sp, modifier = Modifier.padding(vertical = 6.dp))
        PrimaryButton(tx("Arm real money", "Gerçek parayı devreye al"), requestArm, Modifier.fillMaxWidth())
    }
}

/** Each position the bot opened: what it is doing, and where its stop lives. */
@Composable
private fun PositionsCard(held: List<HeldPosition>) {
    val w = Words(LocalTurkish.current)
    Card {
        Text(tx("HOLDING", "ELİMDE"), color = MT.Text3, fontSize = 11.sp, fontWeight = FontWeight.SemiBold, letterSpacing = 1.sp)
        held.forEach { h ->
            val p = h.position
            val pct = if (p.avgEntry > 0) (p.currentPrice / p.avgEntry - 1) * 100 else 0.0
            Spacer(Modifier.height(10.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                Ticker(p.symbol)
                Spacer(Modifier.width(10.dp))
                Column(Modifier.weight(1f)) {
                    Text("${p.symbol} · ${formatQty(p.qty)}", fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
                    Text("${w.usd(p.avgEntry)} → ${w.usd(p.currentPrice)}", color = MT.Text3, fontFamily = MT.Mono, fontSize = 11.sp)
                }
                Column(horizontalAlignment = Alignment.End) {
                    Text(w.signed(p.unrealizedPl), color = p.unrealizedPl.tone(), fontFamily = MT.Mono, fontWeight = FontWeight.SemiBold)
                    Text(String.format(Locale.US, "%+.2f%%", pct), color = pct.tone(), fontFamily = MT.Mono, fontSize = 11.sp)
                }
            }
            Text(
                "Stop ${h.stop?.let { w.usd(it) } ?: "—"} · ${tx("target", "hedef")} ${h.target?.let { w.usd(it) } ?: "—"} · " +
                    if (h.stopAtBroker) tx("stop at Alpaca", "stop Alpaca'da") else tx("stop on this phone", "stop bu telefonda"),
                color = if (h.stopAtBroker) MT.Up else MT.Accent, fontFamily = MT.Mono, fontSize = 10.5.sp,
                modifier = Modifier.padding(start = 48.dp, top = 2.dp),
            )
        }
    }
}

/** Today's closed trades, since midnight in New York. */
@Composable
private fun TodayCard(journal: List<TradeRecord>) {
    val w = Words(LocalTurkish.current)
    val today = remember(journal) {
        val start = startOfNyDay(System.currentTimeMillis())
        journal.filter { it.closedAt >= start }.sortedByDescending { it.closedAt }
    }
    val realised = today.sumOf { it.pnl }
    Card {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(tx("TODAY", "BUGÜN"), Modifier.weight(1f), color = MT.Text3, fontSize = 11.sp, fontWeight = FontWeight.SemiBold, letterSpacing = 1.sp)
            if (today.isNotEmpty()) Text(w.signed(realised), color = realised.tone(), fontFamily = MT.Mono, fontWeight = FontWeight.SemiBold)
        }
        if (today.isEmpty()) {
            Text(tx("No trades closed yet today. Each one shows here with what it made or lost.",
                "Bugün henüz kapanan işlem yok. Her biri ne kazandırıp kaybettirdiğiyle burada görünür."),
                color = MT.Text3, fontSize = 13.sp, modifier = Modifier.padding(top = 6.dp))
        } else {
            Text(tx("${today.size} trade(s) · ${today.count { it.pnl > 0 }} won · ${today.count { it.pnl < 0 }} lost",
                "${today.size} işlem · ${today.count { it.pnl > 0 }} kazanç · ${today.count { it.pnl < 0 }} kayıp"),
                color = MT.Text2, fontSize = 12.5.sp, modifier = Modifier.padding(top = 4.dp, bottom = 4.dp))
            today.take(6).forEach { t ->
                Row(Modifier.fillMaxWidth().padding(vertical = 5.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text(t.symbol, Modifier.width(58.dp), fontFamily = MT.Mono, fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
                    Text(w.reasonName(t.reason) + " · " + SimpleDateFormat("HH:mm", Locale.getDefault()).format(Date(t.closedAt)),
                        Modifier.weight(1f), color = MT.Text3, fontSize = 12.sp)
                    Text(w.signed(t.pnl), color = t.pnl.tone(), fontFamily = MT.Mono, fontSize = 13.sp)
                }
            }
        }
    }
}

/** What the AI said: why it bought, or why it passed. */
@Composable
private fun NotesCard(notes: List<AiNote>) {
    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
    LaunchedEffect(Unit) { while (true) { delay(30_000); now = System.currentTimeMillis() } }
    Card {
        Text(tx("WHAT THE BRAIN SAID", "BEYİN NE DEDİ"), color = MT.Text3, fontSize = 11.sp, fontWeight = FontWeight.SemiBold, letterSpacing = 1.sp)
        notes.take(4).forEach { n ->
            Spacer(Modifier.height(10.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(n.symbol, fontFamily = MT.Mono, fontWeight = FontWeight.SemiBold, fontSize = 12.5.sp, color = MT.Accent)
                Spacer(Modifier.width(8.dp))
                Text(agoText(now - n.at), color = MT.Text3, fontFamily = MT.Mono, fontSize = 11.sp)
            }
            Text(n.text, color = MT.Text2, fontSize = 13.sp, lineHeight = 18.sp, modifier = Modifier.padding(top = 2.dp))
        }
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
private fun StatusCard(state: EngineState, settings: TradingSettings, running: Boolean, armed: Boolean, toast: (String) -> Unit) {
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
            val stopped = tx("Stopped. It will not buy anything until you press Start; stops on what it holds stay at Alpaca.",
                "Durdu. Sen Başlat'a basana kadar hiçbir şey almaz; elindekilerin stop'ları Alpaca'da kalır.")
            // A fraction's stop is a DAY order the running bot renews each morning; stopped, it is not.
            val fractions = state.held.filter { it.managed && it.position.qty != kotlin.math.floor(it.position.qty) }
                .joinToString(", ") { it.position.symbol }
            val fractionNote = if (fractions.isEmpty()) "" else tx(
                " $fractions: its stop is a day order that ends at today's close and is not renewed while stopped.",
                " $fractions: stop'u gün sonunda biten bir emir; bot dururken yenilenmez.",
            )
            GhostButton(tx("Stop the bot", "Botu durdur"), { EngineService.stop(context); toast(stopped + fractionNote) },
                Modifier.fillMaxWidth().border(1.dp, MT.Down.copy(alpha = 0.5f), RoundedCornerShape(12.dp)), color = MT.Down)
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
        Modifier.size(38.dp).clip(RoundedCornerShape(11.dp)).background(MT.Surface2)
            .border(1.dp, MT.Line, RoundedCornerShape(11.dp)),
        contentAlignment = Alignment.Center,
    ) { Text(symbol.take(2), fontFamily = MT.Mono, fontWeight = FontWeight.SemiBold, fontSize = 12.sp, color = MT.Text) }
}
