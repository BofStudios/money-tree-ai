"""What the engine says in the Live tab, in English and Turkish.

Mirrors the phone app's Words.kt so the two monitors read the same. Kept next
to the engine (not in the web i18n file) because these are built from live
numbers on the server, one step at a time.
"""
from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

_NY = ZoneInfo("America/New_York")
_DAYS_EN = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_DAYS_TR = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]

TIMEFRAME_NAMES = {
    "15m": ("15-minute", "15 dakikalık"),
    "1h": ("1-hour", "1 saatlik"),
    "1d": ("daily", "günlük"),
}
AUTONOMY_NAMES = {
    "full": ("Full auto", "Tam otomatik"),
    "semi": ("Semi-auto", "Yarı otomatik"),
    "manual": ("Manual", "Manuel"),
}

# Reasons the engine, strategy, risk rules and protections produce in English,
# with their Turkish. Anything not listed is shown as it is.
_REASONS_TR = [
    (r"^stop-loss$", "stop-loss"),
    (r"^take-profit$", "hedef"),
    (r"^manual close$", "elle kapatıldı"),
    (r"^closed at Alpaca$", "Alpaca'da kapatıldı"),
    (r"^EMA(\d+) crossed above EMA(\d+), RSI (\d+)$", r"EMA\1, EMA\2'nin üstüne çıktı, RSI \3"),
    (r"^EMA(\d+) crossed below EMA(\d+)$", r"EMA\1, EMA\2'nin altına indi"),
    (r"^RSI overbought at (\d+)$", r"RSI aşırı alımda (\1)"),
    (r"^live trading is not armed$", "gerçek para kilidi açılmadı (Arm)"),
    (r"^daily loss limit reached$", "günlük zarar sınırı doldu"),
    (r"^maximum open positions reached$", "açık pozisyon sınırı doldu"),
    (r"^insufficient available balance$", "yeterli nakit yok"),
    (r"^position size below exchange minimum$", "tutar borsa minimumunun altında"),
    (r"^cooldown after the last trade \((\d+)m left\)$", r"son işlemden sonra bekleme (\1 dk kaldı)"),
    (r"^too many stop-outs recently \((\d+)m left\)$", r"son zamanlarda çok fazla stop (\1 dk kaldı)"),
    (r"^drawdown limit hit \((\d+)m left\)$", r"düşüş sınırı aşıldı (\1 dk kaldı)"),
]


