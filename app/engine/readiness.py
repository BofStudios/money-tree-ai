"""Is the bot trading right now, and if not, why not — with the fix.

For days the owner saw no trades and could not tell why: real money was not
armed after each start, so every buy stopped at the last gate. This card puts
every gate a buy must pass in one place, says which one is closed, and gives
the button that opens it. It also counts today's buys that did not happen, by
reason (PortfolioEngine.note_block), so "it does nothing" becomes "it wanted
to buy 7 times; real money was not armed".

Reads only what is already in memory: no network call, cheap to poll.
"""
from __future__ import annotations

BLOCK_WORDS = {
    "not_armed": ("Real money was not armed", "Gerçek para kurulu değildi"),
    "daily_loss": ("The daily loss limit was reached", "Günlük zarar sınırına ulaşıldı"),
    "cap": ("All position slots were full", "Tüm pozisyon yerleri doluydu"),
    "cash": ("Not enough free cash", "Yeterli boş nakit yoktu"),
    "paused": ("A safety pause was active", "Bir güvenlik molası vardı"),
    "research": ("The research desk said wait", "Araştırma masası beklemeyi söyledi"),
    "ai": ("The AI check found a red flag", "Yapay zekâ kontrolü kırmızı bayrak buldu"),
    "too_small": ("The order would be too small", "Emir çok küçük olurdu"),
    "rules": ("The risk rules said no", "Risk kuralları izin vermedi"),
    "sector": ("Nova: the sector already held the maximum", "Nova: sektörde zaten en fazla pozisyon vardı"),
}


