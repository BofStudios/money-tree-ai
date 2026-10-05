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
    (r"^you stopped the bot$", "botu sen durdurdun"),
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
    # Written to ASD-STE100 (Simplified Technical English) rules: one fact per
    # sentence, active voice, simple tenses, no "-ing" verbs, short sentences.
    # A step title says what the bot does now. The line under it says what
    # happened. The Turkish follows the same rules.

    def market_open(self, close: datetime | None) -> str:
        tail = f" {self._('It closes at', 'Kapanış:')} {self.ny(close)}." if close else ""
        return self._("The market is open.", "Piyasa açık.") + tail

    def market_closed(self, opens: datetime | None) -> str:
        tail = f" {self._('It opens at', 'Açılış:')} {self.ny(opens)}." if opens else ""
        return self._("The market is closed.", "Piyasa kapalı.") + tail

    def closed_review(self) -> str:
        return self._("The bot examines the charts. It does not buy or sell until the market opens.",
                      "Bot grafikleri inceler. Piyasa açılana kadar alım ve satım yapmaz.")

    def waiting_for_open(self, opens: datetime | None) -> str:
        when = f" {self._('Next open:', 'Sonraki açılış:')} {self.ny(opens)}." if opens else ""
        return self._("Done. The bot waits for the market to open.", "Bitti. Bot piyasanın açılmasını bekler.") + when

    def reading_account(self) -> str:
        return self._("The bot reads your account.", "Bot hesabını okur.")

    def account_summary(self, equity: float, cash: float, today: float | None) -> str:
        today_text = f" {self._('Today:', 'Bugün:')} {self.signed(today)}." if today is not None else ""
        return self._(f"Equity: {self.usd(equity)}. Cash: {self.usd(cash)}.",
                      f"Varlık: {self.usd(equity)}. Nakit: {self.usd(cash)}.") + today_text

    def checking_positions(self) -> str:
        return self._("The bot examines the positions and the open orders.",
                      "Bot pozisyonları ve açık emirleri kontrol eder.")

    def positions_summary(self, held: int, orders: int | None) -> str:
        if orders is None:
            return self._(f"Positions: {held}.", f"Pozisyon: {held}.")
        return self._(f"Positions: {held}. Open orders: {orders}.", f"Pozisyon: {held}. Açık emir: {orders}.")

    def fetching_bars(self, count: int, timeframe: str) -> str:
        return self._(f"The bot gets {self.tf(timeframe)} prices for {count} stocks.",
                      f"Bot {count} hisse için {self.tf(timeframe)} fiyatları alır.")

    def bars_summary(self, ready: int, total: int) -> str:
        return self._(f"Done. Prices are ready for {ready} of {total} stocks.",
                      f"Bitti. {total} hisseden {ready} tanesinin fiyatı hazır.")

    def analysing(self, count: int) -> str:
        return self._(f"The bot examines {count} stocks.", f"Bot {count} hisseyi inceler.")

    def analysis_line(self, symbol: str, snapshot: dict, action: str) -> str:
        if not snapshot.get("ready"):
            return self._(f"{symbol}: not sufficient data.", f"{symbol}: veri yeterli değil.")
        trend = self._("trend up", "yükselişte") if snapshot.get("trend") == "up" else self._("trend down", "düşüşte")
        verdict = {
            "buy": self._("BUY signal", "ALIM sinyali"),
            "close": self._("SELL signal", "SATIŞ sinyali"),
        }.get(action, self._("no action", "işlem yok"))
        rsi = snapshot.get("rsi")
        rsi_text = f"RSI {rsi:.0f}" if rsi is not None else "RSI —"
        return f"{symbol} {self.usd(snapshot['price'])} · {trend} · {rsi_text} · {verdict}"

    def analysis_summary(self, buys: int, sells: int, trading: bool) -> str:
        if buys == 0 and sells == 0:
            text = self._("Done. There are no trade signals.", "Bitti. İşlem sinyali yok.")
        else:
            text = self._(f"Done. Buy signals: {buys}. Sell signals: {sells}.",
                          f"Bitti. Alım sinyali: {buys}. Satış sinyali: {sells}.")
        if not trading:
            text += " " + self._("The market is closed. The bot does not trade.", "Piyasa kapalı. Bot işlem yapmaz.")
        return text

    def reading_news(self, symbol: str) -> str:
        return self._(f"The bot reads the news for {symbol}.", f"Bot {symbol} haberlerini okur.")

    def news_summary(self, count: int) -> str:
        return self._(f"Done. Headlines: {count}.", f"Bitti. Başlık: {count}.")

    def placing(self, symbol: str, qty: float, stop: float | None, target: float | None, where: str) -> str:
        """Where the stop will be: "broker" (Alpaca), "pc" (this app) or "sim"."""
        levels = ""
        if stop is not None and target is not None:
            levels = self._(f" Stop-loss: {self.usd(stop)}. Target: {self.usd(target)}.",
                            f" Zarar durdur: {self.usd(stop)}. Hedef: {self.usd(target)}.")
        tail = {
            "broker": self._(" Alpaca keeps the stop-loss and the target.", " Zarar durdur ve hedef Alpaca'da durur."),
            "pc": self._(" This PC monitors the stop-loss.", " Zarar durdurmayı bu PC izler."),
            "sim": self._(" This is practice money.", " Bu deneme parasıdır."),
        }.get(where, "")
        return self._(f"The bot sends an order: buy {qty:g} {symbol}.",
                      f"Bot emir gönderir: {qty:g} {symbol} al.") + levels + tail

    def filled(self, qty: float, symbol: str, price: float, where: str) -> str:
        tail = {
            "broker": self._(" Alpaca keeps the stop-loss and the target.", " Zarar durdur ve hedef Alpaca'da duruyor."),
            "pc": self._(" This PC monitors the stop-loss. Keep the PC on.", " Zarar durdurmayı bu PC izliyor. PC'yi açık tut."),
        }.get(where, "")
        return self._(f"Done. The bot bought {qty:g} {symbol} at {self.usd(price)}.",
                      f"Bitti. Bot {qty:g} {symbol} aldı. Fiyat: {self.usd(price)}.") + tail

    def order_not_filled(self) -> str:
        return self._("The order did not fill. The bot bought nothing.", "Emir gerçekleşmedi. Bot bir şey almadı.")

    def raising_stop(self, symbol: str, old: float | None, new: float) -> str:
        before = self.usd(old) if old is not None else "—"
        return self._(f"The bot moves the {symbol} stop-loss up: {before} → {self.usd(new)}.",
                      f"Bot {symbol} zarar durdurmasını yükseltir: {before} → {self.usd(new)}.")

    def stop_moved(self, at_broker: bool) -> str:
        if at_broker:
            return self._("Done. Alpaca has the new stop-loss.", "Bitti. Yeni zarar durdurma Alpaca'da.")
        return self._("Done. This PC keeps the new stop-loss.", "Bitti. Yeni zarar durdurmayı bu PC tutar.")

    def selling(self, symbol: str, reason: str) -> str:
        return self._(f"The bot sells {symbol}. Reason: {self.reason(reason)}.",
                      f"Bot {symbol} satar. Sebep: {self.reason(reason)}.")

    def sold(self, symbol: str, pnl: float) -> str:
        return self._(f"Done. The bot sold {symbol}. Result: {self.signed(pnl)}.",
                      f"Bitti. Bot {symbol} sattı. Sonuç: {self.signed(pnl)}.")

    def sell_failed(self) -> str:
        return self._("The sale failed. This PC continues to monitor the stop-loss. The bot tries again.",
                      "Satış olmadı. Bu PC zarar durdurmayı izlemeye devam eder. Bot tekrar dener.")

    def closed_at_broker(self, symbol: str, reason: str, pnl: float) -> str:
        why = self.reason(reason)
        return self._(f"Alpaca closed {symbol}. Reason: {why}. Result: {self.signed(pnl)}.",
                      f"Alpaca {symbol} pozisyonunu kapattı. Sebep: {why}. Sonuç: {self.signed(pnl)}.")

    def lost_track(self, symbol: str) -> str:
        return self._(f"{symbol} is not in your Alpaca account. The bot stops to monitor it.",
                      f"{symbol} Alpaca hesabında yok. Bot onu izlemeyi bıraktı.")

    def unmanaged_line(self, symbol: str, qty: float, pnl: float) -> str:
        return self._(f"{symbol}: {qty:g} shares, {self.signed(pnl)}. The bot did not buy it. The bot does not touch it.",
                      f"{symbol}: {qty:g} adet, {self.signed(pnl)}. Bunu bot almadı. Bot dokunmaz.")

    def fill_detail(self, qty: float, entry: float, exit_: float) -> str:
        return self._(f"Shares: {qty:g}. Buy price: {self.usd(entry)}. Sell price: {self.usd(exit_)}.",
                      f"Adet: {qty:g}. Alış: {self.usd(entry)}. Satış: {self.usd(exit_)}.")

    def asking_ai(self) -> str:
        return self._("The AI writes why the bot bought.", "Yapay zekâ alımın sebebini yazar.")

    def ai_silent(self) -> str:
        return self._("The AI did not answer.", "Yapay zekâ cevap vermedi.")

    def waiting_approval(self, symbol: str, qty: float, price: float) -> str:
        return self._(f"Your approval is necessary: buy {qty:g} {symbol} at approximately {self.usd(price)}.",
                      f"Onayın gerekli: {qty:g} {symbol} al, yaklaşık {self.usd(price)}.")

    def suggestion(self, symbol: str, qty: float, price: float) -> str:
        return self._(f"Idea only. The bot did not buy: {qty:g} {symbol} at approximately {self.usd(price)}.",
                      f"Sadece fikir. Bot almadı: {qty:g} {symbol}, yaklaşık {self.usd(price)}.")

    def not_placed(self, symbol: str, why: str) -> str:
        return self._(f"{symbol}: the bot did not buy. Reason: {self.reason(why)}.",
                      f"{symbol}: bot almadı. Sebep: {self.reason(why)}.")

    def cap_reached(self, symbol: str, held: int, waiting: int, cap: int) -> str:
        if waiting:
            return self._(f"{symbol}: the bot did not buy. Positions: {held}. Waiting buys: {waiting}. The limit is {cap}.",
                          f"{symbol}: bot almadı. Pozisyon: {held}. Bekleyen alım: {waiting}. Sınır: {cap}.")
        return self._(f"{symbol}: the bot did not buy. Positions: {held}. The limit is {cap}.",
                      f"{symbol}: bot almadı. Pozisyon: {held}. Sınır: {cap}.")

    def too_small(self, symbol: str) -> str:
        return self._(f"{symbol}: the bot did not buy. The order is too small.",
                      f"{symbol}: bot almadı. Emir çok küçük.")

    def account_blocked(self) -> str:
        return self._("Alpaca blocked trades on this account. Open the Alpaca app and do a check.",
                      "Alpaca bu hesapta işlemi durdurdu. Alpaca uygulamasını açıp kontrol et.")

    def no_data(self, total: int) -> str:
        return self._(f"The bot got no prices for {total} stocks.", f"Bot {total} hisse için fiyat alamadı.")

    def no_data_for(self, symbol: str) -> str:
        return self._(f"{symbol}: no prices.", f"{symbol}: fiyat yok.")

    # --------------------------------------------------------- stop / start

    def halted(self) -> str:
        return self._("STOPPED. The bot does not buy. The bot does not sell on a signal.",
                      "DURDU. Bot alım yapmaz. Bot sinyalle satış yapmaz.")

    def halted_detail(self) -> str:
        return self._("Stop-loss and take-profit stay active. They protect the positions. Press Start to trade again.",
                      "Zarar durdur ve kâr al aktif kalır. Pozisyonları korurlar. Tekrar işlem için Başlat'a bas.")

    def halted_reason(self) -> str:
        return self._("you stopped the bot", "botu sen durdurdun")

    def halted_scan(self, held: int) -> str:
        return self._(f"Done. The bot is stopped. It did not buy or sell. Positions: {held}. Stop-loss stays active.",
                      f"Bitti. Bot durdu. Alım ve satım yapmadı. Pozisyon: {held}. Zarar durdur aktif.")

    def still_halted(self, when: datetime | None) -> str:
        since = f" ({self.ny(when)})" if when else ""
        return self._(f"The bot is stopped since your last Stop{since}. It does not trade. Press Start to trade.",
                      f"Bot son Durdur'dan beri durdu{since}. İşlem yapmaz. İşlem için Başlat'a bas.")

    def resumed(self) -> str:
        return self._("STARTED. The bot can trade again.", "BAŞLADI. Bot tekrar işlem yapabilir.")

    def chat_stopped(self) -> str:
        return self._("Done. The bot is stopped. It does not buy. It does not sell on a signal. "
                      "Stop-loss and take-profit stay active. Type \"start\" to trade again.",
                      "Tamam. Bot durdu. Alım yapmaz. Sinyalle satış yapmaz. "
                      "Zarar durdur ve kâr al aktif kalır. Tekrar işlem için \"başlat\" yaz.")

    def chat_started(self) -> str:
        return self._("Done. The bot started. It can trade again. Type \"stop\" to stop it.",
                      "Tamam. Bot başladı. Tekrar işlem yapabilir. Durdurmak için \"dur\" yaz.")

    # ------------------------------------------------ desktop notifications

    def notice_bought(self, symbol: str, qty: float, price: float) -> tuple[str, str]:
        return (self._(f"Bought {symbol}", f"{symbol} alındı"),
                self._(f"Shares: {qty:g}. Price: {self.usd(price)}.", f"Adet: {qty:g}. Fiyat: {self.usd(price)}."))

    def notice_sold(self, symbol: str, pnl: float, reason: str) -> tuple[str, str]:
        return (self._(f"Sold {symbol}: {self.signed(pnl)}", f"{symbol} satıldı: {self.signed(pnl)}"),
                self.reason(reason))

    def notice_approval(self, symbol: str, qty: float, price: float) -> tuple[str, str]:
        return (self._("Your approval is necessary", "Onayın gerekli"), self.waiting_approval(symbol, qty, price))

    def no_position(self, symbol: str) -> str:
        return self._(f"There is no open position in {symbol}.", f"{symbol} için açık pozisyon yok.")

    def market_closed_no_sell(self, symbol: str) -> str:
        return self._(
            f"The market is closed. A sale now waits for the open. Until then, {symbol} has no stop-loss at Alpaca. "
            "Try again after the open.",
            f"Piyasa kapalı. Şimdi satış açılışı bekler. O zamana kadar {symbol} için Alpaca'da zarar durdurma olmaz. "
            "Açılıştan sonra tekrar dene.",
        )

    def keys_refused(self, live: bool, problem: str) -> str:
        account = self._("real-money", "gerçek para") if live else self._("practice", "deneme")
        return self._(
            f"Alpaca refused the {account} keys ({problem}). The bot uses practice money now. "
            "Enter new keys in Settings → Money.",
            f"Alpaca {account} anahtarlarını reddetti ({problem}). Bot şimdi deneme parası kullanır. "
            "Ayarlar → Para kısmına yeni anahtar gir.",
        )

    def live_without_keys(self) -> str:
        return self._(
            "Real money is selected, but there are no real-money keys. The bot uses practice money until you add them.",
            "Gerçek para seçili ama gerçek hesap anahtarı yok. Anahtar ekleyene kadar bot deneme parası kullanır.",
        )

    def restored(self, count: int) -> str:
        return self._(f"The bot found {count} open position(s) from the last session.",
                      f"Bot geçen oturumdan {count} açık pozisyon buldu.")

    def scan_done(self, held: int, next_seconds: int) -> str:
        return self._(f"Done. Positions: {held}. Next check in {next_seconds} seconds.",
                      f"Bitti. Pozisyon: {held}. Sonraki kontrol {next_seconds} saniye sonra.")

    def cycle_failed(self) -> str:
        return self._("This check failed. The bot tries again.", "Bu kontrol başarısız oldu. Bot tekrar dener.")

    def started(self, mode: str, broker: str, autonomy: str, timeframe: str) -> str:
        money = {
            "alpaca_live": self._("REAL money", "GERÇEK para"),
            "alpaca_paper": self._("Alpaca practice money", "Alpaca deneme parası"),
            "simulation": self._("practice money on this PC", "bu PC'de deneme parası"),
        }.get(broker, mode)
        return self._("The bot started.", "Bot başladı.") + f" {money} · {self.autonomy(autonomy)} · {self.tf(timeframe)}"
