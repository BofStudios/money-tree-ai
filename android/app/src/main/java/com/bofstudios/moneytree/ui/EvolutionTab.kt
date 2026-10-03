package com.bofstudios.moneytree.ui

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.bofstudios.moneytree.engine.EvolutionSnapshot
import com.bofstudios.moneytree.engine.Genome
import com.bofstudios.moneytree.engine.Promotion
import com.bofstudios.moneytree.engine.Score
import com.bofstudios.moneytree.engine.TrainMode
import com.bofstudios.moneytree.engine.TradingSettings
import com.bofstudios.moneytree.engine.Words
import com.bofstudios.moneytree.service.Hub
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * Self-improvement, live: how many strategies it has tried, the one it trades
 * with now against the one it shipped with, and every change it made — each
 * with the numbers from data it had never trained on.
 */
@Composable
fun EvolutionTab(fallback: EvolutionSnapshot, settings: TradingSettings, toast: (String) -> Unit) {
    val live by Hub.evolution.collectAsState()
    val e = if (live.tested > 0 || live.ready) live else fallback
    val w = Words(LocalTurkish.current)
    var confirmReset by remember { mutableStateOf(false) }

    LazyColumn(
        Modifier.fillMaxSize(),
        contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 12.dp, bottom = 130.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item { EngineCard(e, settings, w) }
        item { Champion(e, w) }
        if (e.trail.size >= 2) item {
            Card {
                Small(tx("BEST TRAINING SCORE, GENERATION BY GENERATION", "NESİLDEN NESİLE EN İYİ EĞİTİM SKORU"))
                Spacer(Modifier.height(10.dp))
                Trail(e.trail, Modifier.fillMaxWidth().height(70.dp))
            }
        }
        item {
            Card {
                Small(tx("CHANGES IT MADE", "YAPTIĞI DEĞİŞİKLİKLER"))
                if (e.history.isEmpty()) {
                    Text(tx("None yet. It only changes how it trades when a new strategy beats the current one on two stretches of data it never trained on.",
                        "Henüz yok. Sadece yeni bir strateji, hiç eğitilmediği iki ayrı veri diliminde şu ankini geçerse işlem şeklini değiştirir."),
                        color = MT.Text3, fontSize = 12.5.sp, lineHeight = 17.sp, modifier = Modifier.padding(top = 6.dp))
                }
            }
        }
        items(e.history, key = { "p-${it.version}-${it.at}" }) { PromotionRow(it, w) }
        item {
            Text(
                tx("How it stays honest: strategies compete on the oldest 60% of months of candles; the winner must then beat the current one by 0.08R per trade on the next 20% (over at least 15 trades), and do at least as well — and make money — on the newest 20% (at least 10 trades). At most one change per half hour, and every new day re-checks it against the original and rolls back if it fell behind. It never changes your risk per trade, position cap or daily loss limit.",
                    "Nasıl dürüst kalıyor: stratejiler aylarca mumun en eski %60'ında yarışır; kazanan sonraki %20'de şu ankini işlem başı 0.08R geçmeli (en az 15 işlemle), en yeni %20'de de en az onun kadar iyi olmalı ve para kazandırmalı (en az 10 işlem). Yarım saatte en fazla bir değişiklik; her yeni gün orijinalle karşılaştırılır, geride kaldıysa geri alınır. Risk ayarlarına, pozisyon sınırına ve günlük zarar sınırına asla dokunmaz."),
                color = MT.Text3, fontSize = 11.5.sp, lineHeight = 16.sp,
            )
        }
        if (e.champion != Genome.DEFAULT) item {
            GhostButton(tx("Go back to the original strategy…", "Orijinal stratejiye dön…"), { confirmReset = true }, Modifier.fillMaxWidth(), color = MT.Down)
        }
    }

    if (confirmReset) {
        AlertDialog(
            onDismissRequest = { confirmReset = false },
            containerColor = MT.Surface,
            title = { Text(tx("Back to the original strategy?", "Orijinal stratejiye dönülsün mü?")) },
            text = { Text(tx("It trades with EMA 12/26 again. It keeps training, and may change again if something proves better.",
                "Yeniden EMA 12/26 ile işlem yapar. Eğitime devam eder; daha iyisi kanıtlanırsa yine değişebilir.")) },
            confirmButton = {
                TextButton({
                    confirmReset = false
                    val b = Hub.brain
                    if (b == null) toast(pick(settings.turkish, "Start the bot first.", "Önce botu başlat."))
                    else { b.evolution.reset(); Hub.evolution.value = b.evolution.snapshot(); toast(pick(settings.turkish, "Back to the original.", "Orijinale dönüldü.")) }
                }) { Text(tx("Go back", "Dön"), color = MT.Down) }
            },
            dismissButton = { TextButton({ confirmReset = false }) { Text(tx("Cancel", "Vazgeç")) } },
        )
    }
}

