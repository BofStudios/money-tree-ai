package com.bofstudios.moneytree.ui

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.os.SystemClock
import android.widget.Toast
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.biometric.BiometricManager
import androidx.biometric.BiometricManager.Authenticators.BIOMETRIC_WEAK
import androidx.biometric.BiometricManager.Authenticators.DEVICE_CREDENTIAL
import androidx.biometric.BiometricPrompt
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
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
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.List
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Star
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import androidx.fragment.app.FragmentActivity
import com.bofstudios.moneytree.MoneyTreeApp
import com.bofstudios.moneytree.R
import com.bofstudios.moneytree.data.Prefs
import com.bofstudios.moneytree.engine.TradingSettings
import com.bofstudios.moneytree.service.EngineService
import com.bofstudios.moneytree.service.Hub

/**
 * The app opens behind the phone's own lock — fingerprint, face or PIN — and
 * locks again after a minute in the background. Arming real money asks again.
 */
class MainActivity : FragmentActivity() {
    private lateinit var prefs: Prefs
    private var settings by mutableStateOf(TradingSettings())
    private var onboarded by mutableStateOf(false)
    private var unlocked by mutableStateOf(false)
    private var noScreenLock by mutableStateOf(false)
    private var pausedAt = 0L
    private var crash by mutableStateOf<String?>(null)

    private val notificationPermission =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        prefs = Prefs(this)
        settings = prefs.settings(Hub.armed.value)
        onboarded = prefs.onboarded
        crash = MoneyTreeApp.lastCrash(this)
        // Semi-auto approvals arrive as notifications; without this permission
        // they would silently never show. Ask whenever it is missing.
        if (onboarded) askForNotifications()

