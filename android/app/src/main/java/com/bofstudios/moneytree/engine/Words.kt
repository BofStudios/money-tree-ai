package com.bofstudios.moneytree.engine

import java.text.NumberFormat
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale

/**
 * Everything the engine says in the monitor, in English and Turkish.
 *
 * Kept next to the engine rather than in Android resources so the engine stays
 * testable off-device, and so both languages are reviewed side by side.
 */
class Words(val tr: Boolean) {
    private val locale = if (tr) Locale.forLanguageTag("tr-TR") else Locale.US
    private val money = NumberFormat.getCurrencyInstance(Locale.US)
    private val ny = ZoneId.of("America/New_York")
    private val hm = DateTimeFormatter.ofPattern("EEE HH:mm", locale)

    fun usd(v: Double): String = money.format(v)
    fun signed(v: Double): String = (if (v > 0) "+" else if (v < 0) "−" else "") + money.format(kotlin.math.abs(v))
    fun nyTime(epoch: Long): String = hm.format(Instant.ofEpochMilli(epoch).atZone(ny)) + " NY"
    private fun n(v: Double, digits: Int = 2) = String.format(locale, "%.${digits}f", v)

    // -------------------------------------------------------------- the loop
    fun checkingClock() = if (tr) "Piyasa saatini kontrol ediyor" else "Checking the market clock"
    fun marketOpen(close: Long) = if (tr) "Açık · kapanış ${nyTime(close)}" else "Open · closes ${nyTime(close)}"
    fun marketClosed(open: Long) = if (tr) "Kapalı · açılış ${nyTime(open)}" else "Closed · opens ${nyTime(open)}"
    fun waitingForOpen(open: Long) =
        if (tr) "Piyasa kapalı, açılışı bekliyorum (${nyTime(open)})"
        else "Market is closed — waiting for the open (${nyTime(open)})"

    fun readingAccount() = if (tr) "Hesabı okuyor" else "Reading your account"
    fun accountSummary(a: Account) =
        if (tr) "Varlık ${usd(a.equity)} · nakit ${usd(a.cash)} · bugün ${signed(a.equity - a.lastEquity)}"
        else "Equity ${usd(a.equity)} · cash ${usd(a.cash)} · today ${signed(a.equity - a.lastEquity)}"
    fun accountBlocked() = if (tr) "Alpaca bu hesapta işlemi durdurmuş" else "Alpaca has blocked trading on this account"

    fun checkingPositions() = if (tr) "Pozisyonları ve açık emirleri kontrol ediyor" else "Checking positions and open orders"
    fun positionsSummary(held: Int, orders: Int) =
        if (tr) "$held pozisyon · $orders açık emir" else "$held positions · $orders open orders"

    fun fetchingBars(count: Int, tf: Timeframe) =
        if (tr) "$count hisse için ${tfName(tf)} mum çekiyor" else "Fetching ${tfName(tf)} bars for $count stocks"
    fun barsSummary(ok: Int, total: Int) = if (tr) "$ok/$total hisse hazır" else "$ok of $total ready"

    fun analysing(count: Int) = if (tr) "$count hisseyi analiz ediyor" else "Analysing $count stocks"
    fun analysisLine(s: Snapshot, signal: Signal): String {
        if (!s.ready) return if (tr) "${s.symbol} — veri yetersiz (${s.bars} bar)" else "${s.symbol} — not enough data (${s.bars} bars)"
        val trend = if (s.trendUp) (if (tr) "yükselişte" else "trend up") else (if (tr) "düşüşte" else "trend down")
        return "${s.symbol} ${usd(s.price)} · $trend · RSI ${n(s.rsi, 0)} · ${signalName(signal)}"
    }
    fun analysisSummary(buys: Int, sells: Int) = when {
        buys == 0 && sells == 0 -> if (tr) "İşlem sinyali yok" else "No trade signals"
        tr -> "$buys alım, $sells satış sinyali"
        else -> "$buys buy, $sells sell signal(s)"
    }

    fun readingNews(symbol: String) = if (tr) "$symbol haberlerini okuyor" else "Reading news for $symbol"
    fun newsSummary(count: Int) = if (tr) "$count başlık" else "$count headline(s)"

    fun placingBracket(e: Entry) =
        if (tr) "Emir gönderiyor: ${e.qtyText} ${e.symbol} al · stop ${usd(e.stop)} · hedef ${usd(e.target)}"
        else "Placing order: buy ${e.qtyText} ${e.symbol} · stop ${usd(e.stop)} · target ${usd(e.target)}"
    fun orderAccepted(status: String) =
        if (tr) "Alpaca kabul etti ($status). Stop ve hedef Alpaca'da duruyor."
        else "Accepted by Alpaca ($status). The stop and target are held at Alpaca."

