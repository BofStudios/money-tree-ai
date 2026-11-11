package com.bofstudios.moneytree.ui

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Send
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.material3.TextField
import androidx.compose.material3.TextFieldDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.bofstudios.moneytree.ai.ChatAdvisor
import com.bofstudios.moneytree.ai.ChatMessage
import com.bofstudios.moneytree.data.SecureStore
import com.bofstudios.moneytree.engine.EngineState
import com.bofstudios.moneytree.service.Hub
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.ByteArrayOutputStream
import java.util.Locale
import kotlin.math.max

/** A picture ready to send: the JPEG for the AI and a small preview for the screen. */
class Picked(val jpeg: ByteArray, val preview: ImageBitmap)

/** A chat line on the screen. */
class Line(val message: ChatMessage, val previews: List<ImageBitmap> = emptyList())

/**
 * The conversation, in memory only. It is never saved: closing the app
 * (or pressing the bin) forgets it. Errors are shown for a few seconds and
 * never become part of the conversation.
 */
object ChatSession {
    val lines = mutableStateListOf<Line>()
    val attached = mutableStateListOf<Picked>()
    /** Screenshots shared into the app from another app (e.g. Midas), waiting for the chat screen. */
    val incoming = mutableStateListOf<Uri>()
    var draft by mutableStateOf("")

    fun forget() {
        lines.clear(); attached.clear(); incoming.clear(); draft = ""
    }
}

