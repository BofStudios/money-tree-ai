package com.bofstudios.moneytree.ui

import android.content.Context
import android.content.Intent
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.net.toUri
import com.bofstudios.moneytree.engine.TradingSettings
import com.bofstudios.moneytree.engine.Words
import com.bofstudios.moneytree.service.Hub

/*
 * Deposits and withdrawals happen in Alpaca, by the owner, never in this app.
 *
 * Money Tree shows no bank details on purpose: wire instructions are specific
 * to each account and can change, and a stale or copied set would send real
 * money to the wrong place. It only opens Alpaca's own page, where the current
 * instructions live. Everything below is from Alpaca's funding guide
 * (alpaca.markets/learn/fund-live-trading-account, updated January 2026).
 */

private const val ALPACA_LIVE = "https://app.alpaca.markets/brokerage/dashboard/overview"
private const val ALPACA_GUIDE = "https://alpaca.markets/learn/fund-live-trading-account"

private fun open(context: Context, url: String) =
    context.startActivity(Intent(Intent.ACTION_VIEW, url.toUri()))

/** The first thing on Home: whose money this is, and how to move it. */
@Composable
fun MoneyCard(settings: TradingSettings, onOpen: (withdraw: Boolean) -> Unit, onGoReal: () -> Unit = {}) {
    val state by Hub.state.collectAsState()
    val w = Words(LocalTurkish.current)
    val account = state.account

    if (!settings.live) {
        // "Real money" means the switch. Before 4.0.1 this opened Alpaca's
        // deposit steps instead, which read as the switch sending you to Alpaca.
        Card(Modifier.clickable { onGoReal() }) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(tx("PRACTICE MONEY", "DENEME PARASI"), color = MT.Text3, fontSize = 11.sp,
                        fontWeight = FontWeight.SemiBold, letterSpacing = 1.sp)
                    Text(
                        tx("${account?.let { w.usd(it.equity) } ?: "This balance"} is pretend money from Alpaca's paper account.",
                            "${account?.let { w.usd(it.equity) } ?: "Bu bakiye"}, Alpaca'nın paper hesabındaki sahte para."),
                        color = MT.Text2, fontSize = 13.sp, lineHeight = 18.sp,
                    )
                }
                Text(tx("Real money →", "Gerçek para →"), color = MT.Accent, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
            }
        }
        return
    }

    val armed by Hub.armed.collectAsState()
    val empty = account != null && account.equity < 1.0
    Card(glow = true, borderColor = MT.Accent.copy(alpha = 0.45f)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(tx("REAL MONEY", "GERÇEK PARA"), Modifier.weight(1f), color = MT.Accent, fontSize = 11.sp,
                fontWeight = FontWeight.SemiBold, letterSpacing = 1.sp)
            Tag(if (armed) tx("ARMED", "DEVREDE") else tx("NOT ARMED", "DEVRE DIŞI"), if (armed) MT.Down else MT.Text2)
        }
        Spacer(Modifier.height(8.dp))
        if (empty) {
            Text(tx("Your account is empty", "Hesabın boş"), fontSize = 22.sp, fontWeight = FontWeight.SemiBold)
            Text(
                tx("Add money in Alpaca and it shows up here by itself. The bot can't buy anything until it lands.",
                    "Alpaca'dan para ekle, buraya kendiliğinden gelir. Para gelene kadar bot hiçbir şey alamaz."),
                color = MT.Text2, fontSize = 13.sp, lineHeight = 18.sp, modifier = Modifier.padding(top = 4.dp),
            )
        } else {
            AnimatedMoney(account?.equity, w::usd, Figure)
            if (account != null) {
                Text(tx("Cash ${w.usd(account.cash)} · buying power ${w.usd(account.buyingPower)}",
                    "Nakit ${w.usd(account.cash)} · alım gücü ${w.usd(account.buyingPower)}"),
                    color = MT.Text2, fontFamily = MT.Mono, fontSize = 12.sp)
            }
        }
        Spacer(Modifier.height(14.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.CenterVertically) {
            PrimaryButton(tx("Add money", "Para ekle"), { onOpen(false) })
            GhostButton(tx("Withdraw", "Para çek"), { onOpen(true) }, color = MT.Text)
        }
    }
}