    fun placingFractional(e: Entry) =
        if (tr) "Kesirli emir: ${e.qtyText} ${e.symbol} al (~${usd(e.notional)}) · stop ${usd(e.stop)} telefonda"
        else "Fractional order: buy ${e.qtyText} ${e.symbol} (~${usd(e.notional)}) · stop ${usd(e.stop)} on this phone"
    fun fractionalAccepted(status: String) =
        if (tr) "Alpaca kabul etti ($status). Stop ve hedefi bu telefon izliyor."
        else "Accepted by Alpaca ($status). This phone is watching the stop and target."
    fun phoneStopHit(stop: Double) = if (tr) "stop-loss ${usd(stop)} geçildi" else "stop-loss ${usd(stop)} reached"
    fun phoneTargetHit(target: Double) = if (tr) "hedef ${usd(target)} geldi" else "target ${usd(target)} reached"
    fun heldOnPhone() = if (tr) "Bu telefonda tutuluyor" else "Held on this phone"

    fun raisingStop(symbol: String, from: Double?, to: Double) =
        if (tr) "$symbol stop'unu yükseltiyor: ${from?.let { usd(it) } ?: "—"} → ${usd(to)}"
        else "Raising $symbol stop: ${from?.let { usd(it) } ?: "—"} → ${usd(to)}"

    fun selling(symbol: String, reason: String) = if (tr) "$symbol satılıyor — $reason" else "Selling $symbol — $reason"
    fun sold() = if (tr) "Satış emri gönderildi" else "Sell order sent"

    fun closedAtBroker(t: TradeRecord) =
        if (tr) "${t.symbol} kapandı (${reasonName(t.reason)}) · ${signed(t.pnl)}"
        else "${t.symbol} closed (${reasonName(t.reason)}) · ${signed(t.pnl)}"
    fun closedDetail(t: TradeRecord) =
        if (tr) "${formatQty(t.qty)} adet · giriş ${usd(t.entry)} · çıkış ${usd(t.exit)}"
        else "${formatQty(t.qty)} shares · in ${usd(t.entry)} · out ${usd(t.exit)}"

    // --------------------------------------------------------- notifications
    fun justBoughtTitle(e: Entry) =
        if (tr) "Az önce aldım: ${e.qtyText} ${e.symbol}" else "Just bought ${e.qtyText} ${e.symbol}"
    fun justBoughtText(e: Entry) =
        if (tr) "Tanesi ${usd(e.price)} · toplam ${usd(e.notional)} · stop ${usd(e.stop)} · hedef ${usd(e.target)}\n${e.reason}"
        else "${usd(e.price)} each · ${usd(e.notional)} total · stop ${usd(e.stop)} · target ${usd(e.target)}\n${e.reason}"

    fun justSoldTitle(t: TradeRecord): String {
        val pct = n(kotlin.math.abs(t.pnlPct), 1)
        return when {
            t.pnl > 0.005 -> if (tr) "Az önce sattım: ${t.symbol} · ${signed(t.pnl)} kâr (%$pct)" else "Just sold ${t.symbol} · ${signed(t.pnl)} profit (+$pct%)"
            t.pnl < -0.005 -> if (tr) "Az önce sattım: ${t.symbol} · ${signed(t.pnl)} zarar (−%$pct)" else "Just sold ${t.symbol} · ${signed(t.pnl)} loss (−$pct%)"
            else -> if (tr) "Az önce sattım: ${t.symbol} · başabaş" else "Just sold ${t.symbol} · break-even"
        }
    }
    fun justSoldText(t: TradeRecord) =
        if (tr) "${formatQty(t.qty)} adet · giriş ${usd(t.entry)} → çıkış ${usd(t.exit)} · ${reasonName(t.reason)}"
        else "${formatQty(t.qty)} shares · in ${usd(t.entry)} → out ${usd(t.exit)} · ${reasonName(t.reason)}"

    fun researchingTitle(symbol: String) = if (tr) "$symbol araştırılıyor" else "Researching $symbol"
    fun stopRaisedTitle(symbol: String, to: Double) =
        if (tr) "$symbol stop'u yükseltildi: ${usd(to)}" else "Raised $symbol stop to ${usd(to)}"
    fun stopRaisedText(from: Double?, lockedIn: Double?) = buildString {
        from?.let { append(if (tr) "Önceki ${usd(it)}. " else "Was ${usd(it)}. ") }
        lockedIn?.let { append(if (tr) "Dönerse en az ${signed(it)} kârla çıkar." else "Locks in ${signed(it)} if it turns.") }
    }.trim()

