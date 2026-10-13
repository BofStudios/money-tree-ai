"""The Memory card: what the bot knows now that it did not know on day one.

Everything here is counted from what the parts already keep (the journal,
the swarm, the learner, the news memory, the trade history). The level is a
plain summary of that experience, so the owner can see the bot grow; it does
not change how the bot trades.
"""
from __future__ import annotations

import math
import time
from datetime import datetime

XP_PER_LEVEL = 100.0


def level_for(xp: float) -> tuple[int, float, float]:
    """(level, xp into this level, xp this level needs)."""
    level = int(math.sqrt(max(xp, 0.0) / XP_PER_LEVEL)) + 1
    low = XP_PER_LEVEL * (level - 1) ** 2
    high = XP_PER_LEVEL * level ** 2
    return level, xp - low, high - low


def report(engine, turkish: bool = False) -> dict:
    def t(en: str, tr: str) -> str:
        return tr if turkish else en

    journal = getattr(engine, "journal", None)
    brain = getattr(engine, "brain", None)
    reflex = getattr(engine, "reflex", None)
    now = time.time()
    j = journal.snapshot() if journal is not None else {"first_start": None, "starts": 0, "uptime": 0.0,
                                                          "days": 0, "counters": {}, "events": [], "level": 0}
    counters = j["counters"]

    swarm = brain.swarm.lifetime() if brain is not None else {}
    if journal is not None and swarm:
        journal.set_max("strategies_tested", swarm.get("tested", 0))
    samples = list(brain.learner.samples) if brain is not None else []
    rules = brain.learner.rules() if brain is not None else []
    news = reflex.memory.totals() if reflex is not None and getattr(reflex, "memory", None) else {}
    read = getattr(reflex, "read_total", 0) if reflex is not None else 0
    try:
        trades = engine.repo.trade_stats(engine.mode)["total_trades"]
    except Exception:
        trades = 0

    # The first day: the oldest thing any part remembers.
    starts = [x for x in [j.get("first_start")] + [s.at for s in samples[:1]] +
              [p.at for p in (brain.swarm.history[-1:] if brain is not None else [])] if x]
    first = min(starts) if starts else now
    sample_days = {datetime.fromtimestamp(s.at).strftime("%Y-%m-%d") for s in samples if s.at}
    days_open = max(int(j.get("days", 0)), len(sample_days), 1)

    looks = counters.get("looks", 0)
    tested = max(swarm.get("tested", 0), counters.get("strategies_tested", 0))
    promotions = swarm.get("promotions", 0)
    xp = (40 * days_open + 60 * math.log10(1 + looks) + 60 * math.log10(1 + read)
          + 100 * math.log10(1 + tested) + 120 * promotions + 3 * len(samples) + 30 * len(rules)
          + 4 * news.get("graded", 0) + 15 * trades)
    level, into, need = level_for(xp)
    if journal is not None and level > j.get("level", 0):
        if j.get("level", 0):
            journal.event("level", t(f"Reached level {level}", f"Seviye {level} oldu"))
        journal.level = level

    facts = [
        {"key": "age", "value": max(int((now - first) // 86400), days_open),
         "label": t("days of learning", "gündür öğreniyor")},
        {"key": "tested", "value": int(tested), "label": t("strategies tested by the bots", "botların denediği strateji")},
        {"key": "promotions", "value": int(promotions), "label": t("times it found a better strategy", "kez daha iyi strateji buldu")},
        {"key": "samples", "value": len(samples), "label": t("buy signals followed to the end", "sonuna kadar izlenen alım sinyali")},
        {"key": "rules", "value": len(rules), "label": t("rules learned from results", "sonuçlardan öğrenilen kural")},
        {"key": "read", "value": int(read), "label": t("headlines read", "okunan başlık")},
        {"key": "graded", "value": int(news.get("graded", 0)), "label": t("news checked against the real price", "gerçek fiyatla karşılaştırılan haber")},
        {"key": "looks", "value": int(looks), "label": t("looks at the market", "piyasaya bakış")},
        {"key": "trades", "value": int(trades), "label": t("finished trades", "biten işlem")},
    ]
    return {
        "level": level,
        "xp": round(xp),
        "into": round(into),
        "need": round(need),
        "progress": round(into / need, 3) if need else 0.0,
        "first_day": first,
        "days_open": days_open,
        "starts": j.get("starts", 0),
        "uptime_hours": round(j.get("uptime", 0.0) / 3600, 1),
        "facts": facts,
        "growth": j.get("events", [])[:40],
        "news_lessons": reflex.memory.lessons(turkish)[:10] if news else [],
        "rules": [r.to_dict() for r in rules][:8],
        "news_waiting": news.get("waiting", 0),
    }
