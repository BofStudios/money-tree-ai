package com.bofstudios.moneytree.ui

import android.annotation.SuppressLint
import android.content.Intent
import android.net.Uri
import android.os.PowerManager
import android.provider.Settings
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
import com.bofstudios.moneytree.engine.Market
import com.bofstudios.moneytree.engine.NotifyLevel
import com.bofstudios.moneytree.engine.QualityMode
import com.bofstudios.moneytree.engine.RiskLevel
import com.bofstudios.moneytree.engine.TradingSettings
import com.bofstudios.moneytree.engine.Words
import kotlinx.coroutines.launch

/** Roughly how much real money will go in — sets small-account mode and the examples. */
private enum class Size(val example: Double) { SMALL(30.0), MEDIUM(1_000.0), LARGE(10_000.0) }

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
    var s by remember { mutableStateOf(initial) }
    var size by remember { mutableStateOf<Size?>(null) }
    var keyId by remember { mutableStateOf("") }
    var secret by remember { mutableStateOf("") }
    var groq by remember { mutableStateOf("") }
    var checking by remember { mutableStateOf(false) }
    var checkMessage by remember { mutableStateOf<String?>(null) }
    var keysOk by remember { mutableStateOf(secure.has(SecureStore.PAPER_KEY) && secure.has(SecureStore.PAPER_SECRET)) }
    val turkish = LocalTurkish.current
    val w = Words(turkish)
    val total = 16
    val example = (size ?: Size.SMALL).example
    fun next(change: TradingSettings.() -> TradingSettings = { this }) { s = s.change(); step++ }

    Column(Modifier.fillMaxSize().padding(horizontal = 20.dp, vertical = 16.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            LinearProgressIndicator(
                progress = { (step + 1) / total.toFloat() },
                modifier = Modifier.weight(1f).height(3.dp).clip(RoundedCornerShape(3.dp)),
                color = MT.Accent, trackColor = MT.Line,
            )
            Spacer(Modifier.width(10.dp))
            Text("${step + 1}/$total", color = MT.Text3, fontFamily = MT.Mono, fontSize = 11.sp)
        }
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
                        Lead(tx("It watches the US market around the clock, decides with fixed rules, researches the news before every buy, and trades your Alpaca account — with the PC off. Every step shows up live, and every buy and sell pings you.",
                            "ABD piyasasını gece gündüz izler, sabit kurallarla karar verir, her alımdan önce haberleri araştırır ve Alpaca hesabında işlem yapar — PC kapalıyken bile. Attığı her adım canlı görünür, her alım ve satışta bildirim gelir."))
                        Lead(tx("A few questions first. Each answer changes how it trades.", "Önce birkaç soru. Her cevap nasıl işlem yaptığını değiştirir."))
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Chip("English", !initial.turkish, { onLanguage(false); s = s.copy(turkish = false) })
                            Chip("Türkçe", initial.turkish, { onLanguage(true); s = s.copy(turkish = true) })
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
                        Heading(tx("A free AI that researches and explains", "Araştıran ve açıklayan ücretsiz bir AI"))
                        Lead(tx("Optional, but it makes the bot much smarter. With a free Groq key, the AI reads the latest headlines before every buy and can call the buy off on a clear red flag — earnings due, a trading halt, fraud. After a buy it explains the decision in two plain sentences. It can stop a buy, never start one.",
                            "İsteğe bağlı ama botu çok daha akıllı yapar. Ücretsiz bir Groq anahtarıyla AI her alımdan önce son haberleri okur ve net bir kırmızı bayrak görürse — bilanço yaklaşıyor, işlem durduruldu, dolandırıcılık — alımı iptal eder. Alımdan sonra kararı iki sade cümleyle açıklar. Alımı durdurabilir, asla başlatamaz."))
                        GhostButton(tx("Get a free key at console.groq.com", "console.groq.com'dan ücretsiz anahtar al"), {
                            context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("https://console.groq.com/keys")))
                        }, color = MT.Accent)
                        OutlinedTextField(groq, { groq = it.trim() }, Modifier.fillMaxWidth(),
                            label = { Text(tx("Groq key (gsk_…)", "Groq anahtarı (gsk_…)")) }, singleLine = true,
                            visualTransformation = PasswordVisualTransformation(), colors = fieldColors(), shape = RoundedCornerShape(12.dp))
                        if (secure.has(SecureStore.GROQ_KEY) && groq.isEmpty()) {
                            Text(tx("A key is already saved on this phone.", "Bu telefonda zaten bir anahtar kayıtlı."), color = MT.Up, fontSize = 13.sp, modifier = Modifier.padding(top = 10.dp))
                        }
                    }
                    3 -> {
                        Heading(tx("Which market?", "Hangi piyasa?"))
                        Option(tx("US stocks", "ABD hisseleri"), tx("Apple, Microsoft, Nvidia, Amazon, Google, Meta, Tesla and the S&P 500.",
                            "Apple, Microsoft, Nvidia, Amazon, Google, Meta, Tesla ve S&P 500."), s.market == Market.US) {
                            next { copy(market = Market.US, watchlist = Market.US.watchlist) } }
                        Option(tx("Europe", "Avrupa"), tx("ASML, SAP, Novo Nordisk, AstraZeneca, Shell, TotalEnergies, Unilever and a Europe ETF.",
                            "ASML, SAP, Novo Nordisk, AstraZeneca, Shell, TotalEnergies, Unilever ve bir Avrupa ETF'i."), s.market == Market.EUROPE) {
                            next { copy(market = Market.EUROPE, watchlist = Market.EUROPE.watchlist) } }
                        Option(tx("Both", "İkisi de"), tx("The biggest names from each.", "İkisinden de en büyük isimler."), s.market == Market.BOTH) {
                            next { copy(market = Market.BOTH, watchlist = Market.BOTH.watchlist) } }
                        Text(marketNote(), color = MT.Text3, fontSize = 12.5.sp, lineHeight = 18.sp, modifier = Modifier.padding(top = 4.dp))
                    }
                    4 -> {
                        Heading(tx("How long should a trade usually last?", "Bir işlem genelde ne kadar sürsün?"))
                        Option(tx("Short", "Kısa"), tx("Minutes to hours. 15-minute charts, trades the most.", "Dakikalar–saatler. 15 dakikalık grafik, en sık işlem."),
                            s.horizon == Horizon.SHORT) { next { copy(horizon = Horizon.SHORT) } }
                        Option(tx("Medium", "Orta"), tx("Days. 1-hour charts.", "Günler. 1 saatlik grafik."),
                            s.horizon == Horizon.MEDIUM) { next { copy(horizon = Horizon.MEDIUM) } }
                        Option(tx("Long", "Uzun"), tx("Weeks. Daily charts, trades the least.", "Haftalar. Günlük grafik, en seyrek işlem."),
                            s.horizon == Horizon.LONG) { next { copy(horizon = Horizon.LONG) } }
                        Option(tx("Not sure", "Emin değilim"), tx("Start short — that is where this strategy has been tested most.",
                            "Kısa ile başla — bu strateji en çok orada test edildi."), false) { next { copy(horizon = Horizon.SHORT) } }
                    }
                    5 -> {
                        Heading(tx("How much should it do on its own?", "Kendi başına ne kadar iş yapsın?"))
                        Option(w.autonomyName(Autonomy.FULL), tx("Buys and sells by itself, day and night. You get a notification for each.",
                            "Gece gündüz kendi alır, kendi satar. Her biri için bildirim gelir."), s.autonomy == Autonomy.FULL) {
                            next { copy(autonomy = Autonomy.FULL) } }
                        Option(w.autonomyName(Autonomy.SEMI), tx("Asks before every buy, on a notification. Sells and stops stay automatic.",
                            "Her alımdan önce bildirimle sorar. Satış ve stop'lar otomatik kalır."), s.autonomy == Autonomy.SEMI) {
                            next { copy(autonomy = Autonomy.SEMI) } }
                        Option(w.autonomyName(Autonomy.MANUAL), tx("Never buys. Tells you what it sees.", "Asla almaz. Ne gördüğünü söyler."),
                            s.autonomy == Autonomy.MANUAL) { next { copy(autonomy = Autonomy.MANUAL) } }
                    }
                    6 -> {
                        Heading(tx("About how much real money will you put in?", "Aşağı yukarı ne kadar gerçek para koyacaksın?"))
                        Lead(tx("It starts on practice money either way. This sets small-account mode and the examples in the next questions.",
                            "Her durumda deneme parasıyla başlar. Bu, küçük hesap modunu ve sonraki sorulardaki örnekleri belirler."))
                        Option(tx("Under \$500", "500$'dan az"), tx("Like \$30. Buys fractions of a share — \$30 cannot buy one whole Apple share.",
                            "30$ gibi. Hissenin küsuratını alır — 30$ bir tam Apple hissesi bile almaz."), size == Size.SMALL) {
                            size = Size.SMALL; next { copy(fractional = true) } }
                        Option(tx("\$500 – \$5,000", "500$ – 5.000$"), tx("Whole shares where they fit, fractions where they do not.",
                            "Sığan yerde tam hisse, sığmayan yerde küsurat."), size == Size.MEDIUM) {
                            size = Size.MEDIUM; next { copy(fractional = true) } }
                        Option(tx("More than \$5,000", "5.000$'dan fazla"), tx("Whole shares only. Every stop and target sits at Alpaca as one bracket order.",
                            "Sadece tam hisse. Her stop ve hedef Alpaca'da tek bir bracket emir olarak durur."), size == Size.LARGE) {
                            size = Size.LARGE; next { copy(fractional = false) } }
                    }
                    7 -> {
                        Heading(tx("How bold should each trade be?", "Her işlem ne kadar cesur olsun?"))
                        Lead(tx("The stop is set the same way at every level. What changes is how much one stop-out may cost.",
                            "Stop her seviyede aynı şekilde konur. Değişen, bir stop'un ne kadara mal olabileceği."))
                        RiskLevel.entries.forEach { r ->
                            Option(riskName(r), riskHint(r, example, w), s.riskLevel == r) { next { copy(riskLevel = r) } }
                        }
                    }
                    8 -> {
                        Heading(tx("How many stocks at once?", "Aynı anda en fazla kaç hisse?"))
                        Option("1", tx("One at a time. Simplest to follow; everything rides on one stock.", "Tek tek. İzlemesi en kolay; her şey tek hisseye bağlı."), s.maxPositions == 1) {
                            next { copy(maxPositions = 1) } }
                        Option("2", tx("Two. A bit of spread.", "İki. Biraz dağılım."), s.maxPositions == 2) { next { copy(maxPositions = 2) } }
                        Option("3", tx("Three. The tested default.", "Üç. Test edilmiş varsayılan."), s.maxPositions == 3) { next { copy(maxPositions = 3) } }
                        Option("5", tx("Up to five. More trades, smaller each.", "Beşe kadar. Daha çok işlem, her biri daha küçük."), s.maxPositions == 5) {
                            next { copy(maxPositions = 5) } }
                    }
                    9 -> {
                        Heading(tx("When should it stop for the day?", "Gün içinde ne zaman dursun?"))
                        Lead(tx("If the account falls this much in one day, no new buys until tomorrow. Stops on what it holds keep working.",
                            "Hesap bir günde bu kadar düşerse yarına kadar yeni alım yok. Elindekilerin stop'ları çalışmaya devam eder."))
                        listOf(3.0, 5.0, 10.0).forEach { pct ->
                            Option(tx("Down ${pct.toInt()}%", "%${pct.toInt()} düşüşte"),
                                tx("With ${w.usd(example)}: stops after about ${w.usd(example * pct / 100)} lost in a day.",
                                    "${w.usd(example)} ile: günde yaklaşık ${w.usd(example * pct / 100)} kayıptan sonra durur."),
                                s.dailyLossPct == pct) { next { copy(dailyLossPct = pct) } }
                        }
                    }
                    10 -> {
                        Heading(tx("How much of the account may it use?", "Hesabın ne kadarını kullanabilsin?"))
                        Lead(tx("The rest it never touches — handy if you keep money there for yourself.",
                            "Kalanına asla dokunmaz — hesapta kendin için para tutuyorsan işe yarar."))
                        listOf(25, 50, 100).forEach { pct ->
                            Option(if (pct == 100) tx("All of it", "Hepsini") else "%$pct".let { if (turkish) it else "$pct%" },
                                tx("With ${w.usd(example)}: up to ${w.usd(example * pct / 100)} in trades.",
                                    "${w.usd(example)} ile: işlemlerde en fazla ${w.usd(example * pct / 100)}."),
                                s.usePct == pct) { next { copy(usePct = pct) } }
                        }
                    }
                    11 -> {
                        Heading(tx("What should reach your lock screen?", "Kilit ekranına neler gelsin?"))
                        Option(tx("Everything", "Her şey"), tx("Just bought, just sold with the profit or loss, the day's summary — plus silent notes on what it is researching and stops it raised.",
                            "Az önce aldım, az önce sattım (kâr/zararıyla), günün özeti — artı neyi araştırdığına ve yükselttiği stop'lara dair sessiz notlar."),
                            s.notify == NotifyLevel.EVERYTHING) { next { copy(notify = NotifyLevel.EVERYTHING) } }
                        Option(tx("Buys and sells", "Alım ve satışlar"), tx("Just bought, just sold, and the day's summary.", "Az önce aldım, az önce sattım ve günün özeti."),
                            s.notify == NotifyLevel.TRADES) { next { copy(notify = NotifyLevel.TRADES) } }
                        Option(tx("Quiet", "Sessiz"), tx("Only buys waiting for your OK, and warnings.", "Sadece onay bekleyen alımlar ve uyarılar."),
                            s.notify == NotifyLevel.QUIET) { next { copy(notify = NotifyLevel.QUIET) } }
                    }
                    12 -> {
                        Heading(tx("Let the AI veto risky buys?", "AI riskli alımları veto edebilsin mi?"))
                        Lead(tx("Before each buy, two different AI models read the fresh headlines and the research side by side. If either sees a clear red flag, it passes and the stock is left alone for an hour.",
                            "Her alımdan önce iki farklı AI modeli taze başlıkları ve araştırmayı yan yana okur. Biri bile net bir kırmızı bayrak görürse geçer ve o hisseye bir saat dokunulmaz."))
                        val hasKey = groq.isNotEmpty() || secure.has(SecureStore.GROQ_KEY)
                        if (!hasKey) {
                            Text(tx("No Groq key yet, so this does nothing until you add one in Settings.",
                                "Henüz Groq anahtarı yok; Ayarlar'dan ekleyene kadar bu bir şey yapmaz."), color = MT.Accent, fontSize = 13.sp, modifier = Modifier.padding(bottom = 12.dp))
                        }
                        Option(tx("Yes, check the news", "Evet, haberleri kontrol et"), tx("Recommended. It can only ever stop a buy.", "Önerilen. Sadece alımı durdurabilir."),
                            s.aiCheck) { next { copy(aiCheck = true) } }
                        Option(tx("No, rules only", "Hayır, sadece kurallar"), tx("It still reads the news and shows it, but never skips because of it.",
                            "Haberleri yine okur ve gösterir ama yüzünden asla geçmez."), !s.aiCheck) { next { copy(aiCheck = false) } }
                    }
                    13 -> {
                        Heading(tx("How picky should it be?", "Ne kadar seçici olsun?"))
                        Lead(tx("Before buying, it runs five checks from each company's own annual reports: does the business make money, can rivals copy it, does management create value, is the price below the value, what could go wrong. Plus the daily trend, the news and what similar signals returned.",
                            "Almadan önce her şirketin kendi yıllık raporlarından beş kontrol yapar: işletme para kazanıyor mu, rakipler kopyalayabilir mi, yönetim değer yaratıyor mu, fiyat değerin altında mı, ne ters gidebilir. Artı günlük trend, haberler ve benzer sinyallerin sonuçları."))
                        Option(w.qualityModeName(QualityMode.STRICT), tx("Only the buy zone: a good business at a fair price. Very few trades — most big names are rarely cheap.",
                            "Sadece alım bölgesi: makul fiyatlı iyi bir işletme. Çok az işlem — büyük isimler nadiren ucuzdur."),
                            s.qualityMode == QualityMode.STRICT) { next { copy(qualityMode = QualityMode.STRICT) } }
                        Option(w.qualityModeName(QualityMode.BALANCED), tx("Recommended. Never a stock that fails the checks or fights a falling daily chart; good businesses at a high price get a smaller size.",
                            "Önerilen. Kontrolden kalan ya da düşen günlük grafiğe karşı olan hisse asla alınmaz; pahalı iyi işletmelere daha küçük pozisyon."),
                            s.qualityMode == QualityMode.BALANCED) { next { copy(qualityMode = QualityMode.BALANCED) } }
                        Option(w.qualityModeName(QualityMode.OFF), tx("The checks still show, but only the chart rules, the news and learning decide.",
                            "Kontroller yine görünür ama sadece grafik kuralları, haberler ve öğrenme karar verir."),
                            s.qualityMode == QualityMode.OFF) { next { copy(qualityMode = QualityMode.OFF) } }
                    }
                    14 -> {
                        Heading(tx("Keep it running around the clock", "Gece gündüz çalışsın"))
                        Lead(tx("Android pauses apps to save battery. Allow Money Tree to run in the background, or it may stop while the screen is off. While the US market is open it keeps the phone's processor awake so it looks every minute — plugging in during those hours (16:30–23:00 Turkey time) is a good idea.",
                            "Android pil için uygulamaları duraklatır. Money Tree'nin arka planda çalışmasına izin ver, yoksa ekran kapalıyken durabilir. ABD piyasası açıkken dakikada bir bakabilmek için telefonun işlemcisini uyanık tutar — o saatlerde (Türkiye saatiyle 16:30–23:00) şarja takmak iyi fikir."))
                        BatteryPermission()
                    }
                    else -> {
                        Heading(tx("Got it. Here's the plan.", "Anladım. Plan şu."))
                        Summary(tx("I'll watch ${s.watchlist.joinToString(", ")}.", "${s.watchlist.joinToString(", ")} hisselerini izleyeceğim."))
                        Summary(tx("I'll read ${w.tfName(s.horizon.timeframe)} charts, every minute while the US market is open.",
                            "ABD piyasası açıkken her dakika ${w.tfName(s.horizon.timeframe)} grafiğe bakacağım."))
                        Summary(when (s.autonomy) {
                            Autonomy.FULL -> tx("I'll buy and sell on my own and ping you every time.", "Kendim alıp satacağım ve her seferinde haber vereceğim.")
                            Autonomy.SEMI -> tx("I'll ask before every buy. Sells and stops stay automatic.", "Her alımdan önce soracağım. Satış ve stop'lar otomatik.")
                            Autonomy.MANUAL -> tx("I won't open anything — only tell you what I see.", "Hiçbir işlem açmayacağım, sadece ne gördüğümü söyleyeceğim.")
                        })
                        Summary(riskName(s.riskLevel) + " · " + riskHint(s.riskLevel, example, w))
                        Summary(tx("Five checks: ", "5 kontrol: ") + w.qualityModeName(s.qualityMode) + tx(" · news red flags hold buys back · it learns from every signal it follows.",
                            " · haberdeki kırmızı bayraklar alımı durdurur · takip ettiği her sinyalden öğrenir."))
                        Summary(tx("At most ${s.maxPositions} at once · no new buys after a ${s.dailyLossPct.toInt()}% day · using ${s.usePct}% of the account.",
                            "Aynı anda en fazla ${s.maxPositions} · %${s.dailyLossPct.toInt()} düşüşte gün biter · hesabın %${s.usePct}'ı kullanılır."))
                        Summary(if (s.fractional) tx("Small-account mode: fractions of a share. Each stop is placed at Alpaca every trading day; the target is watched by this phone.",
                            "Küçük hesap modu: hissenin küsuratı. Her stop her işlem günü Alpaca'ya konur; hedefi bu telefon izler.")
                        else tx("Whole shares, and every stop and target sits at Alpaca — protected even with this phone off.",
                            "Tam hisse; her stop ve hedef Alpaca'da durur — telefon kapalıyken bile korumalı."))
                        Summary(if (s.live) tx("This is real money. It buys only while armed, and every restart pauses it until you arm it again.",
                            "Bu gerçek para. Sadece devredeyken alır; her yeniden başlatma, sen tekrar devreye alana kadar bekletir.")
                        else tx("This is practice money. Nothing real is at risk until you switch and arm it.",
                            "Bu deneme parası. Sen geçip devreye alana kadar gerçek hiçbir şey risk altında değil."))
                    }
                }
            }
        }

        Row(verticalAlignment = Alignment.CenterVertically) {
            if (step > 0) GhostButton(tx("Back", "Geri"), { step-- })
            Spacer(Modifier.weight(1f))
            when (step) {
                0 -> PrimaryButton(tx("Begin", "Başla"), { step = 1 })
                1 -> {
                    // Keys can wait: without them the bot does not start, and Settings asks again.
                    if (!keysOk) GhostButton(tx("Later", "Sonra"), { step = 2 })
                    PrimaryButton(tx("Next", "İleri"), { step = 2 }, enabled = keysOk)
                }
                2 -> PrimaryButton(if (groq.isEmpty()) tx("Skip", "Atla") else tx("Save", "Kaydet"), {
                    if (groq.isNotEmpty()) secure.put(SecureStore.GROQ_KEY, groq)
                    step = 3
                })
                14 -> PrimaryButton(tx("Next", "İleri"), { step = 15 })
                in 3..13 -> Unit // an option tap moves on
                else -> PrimaryButton(tx("Start Money Tree", "Money Tree'yi başlat"), {
                    // Asked again on an update, a real-money setup stays real money.
                    onDone(s.copy(market = s.market ?: Market.US))
                })
            }
        }
    }
}