        setContent {
            CompositionLocalProvider(LocalTurkish provides settings.turkish) {
                MoneyTreeTheme {
                    Box(Modifier.fillMaxSize().background(MT.Bg).statusBarsPadding()) {
                        when {
                            !unlocked -> Locked { authenticate() }
                            !onboarded -> SetupScreen(
                                initial = settings,
                                onDone = { chosen ->
                                    update(chosen)
                                    prefs.onboarded = true
                                    onboarded = true
                                    askForNotifications()
                                    EngineService.start(this@MainActivity)
                                },
                                onLanguage = { update(settings.copy(turkish = it)) },
                            )
                            else -> Main()
                        }
                    }
                }
            }
        }
    }

    override fun onResume() {
        super.onResume()
        if (unlocked && pausedAt > 0 && SystemClock.elapsedRealtime() - pausedAt > RELOCK_MS) unlocked = false
        if (!unlocked) authenticate()
        settings = prefs.settings(Hub.armed.value)
    }

    override fun onPause() {
        super.onPause()
        pausedAt = SystemClock.elapsedRealtime()
    }

    // ------------------------------------------------------------------- ui

    @Composable
    private fun Main() {
        var tab by rememberSaveable { mutableIntStateOf(0) }
        Box(Modifier.fillMaxSize()) {
            Column(Modifier.fillMaxSize()) {
                Header()
                crash?.let { report ->
                    CrashCard(report, onCopy = {
                        val cm = getSystemService(android.content.ClipboardManager::class.java)
                        cm.setPrimaryClip(android.content.ClipData.newPlainText("Money Tree crash", report))
                        toast(if (settings.turkish) "Kopyalandı — bana gönder." else "Copied — send it to me.")
                    }, onDismiss = { MoneyTreeApp.clearCrash(this@MainActivity); crash = null })
                }
                if (noScreenLock) {
                    Text(
                        tx("This phone has no screen lock, so Money Tree opens without one. Set a PIN or fingerprint to protect it.",
                            "Bu telefonda ekran kilidi yok, Money Tree kilitsiz açılıyor. Korumak için PIN ya da parmak izi ayarla."),
                        color = MT.Down, fontSize = 12.sp, modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp),
                    )
                }
                AnimatedContent(tab, transitionSpec = { fadeIn() togetherWith fadeOut() }, label = "tab") { t ->
                    when (t) {
                        0 -> MonitorScreen(settings, ::toast)
                        1 -> PortfolioScreen(prefs)
                        else -> SettingsScreen(settings, ::update, ::armWithAuth, ::toast)
                    }
                }
            }
            NavBar(tab, { tab = it }, Modifier.align(Alignment.BottomCenter))
        }
    }

    @Composable
    private fun CrashCard(report: String, onCopy: () -> Unit, onDismiss: () -> Unit) {
        Card(Modifier.padding(horizontal = 16.dp, vertical = 6.dp), highlight = true) {
            Text(tx("Money Tree crashed last time", "Money Tree geçen sefer çöktü"), fontWeight = FontWeight.SemiBold, color = MT.Down)
            Text(report.lineSequence().drop(2).firstOrNull { it.isNotBlank() }.orEmpty().take(160),
                color = MT.Text2, fontFamily = MT.Mono, fontSize = 11.sp, modifier = Modifier.padding(vertical = 6.dp))
            Row {
                PrimaryButton(tx("Copy the report", "Raporu kopyala"), onCopy)
                GhostButton(tx("Dismiss", "Kapat"), onDismiss)
            }
        }
    }

    @Composable
    private fun Header() {
        Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
            Image(painterResource(R.mipmap.ic_launcher), null, Modifier.size(30.dp).clip(RoundedCornerShape(8.dp)))
            Spacer(Modifier.size(10.dp))
            Text("Money Tree", fontWeight = FontWeight.SemiBold, fontSize = 18.sp)
        }
    }

    @Composable
    private fun NavBar(tab: Int, onTab: (Int) -> Unit, modifier: Modifier) {
        Row(
            modifier.navigationBarsPadding().padding(bottom = 14.dp)
                .clip(RoundedCornerShape(22.dp)).background(MT.Surface.copy(alpha = 0.97f))
                .border(1.dp, MT.Line, RoundedCornerShape(22.dp)).padding(6.dp),
            horizontalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            NavItem(Icons.Filled.Star, tx("Monitor", "Monitör"), tab == 0) { onTab(0) }
            NavItem(Icons.AutoMirrored.Filled.List, tx("Portfolio", "Portföy"), tab == 1) { onTab(1) }
            NavItem(Icons.Filled.Settings, tx("Settings", "Ayarlar"), tab == 2) { onTab(2) }
        }
    }

    @Composable
    private fun NavItem(icon: ImageVector, label: String, selected: Boolean, onClick: () -> Unit) {
        Column(
            Modifier.clip(RoundedCornerShape(16.dp))
                .background(if (selected) MT.AccentSoft else MT.Surface.copy(alpha = 0f))
                .clickable(onClick = onClick).padding(horizontal = 20.dp, vertical = 8.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Icon(icon, null, tint = if (selected) MT.Accent else MT.Text3, modifier = Modifier.size(20.dp))
            Text(label, color = if (selected) MT.Accent else MT.Text3, fontSize = 10.sp, fontWeight = FontWeight.Medium)
        }
    }

    @Composable
    private fun Locked(onUnlock: () -> Unit) {
        Column(Modifier.fillMaxSize(), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
            Image(painterResource(R.mipmap.ic_launcher), null, Modifier.size(96.dp))
            Spacer(Modifier.height(18.dp))
            Text("Money Tree", fontSize = 22.sp, fontWeight = FontWeight.SemiBold)
            Spacer(Modifier.height(24.dp))
            PrimaryButton(tx("Unlock", "Kilidi aç"), onUnlock)
        }
    }

    // -------------------------------------------------------------- actions

    private fun update(next: TradingSettings) {
        val before = settings
        prefs.save(next)
        settings = next
        if (before.autonomy != next.autonomy || before.horizon != next.horizon || before.watchlist != next.watchlist) {
            Hub.engine?.settingsChanged()
            EngineService.scanNow(this)
        }
    }

    private fun toast(message: String) = Toast.makeText(this, message, Toast.LENGTH_LONG).show()

    private fun canAuthenticate(): Boolean =
        BiometricManager.from(this).canAuthenticate(BIOMETRIC_WEAK or DEVICE_CREDENTIAL) == BiometricManager.BIOMETRIC_SUCCESS

    private fun authenticate() {
        if (!canAuthenticate()) {
            noScreenLock = true
            unlocked = true
            return
        }
        prompt(
            title = if (settings.turkish) "Money Tree'yi aç" else "Unlock Money Tree",
            onSuccess = { unlocked = true },
        )
    }

    /** Real money needs a fresh proof that it is really the owner. */
    private fun armWithAuth() {
        val arm = {
            Hub.armed.value = true
            toast(if (settings.turkish) "Gerçek para devrede. Yeniden başlatınca kapanır." else "Real money armed. Any restart disarms it.")
        }
        if (!canAuthenticate()) {
            toast(if (settings.turkish) "Önce telefona ekran kilidi koy." else "Set a screen lock on this phone first.")
            return
        }
        prompt(title = if (settings.turkish) "Gerçek parayı devreye al" else "Arm real-money trading", onSuccess = arm)
    }

    private fun prompt(title: String, onSuccess: () -> Unit) {
        val info = BiometricPrompt.PromptInfo.Builder()
            .setTitle(title)
            .setAllowedAuthenticators(BIOMETRIC_WEAK or DEVICE_CREDENTIAL)
            .build()
        BiometricPrompt(this, ContextCompat.getMainExecutor(this), object : BiometricPrompt.AuthenticationCallback() {
            override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) = onSuccess()
        }).authenticate(info)
    }

    private fun askForNotifications() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            notificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
        }
    }

    companion object {
        private const val RELOCK_MS = 60_000L
    }
}