/** How to put money in and take it out, step by step, with Alpaca one tap away. */
@Composable
fun MoneyScreen(settings: TradingSettings, withdrawFirst: Boolean, onBack: () -> Unit) {
    val context = LocalContext.current
    val state by Hub.state.collectAsState()
    val w = Words(LocalTurkish.current)
    val account = state.account

    Column(Modifier.fillMaxSize()) {
        Row(Modifier.fillMaxWidth().padding(horizontal = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            IconButton(onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, tx("Back", "Geri"), tint = MT.Text) }
            Text(tx("Money", "Para"), fontSize = 20.sp, fontWeight = FontWeight.SemiBold)
        }
        Column(
            Modifier.fillMaxSize().verticalScroll(rememberScrollState())
                .padding(start = 16.dp, end = 16.dp, top = 4.dp, bottom = 40.dp),
        ) {
            if (settings.live) {
                Card(glow = true) {
                    Text(tx("In your Alpaca account", "Alpaca hesabında"), color = MT.Text3, fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
                    AnimatedMoney(account?.equity, w::usd, Figure)
                    if (account != null) {
                        KeyValue(tx("Cash", "Nakit"), w.usd(account.cash))
                        KeyValue(tx("Buying power", "Alım gücü"), w.usd(account.buyingPower))
                    }
                }
            } else {
                Card(borderColor = MT.Accent.copy(alpha = 0.35f)) {
                    Text(tx("You're on practice money", "Deneme parasındasın"), fontWeight = FontWeight.SemiBold)
                    Text(tx("The paper balance is pretend — there is nothing to deposit or withdraw. This is how it works once you switch to real money in Settings.",
                        "Paper bakiye sahte — yatıracak ya da çekecek bir şey yok. Ayarlar'dan gerçek paraya geçtiğinde işler böyle yürüyor."),
                        color = MT.Text2, fontSize = 13.sp, lineHeight = 18.sp, modifier = Modifier.padding(top = 4.dp))
                }
            }

            val deposit: @Composable () -> Unit = {
                SectionTitle(tx("Add money", "Para ekle"))
                Card {
                    StepLine(1, tx("Open Alpaca, go to your live account, then \"Funds & Wallet\" on the left (or \"Add Funds\" at the top right).",
                        "Alpaca'yı aç, canlı hesabına gir, soldan \"Funds & Wallet\"a (ya da sağ üstte \"Add Funds\") bas."))
                    StepLine(2, tx("From Turkey, pick \"Local Currency Transfer\" and enter your IBAN. Alpaca then shows exactly where to send it. Fee: 1.5%, at most \$40. Send a currency your bank account supports.",
                        "Türkiye'den \"Local Currency Transfer\"ı seç, IBAN'ını gir. Alpaca parayı tam olarak nereye göndereceğini gösterir. Ücret: %1,5, en fazla 40\$. Banka hesabının desteklediği para birimiyle gönder."))
                    StepLine(3, tx("If your bank can send US dollars, \"International Wire\" also works — USD only. Your own bank charges for sending abroad, so ask them first, especially for small amounts.",
                        "Bankan dolar gönderebiliyorsa \"International Wire\" da olur — sadece USD. Yurt dışına gönderim için bankan kendi ücretini alır; özellikle küçük tutarlarda önce bankana sor."))
                    StepLine(4, tx("When it lands, Money Tree sees it by itself. Nothing to do here.",
                        "Para gelince Money Tree kendiliğinden görür. Burada bir şey yapman gerekmez."))
                    Spacer(Modifier.height(8.dp))
                    PrimaryButton(tx("Open Alpaca", "Alpaca'yı aç"), { open(context, ALPACA_LIVE) }, Modifier.fillMaxWidth())
                }
            }
            val withdraw: @Composable () -> Unit = {
                SectionTitle(tx("Withdraw", "Para çek"))
                Card {
                    StepLine(1, tx("Only cash can leave. If the bot holds stocks, stop it and let them close — or sell them in Alpaca — first.",
                        "Sadece nakit çekilebilir. Bot hisse tutuyorsa önce durdur ve kapanmalarını bekle — ya da Alpaca'dan sat."))
                    StepLine(2, tx("In Alpaca: \"Funds & Wallet\" → Withdraw. Withdrawals are paid in US dollars.",
                        "Alpaca'da: \"Funds & Wallet\" → Withdraw. Çekimler dolar olarak ödenir."))
                    StepLine(3, tx("Leave room for the fee — it comes out of your balance, and a withdrawal bigger than what's left after it is declined. International wire out: \$50. Local currency transfer: 1.5%, at most \$40.",
                        "Ücret için pay bırak — bakiyeden düşer ve ücretten sonra kalandan büyük bir çekim reddedilir. Yurt dışına havale: 50\$. Yerel para transferi: %1,5, en fazla 40\$."))
                    if (account != null && account.cash in 0.0..50.0 && settings.live) {
                        Text(tx("With ${w.usd(account.cash)} in cash, a \$50 wire costs more than you have — a local currency transfer is the realistic route.",
                            "${w.usd(account.cash)} nakitle 50\$'lık havale sahip olduğundan fazlasını tutar — gerçekçi yol yerel para transferi."),
                            color = MT.Accent, fontSize = 12.5.sp, lineHeight = 17.sp, modifier = Modifier.padding(top = 4.dp, start = 30.dp))
                    }
                    Spacer(Modifier.height(8.dp))
                    PrimaryButton(tx("Open Alpaca", "Alpaca'yı aç"), { open(context, ALPACA_LIVE) }, Modifier.fillMaxWidth())
                }
            }
            if (withdrawFirst) { withdraw(); deposit() } else { deposit(); withdraw() }

            Spacer(Modifier.height(18.dp))
            Card(borderColor = MT.Down.copy(alpha = 0.45f)) {
                Text(tx("Money Tree never moves money", "Money Tree asla para taşımaz"), fontWeight = FontWeight.SemiBold, color = MT.Down)
                Text(tx("It shows no bank details and can't deposit or withdraw. Only send money to the details shown inside your own Alpaca account. Anyone else giving you \"Alpaca\" bank details is running a scam.",
                    "Banka bilgisi göstermez, para yatıramaz ya da çekemez. Parayı sadece kendi Alpaca hesabının içinde gösterilen bilgilere gönder. Sana başka biri \"Alpaca\" banka bilgisi veriyorsa dolandırıcılıktır."),
                    color = MT.Text2, fontSize = 13.sp, lineHeight = 18.sp, modifier = Modifier.padding(top = 4.dp))
            }
            Spacer(Modifier.height(14.dp))
            Text(tx("From Alpaca's funding guide, updated January 2026. Fees can change — Alpaca shows the exact fee before you confirm.",
                "Alpaca'nın fonlama rehberinden, Ocak 2026 güncellemesi. Ücretler değişebilir — Alpaca onaylamadan önce kesin ücreti gösterir."),
                color = MT.Text3, fontSize = 11.5.sp, lineHeight = 16.sp)
            GhostButton(tx("Read Alpaca's guide", "Alpaca'nın rehberini oku"), { open(context, ALPACA_GUIDE) }, color = MT.Accent)
        }
    }
}

@Composable
private fun StepLine(n: Int, text: String) {
    Row(Modifier.padding(vertical = 6.dp)) {
        Box(Modifier.size(20.dp).clip(CircleShape).background(MT.AccentSoft), contentAlignment = Alignment.Center) {
            Text("$n", color = MT.Accent, fontSize = 11.sp, fontWeight = FontWeight.SemiBold, fontFamily = MT.Mono)
        }
        Spacer(Modifier.width(10.dp))
        Text(text, color = MT.Text, fontSize = 13.5.sp, lineHeight = 19.sp)
    }
}
