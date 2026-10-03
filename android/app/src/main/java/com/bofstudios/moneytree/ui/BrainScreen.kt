package com.bofstudios.moneytree.ui

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.animateContentSize
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
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
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.lerp
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.bofstudios.moneytree.data.BrainFiles
import com.bofstudios.moneytree.engine.AltSignals
import com.bofstudios.moneytree.engine.BrainSnapshot
import com.bofstudios.moneytree.engine.Discovery
import com.bofstudios.moneytree.engine.BucketStats
import com.bofstudios.moneytree.engine.CheckKind
import com.bofstudios.moneytree.engine.Decision
import com.bofstudios.moneytree.engine.NewsItem
import com.bofstudios.moneytree.engine.QualityReport
import com.bofstudios.moneytree.engine.RadarSnapshot
import com.bofstudios.moneytree.engine.Sentiment
import com.bofstudios.moneytree.engine.ShadowTrade
import com.bofstudios.moneytree.engine.TradingSettings
import com.bofstudios.moneytree.engine.Verdict
import com.bofstudios.moneytree.engine.Words
import com.bofstudios.moneytree.engine.moodText
import com.bofstudios.moneytree.service.Hub
import kotlinx.coroutines.delay
import java.io.File
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.sin

/**
 * The research desk, made visible: what the five checks say about every
 * stock, what the news wire is saying right now, and what the bot has
 * learned from following its own signals.
 */
@Composable
fun BrainScreen(settings: TradingSettings, toast: (String) -> Unit) {
    val state by Hub.state.collectAsState()
    val running by Hub.running.collectAsState()
    val brain = state.brain
    var tab by rememberSaveable { mutableStateOf(0) }

    Column(Modifier.fillMaxSize()) {
        Column(Modifier.padding(horizontal = 16.dp, vertical = 4.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(tx("Brain", "Beyin"), fontSize = 22.sp, fontWeight = FontWeight.SemiBold)
                Spacer(Modifier.width(10.dp))
                Tag(tx("${brain.shadowClosed + brain.shadowOpen.size} signals followed", "${brain.shadowClosed + brain.shadowOpen.size} sinyal takipte"))
            }
            Text(tx("Five checks · the whole market's news · alt data · it improves itself", "5 kontrol · tüm piyasanın haberleri · alternatif veri · kendini geliştiriyor"),
                color = MT.Text2, fontSize = 12.5.sp)
            Spacer(Modifier.height(10.dp))
            Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Chip(tx("Picks", "Seçimler"), tab == 0, { tab = 0 })
                Chip(tx("News", "Haberler"), tab == 1, { tab = 1 })
                Chip(tx("Learning", "Öğrenme"), tab == 2, { tab = 2 })
                Chip(tx("Evolution", "Gelişim"), tab == 3, { tab = 3 })
            }
        }
        if (tab != 3 && brain.reports.isEmpty() && brain.radar.items.isEmpty() && brain.shadowClosed == 0 && brain.shadowOpen.isEmpty()) {
            Column(Modifier.padding(16.dp)) {
                Card(glow = true) {
                    Text(tx("The brain wakes up with the bot", "Beyin botla birlikte uyanır"), fontWeight = FontWeight.SemiBold, fontSize = 16.sp)
                    Text(
                        if (running) tx("Reading the annual reports and the news now — this takes a few seconds the first time.",
                            "Şu an yıllık raporları ve haberleri okuyor — ilk seferde birkaç saniye sürer.")
                        else tx("Start Money Tree and it reads each company's annual reports (SEC), the news wire and its own past signals. Everything shows here.",
                            "Money Tree'yi başlat; her şirketin yıllık raporlarını (SEC), haber akışını ve kendi geçmiş sinyallerini okur. Hepsi burada görünür."),
                        color = MT.Text2, fontSize = 13.sp, lineHeight = 18.sp, modifier = Modifier.padding(top = 6.dp),
                    )
                }
            }
            return
        }
        when (tab) {
            0 -> PicksTab(brain, settings)
            1 -> NewsTab(brain.radar)
            2 -> LearningTab(brain, settings, toast)
            else -> EvolutionTab(brain.evolution, settings, toast)
        }
    }
}

// ================================================================== picks