class Words:
    def __init__(self, turkish: bool) -> None:
        self.tr = turkish

    def _(self, en: str, tr: str) -> str:
        return tr if self.tr else en

    @staticmethod
    def usd(value: float) -> str:
        return f"${value:,.2f}"

    def signed(self, value: float) -> str:
        sign = "+" if value > 0 else "−" if value < 0 else ""
        return f"{sign}${abs(value):,.2f}"

    def ny(self, when: datetime) -> str:
        local = when.astimezone(_NY)
        day = (_DAYS_TR if self.tr else _DAYS_EN)[local.weekday()]
        return f"{day} {local:%H:%M} NY"

    def tf(self, timeframe: str) -> str:
        en, tr = TIMEFRAME_NAMES.get(timeframe, (timeframe, timeframe))
        return self._(en, tr)

    def autonomy(self, mode: str) -> str:
        en, tr = AUTONOMY_NAMES.get(mode, (mode, mode))
        return self._(en, tr)

    def reason(self, text: str) -> str:
        """An English reason from the rules, in the owner's language."""
        if not self.tr or not text:
            return text
        for pattern, turkish in _REASONS_TR:
            if re.match(pattern, text):
                return re.sub(pattern, turkish, text)
        return text

    # -------------------------------------------------------------- the loop
    def market_open(self, close: datetime | None) -> str:
        tail = f" · {self._('closes', 'kapanış')} {self.ny(close)}" if close else ""
        return self._("Market open", "Piyasa açık") + tail

    def market_closed(self, opens: datetime | None) -> str:
        tail = f" · {self._('opens', 'açılış')} {self.ny(opens)}" if opens else ""
        return self._("Market closed", "Piyasa kapalı") + tail

    def closed_review(self) -> str:
        return self._("Market closed — reviewing the charts; nothing is bought or sold until the open",
                      "Piyasa kapalı — grafikleri inceliyorum, açılışa kadar alım satım yok")

    def waiting_for_open(self, opens: datetime | None) -> str:
        when = f" ({self.ny(opens)})" if opens else ""
        return self._(f"Waiting for the open{when}", f"Açılışı bekliyorum{when}")

    def reading_account(self) -> str:
        return self._("Reading your account", "Hesabı okuyor")

    def account_summary(self, equity: float, cash: float, today: float | None) -> str:
        today_text = f" · {self._('today', 'bugün')} {self.signed(today)}" if today is not None else ""
        return self._(f"Equity {self.usd(equity)} · cash {self.usd(cash)}",
                      f"Varlık {self.usd(equity)} · nakit {self.usd(cash)}") + today_text

    def checking_positions(self) -> str:
        return self._("Checking positions and open orders", "Pozisyonları ve açık emirleri kontrol ediyor")

    def positions_summary(self, held: int, orders: int | None) -> str:
        if orders is None:
            return self._(f"{held} positions", f"{held} pozisyon")
        return self._(f"{held} positions · {orders} open orders", f"{held} pozisyon · {orders} açık emir")

    def fetching_bars(self, count: int, timeframe: str) -> str:
        return self._(f"Fetching {self.tf(timeframe)} bars for {count} stocks",
                      f"{count} hisse için {self.tf(timeframe)} mum çekiyor")

    def bars_summary(self, ready: int, total: int) -> str:
        return self._(f"{ready} of {total} ready", f"{ready}/{total} hisse hazır")

    def analysing(self, count: int) -> str:
        return self._(f"Analysing {count} stocks", f"{count} hisseyi analiz ediyor")

    def analysis_line(self, symbol: str, snapshot: dict, action: str) -> str:
        if not snapshot.get("ready"):
            return self._(f"{symbol} — not enough data", f"{symbol} — veri yetersiz")
        trend = self._("trend up", "yükselişte") if snapshot.get("trend") == "up" else self._("trend down", "düşüşte")
        verdict = {
            "buy": self._("BUY signal", "ALIM sinyali"),
            "close": self._("SELL signal", "SATIŞ sinyali"),
        }.get(action, self._("hold", "bekle"))
        rsi = snapshot.get("rsi")
        rsi_text = f"RSI {rsi:.0f}" if rsi is not None else "RSI —"
        return f"{symbol} {self.usd(snapshot['price'])} · {trend} · {rsi_text} · {verdict}"

    def analysis_summary(self, buys: int, sells: int, trading: bool) -> str:
        if buys == 0 and sells == 0:
            text = self._("No trade signals", "İşlem sinyali yok")
        else:
            text = self._(f"{buys} buy, {sells} sell signal(s)", f"{buys} alım, {sells} satış sinyali")
        if not trading:
            text += " · " + self._("market closed, not trading", "piyasa kapalı, işlem yok")
        return text

    def reading_news(self, symbol: str) -> str:
        return self._(f"Reading news for {symbol}", f"{symbol} haberlerini okuyor")

    def news_summary(self, count: int) -> str:
        return self._(f"{count} headline(s)", f"{count} başlık")

    def placing(self, symbol: str, qty: float, stop: float | None, target: float | None, where: str) -> str:
        """Where the stop will live: "broker" (Alpaca), "pc" (this app) or "sim"."""
        levels = ""
        if stop is not None and target is not None:
            levels = f" · stop {self.usd(stop)} · {self._('target', 'hedef')} {self.usd(target)}"
        tail = {
            "broker": self._(" · stop and target held at Alpaca", " · stop ve hedef Alpaca'da duracak"),
            "pc": self._(" · stop watched by this PC", " · stop'u bu PC izleyecek"),
            "sim": self._(" · simulated money", " · simülasyon parası"),
        }.get(where, "")
        return self._(f"Placing order: buy {qty:g} {symbol}", f"Emir gönderiyor: {qty:g} {symbol} al") + levels + tail

    def filled(self, qty: float, symbol: str, price: float, where: str) -> str:
        tail = {
            "broker": self._(" The stop and target are held at Alpaca.", " Stop ve hedef Alpaca'da duruyor."),
            "pc": self._(" This PC watches the stop — keep it on.", " Stop'u bu PC izliyor, açık kalsın."),
        }.get(where, "")
        return self._(f"Bought {qty:g} {symbol} at {self.usd(price)}.", f"{qty:g} {symbol} alındı, {self.usd(price)}.") + tail

    def order_not_filled(self) -> str:
        return self._("The order did not fill", "Emir gerçekleşmedi")

    def signal_sent(self, symbol: str, qty: float, price: float) -> str:
        return self._(f"Signal: buy {qty:g} {symbol} at about {self.usd(price)}",
                      f"Sinyal: {qty:g} {symbol} al, yaklaşık {self.usd(price)}")

    def signal_detail(self) -> str:
        return self._("Place it yourself in Midas, then tap Taken", "Midas'ta kendin al, sonra Aldım'a bas")

    def raising_stop(self, symbol: str, old: float | None, new: float) -> str:
        before = self.usd(old) if old is not None else "—"
        return self._(f"Raising {symbol} stop: {before} → {self.usd(new)}", f"{symbol} stop'unu yükseltiyor: {before} → {self.usd(new)}")

    def stop_moved(self, at_broker: bool) -> str:
        return self._("Moved at Alpaca", "Alpaca'da güncellendi") if at_broker else self._("Held on this PC", "Bu PC'de tutuluyor")

    def selling(self, symbol: str, reason: str) -> str:
        return self._(f"Selling {symbol} — {self.reason(reason)}", f"{symbol} satılıyor — {self.reason(reason)}")

    def sold(self, symbol: str, pnl: float) -> str:
        return self._(f"Sold {symbol} · {self.signed(pnl)}", f"{symbol} satıldı · {self.signed(pnl)}")

    def sell_failed(self) -> str:
        return self._("Not sold — this PC keeps watching the stop and will try again",
                      "Satılamadı — stop'u bu PC izlemeye devam ediyor, tekrar denenecek")

    def exit_signal(self, symbol: str, reason: str) -> str:
        return self._(f"Exit signal: sell {symbol} — {self.reason(reason)}",
                      f"Çıkış sinyali: {symbol} sat — {self.reason(reason)}")

    def exit_sent(self) -> str:
        return self._("Sell it yourself in Midas, then confirm", "Midas'ta kendin sat, sonra onayla")

    def closed_at_broker(self, symbol: str, reason: str, pnl: float) -> str:
        why = self.reason(reason)
        return self._(f"{symbol} closed at Alpaca ({why}) · {self.signed(pnl)}",
                      f"{symbol} Alpaca'da kapandı ({why}) · {self.signed(pnl)}")

    def lost_track(self, symbol: str) -> str:
        return self._(f"{symbol} is not in your Alpaca account any more — stopped tracking it",
                      f"{symbol} artık Alpaca hesabında yok — takibi bıraktım")

    def unmanaged_line(self, symbol: str, qty: float, pnl: float) -> str:
        return self._(f"{symbol} {qty:g} shares · {self.signed(pnl)} · not bought by this app, left alone",
                      f"{symbol} {qty:g} adet · {self.signed(pnl)} · bu uygulama almadı, dokunmuyorum")

    def fill_detail(self, qty: float, entry: float, exit_: float) -> str:
        return self._(f"{qty:g} shares · in {self.usd(entry)} · out {self.usd(exit_)}",
                      f"{qty:g} adet · giriş {self.usd(entry)} · çıkış {self.usd(exit_)}")

    def asking_ai(self) -> str:
        return self._("Asking the AI to explain the decision", "AI'a kararı açıklatıyor")

    def ai_silent(self) -> str:
        return self._("No answer from the AI", "AI cevap vermedi")

    def waiting_approval(self, symbol: str, qty: float, price: float) -> str:
        return self._(f"Waiting for your OK: buy {qty:g} {symbol} at about {self.usd(price)}",
                      f"Onayını bekliyor: {qty:g} {symbol} al, yaklaşık {self.usd(price)}")

    def suggestion(self, symbol: str, qty: float, price: float) -> str:
        return self._(f"Idea (manual mode, not placed): {qty:g} {symbol} at about {self.usd(price)}",
                      f"Fikir (manuel mod, işlem açılmadı): {qty:g} {symbol}, yaklaşık {self.usd(price)}")

    def not_placed(self, symbol: str, why: str) -> str:
        return self._(f"{symbol}: not buying — {self.reason(why)}", f"{symbol}: alınmadı — {self.reason(why)}")

    def cap_reached(self, symbol: str, held: int, waiting: int, cap: int) -> str:
        if waiting:
            return self._(f"{symbol}: not buying — holding {held} and {waiting} waiting, the cap is {cap}",
                          f"{symbol}: alınmadı — {held} pozisyon ve {waiting} bekleyen var, sınır {cap}")
        return self._(f"{symbol}: not buying — already holding {held}, the cap is {cap}",
                      f"{symbol}: alınmadı — zaten {held} pozisyon var, sınır {cap}")

    def too_small(self, symbol: str) -> str:
        return self._(f"{symbol}: not buying — the position would be too small to place",
                      f"{symbol}: alınmadı — tutar emir vermek için çok küçük")

    def account_blocked(self) -> str:
        return self._("Alpaca has blocked trading on this account — check the Alpaca app",
                      "Alpaca bu hesapta işlemi durdurmuş — Alpaca uygulamasına bak")

    def no_data(self, total: int) -> str:
        return self._(f"No prices came back for {total} stocks", f"{total} hisse için fiyat gelmedi")

    def no_data_for(self, symbol: str) -> str:
        return self._(f"{symbol} — no prices", f"{symbol} — fiyat yok")

    # ------------------------------------------------ desktop notifications

    def notice_bought(self, symbol: str, qty: float, price: float) -> tuple[str, str]:
        return (self._(f"Bought {symbol}", f"{symbol} alındı"),
                self._(f"{qty:g} at {self.usd(price)}", f"{qty:g} adet, {self.usd(price)}"))

    def notice_sold(self, symbol: str, pnl: float, reason: str) -> tuple[str, str]:
        return (self._(f"Sold {symbol} · {self.signed(pnl)}", f"{symbol} satıldı · {self.signed(pnl)}"),
                self.reason(reason))

    def notice_approval(self, symbol: str, qty: float, price: float) -> tuple[str, str]:
        return (self._("Your OK is needed", "Onayın gerekiyor"), self.waiting_approval(symbol, qty, price))

    def no_position(self, symbol: str) -> str:
        return self._(f"No open position in {symbol}.", f"{symbol} için açık pozisyon yok.")

    def market_closed_no_sell(self, symbol: str) -> str:
        return self._(
            f"The market is closed. A sell sent now would only wait for the open, and {symbol} "
            "would lose its stop at Alpaca until then. Try again after the open.",
            f"Piyasa kapalı. Şimdi gönderilen satış sadece açılışı bekler ve o zamana kadar {symbol} "
            "Alpaca'daki stop'unu kaybeder. Açılıştan sonra tekrar dene.",
        )

    def keys_refused(self, live: bool, problem: str) -> str:
        account = self._("live", "gerçek") if live else self._("paper", "deneme (paper)")
        return self._(
            f"Alpaca refused the saved {account} keys ({problem}) — running on simulated money. "
            "Enter new keys in Settings → Money.",
            f"Alpaca kayıtlı {account} anahtarlarını reddetti ({problem}) — simülasyon parasıyla çalışıyor. "
            "Ayarlar → Para kısmından yeni anahtar gir.",
        )

    def live_without_keys(self) -> str:
        return self._(
            "Real money is selected but no live keys are saved — running on simulated money until you add them.",
            "Gerçek para seçili ama gerçek hesap anahtarı yok — ekleyene kadar simülasyon parasıyla çalışıyor.",
        )

    def restored(self, count: int) -> str:
        return self._(f"Picked up {count} open position(s) from last time",
                      f"Geçen seferden {count} açık pozisyon devralındı")

    def scan_done(self, held: int, next_seconds: int) -> str:
        return self._(f"Scan complete · holding {held} · next look in {next_seconds}s",
                      f"Tarama bitti · {held} pozisyon · {next_seconds} sn sonra tekrar")

    def cycle_failed(self) -> str:
        return self._("Something failed this round — will retry", "Bu turda bir sorun çıktı, yeniden deneyecek")

    def started(self, mode: str, broker: str, autonomy: str, timeframe: str) -> str:
        money = {
            "alpaca_live": self._("REAL money", "GERÇEK para"),
            "alpaca_paper": self._("Alpaca paper money", "Alpaca paper (deneme) para"),
            "simulation": self._("simulated money", "simülasyon parası"),
            "signal": self._("signals only (Midas)", "sadece sinyal (Midas)"),
        }.get(broker, mode)
        return self._("Started", "Başladı") + f" · {money} · {self.autonomy(autonomy)} · {self.tf(timeframe)}"