    fun restartedDisarmedTitle() =
        if (tr) "Money Tree yeniden başladı — gerçek para beklemede" else "Money Tree restarted — real money is paused"
    fun restartedDisarmedText() =
        if (tr) "Telefon ya da Android uygulamayı yeniden başlattı. Tekrar alım yapabilmesi için uygulamayı aç ve Devreye al'a bas. Stop'lar yerinde duruyor."
        else "The phone or Android restarted it. Open the app and tap Arm so it can buy again. Stops stay in place."
    fun stoppedTitle() = if (tr) "Money Tree durdu" else "Money Tree stopped"
    fun stoppedText() =
        if (tr) "Android arka planda yeniden başlatmasına izin vermedi. Başlatmak için dokun."
        else "Android would not let it restart in the background. Tap to start it again."

    fun askingAi() = if (tr) "AI'a kararı açıklatıyor" else "Asking the AI to explain the decision"

    fun waitingApproval(e: Entry) =
        if (tr) "Onayını bekliyor: ${e.qtyText} ${e.symbol} al, yaklaşık ${usd(e.price)}"
        else "Waiting for your OK: buy ${e.qtyText} ${e.symbol} at about ${usd(e.price)}"
    fun suggestion(e: Entry) =
        if (tr) "Fikir (manuel mod, işlem açılmadı): ${e.qtyText} ${e.symbol}, yaklaşık ${usd(e.price)}"
        else "Idea (manual mode, not placed): ${e.qtyText} ${e.symbol} at about ${usd(e.price)}"
    fun approvalExpired(symbol: String) = if (tr) "$symbol onay isteğinin süresi doldu" else "$symbol approval request lapsed"

    fun tooSmall(symbol: String, fractional: Boolean = false) = when {
        fractional && tr -> "$symbol: tutar Alpaca'nın 1$ alt sınırının altında kalırdı, atlanıyor"
        fractional -> "$symbol: the order would be under Alpaca's \$1 minimum — skipping"
        tr -> "$symbol: pozisyon 1 hisseden küçük olurdu, atlanıyor"
        else -> "$symbol: the position would be under one share — skipping"
    }

    // --------------------------------------------------------------- research
    fun researchLine(s: Snapshot, e: Entry) =
        if (tr) "Alım sinyali · ${usd(s.price)} · RSI ${n(s.rsi, 0)} · ~${usd(e.notional)} · haberleri okuyorum"
        else "Buy signal · ${usd(s.price)} · RSI ${n(s.rsi, 0)} · ~${usd(e.notional)} · reading the news"
    fun aiCheckingNews(symbol: String) =
        if (tr) "AI $symbol haberlerinde kırmızı bayrak arıyor" else "AI checking $symbol news for red flags"
    fun aiVerdict(v: Vet) = (if (v.ok) (if (tr) "Sorun yok" else "No red flags") else (if (tr) "Vazgeç" else "Pass")) +
        (if (v.note.isNotBlank()) " — ${v.note}" else "")
    fun aiResting(symbol: String) =
        if (tr) "$symbol: AI az önce geçti, bir saat dokunulmayacak" else "$symbol: the AI passed on it earlier — leaving it for an hour"
    fun orderFailedTitle(symbol: String) = if (tr) "$symbol alınamadı" else "Could not buy $symbol"
    fun aiSkipped(symbol: String) = if (tr) "$symbol alınmadı — AI haberlerde sorun gördü" else "Skipped $symbol — the AI flagged the news"

    // ------------------------------------------------------- fractional stops
    fun placingDayStop(symbol: String, stop: Double) =
        if (tr) "$symbol için bugünün stop emrini Alpaca'ya koyuyor: ${usd(stop)}"
        else "Placing today's $symbol stop at Alpaca: ${usd(stop)}"
    fun dayStopPlaced() =
        if (tr) "Kapanışa kadar Alpaca'da duruyor" else "Held at Alpaca until the close"

    // ---------------------------------------------------------- daily summary
    fun dailySummaryTitle(trades: Int, change: Double) =
        if (tr) "Bugün: $trades işlem · ${signed(change)}" else "Today: $trades trade(s) · ${signed(change)}"
    fun dailySummaryDetail(trades: List<TradeRecord>, equity: Double): String {
        val won = trades.count { it.pnl > 0 }
        val lost = trades.count { it.pnl < 0 }
        return if (tr) "Hesap ${usd(equity)} · $won kazanç, $lost kayıp" else "Account ${usd(equity)} · $won won, $lost lost"
    }
    fun notArmed(symbol: String) =
        if (tr) "$symbol: gerçek para devrede değil (Arm), alım yok"
        else "$symbol: live trading is not armed — not buying"
    fun capReached(symbol: String, cap: Int) =
        if (tr) "$symbol: en fazla $cap pozisyon sınırı dolu" else "$symbol: the $cap-position cap is full"
    fun cooling(symbol: String) =
        if (tr) "$symbol: yakın zamanda kapandı, bekleme süresinde" else "$symbol: closed recently, cooling down"
    fun dailyHalt(loss: Double, limit: Double) =
        if (tr) "Günlük zarar sınırı doldu (${signed(loss)}, sınır ${usd(limit)}). Bugün yeni alım yok."
        else "Daily loss limit reached (${signed(loss)}, limit ${usd(limit)}). No new buys today."