@Composable
private fun PicksTab(brain: BrainSnapshot, settings: TradingSettings) {
    val w = Words(LocalTurkish.current)
    var open by rememberSaveable { mutableStateOf<String?>(null) }
    val order = listOf(Decision.BUY_ZONE, Decision.WAIT, Decision.UNKNOWN, Decision.AVOID)
    val reports = brain.reports.values.sortedWith(compareBy<QualityReport> { order.indexOf(it.decision) }.thenByDescending { it.score })

    LazyColumn(
        Modifier.fillMaxSize(),
        contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 12.dp, bottom = 130.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item { MoodCard(brain.radar, compact = true) }
        item {
            Text(
                tx("Every stock must pass five checks. If the price is wrong, it waits. ", "Her hisse 5 kontrolden geçmeli. Fiyat doğru değilse bekler. ") +
                    tx("Mode: ", "Mod: ") + w.qualityModeName(settings.qualityMode),
                color = MT.Text3, fontSize = 12.sp, lineHeight = 17.sp,
            )
        }
        items(reports, key = { it.symbol }) { r ->
            DecisionCard(r, brain.radar.moods[r.symbol]?.mood, brain.radar.moods[r.symbol]?.count24h ?: 0,
                brain.radar.flags.filter { it.symbol == r.symbol }.map { w.flagName(it.kind) }.distinct(),
                alt = brain.alt[r.symbol], found = brain.discovered.firstOrNull { it.symbol == r.symbol },
                expanded = open == r.symbol) { open = if (open == r.symbol) null else r.symbol }
        }
        item {
            Text(
                tx("From each company's own annual reports at the SEC. Value estimate: owner earnings grown conservatively and discounted at 10%. A tool, not advice.",
                    "Her şirketin SEC'teki kendi yıllık raporlarından. Değer tahmini: sahibine kalan kazanç, temkinli büyütülüp %10 ile iskonto edilir. Bir araç, yatırım tavsiyesi değil."),
                color = MT.Text3, fontSize = 11.sp, lineHeight = 15.sp,
            )
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun DecisionCard(
    r: QualityReport, mood: Double?, count: Int, flags: List<String>,
    alt: AltSignals?, found: Discovery?,
    expanded: Boolean, onClick: () -> Unit,
) {
    val w = Words(LocalTurkish.current)
    val tone = decisionColor(r.decision)
    Card(
        Modifier.clickable(onClick = onClick).animateContentSize(),
        borderColor = if (r.decision == Decision.BUY_ZONE) MT.Accent.copy(alpha = 0.6f) else null,
        glow = r.decision == Decision.BUY_ZONE,
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Ticker(r.symbol)
            Spacer(Modifier.width(10.dp))
            Column(Modifier.weight(1f)) {
                Text(r.symbol, fontFamily = MT.Mono, fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
                Text(if (r.fund) tx("Fund · ${r.name}", "Fon · ${r.name}") else r.name, color = MT.Text3, fontSize = 11.5.sp,
                    maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
            Column(horizontalAlignment = Alignment.End) {
                Text(
                    w.decisionName(r.decision),
                    style = TextStyle(
                        brush = if (r.decision == Decision.BUY_ZONE || r.decision == Decision.WAIT)
                            Brush.verticalGradient(listOf(Color(0xFFFFE680), MT.Accent, Color(0xFFC79A00)))
                        else Brush.verticalGradient(listOf(tone, tone)),
                        fontWeight = FontWeight.Black, fontSize = 22.sp, letterSpacing = 0.5.sp,
                    ),
                )
                Text(String.format(java.util.Locale.US, "%.1f / 5", r.score), color = MT.Text3, fontFamily = MT.Mono, fontSize = 11.sp)
            }
        }
        Spacer(Modifier.height(12.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(5.dp)) {
            CheckKind.entries.forEach { k ->
                VerdictPill(w.checkName(k), r.check(k)?.verdict ?: Verdict.UNKNOWN, Modifier.weight(1f))
            }
        }
        if (r.value != null && r.price != null) {
            Spacer(Modifier.height(12.dp))
            ValueScale(r.price, r.value)
            Text(
                tx("Price ${w.usd(r.price)} · value ~${w.usd(r.value)} · ", "Fiyat ${w.usd(r.price)} · değer ~${w.usd(r.value)} · ") +
                    (r.priceToValue?.let { w.priceVsValue(it) } ?: ""),
                color = MT.Text2, fontFamily = MT.Mono, fontSize = 11.sp, modifier = Modifier.padding(top = 6.dp),
            )
        }
        Spacer(Modifier.height(8.dp))
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(7.dp).clip(CircleShape).background(moodColor(mood)))
            Spacer(Modifier.width(6.dp))
            Text(
                tx("News ", "Haber ") + (mood?.let { w.moodName(it) + " " + it.moodText() } ?: tx("quiet", "sessiz")) + " · $count" + tx("/24h", "/24sa"),
                color = MT.Text3, fontSize = 11.5.sp, modifier = Modifier.weight(1f),
            )
            Text(if (expanded) "▴" else "▾", color = MT.Text3, fontSize = 12.sp)
        }
        alt?.let { a ->
            val parts = listOfNotNull(
                a.attention?.let { "${w.attentionName(it)} ×" + String.format(java.util.Locale.US, "%.1f", it) },
                a.insiderFilings30d?.let { tx("insiders $it/30d", "içeriden $it/30g") },
                a.lastEvent?.let { "8-K " + w.daysAgo(System.currentTimeMillis() - it.filedAt) + ": " + w.eventItems(it.items) },
                a.nextResults?.let { tx("results ~", "bilanço ~") + w.day(it) },
            )
            if (parts.isNotEmpty()) {
                Text(tx("ALT DATA · ", "ALTERNATİF VERİ · ") + parts.joinToString(" · "), color = MT.Text3, fontSize = 11.sp, lineHeight = 15.sp,
                    modifier = Modifier.padding(top = 4.dp))
            }
        }
        found?.let { d ->
            Text(tx("★ Found in the whole market's news · ${d.mentions} stories in 24h", "★ Tüm piyasanın haberlerinde bulundu · 24 saatte ${d.mentions} haber"),
                color = MT.Accent, fontSize = 11.5.sp, modifier = Modifier.padding(top = 4.dp))
        }
        if (flags.isNotEmpty()) {
            FlowRow(Modifier.padding(top = 6.dp), horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                flags.forEach { Tag("⚑ $it", MT.Down) }
            }
        }
        AnimatedVisibility(expanded, enter = expandVertically() + fadeIn(), exit = shrinkVertically()) {
            Column(Modifier.padding(top = 12.dp)) {
                Text(w.decisionLine(r.decision), color = tone, fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
                r.checks.forEachIndexed { i, c ->
                    Spacer(Modifier.height(10.dp))
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text("${i + 1}.", color = MT.Text3, fontFamily = MT.Mono, fontSize = 12.sp)
                        Spacer(Modifier.width(6.dp))
                        Text(w.checkQuestion(c.kind), Modifier.weight(1f), fontWeight = FontWeight.Medium, fontSize = 13.5.sp)
                        Text(w.verdictName(c.verdict).uppercase(), color = verdictColor(c.verdict), fontFamily = MT.Mono,
                            fontWeight = FontWeight.SemiBold, fontSize = 11.sp)
                    }
                    c.facts.mapNotNull { w.factText(it) }.forEach { line ->
                        Text("· $line", color = MT.Text2, fontSize = 12.sp, lineHeight = 16.sp, modifier = Modifier.padding(start = 20.dp, top = 2.dp))
                    }
                    if (c.facts.isEmpty()) {
                        Text(tx("· not in the filings", "· raporlarda yok"), color = MT.Text3, fontSize = 12.sp, modifier = Modifier.padding(start = 20.dp, top = 2.dp))
                    }
                }
                r.aiRead?.let { read ->
                    Spacer(Modifier.height(12.dp))
                    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(MT.Surface2).padding(12.dp)) {
                        Text(tx("THE AI'S READ — may be wrong", "AI'IN YORUMU — yanılabilir"), color = MT.Accent, fontSize = 10.5.sp,
                            fontWeight = FontWeight.SemiBold, letterSpacing = 1.sp)
                        Text(read, color = MT.Text2, fontSize = 12.5.sp, lineHeight = 18.sp, modifier = Modifier.padding(top = 4.dp))
                    }
                }
                r.fiscalYearEnd?.let {
                    Text(tx("Latest annual report: fiscal year ending $it", "Son yıllık rapor: mali yıl sonu $it"),
                        color = MT.Text3, fontSize = 11.sp, modifier = Modifier.padding(top = 10.dp))
                }
            }
        }
    }
}

@Composable
private fun VerdictPill(label: String, v: Verdict, modifier: Modifier) {
    val c = verdictColor(v)
    Column(
        modifier.clip(RoundedCornerShape(9.dp))
            .background(if (v == Verdict.UNKNOWN) MT.Surface2 else c.copy(alpha = 0.10f))
            .border(1.dp, if (v == Verdict.UNKNOWN) MT.Line else c.copy(alpha = 0.55f), RoundedCornerShape(9.dp))
            .padding(vertical = 6.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(when (v) { Verdict.PASS -> "✓"; Verdict.WATCH -> "~"; Verdict.FAIL -> "✕"; Verdict.UNKNOWN -> "—" },
            color = c, fontWeight = FontWeight.Bold, fontSize = 13.sp)
        Text(label, color = if (v == Verdict.UNKNOWN) MT.Text3 else c, fontSize = 8.5.sp, fontWeight = FontWeight.SemiBold,
            letterSpacing = 0.2.sp, maxLines = 1, overflow = TextOverflow.Clip)
    }
}

/**
 * The scale from the screenshots, as a line: where the price sits against
 * the value estimate. Gold tick = value, white dot = price.
 */
@Composable
private fun ValueScale(price: Double, value: Double) {
    val lo = minOf(price, value) * 0.8
    val hi = maxOf(price, value) * 1.1
    val anim by animateFloatAsState(1f, tween(800), label = "scale")
    Canvas(Modifier.fillMaxWidth().height(22.dp)) {
        fun x(v: Double) = ((v - lo) / (hi - lo)).toFloat() * size.width
        val mid = size.height / 2
        drawLine(MT.Line, Offset(0f, mid), Offset(size.width, mid), strokeWidth = 4f, cap = StrokeCap.Round)
        val vx = x(value); val px = x(price)
        // The gap between the two is green when the price is under the value, red over it.
        val gap = if (price <= value) MT.Up else MT.Down
        drawLine(gap.copy(alpha = 0.7f), Offset(minOf(vx, px), mid), Offset(minOf(vx, px) + (kotlin.math.abs(px - vx)) * anim, mid), strokeWidth = 4f, cap = StrokeCap.Round)
        drawLine(MT.Accent, Offset(vx, 2f), Offset(vx, size.height - 2f), strokeWidth = 5f, cap = StrokeCap.Round)
        drawCircle(Color.White, radius = 7f, center = Offset(px, mid))
    }
}

// =================================================================== news

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun NewsTab(radar: RadarSnapshot) {
    val w = Words(LocalTurkish.current)
    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
    LaunchedEffect(Unit) { while (true) { delay(30_000); now = System.currentTimeMillis() } }
    LazyColumn(
        Modifier.fillMaxSize(),
        contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 12.dp, bottom = 130.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item { MoodCard(radar, compact = false) }
        if (radar.hot.isNotEmpty()) item {
            Card {
                Label(tx("WHOLE MARKET · MOST TALKED ABOUT, 24H · ${radar.wireSize} STORIES", "TÜM PİYASA · EN ÇOK KONUŞULANLAR, 24 SA · ${radar.wireSize} HABER"))
                radar.hot.take(8).forEach { h ->
                    Row(Modifier.fillMaxWidth().padding(vertical = 5.dp), verticalAlignment = Alignment.CenterVertically) {
                        Text(h.symbol, Modifier.width(60.dp), fontFamily = MT.Mono, fontWeight = FontWeight.SemiBold, fontSize = 12.5.sp)
                        CenterBar(h.mood, Modifier.weight(1f).height(8.dp))
                        Spacer(Modifier.width(10.dp))
                        Text("${h.mentions}", Modifier.width(30.dp), color = MT.Text2, fontFamily = MT.Mono, fontSize = 12.sp)
                    }
                }
                Text(tx("A few of these may be added to the watch for three days — only if they pass the five checks.",
                    "Bunlardan birkaçı 3 günlüğüne izlemeye alınabilir — sadece 5 kontrolden geçerse."),
                    color = MT.Text3, fontSize = 11.sp, modifier = Modifier.padding(top = 6.dp))
            }
        }
        if (radar.moods.isNotEmpty()) item {
            Card {
                Label(tx("BY STOCK · 48H, RECENT COUNTS MORE", "HİSSE BAZINDA · 48 SA, YENİSİ DAHA ÇOK SAYILIR"))
                radar.moods.values.sortedByDescending { it.mood ?: -9.0 }.forEach { m ->
                    Row(Modifier.fillMaxWidth().padding(vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                        Text(m.symbol, Modifier.width(56.dp), fontFamily = MT.Mono, fontWeight = FontWeight.SemiBold, fontSize = 12.5.sp)
                        CenterBar(m.mood, Modifier.weight(1f).height(10.dp))
                        Spacer(Modifier.width(10.dp))
                        Text(m.mood?.moodText() ?: "—", Modifier.width(48.dp), color = moodColor(m.mood), fontFamily = MT.Mono, fontSize = 11.5.sp)
                        Text("${m.count24h}", Modifier.width(22.dp), color = MT.Text3, fontFamily = MT.Mono, fontSize = 11.sp)
                    }
                }
            }
        }
        if (radar.topics.isNotEmpty()) item {
            Card {
                Label(tx("TOPICS · LAST 24H", "KONULAR · SON 24 SA"))
                radar.topics.take(8).forEach { t ->
                    Row(Modifier.fillMaxWidth().padding(vertical = 5.dp), verticalAlignment = Alignment.CenterVertically) {
                        Box(Modifier.size(6.dp).clip(CircleShape).background(moodColor(t.mood)))
                        Spacer(Modifier.width(8.dp))
                        Text(w.topicName(t.topic), Modifier.weight(1f), fontSize = 13.sp)
                        Text("${t.count}", color = MT.Text2, fontFamily = MT.Mono, fontSize = 12.sp)
                        Spacer(Modifier.width(10.dp))
                        Text(t.mood.moodText(), color = moodColor(t.mood), fontFamily = MT.Mono, fontSize = 11.5.sp)
                    }
                }
            }
        }
        if (radar.flags.isNotEmpty()) item {
            Card(borderColor = MT.Down.copy(alpha = 0.5f)) {
                Label(tx("RED FLAGS · THEY HOLD BUYS BACK", "KIRMIZI BAYRAKLAR · ALIMI DURDURUR"), MT.Down)
                radar.flags.take(8).forEach { f ->
                    Text("⚑ ${f.symbol} · ${w.flagName(f.kind)}", color = MT.Down, fontWeight = FontWeight.SemiBold, fontSize = 12.5.sp,
                        modifier = Modifier.padding(top = 8.dp))
                    Text(f.headline, color = MT.Text2, fontSize = 12.sp, lineHeight = 16.sp)
                }
            }
        }
        item { Label(tx("LIVE WIRE · ${radar.items.size} KEPT · ${radar.aiRead} READ BY AI", "CANLI AKIŞ · ${radar.items.size} BAŞLIK · ${radar.aiRead} TANESİNİ AI OKUDU")) }
        if (radar.items.isEmpty()) item {
            Text(tx("No headlines yet. The wire is read on every look.", "Henüz başlık yok. Akış her bakışta okunur."), color = MT.Text3, fontSize = 13.sp)
        }
        items(radar.items, key = { it.id }) { NewsRow(it, now, w) }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun NewsRow(n: NewsItem, now: Long, w: Words) {
    val text = remember(n.id, n.headline) { highlighted(n.headline) }
    Column(Modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(ago(now - n.createdAt), color = MT.Text3, fontFamily = MT.Mono, fontSize = 10.5.sp)
            Spacer(Modifier.width(8.dp))
            Text(n.symbols.take(4).joinToString(" "), color = MT.Accent, fontFamily = MT.Mono, fontSize = 10.5.sp,
                modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text((if (n.aiScore != null) "AI " else "") + n.mood.moodText(), color = moodColor(n.mood), fontFamily = MT.Mono, fontSize = 10.5.sp)
        }
        Text(text, fontSize = 13.5.sp, lineHeight = 19.sp, modifier = Modifier.padding(top = 3.dp))
        if (n.topics.isNotEmpty() || n.source.isNotBlank()) {
            Text(
                listOfNotNull(n.source.takeIf { it.isNotBlank() }).plus(n.topics.take(3).map { w.topicName(it) }).joinToString(" · "),
                color = MT.Text3, fontSize = 10.5.sp, modifier = Modifier.padding(top = 3.dp),
            )
        }
        Spacer(Modifier.height(10.dp))
        Box(Modifier.fillMaxWidth().height(1.dp).background(MT.Line))
    }
}

/** The words that moved the score, colored: green good, red bad. */
private fun highlighted(text: String): AnnotatedString {
    val weights = Sentiment.hits(text).associate { it.word to it.weight }
    return buildAnnotatedString {
        var last = 0
        for (m in Regex("[A-Za-z0-9'-]+").findAll(text)) {
            append(text.substring(last, m.range.first))
            val wgt = weights[m.value.lowercase()]
            if (wgt != null) withStyle(SpanStyle(color = if (wgt > 0) MT.Up else MT.Down, fontWeight = FontWeight.SemiBold)) { append(m.value) }
            else append(m.value)
            last = m.range.last + 1
        }
        append(text.substring(last))
    }
}

/** The market's mood: a gauge from −1 to +1 and the last 24 hours, hour by hour. */
@Composable
private fun MoodCard(radar: RadarSnapshot, compact: Boolean) {
    val w = Words(LocalTurkish.current)
    val m = radar.market
    Card(glow = m != null && m > 0.15) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Gauge(m, Modifier.size(width = 96.dp, height = 56.dp))
            Spacer(Modifier.width(14.dp))
            Column(Modifier.weight(1f)) {
                Label(tx("MARKET MOOD · NEWS, 12H", "PİYASA HAVASI · HABERLER, 12 SA"))
                Text(m?.let { w.moodName(it).replaceFirstChar { c -> c.uppercase() } } ?: tx("Waiting for news", "Haber bekleniyor"),
                    fontWeight = FontWeight.SemiBold, fontSize = 18.sp, color = moodColor(m))
                Text((m?.moodText() ?: "—") + " · " + tx("${radar.items.size} headlines kept", "${radar.items.size} başlık"),
                    color = MT.Text3, fontFamily = MT.Mono, fontSize = 11.sp)
            }
        }
        if (!compact) {
            Spacer(Modifier.height(12.dp))
            Sparkline(radar.timeline, Modifier.fillMaxWidth().height(64.dp))
            Row {
                Text(tx("24h ago", "24 sa önce"), color = MT.Text3, fontSize = 10.sp, modifier = Modifier.weight(1f))
                Text(tx("now", "şimdi"), color = MT.Text3, fontSize = 10.sp)
            }
        }
    }
}

@Composable
private fun Gauge(value: Double?, modifier: Modifier) {
    val target = ((value ?: 0.0).coerceIn(-1.0, 1.0)).toFloat()
    val v by animateFloatAsState(target, tween(900), label = "gauge")
    Canvas(modifier) {
        val stroke = 9f
        val r = minOf(size.width / 2, size.height) - stroke
        val center = Offset(size.width / 2, size.height - 4f)
        val topLeft = Offset(center.x - r, center.y - r)
        val arc = Size(r * 2, r * 2)
        drawArc(
            Brush.horizontalGradient(listOf(MT.Down, MT.Text3, MT.Up), startX = topLeft.x, endX = topLeft.x + r * 2),
            startAngle = 180f, sweepAngle = 180f, useCenter = false, topLeft = topLeft, size = arc,
            style = Stroke(width = stroke, cap = StrokeCap.Round),
        )
        if (value != null) {
            val angle = PI * (1 - (v + 1) / 2)
            val tip = Offset(center.x + (r - 6f) * cos(angle).toFloat(), center.y - (r - 6f) * sin(angle).toFloat())
            drawLine(Color.White, center, tip, strokeWidth = 4f, cap = StrokeCap.Round)
            drawCircle(Color.White, radius = 6f, center = center)
        }
    }
}

@Composable
private fun Sparkline(values: List<Double?>, modifier: Modifier) {
    Canvas(modifier) {
        val mid = size.height / 2
        drawLine(MT.Line, Offset(0f, mid), Offset(size.width, mid), strokeWidth = 1.5f,
            pathEffect = PathEffect.dashPathEffect(floatArrayOf(8f, 8f)))
        if (values.isEmpty()) return@Canvas
        val step = size.width / (values.size - 1).coerceAtLeast(1)
        val path = Path()
        var started = false
        values.forEachIndexed { i, v ->
            if (v == null) return@forEachIndexed
            val x = i * step
            val y = mid - (v.coerceIn(-1.0, 1.0) * (size.height / 2 - 4)).toFloat()
            if (!started) { path.moveTo(x, y); started = true } else path.lineTo(x, y)
            drawCircle(moodColor(v), radius = 3.5f, center = Offset(x, y))
        }
        if (started) drawPath(path, MT.Accent, style = Stroke(width = 3f, cap = StrokeCap.Round))
    }
}

/** A bar that grows right (green) for good news and left (red) for bad, from the middle. */
@Composable
private fun CenterBar(value: Double?, modifier: Modifier) {
    val v by animateFloatAsState(((value ?: 0.0).coerceIn(-1.0, 1.0)).toFloat(), tween(700), label = "bar")
    Canvas(modifier) {
        val mid = size.width / 2
        drawRoundRect(MT.Surface2, size = size, cornerRadius = androidx.compose.ui.geometry.CornerRadius(6f))
        drawLine(MT.Text3, Offset(mid, 0f), Offset(mid, size.height), strokeWidth = 2f)
        if (value != null) {
            val len = mid * kotlin.math.abs(v)
            val left = if (v >= 0) mid else mid - len
            drawRoundRect(if (v >= 0) MT.Up else MT.Down, topLeft = Offset(left, 1f), size = Size(len, size.height - 2f),
                cornerRadius = androidx.compose.ui.geometry.CornerRadius(5f))
        }
    }
}

// =============================================================== learning

@Composable
private fun LearningTab(brain: BrainSnapshot, settings: TradingSettings, toast: (String) -> Unit) {
    val w = Words(LocalTurkish.current)
    val context = LocalContext.current
    val state by Hub.state.collectAsState()
    var confirmForget by remember { mutableStateOf(false) }
    val prices = state.snapshots.filter { it.ready }.associate { it.symbol to it.price }

    LazyColumn(
        Modifier.fillMaxSize(),
        contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 12.dp, bottom = 130.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Card(glow = brain.rules.isNotEmpty()) {
                Label(tx("LEARNING FROM ITS OWN SIGNALS", "KENDİ SİNYALLERİNDEN ÖĞRENİYOR"))
                Spacer(Modifier.height(10.dp))
                Row {
                    BigStat("${brain.shadowClosed}", tx("results", "sonuç"), Modifier.weight(1f))
                    BigStat(if (brain.shadowClosed > 0) (brain.shadowWins * 100 / brain.shadowClosed).let { tx("$it%", "%$it") } else "—", tx("won", "kazandı"), Modifier.weight(1f))
                    BigStat(brain.shadowAvgR?.let { w.rText(it) } ?: "—", tx("average", "ortalama"), Modifier.weight(1f),
                        color = (brain.shadowAvgR ?: 0.0).tone())
                    BigStat("${brain.rules.size}", tx("rules", "kural"), Modifier.weight(1f), color = if (brain.rules.isNotEmpty()) MT.Accent else MT.Text)
                }
                Text(
                    tx("Every buy signal is followed in its head — bought or not — until its stop, target or sell signal. 1R is what the stop risks: +2R is a full win, −1R a full stop-out. ${brain.realResults} real trade(s) counted too, at double weight.",
                        "Her alım sinyalini — alsa da almasa da — stop'u, hedefi ya da satış sinyali gelene kadar kafasında takip eder. 1R, stop'un riske ettiği tutar: +2R tam kazanç, −1R tam stop. ${brain.realResults} gerçek işlem de çift ağırlıkla sayıldı."),
                    color = MT.Text3, fontSize = 12.sp, lineHeight = 17.sp, modifier = Modifier.padding(top = 10.dp),
                )
                if (!settings.learning) {
                    Text(tx("Learning is off in Settings: it keeps counting, but never holds a buy back.",
                        "Öğrenme Ayarlar'da kapalı: saymaya devam eder ama alımı asla durdurmaz."),
                        color = MT.Accent, fontSize = 12.sp, modifier = Modifier.padding(top = 6.dp))
                }
            }
        }
        item {
            Card(borderColor = if (brain.rules.isNotEmpty()) MT.Accent.copy(alpha = 0.5f) else null) {
                Label(tx("RULES IT NOW FOLLOWS", "ARTIK UYDUĞU KURALLAR"), MT.Accent)
                if (brain.rules.isEmpty()) {
                    Text(tx("None yet. A rule needs at least 10 results of one kind, averaging −0.25R or worse after a fairness discount — so a few unlucky trades never become a rule.",
                        "Henüz yok. Bir kural için aynı türden en az 10 sonuç ve adalet indirimi sonrası −0.25R ya da daha kötü ortalama gerekir — birkaç şanssız işlem asla kural olmaz."),
                        color = MT.Text3, fontSize = 12.5.sp, lineHeight = 17.sp, modifier = Modifier.padding(top = 6.dp))
                }
                brain.rules.forEach { b ->
                    Text("✕ " + w.bucketName(b.bucket), fontWeight = FontWeight.SemiBold, fontSize = 13.5.sp, modifier = Modifier.padding(top = 10.dp))
                    Text(w.lessonText(b) + tx(" → skipped now", " → artık alınmıyor"), color = MT.Text2, fontSize = 12.sp)
                }
            }
        }
        if (brain.lessons.isNotEmpty()) item {
            Card {
                Label(tx("WHAT EACH KIND OF SIGNAL RETURNED", "HER SİNYAL TÜRÜ NE GETİRDİ"))
                brain.lessons.forEach { b -> LessonRow(b, w) }
            }
        }
        if (brain.shadowOpen.isNotEmpty()) item {
            Card {
                Label(tx("FOLLOWING NOW", "ŞU AN TAKİPTE"))
                brain.shadowOpen.take(10).forEach { t -> ShadowRow(t, prices[t.symbol], w) }
            }
        }
        if (brain.shadowRecent.isNotEmpty()) item {
            Card {
                Label(tx("RECENT RESULTS", "SON SONUÇLAR"))
                brain.shadowRecent.forEach { t -> ShadowRow(t, null, w) }
            }
        }
        if (brain.tradeLessons.isNotEmpty()) item {
            Card {
                Label(tx("LESSONS FROM REAL TRADES (AI)", "GERÇEK İŞLEMLERDEN DERSLER (AI)"))
                brain.tradeLessons.take(6).forEach { n ->
                    Text(n.symbol, color = MT.Accent, fontFamily = MT.Mono, fontWeight = FontWeight.SemiBold, fontSize = 12.sp, modifier = Modifier.padding(top = 10.dp))
                    Text(n.text, color = MT.Text2, fontSize = 12.5.sp, lineHeight = 18.sp)
                }
            }
        }
        item {
            GhostButton(tx("Forget what it learned…", "Öğrendiklerini unut…"), { confirmForget = true }, Modifier.fillMaxWidth(), color = MT.Down)
        }
    }

    if (confirmForget) {
        AlertDialog(
            onDismissRequest = { confirmForget = false },
            containerColor = MT.Surface,
            title = { Text(tx("Forget everything it learned?", "Öğrendiği her şey silinsin mi?")) },
            text = { Text(tx("The followed signals, their results, the rules and the AI's lessons are wiped. Company reports and news stay.",
                "Takip edilen sinyaller, sonuçları, kurallar ve AI'ın dersleri silinir. Şirket raporları ve haberler kalır.")) },
            confirmButton = {
                TextButton({
                    confirmForget = false
                    val brainNow = Hub.brain
                    if (brainNow != null) brainNow.forget() else BrainFiles(File(context.filesDir, "brain")).forgetLearning()
                    Hub.state.value = Hub.state.value.copy(brain = Hub.state.value.brain.copy(
                        lessons = emptyList(), rules = emptyList(), shadowOpen = emptyList(), shadowRecent = emptyList(),
                        shadowClosed = 0, shadowWins = 0, shadowAvgR = null, realResults = 0, tradeLessons = emptyList(),
                    ))
                    toast(pick(settings.turkish, "Forgotten. It starts learning again from the next signal.", "Unutuldu. Bir sonraki sinyalden itibaren yeniden öğrenir."))
                }) { Text(tx("Forget", "Unut"), color = MT.Down) }
            },
            dismissButton = { TextButton({ confirmForget = false }) { Text(tx("Cancel", "Vazgeç")) } },
        )
    }
}

@Composable
private fun LessonRow(b: BucketStats, w: Words) {
    Column(Modifier.fillMaxWidth().padding(top = 10.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(w.bucketName(b.bucket), Modifier.weight(1f), fontSize = 13.sp, fontWeight = FontWeight.Medium)
            Text(w.rText(b.shrunk), color = b.shrunk.tone(), fontFamily = MT.Mono, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
        }
        Spacer(Modifier.height(4.dp))
        CenterBar((b.shrunk / 1.0).coerceIn(-1.0, 1.0), Modifier.fillMaxWidth().height(6.dp))
        Text(w.lessonText(b), color = MT.Text3, fontSize = 11.sp, modifier = Modifier.padding(top = 3.dp))
    }
}

@Composable
private fun ShadowRow(t: ShadowTrade, price: Double?, w: Words) {
    Row(Modifier.fillMaxWidth().padding(top = 9.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(t.symbol, Modifier.width(54.dp), fontFamily = MT.Mono, fontWeight = FontWeight.SemiBold, fontSize = 12.5.sp)
        Column(Modifier.weight(1f)) {
            Text("${w.usd(t.entry)} · stop ${w.usd(t.stop)} · ${tx("target", "hedef")} ${w.usd(t.target)}",
                color = MT.Text2, fontFamily = MT.Mono, fontSize = 10.5.sp)
            Text(
                (if (t.bought) tx("bought for real", "gerçekten alındı") else tx("followed in its head", "kafasında takip")) +
                    (t.exit?.let { " · " + w.reasonName(it) } ?: ""),
                color = if (t.bought) MT.Accent else MT.Text3, fontSize = 10.5.sp,
            )
        }
        val r = t.r ?: price?.let { t.rAt(it) }
        Text(r?.let { w.rText(it) } ?: "—", color = (r ?: 0.0).tone(), fontFamily = MT.Mono, fontWeight = FontWeight.SemiBold, fontSize = 12.5.sp)
    }
}

// ================================================================ helpers

@Composable
private fun Label(text: String, color: Color = MT.Text3) {
    Text(text, color = color, fontSize = 11.sp, fontWeight = FontWeight.SemiBold, letterSpacing = 1.sp)
}

@Composable
private fun BigStat(value: String, label: String, modifier: Modifier, color: Color = MT.Text) {
    Column(modifier) {
        Text(value, color = color, fontFamily = MT.Mono, fontWeight = FontWeight.SemiBold, fontSize = 17.sp, maxLines = 1)
        Text(label, color = MT.Text3, fontSize = 11.sp)
    }
}

@Composable
private fun ago(ms: Long): String {
    val m = (ms / 60_000).coerceAtLeast(0)
    return when {
        m < 60 -> tx("${m}m", "${m}dk")
        m < 48 * 60 -> tx("${m / 60}h", "${m / 60}sa")
        else -> tx("${m / 1440}d", "${m / 1440}g")
    }
}

fun moodColor(m: Double?): Color = when {
    m == null -> MT.Text3
    m >= 0 -> lerp(MT.Text2, MT.Up, (m / 0.5).coerceIn(0.0, 1.0).toFloat())
    else -> lerp(MT.Text2, MT.Down, (-m / 0.5).coerceIn(0.0, 1.0).toFloat())
}

fun verdictColor(v: Verdict): Color = when (v) {
    Verdict.PASS -> MT.Up
    Verdict.WATCH -> MT.Accent
    Verdict.FAIL -> MT.Down
    Verdict.UNKNOWN -> MT.Text3
}

fun decisionColor(d: Decision): Color = when (d) {
    Decision.BUY_ZONE -> MT.Up
    Decision.WAIT -> MT.Accent
    Decision.AVOID -> MT.Down
    Decision.UNKNOWN -> MT.Text3
}
