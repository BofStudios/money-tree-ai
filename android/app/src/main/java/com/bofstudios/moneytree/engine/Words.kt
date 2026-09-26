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
        if (tr) "Emir gönderiyor: ${e.qty} ${e.symbol} al · stop ${usd(e.stop)} · hedef ${usd(e.target)}"
        else "Placing order: buy ${e.qty} ${e.symbol} · stop ${usd(e.stop)} · target ${usd(e.target)}"
    fun orderAccepted(status: String) =
        if (tr) "Alpaca kabul etti ($status). Stop ve hedef Alpaca'da duruyor."
        else "Accepted by Alpaca ($status). The stop and target are held at Alpaca."

    fun raisingStop(symbol: String, from: Double?, to: Double) =
        if (tr) "$symbol stop'unu yükseltiyor: ${from?.let { usd(it) } ?: "—"} → ${usd(to)}"
        else "Raising $symbol stop: ${from?.let { usd(it) } ?: "—"} → ${usd(to)}"

    fun selling(symbol: String, reason: String) = if (tr) "$symbol satılıyor — $reason" else "Selling $symbol — $reason"
    fun sold() = if (tr) "Satış emri gönderildi" else "Sell order sent"

    fun closedAtBroker(t: TradeRecord) =
        if (tr) "${t.symbol} kapandı (${reasonName(t.reason)}) · ${signed(t.pnl)}"
        else "${t.symbol} closed (${reasonName(t.reason)}) · ${signed(t.pnl)}"
    fun closedDetail(t: TradeRecord) =
        if (tr) "${n(t.qty, 0)} adet · giriş ${usd(t.entry)} · çıkış ${usd(t.exit)}"
        else "${n(t.qty, 0)} shares · in ${usd(t.entry)} · out ${usd(t.exit)}"

    fun askingAi() = if (tr) "AI'a kararı açıklatıyor" else "Asking the AI to explain the decision"

    fun waitingApproval(e: Entry) =
        if (tr) "Onayını bekliyor: ${e.qty} ${e.symbol} al, yaklaşık ${usd(e.price)}"
        else "Waiting for your OK: buy ${e.qty} ${e.symbol} at about ${usd(e.price)}"
    fun suggestion(e: Entry) =
        if (tr) "Fikir (manuel mod, işlem açılmadı): ${e.qty} ${e.symbol}, yaklaşık ${usd(e.price)}"
        else "Idea (manual mode, not placed): ${e.qty} ${e.symbol} at about ${usd(e.price)}"
    fun approvalExpired(symbol: String) = if (tr) "$symbol onay isteğinin süresi doldu" else "$symbol approval request lapsed"

    fun tooSmall(symbol: String) =
        if (tr) "$symbol: pozisyon 1 hisseden küçük olurdu, atlanıyor"
        else "$symbol: the position would be under one share — skipping"
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
    fun bought(e: Entry) = if (tr) "${e.qty} ${e.symbol} alındı, stop ${usd(e.stop)}." else "Bought ${e.qty} ${e.symbol}, stop ${usd(e.stop)}."

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
