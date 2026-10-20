"""The desk: six named agents, each one a job the bot already does, made visible.

  Atlas   follows the big money: insider filings, unusual attention, 8-K events
  Vega    reads the narrative: what the news says and how the reflex judged it
  Orion   writes the thesis for every buy: why, the counterargument, where it breaks
  Titan   times the entry: an idea waits until the price agrees
  Luna    plans the exit: stop, target, trailing stop, news time limits
  Nova    protects the desk: the final veto (risk rules, daily loss, pauses,
          and no more than two positions in one sector)

Two parts are new behaviour, not only views: Orion's written thesis (kept per
position, shown and logged) and Nova's sector limit (a real veto in the
engine). Nothing here can start a buy or arm real money.
"""
from __future__ import annotations

import time

MAX_PER_SECTOR = 2

SECTORS: dict[str, tuple[str, str]] = {}
for _group, _en, _tr, _symbols in (
    ("chips", "Chips", "Çipler", "NVDA AMD AVGO TSM MU QCOM ASML INTC ARM MRVL AMAT LRCX KLAC TXN ADI ON SMCI SOXX SMH"),
    ("bigtech", "Big tech and software", "Büyük teknoloji ve yazılım",
     "AAPL MSFT GOOGL GOOG AMZN META ORCL CRM ADBE NOW PLTR NFLX RBLX SNOW SHOP UBER"),
    ("power", "Energy and power", "Enerji ve elektrik",
     "XOM CVX COP OXY SLB EOG CEG VST NEE NRG TLN GEV VRT ETN OKLO SMR CCJ LEU FSLR ENPH USO XLE"),
    ("finance", "Banks and finance", "Bankalar ve finans", "JPM BAC WFC C GS MS PNC USB SCHW V MA PYPL COIN HOOD"),
    ("health", "Health", "Sağlık", "LLY UNH JNJ PFE MRK ABBV NVO AZN CAH TMO ISRG"),
    ("consumer", "Consumer", "Tüketici", "TSLA COST WMT HD MCD NKE SBUX KO PEP DIS"),
    ("defense", "Defense", "Savunma", "LMT RTX NOC GD LHX AVAV KTOS"),
    ("index", "Index funds", "Endeks fonları", "SPY QQQ IWM DIA VOO VTI VGK"),
):
    for _s in _symbols.split():
        SECTORS[_s] = (_group, _en, _tr)


def sector_of(symbol: str) -> str:
    return SECTORS.get(symbol.upper(), ("other", "", ""))[0]


def sector_name(group: str, turkish: bool) -> str:
    for g, en, tr in SECTORS.values():
        if g == group:
            return tr if turkish else en
    return "Diğer" if turkish else "Other"


def sector_crowded(symbol: str, held: list[str], cap: int = MAX_PER_SECTOR) -> str | None:
    """The sector already holding `cap` positions, or None. "other" and index funds are never capped."""
    group = sector_of(symbol)
    if group in ("other", "index"):
        return None
    same = [s for s in held if s != symbol and sector_of(s) == group]
    return group if len(same) >= cap else None


# ------------------------------------------------------------------ Orion

def thesis(symbol: str, price: float, stop: float | None, target: float | None, reason: str,
           research=None, turkish: bool = False) -> dict:
    """Why this buy, what speaks against it, and the price where the idea is wrong."""
    def t(en: str, tr: str) -> str:
        return tr if turkish else en

    why = [reason]
    against: list[str] = []
    if research is not None:
        rep = getattr(research, "report", None)
        if rep is not None:
            passed = [c.kind for c in rep.checks if c.verdict == "PASS"]
            weak = [c.kind for c in rep.checks if c.verdict in ("WATCH", "FAIL")]
            why.append(t(f"Five checks {rep.score:.1f}/5 ({rep.decision}); passed: {', '.join(passed) or 'none'}.",
                         f"5 kontrol {rep.score:.1f}/5 ({rep.decision}); geçen: {', '.join(passed) or 'yok'}."))
            if weak:
                against.append(t(f"Weak checks: {', '.join(weak)}.", f"Zayıf kontroller: {', '.join(weak)}."))
        if research.daily_up is False:
            against.append(t("The daily chart is falling; the order was halved.",
                             "Günlük grafik düşüyor; emir yarıya indirildi."))
        elif research.daily_up:
            why.append(t("The daily chart is above its 50-day average.", "Günlük grafik 50 günlük ortalamanın üstünde."))
        if research.mood is not None:
            (why if research.mood >= 0 else against).append(
                t(f"News mood {research.mood:+.2f} over {research.news_count} items.",
                  f"Haber havası {research.mood:+.2f}, {research.news_count} haber."))
        for f in research.flags[:2]:
            against.append(t(f"Flag: {f.kind}.", f"Bayrak: {f.kind}."))
        if research.learned.evidence:
            e = research.learned.evidence[0]
            against.append(t(f"Past signals like this: {e.key} {e.value} averaged {e.avg_r:+.2f}R over {e.n:.0f}.",
                             f"Benzer geçmiş sinyaller: {e.key} {e.value}, {e.n:.0f} sonuçta ortalama {e.avg_r:+.2f}R."))
    if not against:
        against.append(t("No clear counterargument found; the stop-loss still limits the loss.",
                         "Açık bir karşı argüman yok; zarar durdur yine kaybı sınırlar."))
    rr = None
    if stop and target and price > stop:
        rr = (target - price) / (price - stop)
    return {
        "symbol": symbol,
        "at": time.time(),
        "price": round(price, 4),
        "why": why,
        "against": against,
        "invalid": t(f"The idea is wrong below {stop:,.2f} (the stop-loss).", f"Fiyat {stop:,.2f} altına inerse fikir yanlış (zarar durdur).")
        if stop else t("No stop-loss price is known.", "Zarar durdur fiyatı bilinmiyor."),
        "target": round(target, 4) if target else None,
        "reward_risk": round(rr, 2) if rr else None,
    }