@Composable
fun riskName(r: RiskLevel) = when (r) {
    RiskLevel.CAREFUL -> tx("Careful", "Temkinli")
    RiskLevel.NORMAL -> tx("Normal", "Normal")
    RiskLevel.BOLD -> tx("Bold", "Cesur")
}

/** What a level means in money, on an example balance. */
@Composable
fun riskHint(r: RiskLevel, example: Double, w: Words): String {
    val loss = example * r.riskPerTradePct / 100
    val max = example * r.maxPositionPct / 100
    return tx(
        "A stop-out costs about ${r.riskPerTradePct}% — ${w.usd(loss)} of ${w.usd(example)}. One position at most ${w.usd(max)}.",
        "Bir stop yaklaşık %${r.riskPerTradePct} kaybettirir — ${w.usd(example)}'da ${w.usd(loss)}. Tek pozisyon en fazla ${w.usd(max)}.",
    )
}

@SuppressLint("BatteryLife")
@Composable
fun BatteryPermission() {
    val context = LocalContext.current
    val power = context.getSystemService(PowerManager::class.java)
    var exempt by remember { mutableStateOf(power.isIgnoringBatteryOptimizations(context.packageName)) }
    if (exempt) {
        Text(tx("✓ Allowed — it keeps running with the screen off.", "✓ İzin verildi — ekran kapalıyken de çalışır."),
            color = MT.Up, fontSize = 13.sp, modifier = Modifier.padding(top = 8.dp))
    } else {
        PrimaryButton(tx("Allow background running", "Arka planda çalışmaya izin ver"), {
            context.startActivity(Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:${context.packageName}")))
        }, Modifier.fillMaxWidth())
        GhostButton(tx("I allowed it — check again", "İzin verdim — tekrar kontrol et"), {
            exempt = power.isIgnoringBatteryOptimizations(context.packageName)
        }, color = MT.Accent)
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