@Composable
fun ChatScreen(turkish: Boolean) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val secure = remember { SecureStore(context) }
    val key = remember { secure.get(SecureStore.GROQ_KEY) }
    val state by Hub.state.collectAsState()
    var thinking by remember { mutableStateOf(false) }
    var notice by remember { mutableStateOf<String?>(null) }
    val list = rememberLazyListState()

    fun flash(text: String) {
        notice = text
        scope.launch { delay(5000); if (notice == text) notice = null }
    }

    fun attach(uris: List<Uri>) {
        scope.launch {
            for (uri in uris) {
                if (ChatSession.attached.size >= ChatAdvisor.MAX_IMAGES) break
                val picked = withContext(Dispatchers.IO) { shrink(context, uri) }
                if (picked != null) ChatSession.attached.add(picked)
                else flash(if (turkish) "Bu resim açılamadı." else "Could not open that picture.")
            }
        }
    }

    val picker = rememberLauncherForActivityResult(ActivityResultContracts.PickMultipleVisualMedia(ChatAdvisor.MAX_IMAGES)) { uris ->
        attach(uris)
    }

    // A screenshot shared from another app lands here.
    LaunchedEffect(ChatSession.incoming.size) {
        if (ChatSession.incoming.isNotEmpty()) {
            val uris = ChatSession.incoming.toList()
            ChatSession.incoming.clear()
            attach(uris)
        }
    }
    LaunchedEffect(ChatSession.lines.size, thinking) {
        val count = ChatSession.lines.size + (if (thinking) 1 else 0)
        if (count > 0) list.animateScrollToItem(count - 1)
    }

    fun send(text: String) {
        val k = key
        if (k.isNullOrBlank()) {
            flash(if (turkish) "Önce Ayarlar'dan Groq anahtarını gir (ücretsiz)." else "Add your free Groq key in Settings first.")
            return
        }
        val pics = ChatSession.attached.toList()
        if (text.isBlank() && pics.isEmpty()) return
        ChatSession.lines.add(Line(ChatMessage(true, text.trim(), pics.map { it.jpeg }), pics.map { it.preview }))
        ChatSession.attached.clear()
        ChatSession.draft = ""
        thinking = true
        scope.launch {
            val reply = ChatAdvisor(k).reply(ChatSession.lines.map { it.message }, describe(state), turkish)
            thinking = false
            when (reply) {
                is ChatAdvisor.Reply.Ok -> ChatSession.lines.add(Line(ChatMessage(false, reply.text)))
                is ChatAdvisor.Reply.Failed -> {
                    // The question stays so it can be sent again; the error is not kept.
                    val last = ChatSession.lines.removeAt(ChatSession.lines.lastIndex)
                    ChatSession.draft = last.message.text
                    ChatSession.attached.addAll(last.message.images.zip(last.previews) { j, p -> Picked(j, p) })
                    flash((if (turkish) "Gönderilemedi: " else "Not sent: ") + reply.why)
                }
            }
        }
    }

    Column(Modifier.fillMaxSize().imePadding().padding(bottom = 96.dp)) {
        Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(if (turkish) "Sohbet" else "Chat", fontSize = 20.sp, fontWeight = FontWeight.SemiBold)
                Text(
                    if (turkish) "Borsa, portföyün ve ekran görüntülerin. Hiçbir şey kaydedilmez."
                    else "Markets, your portfolio and your screenshots. Nothing is saved.",
                    color = MT.Text2, fontSize = 11.sp,
                )
            }
            if (ChatSession.lines.isNotEmpty()) {
                Icon(Icons.Filled.Delete, if (turkish) "Sohbeti sil" else "Clear chat", tint = MT.Text3,
                    modifier = Modifier.size(36.dp).clip(CircleShape).clickable { ChatSession.forget() }.padding(8.dp))
            }
        }

        LazyColumn(
            Modifier.weight(1f).fillMaxWidth(), state = list,
            verticalArrangement = Arrangement.spacedBy(8.dp),
            contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 14.dp, vertical = 8.dp),
        ) {
            if (ChatSession.lines.isEmpty()) {
                item { Welcome(turkish) { send(it) } }
            }
            items(ChatSession.lines) { line -> Bubble(line) }
            if (thinking) item { Typing(turkish) }
        }

        notice?.let {
            Text(it, color = MT.Down, fontSize = 12.sp, modifier = Modifier.padding(horizontal = 16.dp, vertical = 2.dp))
        }
        if (ChatSession.attached.isNotEmpty()) {
            Row(Modifier.horizontalScroll(rememberScrollState()).padding(horizontal = 14.dp, vertical = 4.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                ChatSession.attached.toList().forEach { p ->
                    Box {
                        Image(p.preview, null, contentScale = ContentScale.Crop,
                            modifier = Modifier.size(64.dp).clip(RoundedCornerShape(10.dp)).border(1.dp, MT.Line, RoundedCornerShape(10.dp)))
                        Icon(Icons.Filled.Close, null, tint = MT.Text,
                            modifier = Modifier.align(Alignment.TopEnd).size(20.dp).clip(CircleShape)
                                .background(MT.Bg.copy(alpha = 0.7f)).clickable { ChatSession.attached.remove(p) }.padding(3.dp))
                    }
                }
            }
        }
        Row(
            Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 6.dp)
                .clip(RoundedCornerShape(22.dp)).background(MT.Surface).border(1.dp, MT.Line, RoundedCornerShape(22.dp))
                .padding(4.dp),
            verticalAlignment = Alignment.Bottom,
        ) {
            Icon(Icons.Filled.Add, if (turkish) "Fotoğraf ekle" else "Add a picture", tint = MT.Accent,
                modifier = Modifier.size(44.dp).clip(CircleShape).clickable(enabled = !thinking) {
                    picker.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly))
                }.padding(10.dp))
            TextField(
                value = ChatSession.draft, onValueChange = { ChatSession.draft = it },
                modifier = Modifier.weight(1f).heightIn(min = 44.dp, max = 140.dp),
                placeholder = { Text(if (turkish) "Sor ya da ekran görüntüsü ekle…" else "Ask, or add a screenshot…", color = MT.Text3, fontSize = 14.sp) },
                colors = TextFieldDefaults.colors(
                    focusedContainerColor = MT.Surface, unfocusedContainerColor = MT.Surface,
                    focusedIndicatorColor = MT.Surface, unfocusedIndicatorColor = MT.Surface,
                    focusedTextColor = MT.Text, unfocusedTextColor = MT.Text, cursorColor = MT.Accent,
                ),
            )
            val canSend = !thinking && (ChatSession.draft.isNotBlank() || ChatSession.attached.isNotEmpty())
            Icon(Icons.Filled.Send, if (turkish) "Gönder" else "Send", tint = if (canSend) MT.Bg else MT.Text3,
                modifier = Modifier.size(44.dp).clip(CircleShape).background(if (canSend) MT.Accent else MT.Surface2)
                    .clickable(enabled = canSend) { send(ChatSession.draft) }.padding(11.dp))
        }
    }
}

@Composable
private fun Welcome(turkish: Boolean, onPick: (String) -> Unit) {
    val ideas = if (turkish) listOf(
        "Portföyüm nasıl, ne yapmalıyım?",
        "Şu an hangi hisseler ilginç?",
        "Botum neden bu hisseleri aldı?",
        "Stop-loss'larım mantıklı mı?",
    ) else listOf(
        "How is my portfolio doing?",
        "Which stocks look interesting right now?",
        "Why did my bot buy these?",
        "Are my stop-losses sensible?",
    )
    Card(glow = true) {
        Text(if (turkish) "Selam 👋" else "Hi 👋", fontSize = 18.sp, fontWeight = FontWeight.SemiBold)
        Spacer(Modifier.height(6.dp))
        Text(
            if (turkish) "Midas'ta ya da başka bir uygulamada ekran görüntüsü al, + ile ekle ya da o uygulamadan \"Paylaş → Money Tree\" de. Ne gördüğümü, al/sat/bekle eğilimimi ve riskleri söylerim. Karar her zaman senin."
            else "Take a screenshot in your broker app, add it with +, or use \"Share → Money Tree\" from that app. I'll tell you what I see, which way I lean and the risks. The call is always yours.",
            color = MT.Text2, fontSize = 13.sp,
        )
        Spacer(Modifier.height(10.dp))
        ideas.forEach { idea ->
            Text(idea, color = MT.Accent, fontSize = 13.sp,
                modifier = Modifier.padding(vertical = 3.dp).clip(RoundedCornerShape(12.dp))
                    .background(MT.AccentSoft).clickable { onPick(idea) }.padding(horizontal = 12.dp, vertical = 8.dp))
        }
    }
}

