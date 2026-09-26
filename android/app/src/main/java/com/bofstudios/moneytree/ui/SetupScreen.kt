package com.bofstudios.moneytree.ui

import android.content.Intent
import android.net.Uri
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
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
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.bofstudios.moneytree.R
import com.bofstudios.moneytree.broker.AlpacaBroker
import com.bofstudios.moneytree.data.SecureStore
import com.bofstudios.moneytree.engine.Autonomy
import com.bofstudios.moneytree.engine.Horizon
import com.bofstudios.moneytree.engine.TradingSettings
import com.bofstudios.moneytree.engine.Words
import kotlinx.coroutines.launch

/**
 * First launch. Every question here changes what the bot does — nothing is
 * asked just to fill a profile — and "Not sure" is always an answer.
 */
@Composable
fun SetupScreen(initial: TradingSettings, onDone: (TradingSettings) -> Unit, onLanguage: (Boolean) -> Unit) {
    val context = LocalContext.current
    val secure = remember { SecureStore(context) }
    val scope = rememberCoroutineScope()
    var step by remember { mutableIntStateOf(0) }
    var horizon by remember { mutableStateOf<Horizon?>(null) }
    var autonomy by remember { mutableStateOf<Autonomy?>(null) }
    var keyId by remember { mutableStateOf("") }
    var secret by remember { mutableStateOf("") }
    var groq by remember { mutableStateOf("") }
    var checking by remember { mutableStateOf(false) }
    var checkMessage by remember { mutableStateOf<String?>(null) }
    var keysOk by remember { mutableStateOf(secure.has(SecureStore.PAPER_KEY) && secure.has(SecureStore.PAPER_SECRET)) }
    val turkish = LocalTurkish.current
    val w = Words(turkish)
    val total = 6

    Column(Modifier.fillMaxSize().padding(horizontal = 20.dp, vertical = 16.dp)) {
        LinearProgressIndicator(
            progress = { (step + 1) / total.toFloat() },
            modifier = Modifier.fillMaxWidth().height(3.dp).clip(RoundedCornerShape(3.dp)),
            color = MT.Accent, trackColor = MT.Line,
        )
        Spacer(Modifier.height(24.dp))

        AnimatedContent(
            step,
            transitionSpec = { (slideInHorizontally(tween(320)) { it / 3 } + fadeIn(tween(320))) togetherWith fadeOut(tween(160)) },
            label = "setup",
            modifier = Modifier.weight(1f),
        ) { current ->
            Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
                when (current) {
                    0 -> {
                        Image(painterResource(R.mipmap.ic_launcher), null, Modifier.size(84.dp))
                        Spacer(Modifier.height(18.dp))
                        Heading(tx("Money Tree, on your phone", "Money Tree, telefonunda"))
                        Lead(tx("It watches the market, decides with the same rules as the desktop bot, and trades your Alpaca account — with the PC off. Every step it takes shows up live.",
                            "Piyasayı izler, masaüstündeki botla aynı kurallarla karar verir ve Alpaca hesabında işlem yapar — PC kapalıyken bile. Attığı her adım canlı görünür."))
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Chip("English", !initial.turkish, { onLanguage(false) })
                            Chip("Türkçe", initial.turkish, { onLanguage(true) })
                        }
                    }
                    1 -> {
                        Heading(tx("Connect Alpaca (practice first)", "Alpaca'yı bağla (önce deneme)"))
                        Lead(tx("Use your PAPER keys: Alpaca → Paper Trading → API Keys → Generate. Real-money keys can be added later in Settings.",
                            "PAPER anahtarlarını kullan: Alpaca → Paper Trading → API Keys → Generate. Gerçek para anahtarları sonra Ayarlar'dan eklenebilir."))
                        GhostButton(tx("Open Alpaca", "Alpaca'yı aç"), {
                            context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("https://app.alpaca.markets/paper/dashboard/overview")))
                        }, color = MT.Accent)
                        OutlinedTextField(keyId, { keyId = it.trim(); keysOk = false }, Modifier.fillMaxWidth(),
                            label = { Text("API Key ID") }, singleLine = true, colors = fieldColors(), shape = RoundedCornerShape(12.dp))
                        Spacer(Modifier.height(8.dp))
                        OutlinedTextField(secret, { secret = it.trim(); keysOk = false }, Modifier.fillMaxWidth(),
                            label = { Text("Secret Key") }, singleLine = true, visualTransformation = PasswordVisualTransformation(),
                            colors = fieldColors(), shape = RoundedCornerShape(12.dp))
                        Spacer(Modifier.height(12.dp))
                        PrimaryButton(if (checking) tx("Checking…", "Kontrol ediliyor…") else tx("Check keys", "Anahtarları kontrol et"),
                            enabled = !checking && keyId.isNotEmpty() && secret.isNotEmpty(), onClick = {
                                checking = true; checkMessage = null
                                scope.launch {
                                    val result = runCatching { AlpacaBroker(keyId, secret, live = false).account() }
                                    checking = false
                                    result.onSuccess {
                                        secure.put(SecureStore.PAPER_KEY, keyId)
                                        secure.put(SecureStore.PAPER_SECRET, secret)
                                        keysOk = true
                                        checkMessage = pick(turkish, "Connected. Paper balance ${w.usd(it.equity)}.", "Bağlandı. Paper bakiye ${w.usd(it.equity)}.")
                                    }.onFailure {
                                        checkMessage = pick(turkish, "Alpaca said: ", "Alpaca'nın cevabı: ") + (it.message ?: "?")
                                    }
                                }
                            })
                        checkMessage?.let { Text(it, color = if (keysOk) MT.Up else MT.Down, fontSize = 13.sp, modifier = Modifier.padding(top = 10.dp)) }
                        if (keysOk && checkMessage == null) {
                            Text(tx("Keys already saved on this phone.", "Anahtarlar bu telefonda zaten kayıtlı."), color = MT.Up, fontSize = 13.sp, modifier = Modifier.padding(top = 10.dp))
                        }
                    }
                    2 -> {
                        Heading(tx("A free AI to explain its trades", "İşlemlerini açıklayan ücretsiz bir AI"))
                        Lead(tx("Optional. With a free Groq key, every trade gets two plain sentences explaining what the rule saw. The AI never decides anything — the rules do.",
                            "İsteğe bağlı. Ücretsiz bir Groq anahtarıyla her işlem, kuralın ne gördüğünü anlatan iki sade cümle alır. AI hiçbir şeye karar vermez — kurallar verir."))
                        GhostButton(tx("Get a free key at console.groq.com", "console.groq.com'dan ücretsiz anahtar al"), {
                            context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("https://console.groq.com/keys")))
                        }, color = MT.Accent)
                        OutlinedTextField(groq, { groq = it.trim() }, Modifier.fillMaxWidth(),
                            label = { Text(tx("Groq key (gsk_…)", "Groq anahtarı (gsk_…)")) }, singleLine = true,
                            visualTransformation = PasswordVisualTransformation(), colors = fieldColors(), shape = RoundedCornerShape(12.dp))
                    }
                    3 -> {
                        Heading(tx("How long should a trade usually last?", "Bir işlem genelde ne kadar sürsün?"))
                        Option(tx("Short", "Kısa"), tx("Minutes to hours. 15-minute charts, trades the most.", "Dakikalar–saatler. 15 dakikalık grafik, en sık işlem."),
                            horizon == Horizon.SHORT) { horizon = Horizon.SHORT; step++ }
                        Option(tx("Medium", "Orta"), tx("Days. 1-hour charts.", "Günler. 1 saatlik grafik."),
                            horizon == Horizon.MEDIUM) { horizon = Horizon.MEDIUM; step++ }
                        Option(tx("Long", "Uzun"), tx("Weeks. Daily charts, trades the least.", "Haftalar. Günlük grafik, en seyrek işlem."),
                            horizon == Horizon.LONG) { horizon = Horizon.LONG; step++ }
                        Option(tx("Not sure", "Emin değilim"), tx("Start short — that is where this strategy has been tested most.",
                            "Kısa ile başla — bu strateji en çok orada test edildi."), false) { horizon = Horizon.SHORT; step++ }
                    }
                    4 -> {
                        Heading(tx("How much should it do on its own?", "Kendi başına ne kadar iş yapsın?"))
                        Option(w.autonomyName(Autonomy.FULL), tx("Buys and sells by itself.", "Kendi alır, kendi satar."),
                            autonomy == Autonomy.FULL) { autonomy = Autonomy.FULL; step++ }
                        Option(w.autonomyName(Autonomy.SEMI), tx("Asks before every buy, on a notification. Sells and stops stay automatic.",
                            "Her alımdan önce bildirimle sorar. Satış ve stop'lar otomatik kalır."),
                            autonomy == Autonomy.SEMI) { autonomy = Autonomy.SEMI; step++ }
                        Option(w.autonomyName(Autonomy.MANUAL), tx("Never buys. Tells you what it sees.", "Asla almaz. Ne gördüğünü söyler."),
                            autonomy == Autonomy.MANUAL) { autonomy = Autonomy.MANUAL; step++ }
                        Option(tx("Not sure", "Emin değilim"), tx("Practice money: full auto, so you can watch it work.",
                            "Deneme parası: tam otomatik, çalışırken izleyebilesin."), false) { autonomy = Autonomy.FULL; step++ }
                    }
                    else -> {
                        val h = horizon ?: Horizon.SHORT
                        val a = autonomy ?: Autonomy.FULL
                        Heading(tx("Got it.", "Anladım."))
                        Summary(tx("I'll read ${w.tfName(h.timeframe)} charts.", "${w.tfName(h.timeframe)} grafiğe bakacağım."))
                        Summary(when (a) {
                            Autonomy.FULL -> tx("I'll buy and sell on my own.", "Kendim alıp satacağım.")
                            Autonomy.SEMI -> tx("I'll ask before every buy. Sells and stops stay automatic.", "Her alımdan önce soracağım. Satış ve stop'lar otomatik.")
                            Autonomy.MANUAL -> tx("I won't open anything — only tell you what I see.", "Hiçbir işlem açmayacağım, sadece ne gördüğümü söyleyeceğim.")
                        })
                        Summary(tx("Every stop-loss sits at Alpaca, so it works even when this phone is off.",
                            "Her stop-loss Alpaca'da durur, yani bu telefon kapalıyken bile çalışır."))
                        Summary(tx("This is practice money. Nothing real is at risk.", "Bu deneme parası. Gerçek hiçbir şey risk altında değil."))
                    }
                }
            }
        }

        Row(verticalAlignment = Alignment.CenterVertically) {
            if (step > 0) GhostButton(tx("Back", "Geri"), { step-- })
            Spacer(Modifier.weight(1f))
            when (step) {
                0 -> PrimaryButton(tx("Begin", "Başla"), { step = 1 })
                1 -> PrimaryButton(tx("Next", "İleri"), { step = 2 }, enabled = keysOk)
                2 -> PrimaryButton(if (groq.isEmpty()) tx("Skip", "Atla") else tx("Save", "Kaydet"), {
                    if (groq.isNotEmpty()) secure.put(SecureStore.GROQ_KEY, groq)
                    step = 3
                })
                3, 4 -> Unit // an option tap moves on
                else -> PrimaryButton(tx("Start Money Tree", "Money Tree'yi başlat"), {
                    onDone(initial.copy(horizon = horizon ?: Horizon.SHORT, autonomy = autonomy ?: Autonomy.FULL, live = false))
                })
            }
        }
    }
}