@Composable
private fun EngineCard(e: EvolutionSnapshot, settings: TradingSettings, w: Words) {
    val running = e.mode == TrainMode.FULL || e.mode == TrainMode.LIGHT
    val loc = if (LocalTurkish.current) Locale.forLanguageTag("tr-TR") else Locale.US
    val shown by animateFloatAsState(e.tested.toFloat(), tween(900), label = "tested")
    Card(glow = running, highlight = running) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Pulse(if (running) MT.Accent else MT.Text3, live = running, size = 7)
            Small(tx("IMPROVING ITSELF", "KENDİNİ GELİŞTİRİYOR"), if (running) MT.Accent else MT.Text3)
        }
        Spacer(Modifier.height(10.dp))
        Text(String.format(loc, "%,d", shown.toLong()), style = Figure, color = MT.Text)
        Text(tx("strategies tested on real candles", "gerçek mumlarda denenen strateji"), color = MT.Text2, fontSize = 12.5.sp)
        Spacer(Modifier.height(12.dp))
        Row {
            Stat(String.format(loc, "%,.0f", e.perSecond), tx("per second", "saniyede"), Modifier.weight(1f))
            Stat(String.format(loc, "%,d", e.generations), tx("generations", "nesil"), Modifier.weight(1f))
            Stat("v${e.version}", tx("strategy", "strateji"), Modifier.weight(1f), MT.Accent)
        }
        Spacer(Modifier.height(10.dp))
        Text(
            w.trainModeName(if (!settings.selfImprove) TrainMode.OFF else e.mode) +
                (if (e.symbols > 0) " · " + tx("${e.symbols} stocks, ${String.format(loc, "%,d", e.bars)} candles",
                    "${e.symbols} hisse, ${String.format(loc, "%,d", e.bars)} mum") else ""),
            color = MT.Text3, fontSize = 12.sp,
        )
        if (!settings.selfImprove) {
            Text(tx("Self-improvement is off in Settings.", "Kendini geliştirme Ayarlar'da kapalı."), color = MT.Accent, fontSize = 12.sp, modifier = Modifier.padding(top = 4.dp))
        } else if (e.mode == TrainMode.LIGHT) {
            Text(tx("Plug in the charger and it trains at full speed.", "Şarja tak, tam hızda eğitsin."), color = MT.Accent, fontSize = 12.sp, modifier = Modifier.padding(top = 4.dp))
        }
    }
}

@Composable
private fun Champion(e: EvolutionSnapshot, w: Words) {
    val c = e.champion
    val d = Genome.DEFAULT
    Card {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Small(tx("TRADING WITH NOW", "ŞU AN BUNUNLA İŞLEM YAPIYOR"), Modifier.weight(1f))
            Tag(if (c == d) tx("original", "orijinal") else "v${e.version}", if (c == d) MT.Text2 else MT.Accent)
        }
        Spacer(Modifier.height(8.dp))
        Row { Text("", Modifier.weight(1.4f)); Head(tx("now", "şimdi"), Modifier.weight(1f)); Head(tx("original", "orijinal"), Modifier.weight(1f)) }
        Gene(tx("Fast / slow average", "Hızlı / yavaş ortalama"), "${c.fast} / ${c.slow}", "${d.fast} / ${d.slow}")
        Gene(tx("Buy only if RSI under", "RSI şunun altındaysa al"), fmt(c.entryRsi, 0), fmt(d.entryRsi, 0))
        Gene(tx("Sell when RSI over", "RSI şunu geçince sat"), fmt(c.exitRsi, 0), fmt(d.exitRsi, 0))
        Gene(tx("Stop distance (ATR)", "Stop mesafesi (ATR)"), fmt(c.atrMultiple, 2), fmt(d.atrMultiple, 2))
        Gene(tx("Target : stop", "Hedef : stop"), fmt(c.rewardRisk, 2) + ":1", fmt(d.rewardRisk, 2) + ":1")
        Spacer(Modifier.height(12.dp))
        Small(tx("ON DATA IT NEVER TRAINED ON", "HİÇ EĞİTİLMEDİĞİ VERİDE"))
        ScoreRow(tx("Now", "Şimdi"), e.championTest, w)
        ScoreRow(tx("Original", "Orijinal"), e.defaultTest, w)
        e.best?.let { b ->
            Text(tx("Best candidate in training: ", "Eğitimdeki en iyi aday: ") + w.rText(b.train.expectancy) +
                tx(" per trade over ${b.train.trades} trades", " işlem başı, ${b.train.trades} işlem"),
                color = MT.Text3, fontSize = 11.5.sp, modifier = Modifier.padding(top = 8.dp))
        }
    }
}

