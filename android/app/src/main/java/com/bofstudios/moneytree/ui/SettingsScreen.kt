package com.bofstudios.moneytree.ui

import android.annotation.SuppressLint
import android.content.Intent
import android.net.Uri
import android.os.PowerManager
import android.provider.Settings
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.ui.graphics.Color
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.bofstudios.moneytree.data.SecureStore
import com.bofstudios.moneytree.engine.Autonomy
import com.bofstudios.moneytree.engine.Horizon
import com.bofstudios.moneytree.engine.Market
import com.bofstudios.moneytree.engine.NotifyLevel
import com.bofstudios.moneytree.engine.QualityMode
import com.bofstudios.moneytree.engine.RiskLevel
import com.bofstudios.moneytree.engine.TradingSettings
import com.bofstudios.moneytree.engine.Words
import com.bofstudios.moneytree.service.EngineService
import com.bofstudios.moneytree.service.Hub

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun SettingsScreen(
    settings: TradingSettings,
    onChange: (TradingSettings) -> Unit,
    requestArm: () -> Unit,
    toast: (String) -> Unit,
    onOpenMoney: () -> Unit,
    onRedoSetup: () -> Unit,
    /** Opened from Home's "Real money ->": go straight to the switch. */
    askLive: Boolean = false,
    onAskedLive: () -> Unit = {},
) {
    val context = LocalContext.current
    val secure = remember { SecureStore(context) }
    val running by Hub.running.collectAsState()
    val armed by Hub.armed.collectAsState()
    val state by Hub.state.collectAsState()
    val turkish = LocalTurkish.current
    val w = Words(turkish)
    var confirmLive by remember { mutableStateOf(false) }
    androidx.compose.runtime.LaunchedEffect(askLive) {
        if (!askLive) return@LaunchedEffect
        onAskedLive()
        when {
            settings.live -> Unit
            secure.has(SecureStore.LIVE_KEY) && secure.has(SecureStore.LIVE_SECRET) -> confirmLive = true
            else -> toast(pick(turkish, "First add your LIVE Alpaca keys under Keys below, then tap Switch to real money.",
                "Önce aşağıda Anahtarlar'a CANLI Alpaca anahtarlarını ekle, sonra Gerçek paraya geç'e bas."))
        }
    }
    var keysVersion by remember { mutableStateOf(0) }

    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState())
            .padding(start = 16.dp, end = 16.dp, top = 12.dp, bottom = 110.dp),
    ) {
        SectionTitle(tx("How it trades", "Nasıl işlem yapar"))
        Card {
            Text(tx("Autonomy", "Otomasyon"), color = MT.Text2, fontSize = 12.5.sp)
            Spacer(Modifier.height(8.dp))
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Autonomy.entries.forEach { a ->
                    Chip(w.autonomyName(a), settings.autonomy == a, { onChange(settings.copy(autonomy = a)) })
                }
            }
            Text(
                when (settings.autonomy) {
                    Autonomy.FULL -> tx("Buys and sells by itself.", "Kendi alır, kendi satar.")
                    Autonomy.SEMI -> tx("Asks before every buy — tap Approve here or on the notification.",
                        "Her alımdan önce sorar — burada ya da bildirimde Onayla'ya bas.")
                    Autonomy.MANUAL -> tx("Never buys. Shows what it would have done.", "Asla almaz. Ne yapacağını gösterir.")
                } + " " + tx("Sells and stop-losses are always automatic.", "Satış ve stop-loss her zaman otomatik."),
                color = MT.Text3, fontSize = 12.sp, modifier = Modifier.padding(top = 8.dp),
            )
            Spacer(Modifier.height(16.dp))
            Text(tx("Trade length", "İşlem süresi"), color = MT.Text2, fontSize = 12.5.sp)
            Spacer(Modifier.height(8.dp))
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Horizon.entries.forEach { h ->
                    Chip(horizonName(h), settings.horizon == h, { onChange(settings.copy(horizon = h)) })
                }
            }
            Text(tx("Reads ${w.tfName(settings.horizon.timeframe)} charts.", "${w.tfName(settings.horizon.timeframe)} grafiğe bakar."),
                color = MT.Text3, fontSize = 12.sp, modifier = Modifier.padding(top = 8.dp))
        }

        SectionTitle(tx("Risk", "Risk"))
        Card {
            val example = state.account?.equity?.takeIf { it > 0 } ?: 30.0
            Text(tx("How bold each trade is", "Her işlem ne kadar cesur"), color = MT.Text2, fontSize = 12.5.sp)
            Spacer(Modifier.height(8.dp))
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                RiskLevel.entries.forEach { r -> Chip(riskName(r), settings.riskLevel == r, { onChange(settings.copy(riskLevel = r)) }) }
            }
            Text(riskHint(settings.riskLevel, example, w), color = MT.Text3, fontSize = 12.sp, modifier = Modifier.padding(top = 8.dp))

            Spacer(Modifier.height(16.dp))
            Text(tx("Most positions at once", "Aynı anda en fazla pozisyon"), color = MT.Text2, fontSize = 12.5.sp)
            Spacer(Modifier.height(8.dp))
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf(1, 2, 3, 5).forEach { n -> Chip("$n", settings.maxPositions == n, { onChange(settings.copy(maxPositions = n)) }) }
            }

            Spacer(Modifier.height(16.dp))
            Text(tx("Stop buying for the day after a drop of", "Gün içinde şu kadar düşüşte alımı bırak"), color = MT.Text2, fontSize = 12.5.sp)
            Spacer(Modifier.height(8.dp))
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf(3.0, 5.0, 10.0).forEach { p ->
                    Chip(if (turkish) "%${p.toInt()}" else "${p.toInt()}%", settings.dailyLossPct == p, { onChange(settings.copy(dailyLossPct = p)) })
                }
            }

            Spacer(Modifier.height(16.dp))
            Text(tx("Share of the account it may use", "Kullanabileceği hesap payı"), color = MT.Text2, fontSize = 12.5.sp)
            Spacer(Modifier.height(8.dp))
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf(25, 50, 75, 100).forEach { p ->
                    Chip(if (turkish) "%$p" else "$p%", settings.usePct == p, { onChange(settings.copy(usePct = p)) })
                }
            }
            state.budget?.let {
                Text(tx("Right now that is ${w.usd(it)}. The rest is never touched.", "Şu an bu ${w.usd(it)} ediyor. Kalanına asla dokunmaz."),
                    color = MT.Text3, fontSize = 12.sp, modifier = Modifier.padding(top = 8.dp))
            }
        }

        SectionTitle(tx("Notifications", "Bildirimler"))
        Card {
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Chip(tx("Everything", "Her şey"), settings.notify == NotifyLevel.EVERYTHING, { onChange(settings.copy(notify = NotifyLevel.EVERYTHING)) })
                Chip(tx("Buys & sells", "Alım & satış"), settings.notify == NotifyLevel.TRADES, { onChange(settings.copy(notify = NotifyLevel.TRADES)) })
                Chip(tx("Quiet", "Sessiz"), settings.notify == NotifyLevel.QUIET, { onChange(settings.copy(notify = NotifyLevel.QUIET)) })
            }
            Text(
                when (settings.notify) {
                    NotifyLevel.EVERYTHING -> tx("Just bought, just sold with the profit or loss, the day's summary — plus silent notes on research and raised stops.",
                        "Az önce aldım, az önce sattım (kâr/zarar), günün özeti — artı araştırma ve yükseltilen stop'lar için sessiz notlar.")
                    NotifyLevel.TRADES -> tx("Just bought, just sold, and the day's summary.", "Az önce aldım, az önce sattım ve günün özeti.")
                    NotifyLevel.QUIET -> tx("Only approvals and warnings.", "Sadece onaylar ve uyarılar.")
                },
                color = MT.Text3, fontSize = 12.sp, modifier = Modifier.padding(top = 8.dp),
            )
        }

        SectionTitle(tx("Brain", "Beyin"))
        Card(highlight = settings.qualityMode != QualityMode.OFF) {
            Text(tx("Five checks before a buy", "Alımdan önce 5 kontrol"), color = MT.Text2, fontSize = 12.5.sp)
            Spacer(Modifier.height(8.dp))
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                QualityMode.entries.forEach { m -> Chip(w.qualityModeName(m), settings.qualityMode == m, { onChange(settings.copy(qualityMode = m)) }) }
            }
            Text(
                when (settings.qualityMode) {
                    QualityMode.STRICT -> tx("Buys only the buy zone: a good business at a fair price, daily chart rising. Expect very few trades.",
                        "Sadece alım bölgesi: makul fiyatlı iyi işletme, günlük grafik yükselişte. Çok az işlem bekle.")
                    QualityMode.BALANCED -> tx("Never a stock that fails the checks or fights a falling daily chart. A good business at a high price gets a smaller size.",
                        "Kontrolden kalan ya da düşen günlük grafiğe karşı hisse asla alınmaz. Pahalı iyi işletmeye daha küçük pozisyon.")
                    QualityMode.OFF -> tx("The checks still show in the Brain tab, but never hold a buy back.",
                        "Kontroller Beyin sekmesinde yine görünür ama alımı asla durdurmaz.")
                },
                color = MT.Text3, fontSize = 12.sp, modifier = Modifier.padding(top = 8.dp),
            )
            BrainSwitch(tx("News check", "Haber kontrolü"),
                tx("Holds a buy back on a fresh red flag (earnings due, an offering, a halt, a guidance cut) or clearly bad news.",
                    "Taze bir kırmızı bayrakta (bilanço yaklaşıyor, hisse satışı, işlem durdurma, beklenti düşürme) ya da net kötü haberde alımı durdurur."),
                settings.newsCheck) { onChange(settings.copy(newsCheck = it)) }
            BrainSwitch(tx("Learn from results", "Sonuçlardan öğren"),
                tx("Follows every signal to its result and stops buying the kinds that keep losing — only after 10 results of a kind.",
                    "Her sinyali sonucuna kadar takip eder, sürekli kaybettiren türleri almayı bırakır — aynı türden 10 sonuçtan sonra."),
                settings.learning) { onChange(settings.copy(learning = it)) }
            BrainSwitch(tx("Improve itself", "Kendini geliştir"),
                tx("Breeds and tests strategy settings on months of real candles, around the clock, and switches only to ones that prove better on data they never trained on. Never touches your risk settings.",
                    "Aylarca gerçek mum üzerinde gece gündüz strateji ayarları üretip dener; sadece hiç eğitilmediği veride daha iyi olduğu kanıtlanana geçer. Risk ayarlarına asla dokunmaz."),
                settings.selfImprove) { onChange(settings.copy(selfImprove = it)) }
            BrainSwitch(tx("Train at full speed on battery", "Pildeyken de tam hızda eğit"),
                tx("Off: full speed on the charger, a tenth of that on battery. On: full speed always — the phone gets warm and the battery drains faster.",
                    "Kapalı: şarjda tam hız, pilde onun onda biri. Açık: her zaman tam hız — telefon ısınır, pil daha hızlı biter."),
                settings.trainOnBattery) { onChange(settings.copy(trainOnBattery = it)) }
            BrainSwitch(tx("Find stocks in the news", "Haberlerde hisse bul"),
                tx("Reads the whole market's news and watches up to three of the most talked-about stocks for three days — only if they pass the five checks.",
                    "Tüm piyasanın haberlerini okur, en çok konuşulan en fazla 3 hisseyi 3 gün izler — sadece 5 kontrolden geçerlerse."),
                settings.discover) { onChange(settings.copy(discover = it)) }
            BrainSwitch(tx("AI committee veto", "AI kurulu vetosu"),
                tx("Two different AI models read the headlines and the research before each buy; either can stop it. Never starts one.",
                    "Her alımdan önce iki farklı AI modeli başlıkları ve araştırmayı okur; biri bile durdurabilir. Asla alım başlatmaz."),
                settings.aiCheck) { onChange(settings.copy(aiCheck = it)) }
            if (!secure.has(SecureStore.GROQ_KEY)) {
                Text(tx("The AI parts need a free Groq key — add it under Keys below.", "AI kısımları ücretsiz bir Groq anahtarı ister — aşağıda Anahtarlar'a ekle."),
                    color = MT.Accent, fontSize = 12.sp, modifier = Modifier.padding(top = 8.dp))
            }
        }

        SectionTitle(tx("Money", "Para"))
        Card(highlight = settings.live) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(if (settings.live) tx("Real money", "Gerçek para") else tx("Practice money (paper)", "Deneme parası (paper)"),
                        fontWeight = FontWeight.SemiBold)
                    Text(
                        if (settings.live) tx("Orders go to your real Alpaca account.", "Emirler gerçek Alpaca hesabına gider.")
                        else tx("Real prices, pretend money. Nothing real is at risk.", "Gerçek fiyat, sahte para. Gerçek hiçbir şey risk altında değil."),
                        color = MT.Text3, fontSize = 12.sp,
                    )
                }
                Tag(if (settings.live) tx("REAL", "GERÇEK") else "PAPER", if (settings.live) MT.Down else MT.Accent)
            }
            Spacer(Modifier.height(12.dp))
            if (!settings.live) {
                GhostButton(tx("Switch to real money…", "Gerçek paraya geç…"), {
                    if (!secure.has(SecureStore.LIVE_KEY) || !secure.has(SecureStore.LIVE_SECRET)) toast(pick(turkish, "Add your live Alpaca keys below first.", "Önce aşağıya canlı Alpaca anahtarlarını ekle."))
                    else confirmLive = true
                }, color = MT.Down)
            } else {
                if (armed) {
                    Text(tx("ARMED — real orders can be placed until you disarm or restart.",
                        "DEVREDE — kapatana ya da yeniden başlatana kadar gerçek emir verilebilir."),
                        color = MT.Down, fontSize = 12.5.sp, fontWeight = FontWeight.SemiBold)
                    GhostButton(tx("Disarm", "Devreden çıkar"), { Hub.armed.value = false }, color = MT.Text)
                } else {
                    Text(tx("Not armed. The bot watches but will not buy with real money.",
                        "Devrede değil. Bot izler ama gerçek parayla almaz."), color = MT.Text2, fontSize = 12.5.sp)
                    PrimaryButton(tx("Arm real-money trading", "Gerçek parayı devreye al"), requestArm, Modifier.fillMaxWidth())
                }
                GhostButton(tx("Back to practice money", "Deneme parasına dön"), {
                    Hub.armed.value = false
                    onChange(settings.copy(live = false))
                    if (running) EngineService.restart(context)
                })
            }
            GhostButton(tx("Deposit & withdraw", "Para yatır ve çek"), onOpenMoney, color = MT.Accent)
        }

        SectionTitle(tx("Market", "Piyasa"))
        Card {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Market.entries.forEach { m ->
                    Chip(marketName(m), settings.market == m, {
                        onChange(settings.copy(market = m, watchlist = m.watchlist))
                        toast(pick(turkish, "Watching ${m.watchlist.joinToString(", ")}", "İzleniyor: ${m.watchlist.joinToString(", ")}"))
                    })
                }
            }
            Text(marketNote(), color = MT.Text3, fontSize = 12.sp, lineHeight = 17.sp, modifier = Modifier.padding(top = 10.dp))
        }

        SectionTitle(tx("Small account", "Küçük hesap"))
        Card(highlight = settings.fractional) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(tx("Buy fractions of a share", "Hissenin küsuratını al"), fontWeight = FontWeight.SemiBold)
                    Text(tx("For balances like \$10, where one whole share is too much.", "10$ gibi, tek hissenin bile fazla geldiği bakiyeler için."),
                        color = MT.Text3, fontSize = 12.sp)
                }
                Switch(
                    settings.fractional, { onChange(settings.copy(fractional = it)) },
                    colors = SwitchDefaults.colors(checkedThumbColor = Color.Black, checkedTrackColor = MT.Accent),
                )
            }
            Text(
                if (settings.fractional) tx("On. Where one whole share fits it still buys whole shares, with the stop and target at Alpaca. A fraction gets a stop order at Alpaca every trading day (Alpaca only takes day orders on fractions); its target is watched by this phone.",
                    "Açık. Tam hisse sığıyorsa yine tam hisse alır, stop ve hedef Alpaca'da. Küsurat için her işlem günü Alpaca'ya stop emri konur (Alpaca küsurata sadece günlük emir alıyor); hedefini bu telefon izler.")
                else tx("Off. Whole shares only, and every stop sits at Alpaca — protected even with the phone off.",
                    "Kapalı. Sadece tam hisse, her stop Alpaca'da durur — telefon kapalıyken bile korumalı."),
                color = MT.Text3, fontSize = 12.sp, modifier = Modifier.padding(top = 8.dp),
            )
        }

        SectionTitle(tx("Watchlist", "İzleme listesi"))
        Card {
            var text by remember(settings.watchlist) { mutableStateOf(settings.watchlist.joinToString(", ")) }
            OutlinedTextField(
                text, { text = it }, Modifier.fillMaxWidth(),
                label = { Text(tx("Symbols, comma separated", "Semboller, virgülle ayır")) },
                keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Characters),
                colors = fieldColors(), shape = RoundedCornerShape(12.dp),
            )
            GhostButton(tx("Save watchlist", "Listeyi kaydet"), {
                val list = text.split(",", " ").map { it.trim().uppercase() }.filter { it.matches(Regex("[A-Z.]{1,6}")) }.distinct()
                if (list.isEmpty()) toast(pick(turkish, "Add at least one symbol.", "En az bir sembol ekle."))
                else { onChange(settings.copy(watchlist = list.take(20))); toast(pick(turkish, "Saved.", "Kaydedildi.")) }
            }, color = MT.Accent)
        }

        SectionTitle(tx("Keys", "Anahtarlar"))
        Card {
            KeyField(tx("Alpaca paper key ID", "Alpaca paper anahtar ID"), SecureStore.PAPER_KEY, secure, keysVersion) { keysVersion++ }
            KeyField(tx("Alpaca paper secret", "Alpaca paper gizli anahtar"), SecureStore.PAPER_SECRET, secure, keysVersion) { keysVersion++ }
            KeyField(tx("Alpaca LIVE key ID", "Alpaca CANLI anahtar ID"), SecureStore.LIVE_KEY, secure, keysVersion) { keysVersion++ }
            KeyField(tx("Alpaca LIVE secret", "Alpaca CANLI gizli anahtar"), SecureStore.LIVE_SECRET, secure, keysVersion) { keysVersion++ }
            KeyField(tx("Groq key (free AI, optional)", "Groq anahtarı (ücretsiz AI, isteğe bağlı)"), SecureStore.GROQ_KEY, secure, keysVersion) { keysVersion++ }
            Text(tx("Stored encrypted with this phone's Keystore. Never backed up, never sent anywhere but Alpaca and Groq.",
                "Bu telefonun Keystore'uyla şifreli saklanır. Yedeklenmez, Alpaca ve Groq dışında hiçbir yere gitmez."),
                color = MT.Text3, fontSize = 11.5.sp, modifier = Modifier.padding(top = 6.dp))
            if (running) GhostButton(tx("Apply new keys (restart bot)", "Yeni anahtarları uygula (botu yeniden başlat)"),
                { EngineService.restart(context) }, color = MT.Accent)
        }

        SectionTitle(tx("Running in the background", "Arka planda çalışma"))
        Card {
            Text(tx("Android may pause apps to save battery. Exempt Money Tree so its checks keep running with the screen off. Stops are held at Alpaca either way.",
                "Android pil için uygulamaları durdurabilir. Ekran kapalıyken de kontrol etmeye devam etsin diye Money Tree'yi muaf tut. Stop'lar her durumda Alpaca'da durur."),
                color = MT.Text2, fontSize = 12.5.sp)
            BatteryButton()
        }

        SectionTitle(tx("Setup", "Kurulum"))
        Card {
            Text(tx("Go through the setup questions again. Your keys stay saved and the bot keeps running.",
                "Kurulum sorularından tekrar geç. Anahtarların kayıtlı kalır, bot çalışmaya devam eder."),
                color = MT.Text2, fontSize = 12.5.sp)
            GhostButton(tx("Ask me the questions again", "Soruları tekrar sor"), onRedoSetup, color = MT.Accent)
        }

        SectionTitle(tx("Language", "Dil"))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Chip("English", !settings.turkish, { onChange(settings.copy(turkish = false)) })
            Chip("Türkçe", settings.turkish, { onChange(settings.copy(turkish = true)) })
        }

        Spacer(Modifier.height(24.dp))
        Text(tx("Prices and news come from Alpaca's free feeds; company reports from the SEC and exchange rates from the ECB — public data, and nothing about you is sent to either. This is a tool, not financial advice.",
            "Fiyatlar ve haberler Alpaca'nın ücretsiz akışlarından; şirket raporları SEC'ten, döviz kurları Avrupa Merkez Bankası'ndan gelir — açık veriler, ikisine de senin hakkında hiçbir şey gitmez. Bu bir araç, yatırım tavsiyesi değil."),
            color = MT.Text3, fontSize = 11.sp, lineHeight = 15.sp)
    }

    if (confirmLive) {
        AlertDialog(
            onDismissRequest = { confirmLive = false },
            containerColor = MT.Surface,
            title = { Text(tx("Switch to real money?", "Gerçek paraya geçilsin mi?")) },
            text = {
                Text(tx("Orders will go to your real Alpaca account. The bot starts disarmed: nothing is bought until you arm it, and every restart disarms it again. Losses are real.",
                    "Emirler gerçek Alpaca hesabına gider. Bot devre dışı başlar: sen devreye almadan hiçbir şey almaz ve her yeniden başlatmada tekrar devre dışı kalır. Kayıplar gerçektir."))
            },
            confirmButton = {
                TextButton({
                    confirmLive = false
                    Hub.armed.value = false
                    onChange(settings.copy(live = true))
                    if (running) EngineService.restart(context)
                    // Stay here: the switch is done, and arming is the next step on this page.
                    toast(pick(turkish, "Switched to real money. It buys nothing until you tap Arm.",
                        "Gerçek paraya geçildi. Devreye al'a basana kadar hiçbir şey almaz."))
                }) { Text(tx("Switch", "Geç"), color = MT.Down) }
            },
            dismissButton = { TextButton({ confirmLive = false }) { Text(tx("Cancel", "Vazgeç")) } },
        )
    }
}

