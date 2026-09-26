package com.bofstudios.moneytree.ui

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.clickable
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
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.bofstudios.moneytree.data.Prefs
import com.bofstudios.moneytree.engine.HeldPosition
import com.bofstudios.moneytree.engine.Snapshot
import com.bofstudios.moneytree.engine.TradeRecord
import com.bofstudios.moneytree.engine.Words
import com.bofstudios.moneytree.service.Hub
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

@Composable
fun PortfolioScreen(prefs: Prefs) {
    val state by Hub.state.collectAsState()
    val steps by Hub.steps.collectAsState()
    val w = Words(LocalTurkish.current)
    // Re-read the journal whenever the feed moves; closes are announced there.
    val trades = remember(steps.size) { prefs.trades().asReversed() }
    var open by rememberSaveable { mutableStateOf<String?>(null) }

    LazyColumn(
        Modifier.fillMaxSize(),
        contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 12.dp, bottom = 110.dp),
    ) {
        item {
            val a = state.account
            Card {
                Text(tx("Account", "Hesap"), color = MT.Text3, fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
                Text(a?.let { w.usd(it.equity) } ?: "—", style = Figure)
                if (a != null) {
                    KeyValue(tx("Cash", "Nakit"), w.usd(a.cash))
                    KeyValue(tx("Buying power", "Alım gücü"), w.usd(a.buyingPower))
                    val today = a.equity - a.lastEquity
                    KeyValue(tx("Today", "Bugün"), w.signed(today), today.tone())
                }
                val realised = trades.sumOf { it.pnl }
                if (trades.isNotEmpty()) {
                    KeyValue(
                        tx("Closed trades, total", "Kapanan işlemler, toplam"),
                        w.signed(realised), realised.tone(),
                    )
                }
            }
        }

        item { SectionTitle(tx("Holdings", "Pozisyonlar")) }
        if (state.held.isEmpty()) {
            item { Text(tx("Nothing open.", "Açık pozisyon yok."), color = MT.Text3, fontSize = 13.sp) }
        }
        items(state.held, key = { it.position.symbol }) { HeldRow(it, w) }

        if (state.snapshots.isNotEmpty()) {
            item { SectionTitle(tx("Watchlist — tap for the chart", "İzleme listesi — grafik için dokun")) }
            item {
                Card(padding = PaddingValues(horizontal = 14.dp, vertical = 6.dp)) {
                    state.snapshots.forEachIndexed { i, s ->
                        if (i > 0) HorizontalDivider(color = MT.Line)
                        SnapshotRow(s, w, open == s.symbol) { open = if (open == s.symbol) null else s.symbol }
                        AnimatedVisibility(open == s.symbol, enter = expandVertically() + fadeIn(), exit = shrinkVertically()) {
                            val held = state.held.firstOrNull { it.position.symbol == s.symbol && it.managed }
                            CandleChart(
                                state.bars[s.symbol].orEmpty(),
                                Modifier.padding(vertical = 10.dp),
                                stop = held?.stop, target = held?.target,
                            )
                        }
                    }
                }
            }
        }

        item { SectionTitle(tx("Closed trades", "Kapanan işlemler")) }
        if (trades.isEmpty()) {
            item {
                Text(
                    tx("None yet. When a trade closes, what it actually filled at — and what it made or lost — shows here.",
                        "Henüz yok. Bir işlem kapandığında gerçekte hangi fiyattan dolduğu ve ne kazandırıp kaybettirdiği burada görünür."),
                    color = MT.Text3, fontSize = 13.sp,
                )
            }
        }
        items(trades, key = { "${it.symbol}-${it.closedAt}" }) { TradeRow(it, w) }
    }
}

@Composable
private fun HeldRow(h: HeldPosition, w: Words) {
    val p = h.position
    Card(modifier = Modifier.padding(bottom = 8.dp), highlight = h.managed) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Ticker(p.symbol)
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text("${p.symbol} · ${"%.0f".format(p.qty)} ${tx("shares", "adet")}", fontWeight = FontWeight.SemiBold)
                Text("${tx("in", "giriş")} ${w.usd(p.avgEntry)} · ${tx("now", "şimdi")} ${w.usd(p.currentPrice)}",
                    color = MT.Text3, fontFamily = MT.Mono, fontSize = 11.sp)
            }
            Text(w.signed(p.unrealizedPl), color = p.unrealizedPl.tone(), fontFamily = MT.Mono, fontWeight = FontWeight.SemiBold)
        }
        Spacer(Modifier.height(8.dp))
        if (h.managed) {
            Text(
                "Stop ${h.stop?.let { w.usd(it) } ?: "—"} · ${tx("target", "hedef")} ${h.target?.let { w.usd(it) } ?: "—"} · ${tx("held at Alpaca", "Alpaca'da duruyor")}",
                color = MT.Accent, fontFamily = MT.Mono, fontSize = 11.sp,
            )
        } else {
            Text(tx("Yours — Money Tree does not touch this position.", "Senin — Money Tree bu pozisyona dokunmaz."),
                color = MT.Text3, fontSize = 11.5.sp)
        }
    }
}

@Composable
private fun SnapshotRow(s: Snapshot, w: Words, open: Boolean, onClick: () -> Unit) {
    Row(Modifier.fillMaxWidth().clickable(onClick = onClick).padding(vertical = 9.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(s.symbol, Modifier.width(64.dp), fontFamily = MT.Mono, fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
        if (!s.ready) {
            Text(tx("not enough data", "veri yetersiz"), color = MT.Text3, fontSize = 12.sp)
            return@Row
        }
        Text(w.usd(s.price), Modifier.weight(1f), fontFamily = MT.Mono, fontSize = 12.5.sp)
        Text(if (s.trendUp) "▲" else "▼", color = if (s.trendUp) MT.Up else MT.Down, fontSize = 12.sp)
        Spacer(Modifier.width(10.dp))
        Text("RSI ${"%.0f".format(s.rsi)}", color = when {
            s.rsi >= 70 -> MT.Down; s.rsi <= 30 -> MT.Up; else -> MT.Text2
        }, fontFamily = MT.Mono, fontSize = 12.sp)
        Spacer(Modifier.width(8.dp))
        Text(if (open) "▴" else "▾", color = MT.Text3, fontSize = 12.sp)
    }
}

@Composable
private fun TradeRow(t: TradeRecord, w: Words) {
    val date = remember(t.closedAt) { SimpleDateFormat("d MMM HH:mm", Locale.getDefault()).format(Date(t.closedAt)) }
    Row(Modifier.fillMaxWidth().padding(vertical = 9.dp), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text("${t.symbol} · ${w.reasonName(t.reason)}", fontWeight = FontWeight.Medium, fontSize = 13.5.sp)
            Text("$date · ${w.closedDetail(t)}", color = MT.Text3, fontFamily = MT.Mono, fontSize = 10.5.sp)
        }
        Text(w.signed(t.pnl), color = t.pnl.tone(), fontFamily = MT.Mono, fontWeight = FontWeight.SemiBold)
    }
    HorizontalDivider(color = MT.Line)
}