@Composable
private fun Gene(label: String, now: String, original: String) {
    Row(Modifier.fillMaxWidth().padding(vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(label, Modifier.weight(1.4f), color = MT.Text2, fontSize = 12.5.sp)
        Text(now, Modifier.weight(1f), color = if (now != original) MT.Accent else MT.Text, fontFamily = MT.Mono, fontSize = 12.5.sp,
            fontWeight = if (now != original) FontWeight.SemiBold else FontWeight.Normal)
        Text(original, Modifier.weight(1f), color = MT.Text3, fontFamily = MT.Mono, fontSize = 12.5.sp)
    }
}

@Composable
private fun ScoreRow(label: String, s: Score?, w: Words) {
    Row(Modifier.fillMaxWidth().padding(top = 6.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(label, Modifier.width(72.dp), color = MT.Text2, fontSize = 12.5.sp)
        if (s == null || s.trades == 0) {
            Text("—", color = MT.Text3, fontFamily = MT.Mono, fontSize = 12.5.sp)
        } else {
            Text(w.rText(s.expectancy) + tx(" /trade", " /işlem"), Modifier.weight(1f), color = s.expectancy.tone(), fontFamily = MT.Mono, fontSize = 12.5.sp, fontWeight = FontWeight.SemiBold)
            Text(tx("${(s.winRate * 100).toInt()}% won · ${s.trades}", "%${(s.winRate * 100).toInt()} kazandı · ${s.trades}"), color = MT.Text3, fontSize = 11.5.sp)
        }
    }
}

@Composable
private fun PromotionRow(p: Promotion, w: Words) {
    val date = remember(p.at) { SimpleDateFormat("d MMM HH:mm", Locale.getDefault()).format(Date(p.at)) }
    Card(borderColor = if (p.rollback) MT.Down.copy(alpha = 0.4f) else MT.Accent.copy(alpha = 0.4f)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(w.promotionTitle(p), Modifier.weight(1f), fontWeight = FontWeight.SemiBold, fontSize = 13.5.sp,
                color = if (p.rollback) MT.Down else MT.Accent)
            Text(date, color = MT.Text3, fontFamily = MT.Mono, fontSize = 11.sp)
        }
        Text(p.to.label, color = MT.Text2, fontFamily = MT.Mono, fontSize = 11.sp, modifier = Modifier.padding(top = 4.dp))
        Text(tx("Unseen data: ${w.rText(p.before)} → ${w.rText(p.after)} per trade", "Görmediği veride: işlem başı ${w.rText(p.before)} → ${w.rText(p.after)}") +
            (if (p.trades > 0) " · ${p.trades}" + tx(" trades", " işlem") else ""),
            color = (p.after - p.before).tone(), fontSize = 12.sp, modifier = Modifier.padding(top = 4.dp))
    }
}

@Composable
private fun Trail(values: List<Double>, modifier: Modifier) {
    Canvas(modifier.clip(RoundedCornerShape(8.dp)).background(MT.Surface2)) {
        val lo = values.min(); val hi = values.max()
        val span = (hi - lo).takeIf { it > 1e-9 } ?: 1.0
        val step = size.width / (values.size - 1)
        val path = Path()
        values.forEachIndexed { i, v ->
            val x = i * step
            val y = (size.height - 6f) - ((v - lo) / span * (size.height - 12f)).toFloat()
            if (i == 0) path.moveTo(x, y) else path.lineTo(x, y)
        }
        drawPath(path, MT.Accent, style = Stroke(width = 3f, cap = StrokeCap.Round))
        val lastY = (size.height - 6f) - ((values.last() - lo) / span * (size.height - 12f)).toFloat()
        drawCircle(MT.Accent, 5f, Offset(size.width, lastY))
    }
}

@Composable
private fun Stat(value: String, label: String, modifier: Modifier, color: androidx.compose.ui.graphics.Color = MT.Text) {
    Column(modifier) {
        Text(value, color = color, fontFamily = MT.Mono, fontWeight = FontWeight.SemiBold, fontSize = 16.sp, maxLines = 1)
        Text(label, color = MT.Text3, fontSize = 11.sp)
    }
}

@Composable
private fun Head(text: String, modifier: Modifier) = Text(text, modifier, color = MT.Text3, fontSize = 10.5.sp, fontWeight = FontWeight.SemiBold)

@Composable
private fun Small(text: String, color: androidx.compose.ui.graphics.Color = MT.Text3) =
    Text(text, color = color, fontSize = 11.sp, fontWeight = FontWeight.SemiBold, letterSpacing = 1.sp)

@Composable
private fun Small(text: String, modifier: Modifier) =
    Text(text, modifier, color = MT.Text3, fontSize = 11.sp, fontWeight = FontWeight.SemiBold, letterSpacing = 1.sp)

private fun fmt(v: Double, digits: Int) = String.format(Locale.US, "%.${digits}f", v)