@Composable
fun marketName(m: Market) = when (m) {
    Market.US -> tx("US", "ABD")
    Market.EUROPE -> tx("Europe", "Avrupa")
    Market.BOTH -> tx("Both", "İkisi")
}

@Composable
private fun horizonName(h: Horizon) = when (h) {
    Horizon.SHORT -> tx("Short", "Kısa")
    Horizon.MEDIUM -> tx("Medium", "Orta")
    Horizon.LONG -> tx("Long", "Uzun")
}

@Composable
private fun BrainSwitch(title: String, hint: String, on: Boolean, onToggle: (Boolean) -> Unit) {
    Row(Modifier.padding(top = 14.dp), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text(title, fontWeight = FontWeight.SemiBold)
            Text(hint, color = MT.Text3, fontSize = 12.sp, lineHeight = 16.sp)
        }
        Spacer(Modifier.width(10.dp))
        Switch(on, onToggle, colors = SwitchDefaults.colors(checkedThumbColor = Color.Black, checkedTrackColor = MT.Accent))
    }
}

@Composable
private fun KeyField(label: String, name: String, secure: SecureStore, version: Int, onSaved: () -> Unit) {
    val set = remember(version) { secure.has(name) }
    var value by remember(version) { mutableStateOf("") }
    Column(Modifier.padding(vertical = 4.dp)) {
        OutlinedTextField(
            value, { value = it.trim() }, Modifier.fillMaxWidth(),
            label = { Text(label + if (set) " ✓" else "") },
            placeholder = { Text(if (set) tx("saved — type to replace", "kayıtlı — değiştirmek için yaz") else "") },
            singleLine = true, visualTransformation = PasswordVisualTransformation(),
            colors = fieldColors(), shape = RoundedCornerShape(12.dp),
        )
        if (value.isNotEmpty()) {
            GhostButton(tx("Save", "Kaydet"), { secure.put(name, value); onSaved() }, color = MT.Accent)
        }
    }
}

@SuppressLint("BatteryLife")
@Composable
private fun BatteryButton() {
    val context = LocalContext.current
    val power = context.getSystemService(PowerManager::class.java)
    val exempt = power.isIgnoringBatteryOptimizations(context.packageName)
    if (exempt) {
        Text(tx("✓ Exempt — it keeps running with the screen off.", "✓ Muaf — ekran kapalıyken de çalışır."),
            color = MT.Up, fontSize = 12.5.sp, modifier = Modifier.padding(top = 8.dp))
    } else {
        GhostButton(tx("Keep running in the background", "Arka planda çalışmaya devam et"), {
            context.startActivity(
                Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:${context.packageName}"))
            )
        }, color = MT.Accent)
    }
}

@Composable
fun fieldColors() = OutlinedTextFieldDefaults.colors(
    focusedBorderColor = MT.Accent, unfocusedBorderColor = MT.Line,
    focusedLabelColor = MT.Accent, cursorColor = MT.Accent,
)
