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
) {
    val context = LocalContext.current
    val secure = remember { SecureStore(context) }
    val running by Hub.running.collectAsState()
    val armed by Hub.armed.collectAsState()
    val turkish = LocalTurkish.current
    val w = Words(turkish)
    var confirmLive by remember { mutableStateOf(false) }
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
                    if (!secure.has(SecureStore.LIVE_KEY)) toast(pick(turkish, "Add your live Alpaca keys below first.", "Önce aşağıya canlı Alpaca anahtarlarını ekle."))
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
                if (settings.fractional) tx("On. Alpaca takes no stop-loss order on fractions, so THIS PHONE watches the stop and target. If the phone is off or asleep, those positions are not protected.",
                    "Açık. Alpaca küsurata stop-loss emri almıyor, stop ve hedefi BU TELEFON izliyor. Telefon kapalı ya da uykudaysa bu pozisyonlar korumasız.")
                else tx("Off. Whole shares only, and every stop sits at Alpaca — protected even with the phone off.",
                    "Kapalı. Sadece tam hisse, her stop Alpaca'da durur — telefon kapalıyken bile korumalı."),
                color = if (settings.fractional) MT.Down else MT.Text3, fontSize = 12.sp, modifier = Modifier.padding(top = 8.dp),
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

        SectionTitle(tx("Language", "Dil"))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Chip("English", !settings.turkish, { onChange(settings.copy(turkish = false)) })
            Chip("Türkçe", settings.turkish, { onChange(settings.copy(turkish = true)) })
        }

        Spacer(Modifier.height(24.dp))
        Text(tx("Prices come from Alpaca's free IEX feed. This is a tool, not financial advice.",
            "Fiyatlar Alpaca'nın ücretsiz IEX akışından gelir. Bu bir araç, yatırım tavsiyesi değil."),
            color = MT.Text3, fontSize = 11.sp)
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
                }) { Text(tx("Switch", "Geç"), color = MT.Down) }
            },
            dismissButton = { TextButton({ confirmLive = false }) { Text(tx("Cancel", "Vazgeç")) } },
        )
    }
}

@Composable
private fun horizonName(h: Horizon) = when (h) {
    Horizon.SHORT -> tx("Short", "Kısa")
    Horizon.MEDIUM -> tx("Medium", "Orta")
    Horizon.LONG -> tx("Long", "Uzun")
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