def readiness(engine, brain=None, reflex=None) -> dict:
    turkish = getattr(engine, "language", "en") == "tr"

    def t(en: str, tr: str) -> str:
        return tr if turkish else en

    checks: list[dict] = []

    def add(key: str, state: str, title: str, detail: str = "", fix: str | None = None) -> None:
        checks.append({"id": key, "state": state, "title": title, "detail": detail, "fix": fix})

    risk = engine.risk
    broker = engine.executor.broker
    market = engine.clock.state()
    try:
        balance = engine.executor.get_balance()
    except Exception:
        balance = None
    with engine._lock:
        held = len(engine._positions)

    # 1. Running and not stopped
    if not engine.running:
        add("running", "bad", t("The engine is not running", "Motor çalışmıyor"), "", "start")
    elif engine.halted:
        add("halted", "bad", t("You pressed STOP", "STOP'a bastın"),
            t("Press START to let the bot buy again.", "Botun tekrar alması için START'a bas."), "start")
    else:
        add("running", "ok", t("The engine is running", "Motor çalışıyor"))

    # 2. Whose money
    if broker == "alpaca_live":
        if risk.armed:
            add("money", "ok", t("Real money is armed", "Gerçek para kurulu"),
                t("The bot places real orders.", "Bot gerçek emir verir."))
        elif risk.disarm_reason == "daily loss limit reached":
            add("money", "bad", t("The daily loss limit disarmed real money", "Günlük zarar sınırı gerçek parayı kapattı"),
                t("This protects you. It can be armed again tomorrow.", "Bu seni korur. Yarın tekrar kurulabilir."))
        else:
            add("money", "bad", t("Real money is not armed", "Gerçek para kurulu değil"),
                t("The bot only watches. It arms only when you press Arm, after every start of the app.",
                  "Bot sadece izler. Sadece sen Kur'a basınca kurulur; uygulama her açıldığında yeniden."), "arm")
    elif broker == "alpaca_paper":
        add("money", "ok", t("Alpaca practice account", "Alpaca deneme hesabı"),
            t("Real prices, practice money. No arming needed.", "Gerçek fiyatlar, deneme parası. Kurmak gerekmez."))
    else:
        add("money", "info", t("Simulated practice money", "Simüle deneme parası"),
            t("Real prices, money on this PC only.", "Gerçek fiyatlar, para sadece bu bilgisayarda."))

    # 3. Who decides
    autonomy = getattr(engine, "autonomy", "full")
    if autonomy == "full":
        add("autonomy", "ok", t("The bot buys by itself", "Bot kendi alır"))
    elif autonomy == "semi":
        add("autonomy", "warn", t("The bot asks you before each buy", "Bot her alımdan önce sana sorar"),
            t("Approve requests in time, or choose Full auto in Modes.", "İstekleri zamanında onayla ya da Modlar'dan Tam otomatik seç."),
            "modes")
    else:
        add("autonomy", "warn", t("The bot only suggests", "Bot sadece önerir"),
            t("It never buys. Choose Full auto in Modes to let it trade.", "Asla almaz. İşlem için Modlar'dan Tam otomatik seç."),
            "modes")

    # 4. Market
    if market.is_open:
        add("market", "ok", t("The US market is open", "ABD piyasası açık"), market.countdown_text() or "")
    else:
        add("market", "info", t("The US market is closed", "ABD piyasası kapalı"), market.countdown_text() or "")

    # 5. Money to use and room for it
    min_order = float(getattr(engine.config.risk, "min_order_value", 1.0))
    if balance is not None and balance.available < min_order * 2:
        add("cash", "bad", t("Not enough free cash", "Yeterli boş nakit yok"),
            t(f"Free: ${balance.available:,.2f}.", f"Boş: ${balance.available:,.2f}."), "money")
    elif balance is not None:
        add("cash", "ok", t(f"Free cash ${balance.available:,.2f}", f"Boş nakit ${balance.available:,.2f}"))
    cap = int(engine.config.risk.max_open_positions)
    if held >= cap:
        add("slots", "warn", t(f"All {cap} position slots are in use", f"{cap} pozisyon yerinin hepsi dolu"),
            t("New buys wait until a position closes.", "Yeni alımlar bir pozisyon kapanana kadar bekler."))

    # 6. Safety pauses
    locks = engine.protections.active_locks()
    if locks:
        first = locks[0]
        add("paused", "warn", t("A safety pause is on", "Bir güvenlik molası var"),
            f"{first['reason']} · {first['minutes_left']}m")

    # 7. News trading and the AI behind it
    if brain is not None:
        s = brain.settings
        ai_ok = bool(getattr(brain.ai, "available", False)) if brain.ai is not None else False
        if not getattr(s, "news_trading", True):
            add("news", "info", t("News trading is off", "Haberle işlem kapalı"), "", "modes")
        elif not ai_ok:
            add("news", "warn", t("No AI connected", "Bağlı yapay zekâ yok"),
                t("News trading needs an AI to judge the news. Add a free Groq key in Settings.",
                  "Haberle işlem, haberi değerlendirecek bir yapay zekâ ister. Ayarlar'dan ücretsiz Groq anahtarı ekle."),
                "settings")
        else:
            add("news", "ok", t("News trading is on", "Haberle işlem açık"))

    blocked = engine.blocked_today()
    missed = sorted(blocked.items(), key=lambda kv: -kv[1].get("count", 0))
    lines = [{"key": k, "count": int(v.get("count", 0)), "symbol": v.get("symbol", ""),
              "detail": v.get("detail", ""),
              "title": t(*BLOCK_WORDS.get(k, BLOCK_WORDS["rules"]))} for k, v in missed]

    bad = [c for c in checks if c["state"] == "bad"]
    if bad:
        verdict = "watching"
        headline = t("The bot is only watching: ", "Bot sadece izliyor: ") + bad[0]["title"].lower()
    elif not market.is_open:
        verdict = "waiting"
        headline = t("Ready. The bot trades when the market opens.", "Hazır. Bot piyasa açılınca işlem yapar.")
    else:
        verdict = "trading"
        headline = t("Ready. The bot trades when its rules agree.", "Hazır. Bot kuralları uyunca işlem yapar.")
    return {"verdict": verdict, "headline": headline, "checks": checks, "missed": lines,
            "missed_total": sum(l["count"] for l in lines), "fix": bad[0]["fix"] if bad else None}