# --------------------------------------------------------------- the desk

def report(engine, turkish: bool = False) -> dict:
    def t(en: str, tr: str) -> str:
        return tr if turkish else en

    brain = getattr(engine, "brain", None)
    reflex = getattr(engine, "reflex", None)
    now = time.time()
    with engine._lock:
        positions = [p.to_dict() for p in engine._positions.values()]
        held = list(engine._positions)
    watched = engine.watched_symbols()

    # Atlas: the big money
    atlas_items = []
    if brain is not None:
        rows = []
        for s in watched:
            a = brain.alt(s)
            ins, att = a.get("insiders_30d"), a.get("attention")
            if ins or (att and att >= 1.5):
                rows.append((ins or 0, att or 0, s))
        for ins, att, s in sorted(rows, reverse=True)[:6]:
            atlas_items.append(t(f"{s}: {ins} insider filings in 30 days" + (f", attention ×{att:.1f}" if att else ""),
                                 f"{s}: 30 günde {ins} içeriden bildirim" + (f", ilgi ×{att:.1f}" if att else "")))
    atlas = {"id": "atlas", "name": "Atlas", "role": t("Tracks the big money", "Büyük parayı izler"),
             "how": t("SEC Form 4 insider filings, 8-K events and unusual Wikipedia attention.",
                      "SEC Form 4 içeriden işlemler, 8-K olayları ve olağandışı Wikipedia ilgisi."),
             "stat": t(f"{len(atlas_items)} stocks with a signal", f"{len(atlas_items)} hissede sinyal"),
             "items": atlas_items or [t("Nothing unusual right now.", "Şu an olağandışı bir şey yok.")]}

    # Vega: the narrative
    vega_items, read = [], 0
    if reflex is not None:
        read = getattr(reflex, "read_total", 0)
        for d in list(reflex.decisions)[:6]:
            ideas = ", ".join(f"{i['symbol']} {'↑' if i['effect'] > 0 else '↓'}{i['confidence']:.0%}" for i in d.ideas[:3])
            vega_items.append(f"{(d.event or d.title)[:70]}" + (f" → {ideas}" if ideas else ""))
    vega = {"id": "vega", "name": "Vega", "role": t("Reads the narrative", "Hikâyeyi okur"),
            "how": t("Central banks, the White House, the SEC, company newsrooms and the news wire; the AI groups and rates them.",
                     "Merkez bankaları, Beyaz Saray, SEC, şirket haber odaları ve haber akışı; yapay zekâ gruplar ve puanlar."),
            "stat": t(f"{read:,} headlines read", f"{read:,} başlık okundu"),
            "items": vega_items or [t("No news judged yet.", "Henüz değerlendirilen haber yok.")]}

    # Orion: the theses
    theses = engine.theses()
    orion = {"id": "orion", "name": "Orion", "role": t("Builds the thesis", "Tezi kurar"),
             "how": t("For every buy: the reasons, the counterargument and the price where the idea is wrong.",
                      "Her alım için: nedenler, karşı argüman ve fikrin yanlış olduğu fiyat."),
             "stat": t(f"{len(theses)} theses", f"{len(theses)} tez"),
             "theses": theses[:6], "items": [] if theses else [t("No buy yet, so no thesis yet.", "Henüz alım yok, tez de yok.")]}

    # Titan: the entry
    counts = {"bought": 0, "watch": 0, "skip": 0}
    pending = 0
    if reflex is not None:
        day = now - 86400
        for d in reflex.decisions:
            if d.at < day:
                continue
            for o in d.outcome:
                if o["action"] in counts:
                    counts[o["action"]] += 1
        pending = len(reflex.pending)
    titan = {"id": "titan", "name": "Titan", "role": t("Times the entry", "Girişi zamanlar"),
             "how": t("An idea waits up to ten minutes for the price to agree: up a little, not a move that is already over.",
                      "Bir fikir, fiyat onaylayana kadar on dakikaya kadar bekler: biraz yükseliş, bitmiş bir hareket değil."),
             "stat": t(f"24h: {counts['bought']} entered, {counts['skip']} skipped, {pending} waiting",
                       f"24 saat: {counts['bought']} girildi, {counts['skip']} atlandı, {pending} bekliyor"),
             "items": [f"{p.idea.symbol}: {p.decision.title[:60]}" for p in (reflex.pending if reflex else [])][:5]}

    # Luna: the exits
    luna_items = []
    deadlines = dict(getattr(engine, "_news_deadline", {}))
    for p in positions:
        price = p.get("current_price") or p["entry_price"]
        stop, target = p.get("stop_loss"), p.get("take_profit")
        parts = [f"{p['symbol']} {p['unrealized_pnl_pct']:+.2f}%"]
        if stop:
            parts.append(t(f"stop {stop:,.2f} ({(stop / price - 1) * 100:+.1f}%)", f"stop {stop:,.2f} (%{(stop / price - 1) * 100:+.1f})"))
        if target:
            parts.append(t(f"target {target:,.2f} ({(target / price - 1) * 100:+.1f}%)", f"hedef {target:,.2f} (%{(target / price - 1) * 100:+.1f})"))
        if p["symbol"] in deadlines:
            parts.append(t(f"news limit in {(deadlines[p['symbol']] - now) / 3600:.0f}h", f"haber süresi {(deadlines[p['symbol']] - now) / 3600:.0f} sa"))
        luna_items.append(" · ".join(parts))
    exits: dict[str, int] = {}
    try:
        for tr in engine.repo.recent_trades(engine.mode, limit=50):
            exits[tr["exit_reason"]] = exits.get(tr["exit_reason"], 0) + 1
    except Exception:
        pass
    luna = {"id": "luna", "name": "Luna", "role": t("Knows when to exit", "Ne zaman çıkacağını bilir"),
            "how": t("Every buy has a stop-loss and a target; the stop trails a winner from +2%; news trades have a time limit.",
                     "Her alımın zarar durdur ve hedefi var; kazanan işlemde stop +%2'den sonra takip eder; haber işlemlerinin süresi var."),
            "stat": t(f"{len(positions)} open · last 50 exits: ", f"{len(positions)} açık · son 50 çıkış: ")
            + (", ".join(f"{k} {v}" for k, v in sorted(exits.items(), key=lambda kv: -kv[1])[:3]) or "—"),
            "items": luna_items or [t("Nothing open.", "Açık pozisyon yok.")]}

    # Nova: the veto
    blocked = engine.blocked_today()
    from app.engine.readiness import BLOCK_WORDS
    nova_items = [f"{v['count']}× " + (BLOCK_WORDS.get(k, BLOCK_WORDS["rules"])[1 if turkish else 0])
                  + (f" ({v.get('symbol')})" if v.get("symbol") else "")
                  for k, v in sorted(blocked.items(), key=lambda kv: -kv[1].get("count", 0))]
    groups: dict[str, int] = {}
    for s in held:
        groups[sector_of(s)] = groups.get(sector_of(s), 0) + 1
    exposure = ", ".join(f"{sector_name(g, turkish)} {n}" for g, n in groups.items()) or "—"
    try:
        snap = engine.risk.snapshot(engine.executor.get_balance().total)
        loss = t(f"daily loss used {snap['daily_loss_used_pct']:.0f}%", f"günlük zarar kullanımı %{snap['daily_loss_used_pct']:.0f}")
    except Exception:
        loss = ""
    nova = {"id": "nova", "name": "Nova", "role": t("Protects the desk", "Masayı korur"),
            "how": t(f"The final veto: risk per trade, the daily loss limit, the position cap, safety pauses, arming, "
                     f"and at most {MAX_PER_SECTOR} positions in one sector.",
                     f"Son veto: işlem başına risk, günlük zarar sınırı, pozisyon sınırı, güvenlik molaları, kurma "
                     f"ve bir sektörde en fazla {MAX_PER_SECTOR} pozisyon."),
            "stat": t(f"Today vetoed {sum(v.get('count', 0) for v in blocked.values())} · {loss} · sectors: {exposure}",
                      f"Bugün {sum(v.get('count', 0) for v in blocked.values())} veto · {loss} · sektörler: {exposure}"),
            "items": nova_items or [t("No veto today.", "Bugün veto yok.")]}

    return {"agents": [atlas, vega, orion, titan, luna, nova],
            "note": t("Each agent is a part of the bot. Nova always has the last word. No agent can arm real money.",
                      "Her ajan botun bir parçasıdır. Son söz her zaman Nova'nındır. Hiçbir ajan gerçek parayı kuramaz.")}