@Composable private fun Heading(text: String) =
    Text(text, fontSize = 24.sp, fontWeight = FontWeight.SemiBold, lineHeight = 30.sp, modifier = Modifier.padding(bottom = 12.dp))

@Composable private fun Lead(text: String) =
    Text(text, color = MT.Text2, fontSize = 15.sp, lineHeight = 22.sp, modifier = Modifier.padding(bottom = 18.dp))

@Composable
private fun Option(title: String, hint: String, selected: Boolean, onClick: () -> Unit) {
    Column(
        Modifier.fillMaxWidth().padding(bottom = 10.dp)
            .clip(RoundedCornerShape(14.dp))
            .background(if (selected) MT.AccentSoft else MT.Surface)
            .border(1.dp, if (selected) MT.Accent else MT.Line, RoundedCornerShape(14.dp))
            .clickable(onClick = onClick)
            .padding(16.dp),
    ) {
        Text(title, fontWeight = FontWeight.SemiBold, fontSize = 15.sp)
        Text(hint, color = MT.Text2, fontSize = 13.sp, lineHeight = 18.sp)
    }
}

@Composable
private fun Summary(text: String) {
    Row(Modifier.padding(bottom = 12.dp)) {
        Box(Modifier.padding(top = 7.dp).size(8.dp).clip(RoundedCornerShape(4.dp)).background(MT.Accent))
        Spacer(Modifier.width(12.dp))
        Text(text, fontSize = 15.sp, lineHeight = 21.sp)
    }
}
