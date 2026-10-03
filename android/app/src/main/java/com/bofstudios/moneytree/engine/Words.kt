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
    fun stoppedNoBuy(symbol: String) =
        if (tr) "$symbol alınmadı — bot durduruldu" else "Did not buy $symbol — the bot was stopped"
    fun cancelledOnStop(n: Int) =
        if (tr) "Durduruldu · dolmamış $n alım emri Alpaca'da iptal edildi" else "Stopped · withdrew $n unfilled buy order(s) at Alpaca"
    fun approveStopped() = if (tr) "bot durduruldu" else "the bot is stopped"
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

    // ----------------------------------------------------------------- brain
    fun readingFilings(count: Int) =
        if (tr) "$count şirketin yıllık raporlarını okuyor (SEC)" else "Reading annual reports for $count companies (SEC)"
    fun filingsMissing(symbol: String) = if (tr) "$symbol — SEC'te rapor bulunamadı" else "$symbol — no SEC filings found"
    fun filingsLine(f: Filings): String {
        if (f.fund) return if (tr) "${f.symbol} — fon (ETF): şirket raporu yok, fon gibi değerlendirilecek" else "${f.symbol} — a fund (ETF): judged as a fund"
        val y = f.years.lastOrNull()
        val rev = y?.revenue?.let { big(it) + " " + f.currency } ?: "—"
        val ni = y?.netIncome?.let { big(it) + " " + f.currency } ?: "—"
        return if (tr) "${f.symbol} · ${f.name} · ${f.years.size} yıl · ciro $rev · net kâr $ni"
        else "${f.symbol} · ${f.name} · ${f.years.size} years · revenue $rev · net income $ni"
    }
    fun filingsSummary(ok: Int, total: Int) = if (tr) "$ok/$total şirket okundu" else "$ok of $total read"
    fun aiReadingBusiness(name: String) = if (tr) "AI $name işini okuyor" else "AI reading $name's business"
    fun fetchingDaily(count: Int) = if (tr) "$count hisse için günlük grafik çekiyor" else "Fetching daily charts for $count stocks"
    fun dailyChartsSummary(ok: Int, total: Int) = if (tr) "$ok/$total günlük grafik hazır" else "$ok of $total daily charts ready"
    fun readingFx(currencies: Set<String>) =
        if (tr) "Döviz kurlarını okuyor (${currencies.joinToString()})" else "Reading exchange rates (${currencies.joinToString()})"
    fun fxSummary(rates: Map<String, Double>) =
        rates.entries.joinToString(" · ") { "1 ${it.key} = ${String.format(Locale.US, "%.4f", it.value)} USD" }.ifEmpty { "—" }
    fun newsWireFailed() = if (tr) "Haber akışı okunamadı, sonra tekrar" else "Could not read the news wire — will retry"
    fun newsWire(added: Int, total: Int) =
        if (tr) "Haber akışı · $added yeni başlık (toplam $total)" else "News wire · $added new headline(s) ($total kept)"
    fun aiReadingHeadlines(count: Int) = if (tr) "AI $count başlığı okuyup puanlıyor" else "AI reading and scoring $count headlines"
    fun aiScored(count: Int) = if (tr) "$count başlık puanlandı" else "$count scored"
    fun aiLesson(symbol: String) = if (tr) "AI $symbol işleminden ders çıkarıyor" else "AI drawing the lesson from the $symbol trade"
    fun lessonTitle(symbol: String) = if (tr) "$symbol işleminden ders" else "Lesson from the $symbol trade"

    /** One line for a research step: where the signal stands after all four gates. */
    fun researchTitle(r: Research): String {
        val size = if (r.size < 0.999) (if (tr) " · boyut %${(r.size * 100).toInt()}" else " · size ${(r.size * 100).toInt()}%") else ""
        return if (r.ok) (if (tr) "Araştırma · ${r.symbol} → geçti$size" else "Research · ${r.symbol} → cleared$size")
        else (if (tr) "Araştırma · ${r.symbol} → bekletildi" else "Research · ${r.symbol} → held back")
    }
    fun researchDetail(r: Research): String = r.report?.let { q ->
        decisionName(q.decision) + " · " + String.format(Locale.US, "%.1f/5", q.score) + (q.priceToValue?.let { pv -> " · " + priceVsValue(pv) } ?: "")
    } ?: (if (tr) "Rapor yok — sadece grafik ve haber" else "No report — charts and news only")

    fun researchLines(r: Research): List<String> {
        val mark = { ok: Boolean -> if (ok) "✓" else "✕" }
        val out = ArrayList<String>()
        r.report?.let { q ->
            out += "${mark(r.qualityOk)} " + (if (tr) "5 kontrol: " else "5 checks: ") +
                q.checks.joinToString("  ") { c -> checkShort(c.kind) + " " + verdictMark(c.verdict) }
        }
        out += "${mark(r.trendOk)} " + when (r.dailyUp) {
            true -> if (tr) "Günlük grafik yükselişte (50 günlük ortalamanın üstünde)" else "Daily chart rising (above its 50-day average)"
            false -> if (tr) "Günlük grafik düşüşte (50 günlük ortalamanın altında)" else "Daily chart falling (below its 50-day average)"
            null -> if (tr) "Günlük grafik henüz yok" else "No daily chart yet"
        }
        out += "${mark(r.newsOk)} " + (if (tr) "Haber: " else "News: ") + (r.mood?.let { moodName(it) + " (${it.moodText()})" } ?: (if (tr) "haber yok" else "no news")) +
            " · ${r.newsCount}" + (if (tr) "/24sa" else "/24h") +
            (if (r.flags.isEmpty()) (if (tr) " · kırmızı bayrak yok" else " · no red flags") else " · " + r.flags.joinToString { flagName(it.kind) })
        out += "${mark(r.learnedOk)} " + learnedLine(r.learned)
        return out
    }

    fun learnedLine(v: LearnedVerdict): String {
        val b = v.evidence.firstOrNull()
        if (v.edge == null || b == null) return if (tr) "Öğrendiklerim: bu tür sinyal için henüz yeterli sonuç yok" else "Learned: not enough results for signals like this yet"
        val n = v.evidence.maxOf { it.n }.toInt()
        return if (tr) "Öğrendiklerim: benzer $n sinyal · beklenen ${rText(v.edge)} · en zayıf: ${bucketName(b.bucket)} (${rText(b.shrunk)})"
        else "Learned: $n similar signals · expected ${rText(v.edge)} · weakest: ${bucketName(b.bucket)} (${rText(b.shrunk)})"
    }

    fun heldBack(symbol: String) = if (tr) "$symbol alınmadı" else "Held back on $symbol"
    fun heldBackWhy(r: Research): String = when {
        !r.qualityOk -> r.report?.let { q ->
            if (q.decision == Decision.AVOID) (if (tr) "5 kontrol ${decisionName(q.decision)} diyor (${weakest(q)})" else "the five checks say ${decisionName(q.decision)} (${weakest(q)})")
            else (if (tr) "katı modda sadece ALIM BÖLGESİ alınır, bu ${decisionName(q.decision)}" else "strict mode buys only the BUY ZONE; this is ${decisionName(q.decision)}")
        } ?: (if (tr) "katı modda raporu olmayan hisse alınmaz" else "strict mode needs a report first")
        !r.trendOk -> if (tr) "günlük grafik düşüşte — büyük resim aşağı" else "the daily chart is falling — the big picture points down"
        !r.newsOk -> r.flags.firstOrNull { it.kind.blocksBuys }?.let { flagName(it.kind) + ": \"" + it.headline.take(80) + "\"" }
            ?: (if (tr) "haberler kötü (${r.mood?.moodText()})" else "the news is bad (${r.mood?.moodText()})")
        else -> r.learned.evidence.firstOrNull()?.let { ruleText(it) } ?: (if (tr) "geçmiş sonuçlar zayıf" else "past results are poor")
    }

    private fun weakest(q: QualityReport): String =
        q.checks.filter { it.verdict == Verdict.FAIL }.joinToString { checkName(it.kind) }.ifEmpty { String.format(Locale.US, "%.1f/5", q.score) }

    fun shadowTitle(opened: Int, closed: Int) = when {
        opened > 0 && closed > 0 -> if (tr) "Kafamda takip: $opened yeni sinyal, $closed sonuç" else "Tracking in my head: $opened new signal(s), $closed result(s)"
        opened > 0 -> if (tr) "Kafamda takip: $opened yeni sinyal (alsam da almasam da sonucunu izliyorum)" else "Tracking in my head: $opened new signal(s) — I follow the result whether I buy or not"
        else -> if (tr) "Kafamdaki işlemlerden $closed sonuç geldi" else "$closed tracked signal(s) finished"
    }
    fun shadowOpened(t: ShadowTrade) = "${t.symbol} ${usd(t.entry)} · stop ${usd(t.stop)} · " + (if (tr) "hedef " else "target ") + usd(t.target)
    fun shadowClosed(t: ShadowTrade) = "${t.symbol} · ${reasonName(t.exit ?: "")} · ${rText(t.r ?: 0.0)}"

    fun learnedTitle() = if (tr) "Yeni bir şey öğrendim" else "I learned something"
    fun ruleText(b: BucketStats): String {
        val n = b.n.toInt()
        val won = (b.winRate * 100).toInt()
        return if (tr) "${bucketName(b.bucket)}: $n sonuç · %$won kazandı · ortalama ${rText(b.avgR)}. Bunları artık almıyorum."
        else "${bucketName(b.bucket)}: $n results · $won% won · avg ${rText(b.avgR)}. I skip these now."
    }
    fun lessonText(b: BucketStats): String {
        val n = b.n.toInt()
        val won = (b.winRate * 100).toInt()
        return if (tr) "$n sonuç · %$won kazandı · ortalama ${rText(b.avgR)}" else "$n results · $won% won · avg ${rText(b.avgR)}"
    }

    /** "+0.42R" — one R is what the stop risks. */
    fun rText(r: Double) = String.format(Locale.US, "%+.2fR", r)

    fun priceVsValue(pv: Double): String {
        val pct = ((pv - 1) * 100).toInt()
        return when {
            pct > 0 -> if (tr) "değer tahminimin %$pct üstünde" else "$pct% above my value estimate"
            pct < 0 -> if (tr) "değer tahminimin %${-pct} altında" else "${-pct}% below my value estimate"
            else -> if (tr) "değer tahminime eşit" else "right at my value estimate"
        }
    }

    fun moodName(m: Double) = when {
        m >= 0.35 -> if (tr) "çok olumlu" else "very positive"
        m >= NewsRadar.GOOD_MOOD -> if (tr) "olumlu" else "positive"
        m > -NewsRadar.GOOD_MOOD -> if (tr) "karışık" else "mixed"
        m > NewsRadar.BAD_MOOD -> if (tr) "olumsuz" else "negative"
        else -> if (tr) "çok olumsuz" else "very negative"
    }

    fun decisionName(d: Decision) = when (d) {
        Decision.BUY_ZONE -> if (tr) "ALIM BÖLGESİ" else "BUY ZONE"
        Decision.WAIT -> if (tr) "BEKLE" else "WAIT"
        Decision.AVOID -> if (tr) "UZAK DUR" else "AVOID"
        Decision.UNKNOWN -> if (tr) "VERİ YOK" else "NO DATA"
    }
    fun decisionLine(d: Decision) = when (d) {
        Decision.BUY_ZONE -> if (tr) "İyi bir işletme, makul bir fiyat." else "A good business at a fair price."
        Decision.WAIT -> if (tr) "Fiyat doğru değilse bekler." else "If the price is wrong, it waits."
        Decision.AVOID -> if (tr) "Kontrollerden geçmedi." else "It failed the checks."
        Decision.UNKNOWN -> if (tr) "Raporlar henüz okunmadı." else "The reports are not read yet."
    }
    fun checkName(k: CheckKind) = when (k) {
        CheckKind.BUSINESS -> if (tr) "İŞLETME" else "BUSINESS"
        CheckKind.MOAT -> if (tr) "KALE" else "MOAT"
        CheckKind.MANAGEMENT -> if (tr) "YÖNETİM" else "MANAGEMENT"
        CheckKind.VALUE -> if (tr) "DEĞER" else "VALUE"
        CheckKind.RISK -> "RISK"
    }
    fun checkShort(k: CheckKind) = when (k) {
        CheckKind.BUSINESS -> if (tr) "İŞL" else "BUS"
        CheckKind.MOAT -> if (tr) "KALE" else "MOAT"
        CheckKind.MANAGEMENT -> if (tr) "YÖN" else "MGMT"
        CheckKind.VALUE -> if (tr) "DEĞ" else "VAL"
        CheckKind.RISK -> "RISK"
    }
    fun checkQuestion(k: CheckKind) = when (k) {
        CheckKind.BUSINESS -> if (tr) "İşletme düzenli para kazanıyor mu?" else "Does the business reliably make money?"
        CheckKind.MOAT -> if (tr) "Rakipler bunu kopyalayabilir mi?" else "Can competitors copy it?"
        CheckKind.MANAGEMENT -> if (tr) "Yönetim değer yaratıyor mu?" else "Does management create value?"
        CheckKind.VALUE -> if (tr) "Fiyat değerin altında mı?" else "Is the price below the value?"
        CheckKind.RISK -> if (tr) "Ne ters gidebilir?" else "What could go wrong?"
    }
    fun verdictMark(v: Verdict) = when (v) { Verdict.PASS -> "✓"; Verdict.WATCH -> "~"; Verdict.FAIL -> "✕"; Verdict.UNKNOWN -> "?" }
    fun verdictName(v: Verdict) = when (v) {
        Verdict.PASS -> if (tr) "geçti" else "pass"
        Verdict.WATCH -> if (tr) "dikkat" else "watch"
        Verdict.FAIL -> if (tr) "kaldı" else "fail"
        Verdict.UNKNOWN -> if (tr) "bilinmiyor" else "unknown"
    }

    /** One fact behind a check, as the owner reads it. */
    fun factText(f: Fact): String? {
        val pct = { v: Double -> String.format(Locale.US, "%.0f%%", v * 100).let { if (tr) "%" + it.dropLast(1) else it } }
        val pctSigned = { v: Double -> String.format(Locale.US, "%+.1f%%", v * 100).let { if (tr) it.first() + "%" + it.drop(1).dropLast(1) else it } }
        return when (f.metric) {
            Metric.PROFIT_YEARS -> if (tr) "${f.text} yıl kârlı" else "profitable ${f.text} years"
            Metric.REVENUE_GROWTH -> if (tr) "ciro yılda ${pctSigned(f.value)}" else "revenue ${pctSigned(f.value)} a year"
            Metric.GROSS_MARGIN -> if (tr) "brüt marj ${pct(f.value)}" else "gross margin ${pct(f.value)}"
            Metric.OPERATING_MARGIN -> if (tr) "faaliyet marjı ${pct(f.value)}" else "operating margin ${pct(f.value)}"
            Metric.RETURN_ON_EQUITY -> if (tr) "özsermaye kârlılığı ${pct(f.value)}" else "return on equity ${pct(f.value)}"
            Metric.SHARE_CHANGE -> if (f.value <= 0) (if (tr) "hisse sayısı yılda ${pctSigned(f.value)} (geri alım)" else "share count ${pctSigned(f.value)} a year (buybacks)")
                else (if (tr) "hisse sayısı yılda ${pctSigned(f.value)} (sulanma)" else "share count ${pctSigned(f.value)} a year (dilution)")
            Metric.DEBT_TO_PROFIT -> if (tr) "borç = ${n(f.value, 1)} yıllık kâr" else "debt = ${n(f.value, 1)} years of profit"
            Metric.INTEREST_COVER -> if (tr) "faiz ${n(f.value, 0)} kat karşılanıyor" else "interest covered ${n(f.value, 0)}x"
            Metric.PRICE -> if (tr) "fiyat ${usd(f.value)}" else "price ${usd(f.value)}"
            Metric.VALUE -> if (tr) "değer tahmini ${usd(f.value)}" else "value estimate ${usd(f.value)}"
            Metric.PRICE_TO_VALUE -> priceVsValue(f.value)
            Metric.VS_200_DAY -> String.format(Locale.US, "%+.0f%%", (f.value - 1) * 100).let {
                if (tr) "200 günlük ortalamaya göre ${it.first()}%${it.drop(1).dropLast(1)}" else "$it vs its 200-day average"
            }
            Metric.DAILY_SWING -> if (tr) "günlük oynaklık ${pct(f.value)}" else "daily swing ${pct(f.value)}"
            Metric.RED_FLAG -> f.text?.let { runCatching { flagName(RedFlagKind.valueOf(it)) }.getOrNull() }
            Metric.FUND -> if (tr) "fon — tek bir şirket değil" else "a fund — not one company"
        }
    }

    fun flagName(k: RedFlagKind) = when (k) {
        RedFlagKind.HALT -> if (tr) "işlem durdurma" else "trading halt"
        RedFlagKind.BANKRUPTCY -> if (tr) "iflas" else "bankruptcy"
        RedFlagKind.FRAUD -> if (tr) "dolandırıcılık iddiası" else "fraud allegation"
        RedFlagKind.DELISTING -> if (tr) "borsadan çıkarılma" else "delisting"
        RedFlagKind.OFFERING -> if (tr) "yeni hisse satışı (sulanma)" else "share offering (dilution)"
        RedFlagKind.ACCOUNTING -> if (tr) "geçmiş mali tablolar güvenilmez (SEC)" else "past financials unreliable (SEC)"
        RedFlagKind.GUIDANCE_CUT -> if (tr) "beklenti düşürüldü" else "guidance cut"
        RedFlagKind.EARNINGS_SOON -> if (tr) "bilanço yaklaşıyor" else "earnings due soon"
        RedFlagKind.REGULATOR -> if (tr) "düzenleyici soruşturma" else "regulator probe"
        RedFlagKind.RECALL -> if (tr) "geri çağırma" else "recall"
    }

    fun topicName(t: Topic) = when (t) {
        Topic.EARNINGS -> if (tr) "Bilanço & beklenti" else "Earnings & guidance"
        Topic.AI_CHIPS -> if (tr) "AI & çipler" else "AI & chips"
        Topic.CLOUD -> if (tr) "Bulut & kurumsal" else "Cloud & enterprise"
        Topic.PRODUCT -> if (tr) "Ürün & lansman" else "Product & launches"
        Topic.ANALYSTS -> if (tr) "Analist notları" else "Analyst ratings"
        Topic.DEALS -> if (tr) "Anlaşmalar & satın alma" else "Deals & M&A"
        Topic.CAPITAL -> if (tr) "Temettü, geri alım, borç" else "Dividends, buybacks, debt"
        Topic.LEGAL -> if (tr) "Dava & hukuk" else "Legal & litigation"
        Topic.REGULATION -> if (tr) "Düzenleme & antitröst" else "Regulation & antitrust"
        Topic.SUPPLY -> if (tr) "Tedarik zinciri" else "Supply chain"
        Topic.MACRO -> if (tr) "Ekonomi & Fed" else "Macro & the Fed"
        Topic.LEADERSHIP -> if (tr) "Yönetim değişikliği" else "Leadership"
    }

    fun bucketName(b: Bucket): String = when (b.key) {
        FeatureKey.QUALITY -> (if (tr) "5 kontrol " else "Checks said ") +
            (runCatching { decisionName(Decision.valueOf(b.value)) }.getOrDefault(b.value))
        FeatureKey.NEWS -> when (b.value) {
            "BAD" -> if (tr) "Kötü haberle alım" else "Buys on bad news"
            "GOOD" -> if (tr) "İyi haberle alım" else "Buys on good news"
            "MIXED" -> if (tr) "Karışık haberle alım" else "Buys on mixed news"
            else -> if (tr) "Haber yokken alım" else "Buys with no news"
        }
        FeatureKey.RSI -> if (tr) "Girişte RSI ${b.value}" else "RSI ${b.value} at entry"
        FeatureKey.STRETCH -> when (b.value) {
            "NEAR" -> if (tr) "Ortalamaya yakın giriş" else "Entries close to the average"
            "EXTENDED" -> if (tr) "Ortalamadan uzaklaşmış giriş" else "Entries stretched from the average"
            else -> if (tr) "Çok uzaklaşmış giriş" else "Entries far above the average"
        }
        FeatureKey.SESSION -> when (b.value) {
            "OPEN" -> if (tr) "Açılışın ilk saati" else "The first hour after the open"
            "CLOSE" -> if (tr) "Kapanışın son saati" else "The last hour before the close"
            "MIDDAY" -> if (tr) "Gün ortası" else "Midday"
            else -> if (tr) "Günlük grafik" else "Daily chart"
        }
        FeatureKey.DAILY_TREND -> if (b.value == "UP") (if (tr) "Günlük trend yukarıyken" else "Daily trend up")
            else (if (tr) "Günlük trend aşağıyken" else "Daily trend down")
        FeatureKey.ATTENTION -> when (b.value) {
            "SPIKE" -> if (tr) "İlgi patlamasında alım (Wikipedia ×3+)" else "Buys during an attention spike (Wikipedia ×3+)"
            "HIGH" -> if (tr) "İlgi yüksekken alım" else "Buys while attention is high"
            else -> if (tr) "İlgi normalken alım" else "Buys at normal attention"
        }
        FeatureKey.SYMBOL -> b.value
    }

    fun qualityModeName(m: QualityMode) = when (m) {
        QualityMode.STRICT -> if (tr) "Katı (Buffett)" else "Strict (Buffett)"
        QualityMode.BALANCED -> if (tr) "Dengeli" else "Balanced"
        QualityMode.OFF -> if (tr) "Sadece grafik" else "Charts only"
    }

    /** 416_161_000_000 → "416.2bn" ("416.2 milyar"). */
    fun big(v: Double): String {
        val a = kotlin.math.abs(v)
        val (x, en, trWord) = when {
            a >= 1e12 -> Triple(v / 1e12, "tn", " trilyon")
            a >= 1e9 -> Triple(v / 1e9, "bn", " milyar")
            a >= 1e6 -> Triple(v / 1e6, "m", " milyon")
            else -> Triple(v, "", "")
        }
        val digits = if (a >= 1e12) 2 else if (a >= 1e9) 1 else 0
        return String.format(Locale.US, "%.${digits}f", x) + if (tr) trWord else en
    }

    // ------------------------------------------------------------ alt data
    fun readingEvents(count: Int) =
        if (tr) "$count şirketin SEC olay kayıtlarını okuyor (8-K, içeriden işlemler)" else "Reading SEC filing index for $count companies (8-Ks, insider filings)"
    fun eventsLine(symbol: String, e: CompanyEvents, now: Long): String {
        val last = e.events.firstOrNull { it.items.any { i -> i != "9.01" } }
        val event = last?.let { " · 8-K ${daysAgo(now - it.filedAt)}: ${eventItems(it.items)}" } ?: ""
        val next = e.nextResults()?.let { if (tr) " · sonraki bilanço ~${day(it)}" else " · next results ~${day(it)}" } ?: ""
        return "$symbol · " + (if (tr) "içeriden ${e.insiderFilings30d}/30g" else "insiders ${e.insiderFilings30d}/30d") + event + next
    }
    fun eventsSummary(ok: Int, total: Int) = if (tr) "$ok/$total şirket okundu" else "$ok of $total read"
    fun readingAttention(count: Int) = if (tr) "$count şirkete olan ilgiyi ölçüyor (Wikipedia)" else "Measuring attention on $count companies (Wikipedia)"
    fun attentionLine(symbol: String, ratio: Double, views: Int) =
        "$symbol · ×${String.format(Locale.US, "%.1f", ratio)} · " + (if (tr) "dün $views okunma" else "$views views yesterday")
    fun attentionSummary(ok: Int, total: Int) = if (tr) "$ok/$total ölçüldü" else "$ok of $total measured"
    fun attentionName(ratio: Double) = when {
        ratio >= 3.0 -> if (tr) "ilgi patlaması" else "attention spike"
        ratio >= 1.5 -> if (tr) "ilgi yüksek" else "attention high"
        ratio < 0.7 -> if (tr) "ilgi düşük" else "attention low"
        else -> if (tr) "ilgi normal" else "attention normal"
    }
    fun eventItems(items: List<String>): String = items.filter { it != "9.01" }.mapNotNull { eventItem(it) }.joinToString(", ").ifEmpty { "8-K" }
    private fun eventItem(code: String): String? = if (!tr) EightK.ITEMS[code] else when (code) {
        "1.01" -> "önemli anlaşma"; "1.02" -> "anlaşma sona erdi"; "1.03" -> "iflas"; "1.05" -> "siber saldırı"
        "2.01" -> "satın alma/satış tamamlandı"; "2.02" -> "bilanço (faaliyet sonuçları)"; "2.03" -> "yeni borç"
        "2.05" -> "yeniden yapılanma"; "2.06" -> "değer düşüklüğü"; "3.01" -> "borsadan çıkarma uyarısı"
        "3.02" -> "kayıtsız hisse satışı"; "3.03" -> "ortak hakları değişti"; "4.01" -> "denetçi değişti"
        "4.02" -> "geçmiş tablolar güvenilmez"; "5.01" -> "kontrol değişti"; "5.02" -> "yönetici değişikliği"
        "5.03" -> "esas sözleşme değişti"; "5.07" -> "hissedar oylaması"; "7.01" -> "kamuya açıklama"; "8.01" -> "diğer olaylar"
        else -> null
    }
    fun daysAgo(ms: Long): String {
        val d = (ms / 86_400_000L).toInt()
        return when {
            d <= 0 -> if (tr) "bugün" else "today"
            d == 1 -> if (tr) "dün" else "yesterday"
            else -> if (tr) "$d gün önce" else "$d days ago"
        }
    }
    fun day(epoch: Long): String = DateTimeFormatter.ofPattern("d MMM", locale).format(Instant.ofEpochMilli(epoch).atZone(ny))

    // ------------------------------------------------------------ evolution
    fun fetchingHistory(count: Int, days: Int, tf: Timeframe) =
        if (tr) "Kendini geliştirmek için $count hissenin $days günlük ${tfName(tf)} geçmişini çekiyor"
        else "Fetching $days days of ${tfName(tf)} history for $count stocks to train on"
    fun historySummary(series: Int, bars: Int) =
        if (tr) "$series hisse · ${String.format(locale, "%,d", bars)} mum — eğitim verisi hazır" else "$series stocks · ${String.format(Locale.US, "%,d", bars)} candles — training data ready"
    fun promotionTitle(p: Promotion) =
        if (p.rollback) (if (tr) "Strateji geri alındı (v${p.version})" else "Strategy rolled back (v${p.version})")
        else (if (tr) "Kendimi geliştirdim: strateji v${p.version}" else "I improved myself: strategy v${p.version}")
    fun promotionText(p: Promotion) = if (p.rollback) {
        if (tr) "Yeni veride eski ayarlar daha iyi gidiyordu; orijinal stratejiye döndüm. Görmediği veride ${rText(p.before)} → ${rText(p.after)} işlem başı."
        else "On the newest data the original was doing better, so I went back to it. Unseen data: ${rText(p.before)} → ${rText(p.after)} per trade."
    } else {
        if (tr) "${p.to.label}\nHiç eğitilmediği veride işlem başı ${rText(p.before)} → ${rText(p.after)} (${p.trades} işlem). Risk ayarların aynı."
        else "${p.to.label}\nOn data it never trained on: ${rText(p.before)} → ${rText(p.after)} per trade (${p.trades} trades). Your risk settings are unchanged."
    }
    fun trainModeName(m: TrainMode) = when (m) {
        TrainMode.FULL -> if (tr) "Tam güç — şarjda" else "Full power — on the charger"
        TrainMode.LIGHT -> if (tr) "Hafif — pilde (%10)" else "Light — on battery (10%)"
        TrainMode.WAITING -> if (tr) "Eğitim verisi bekleniyor" else "Waiting for training data"
        TrainMode.OFF -> if (tr) "Kapalı" else "Off"
    }

    // ------------------------------------------------------------ discovery
    fun scanningMarket(count: Int) =
        if (tr) "Tüm piyasanın haberlerini tarıyor · en çok konuşulan $count hisse kontrol ediliyor" else "Scanning the whole market's news · checking the $count most talked-about stocks"
    fun discoverRejected(symbol: String, mentions: Int, why: String) = "✕ $symbol ($mentions) — $why"
    fun notTradableHere() = if (tr) "Alpaca'da alınamıyor" else "not tradable on Alpaca"
    fun tooCheap() = if (tr) "5$ altı, çok oynak" else "under \$5, too volatile"
    fun newsNegative(mood: Double) = if (tr) "haberler olumsuz (${mood.moodText()})" else "news negative (${mood.moodText()})"
    fun discoverChecks(q: QualityReport) = if (tr) "5 kontrol: ${decisionName(q.decision)} ${String.format(Locale.US, "%.1f", q.score)}/5" else "five checks: ${decisionName(q.decision)} ${String.format(Locale.US, "%.1f", q.score)}/5"
    fun discoverAccepted(d: Discovery) = "✓ ${d.symbol} · ${d.name} · ${decisionName(d.decision)} ${String.format(Locale.US, "%.1f", d.score)}/5 · " +
        if (tr) "24 saatte ${d.mentions} haber" else "${d.mentions} stories in 24h"
    fun discoverSummary(found: Int, total: Int) =
        if (tr) "$total aday, $found tanesi 3 gün izlemeye alındı" else "$total candidates, $found added to the watch for 3 days"
    fun discoveredTitle(d: Discovery) = if (tr) "Haberlerde yeni hisse buldum: ${d.symbol}" else "Found a new stock in the news: ${d.symbol}"
    fun discoveredText(d: Discovery) =
        if (tr) "${d.name} · ${decisionName(d.decision)} ${String.format(Locale.US, "%.1f", d.score)}/5 · 24 saatte ${d.mentions} haber. 3 gün izleyeceğim; diğerleri gibi tüm kontrollerden geçmeden alınmaz."
        else "${d.name} · ${decisionName(d.decision)} ${String.format(Locale.US, "%.1f", d.score)}/5 · ${d.mentions} stories in 24h. Watching it for 3 days; like the rest, it is only bought if it passes every check."

    // ------------------------------------------------------------- briefing
    fun briefingTitle(mood: Double?) =
        (if (tr) "Sabah brifingi · piyasa havası " else "Morning briefing · market mood ") + (mood?.let { moodName(it) } ?: "—")
    fun briefingText(
        best: List<QualityReport>, careful: List<Pair<String, RedFlagKind>>, promotions: List<Promotion>,
        version: Int, discovered: List<String>, rules: Int,
    ): String = buildString {
        if (best.isNotEmpty()) append((if (tr) "En iyiler: " else "Best: ") + best.joinToString { "${it.symbol} ${decisionName(it.decision)} ${String.format(Locale.US, "%.1f", it.score)}" } + "\n")
        if (careful.isNotEmpty()) append((if (tr) "Dikkat: " else "Careful: ") + careful.joinToString { "${it.first} (${flagName(it.second)})" } + "\n")
        if (discovered.isNotEmpty()) append((if (tr) "Haberden bulunan: " else "Found in the news: ") + discovered.joinToString() + "\n")
        append(if (tr) "Strateji v$version" else "Strategy v$version")
        if (promotions.isNotEmpty()) append(if (tr) " · gece ${promotions.size} kez geliştirdi" else " · improved ${promotions.size}x overnight")
        if (rules > 0) append(if (tr) " · $rules öğrenilmiş kural" else " · $rules learned rule(s)")
    }

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
        "time" -> if (tr) "süre doldu" else "time's up"
        else -> if (tr) "kapandı" else "closed"
    }

    companion object {
        const val MAX_DRIFT_PCT = 1.5
    }
}
