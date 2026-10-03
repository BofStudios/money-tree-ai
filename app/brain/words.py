"""What the research desk says in the Live feed and on the lock screen, in English and Turkish."""
from __future__ import annotations

from datetime import datetime, timezone

DECISIONS = {
    "BUY_ZONE": ("BUY ZONE", "ALIM BÖLGESİ"), "WAIT": ("WAIT", "BEKLE"),
    "AVOID": ("AVOID", "UZAK DUR"), "UNKNOWN": ("NO DATA", "VERİ YOK"),
}
FLAG_NAMES = {
    "HALT": ("trading halt", "işlem durdurma"), "BANKRUPTCY": ("bankruptcy", "iflas"),
    "FRAUD": ("fraud allegation", "dolandırıcılık iddiası"), "DELISTING": ("delisting", "borsadan çıkarılma"),
    "OFFERING": ("share offering (dilution)", "yeni hisse satışı (sulanma)"),
    "ACCOUNTING": ("past financials unreliable (SEC)", "geçmiş mali tablolar güvenilmez (SEC)"),
    "GUIDANCE_CUT": ("guidance cut", "beklenti düşürüldü"), "EARNINGS_SOON": ("earnings due soon", "bilanço yaklaşıyor"),
    "REGULATOR": ("regulator probe", "düzenleyici soruşturma"), "RECALL": ("recall", "geri çağırma"),
}


def _r(x: float) -> str:
    return f"{x:+.2f}R"