    fun closedReviewOnly() =
        if (tr) "Piyasa kapalı — grafikleri inceliyorum, açılışa kadar alım satım yok"
        else "Market closed — reviewing the charts; nothing is bought or sold until the open"
    fun notTradingNow() = if (tr) "piyasa kapalı, işlem yok" else "market closed, not trading"

    fun scanDone(held: Int, next: Int) =
        if (tr) "Tarama bitti · $held pozisyon · $next sn sonra tekrar"
        else "Scan complete · holding $held · next look in ${next}s"
    fun cycleFailed() = if (tr) "Bu turda bir sorun çıktı, yeniden deneyecek" else "Something failed this round — will retry"

    fun started(settings: TradingSettings) = if (tr) {
        "Başladı · ${if (settings.live) "GERÇEK para" else "paper (deneme) para"} · ${autonomyName(settings.autonomy)} · ${tfName(settings.horizon.timeframe)}"
    } else {
        "Started · ${if (settings.live) "REAL money" else "paper money"} · ${autonomyName(settings.autonomy)} · ${tfName(settings.horizon.timeframe)}"
    }

    // ------------------------------------------------------------- approvals
    fun approveFailedExpired() = if (tr) "Bu isteğin süresi doldu ya da zaten cevaplandı." else "That request expired or was already answered."
    fun approveMarketClosed() = if (tr) "piyasa kapalı" else "the market is closed"
    fun approveNotArmed() = if (tr) "gerçek para devrede değil" else "live trading is not armed"
    fun approveDrift(pct: Double) =
        if (tr) "fiyat sorduğumdan beri %${n(pct, 1)} oynadı (sınır %${n(MAX_DRIFT_PCT, 1)})"
        else "the price moved ${n(pct, 1)}% since I asked (limit ${n(MAX_DRIFT_PCT, 1)}%)"
    fun approveThroughStop() = if (tr) "fiyat zaten stop'un altında" else "the price is already through the stop"
    fun approveAtTarget() = if (tr) "fiyat zaten hedefe ulaştı" else "the price already reached the target"
    fun approveNoPrice() = if (tr) "güncel fiyat alınamadı" else "no current price"
    fun approveHeld(symbol: String) = if (tr) "$symbol zaten elimde" else "I already hold $symbol"
    fun approveCap(cap: Int) = if (tr) "$cap pozisyon sınırı dolu" else "the $cap-position cap is full"
    fun didNotBuy(symbol: String, why: String) = if (tr) "$symbol alınmadı: $why." else "Did not buy $symbol: $why."
    fun bought(e: Entry) = if (tr) "${e.qtyText} ${e.symbol} alındı, stop ${usd(e.stop)}." else "Bought ${e.qtyText} ${e.symbol}, stop ${usd(e.stop)}."

    // ----------------------------------------------------------------- names
    fun tfName(tf: Timeframe) = when (tf) {
        Timeframe.M15 -> if (tr) "15 dakikalık" else "15-minute"
        Timeframe.H1 -> if (tr) "1 saatlik" else "1-hour"
        Timeframe.D1 -> if (tr) "günlük" else "daily"
    }
    fun autonomyName(a: Autonomy) = when (a) {
        Autonomy.FULL -> if (tr) "Tam otomatik" else "Full auto"
        Autonomy.SEMI -> if (tr) "Yarı otomatik" else "Semi-auto"
        Autonomy.MANUAL -> if (tr) "Manuel" else "Manual"
    }
    private fun signalName(s: Signal) = when (s.action) {
        Action.BUY -> if (tr) "ALIM sinyali" else "BUY signal"
        Action.CLOSE -> if (tr) "SATIŞ sinyali" else "SELL signal"
        Action.HOLD -> if (tr) "bekle" else "hold"
    }
    fun reasonName(reason: String) = when (reason) {
        "stop-loss" -> if (tr) "stop-loss" else "stop-loss"
        "take-profit" -> if (tr) "hedef" else "target"
        "signal" -> if (tr) "sinyal" else "signal"
        else -> if (tr) "kapandı" else "closed"
    }

    companion object {
        const val MAX_DRIFT_PCT = 1.5
    }
}