@Composable
private fun Bubble(line: Line) {
    val mine = line.message.fromMe
    Row(Modifier.fillMaxWidth(), horizontalArrangement = if (mine) Arrangement.End else Arrangement.Start) {
        Column(
            Modifier.widthIn(max = 320.dp)
                .clip(RoundedCornerShape(18.dp, 18.dp, if (mine) 4.dp else 18.dp, if (mine) 18.dp else 4.dp))
                .background(if (mine) MT.Accent else MT.Surface2)
                .padding(horizontal = 13.dp, vertical = 9.dp),
        ) {
            line.previews.forEach { p ->
                Image(p, null, contentScale = ContentScale.FillWidth,
                    modifier = Modifier.fillMaxWidth().padding(bottom = 6.dp).clip(RoundedCornerShape(12.dp)))
            }
            if (line.message.text.isNotBlank()) {
                SelectionContainer {
                    Text(line.message.text, color = if (mine) MT.Bg else MT.Text, fontSize = 14.sp, lineHeight = 20.sp)
                }
            }
        }
    }
}

@Composable
private fun Typing(turkish: Boolean) {
    var dots by remember { mutableStateOf(1) }
    LaunchedEffect(Unit) { while (true) { delay(400); dots = dots % 3 + 1 } }
    Text((if (turkish) "Bakıyorum" else "Looking") + ".".repeat(dots), color = MT.Text2, fontSize = 13.sp,
        modifier = Modifier.clip(RoundedCornerShape(18.dp)).background(MT.Surface2).padding(horizontal = 13.dp, vertical = 9.dp))
}

/** The picture at [uri], at most 1280 px on its long side, as JPEG, with a small preview. */
private fun shrink(context: Context, uri: Uri): Picked? = runCatching {
    val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
    context.contentResolver.openInputStream(uri)?.use { BitmapFactory.decodeStream(it, null, bounds) }
    var sample = 1
    while (max(bounds.outWidth, bounds.outHeight) / (sample * 2) >= 1280) sample *= 2
    val decoded = context.contentResolver.openInputStream(uri)?.use {
        BitmapFactory.decodeStream(it, null, BitmapFactory.Options().apply { inSampleSize = sample })
    } ?: return null
    val long = max(decoded.width, decoded.height)
    val bmp = if (long > 1280) {
        val f = 1280f / long
        Bitmap.createScaledBitmap(decoded, (decoded.width * f).toInt(), (decoded.height * f).toInt(), true)
    } else decoded
    val out = ByteArrayOutputStream()
    bmp.compress(Bitmap.CompressFormat.JPEG, 82, out)
    Picked(out.toByteArray(), bmp.asImageBitmap())
}.getOrNull()

/** What the assistant knows about the phone's bot: account, positions, the latest readings. */
fun describe(s: EngineState): String = buildString {
    fun f(v: Double) = String.format(Locale.US, "%.2f", v)
    when (s.marketOpen) {
        true -> append("US market: open\n")
        false -> append("US market: closed\n")
        null -> {}
    }
    s.account?.let { a ->
        append("Account: equity $").append(f(a.equity)).append(", cash $").append(f(a.cash))
            .append(", today ").append(f(a.equity - a.lastEquity)).append(" USD\n")
    }
    if (s.held.isEmpty()) append("Positions: none\n") else {
        append("Positions:\n")
        s.held.forEach { h ->
            val p = h.position
            append("- ").append(p.symbol).append(": ").append(p.qty).append(" @ ").append(f(p.avgEntry))
                .append(", now ").append(f(p.currentPrice)).append(", P/L ").append(f(p.unrealizedPl))
            h.stop?.let { append(", stop ").append(f(it)) }
            h.target?.let { append(", target ").append(f(it)) }
            append(if (h.managed) " (bot)" else " (bought by hand)").append('\n')
        }
    }
    val ready = s.snapshots.filter { it.ready && !it.price.isNaN() }.take(12)
    if (ready.isNotEmpty()) {
        append("Watchlist readings (15-minute chart):\n")
        ready.forEach { r ->
            append("- ").append(r.symbol).append(" $").append(f(r.price))
            if (!r.rsi.isNaN()) append(", RSI ").append(r.rsi.toInt())
            append(if (r.trendUp) ", trend up" else ", trend down").append('\n')
        }
    }
    s.notes.take(4).forEach { append("Bot note on ").append(it.symbol).append(": ").append(it.text.take(200)).append('\n') }
    if (isEmpty()) append("The bot has not looked at the market yet.")
}