class BrainWords:
    def __init__(self, turkish: bool) -> None:
        self.tr = turkish

    def t(self, en: str, tr: str) -> str:
        return tr if self.tr else en

    def decision(self, d: str) -> str:
        en, tr = DECISIONS.get(d, (d, d))
        return self.t(en, tr)

    def flag(self, kind: str) -> str:
        en, tr = FLAG_NAMES.get(kind, (kind, kind))
        return self.t(en, tr)

    # -------------------------------------------------------- research steps
    def reading_filings(self, n: int) -> str:
        return self.t(f"Reading annual reports for {n} companies (SEC)", f"{n} şirketin yıllık raporlarını okuyor (SEC)")

    def filings_line(self, symbol: str, name: str, years: int, fund: bool) -> str:
        if fund:
            return self.t(f"{symbol} — a fund (ETF): judged as a fund", f"{symbol} — fon (ETF): fon gibi değerlendirilecek")
        return self.t(f"{symbol} · {name} · {years} years", f"{symbol} · {name} · {years} yıl")

    def reading_events(self, n: int) -> str:
        return self.t(f"Reading the SEC filing index for {n} companies (8-Ks, insiders)",
                      f"{n} şirketin SEC olay kayıtlarını okuyor (8-K, içeriden işlemler)")

    def reading_attention(self, n: int) -> str:
        return self.t(f"Measuring attention on {n} companies (Wikipedia)", f"{n} şirkete olan ilgiyi ölçüyor (Wikipedia)")

    def fetching_daily(self, n: int) -> str:
        return self.t(f"Fetching daily charts for {n} stocks", f"{n} hisse için günlük grafik çekiyor")

    def fetching_history(self, n: int, bars: int, tf: str) -> str:
        return self.t(f"Fetching {bars} {tf} candles each for {n} stocks — training data for the swarm",
                      f"{n} hisse için {bars}'er {tf} mum çekiyor — sürünün eğitim verisi")

    def history_done(self, series: int, bars: int) -> str:
        return self.t(f"{series} stocks · {bars:,} candles ready", f"{series} hisse · {bars:,} mum hazır".replace(",", "."))

    def news_wire(self, added: int, kept: int) -> str:
        return self.t(f"News wire · {added} new headline(s) ({kept} kept)", f"Haber akışı · {added} yeni başlık (toplam {kept})")

    def ai_scoring(self, n: int) -> str:
        return self.t(f"AI reading and scoring {n} headlines", f"AI {n} başlığı okuyup puanlıyor")

    def scanning_market(self, n: int) -> str:
        return self.t(f"Scanning the whole market's news · checking the {n} most talked-about stocks",
                      f"Tüm piyasanın haberlerini tarıyor · en çok konuşulan {n} hisse kontrol ediliyor")

    def discovered(self, symbol: str, name: str, decision: str, score: float, mentions: int) -> str:
        return self.t(f"✓ {symbol} · {name} · {self.decision(decision)} {score:.1f}/5 · {mentions} stories in 24h",
                      f"✓ {symbol} · {name} · {self.decision(decision)} {score:.1f}/5 · 24 saatte {mentions} haber")

    def rejected(self, symbol: str, mentions: int, why: str) -> str:
        return f"✕ {symbol} ({mentions}) — {why}"

    # ------------------------------------------------------------- research
    def research_title(self, symbol: str, ok: bool, size: float) -> str:
        tail = "" if size >= 0.999 else self.t(f" · size {size * 100:.0f}%", f" · boyut %{size * 100:.0f}")
        return (self.t(f"Research · {symbol} → cleared", f"Araştırma · {symbol} → geçti") + tail) if ok \
            else self.t(f"Research · {symbol} → held back", f"Araştırma · {symbol} → bekletildi")

    def research_lines(self, r) -> list[str]:
        mark = lambda ok: "✓" if ok else "✕"  # noqa: E731
        out = []
        if r.report:
            checks = "  ".join(f"{c.kind[:4]} {'✓' if c.verdict == 'PASS' else '~' if c.verdict == 'WATCH' else '✕' if c.verdict == 'FAIL' else '?'}"
                               for c in r.report.checks)
            out.append(f"{mark(r.quality_ok)} " + self.t("5 checks: ", "5 kontrol: ") + checks
                       + f" → {self.decision(r.report.decision)} {r.report.score:.1f}/5")
        trend = {True: self.t("Daily chart rising (above its 50-day average)", "Günlük grafik yükselişte (50 günlük ortalamanın üstünde)"),
                 False: self.t("Daily chart falling (below its 50-day average)", "Günlük grafik düşüşte (50 günlük ortalamanın altında)"),
                 None: self.t("No daily chart yet", "Günlük grafik henüz yok")}[r.daily_up]
        out.append(f"{mark(r.trend_ok)} {trend}")
        mood = self.t("no news", "haber yok") if r.mood is None else f"{r.mood:+.2f}"
        flags = ", ".join(self.flag(f.kind) for f in r.flags) or self.t("no red flags", "kırmızı bayrak yok")
        out.append(f"{mark(r.news_ok)} " + self.t(f"News: {mood} · {r.news_count}/24h · {flags}", f"Haber: {mood} · {r.news_count}/24sa · {flags}"))
        if r.learned.edge is None:
            out.append(f"{mark(r.learned_ok)} " + self.t("Learned: not enough results for signals like this yet",
                                                         "Öğrendiklerim: bu tür sinyal için henüz yeterli sonuç yok"))
        else:
            out.append(f"{mark(r.learned_ok)} " + self.t(f"Learned: expected {_r(r.learned.edge)} for signals like this",
                                                         f"Öğrendiklerim: bu tür sinyallerde beklenen {_r(r.learned.edge)}"))
        if r.alt:
            a = r.alt
            parts = []
            if a.get("attention"):
                parts.append(self.t(f"attention ×{a['attention']:.1f}", f"ilgi ×{a['attention']:.1f}"))
            if a.get("insiders_30d") is not None:
                parts.append(self.t(f"insiders {a['insiders_30d']}/30d", f"içeriden {a['insiders_30d']}/30g"))
            if a.get("next_results"):
                parts.append(self.t("results ~", "bilanço ~") + datetime.fromtimestamp(a["next_results"], tz=timezone.utc).strftime("%d %b"))
            if parts:
                out.append("· " + self.t("Alt data: ", "Alternatif veri: ") + " · ".join(parts))
        return out

    def held_back_why(self, r) -> str:
        if not r.quality_ok:
            if r.report and r.report.decision == "AVOID":
                failed = ", ".join(c.kind for c in r.report.checks if c.verdict == "FAIL") or f"{r.report.score:.1f}/5"
                return self.t(f"the five checks say AVOID ({failed})", f"5 kontrol UZAK DUR diyor ({failed})")
            return self.t("strict mode buys only the BUY ZONE", "katı modda sadece ALIM BÖLGESİ alınır")
        if not r.trend_ok:
            return self.t("the daily chart is falling — the big picture points down", "günlük grafik düşüşte — büyük resim aşağı")
        if not r.news_ok:
            blocking = next((f for f in r.flags if f.kind in ("HALT", "BANKRUPTCY", "FRAUD", "DELISTING", "OFFERING",
                                                               "ACCOUNTING", "GUIDANCE_CUT", "EARNINGS_SOON")), None)
            if blocking:
                return f'{self.flag(blocking.kind)}: "{blocking.headline[:90]}"'
            return self.t(f"the news is bad ({r.mood:+.2f})", f"haberler kötü ({r.mood:+.2f})")
        worst = r.learned.evidence[0] if r.learned.evidence else None
        if worst:
            return self.t(f"signals like this lost: {worst.key} {worst.value} averaged {_r(worst.avg_r)} over {worst.n:.0f}",
                          f"bu tür sinyaller kaybettirdi: {worst.key} {worst.value} ortalama {_r(worst.avg_r)} ({worst.n:.0f} sonuç)")
        return self.t("past results are poor", "geçmiş sonuçlar zayıf")

    def ai_committee(self, symbol: str) -> str:
        return self.t(f"AI committee reading {symbol}'s research and news", f"AI kurulu {symbol} araştırmasını ve haberlerini okuyor")

    def ai_skip(self, symbol: str) -> str:
        return self.t(f"Skipped {symbol} — the AI committee found a red flag", f"{symbol} alınmadı — AI kurulu kırmızı bayrak buldu")

    # -------------------------------------------------------------- swarm
    def promotion_title(self, p) -> str:
        if p.rollback:
            return self.t(f"Strategy rolled back (v{p.version})", f"Strateji geri alındı (v{p.version})")
        return self.t(f"Bot {p.bot} improved the strategy: v{p.version}", f"{p.bot} botu stratejiyi geliştirdi: v{p.version}")

    def promotion_text(self, p) -> str:
        return self.t(f"{p.after.label}\nOn data no bot trained on: {_r(p.unseen_before)} → {_r(p.unseen_after)} per trade ({p.trades} trades). Your risk settings are unchanged.",
                      f"{p.after.label}\nHiçbir botun eğitilmediği veride: işlem başı {_r(p.unseen_before)} → {_r(p.unseen_after)} ({p.trades} işlem). Risk ayarların aynı.")

    def learned_rule(self, b) -> str:
        return self.t(f"I learned: {b.key} {b.value} — {b.n:.0f} results, {b.win_rate * 100:.0f}% won, avg {_r(b.avg_r)}. I skip these now.",
                      f"Öğrendim: {b.key} {b.value} — {b.n:.0f} sonuç, %{b.win_rate * 100:.0f} kazandı, ortalama {_r(b.avg_r)}. Artık bunları almıyorum.")
