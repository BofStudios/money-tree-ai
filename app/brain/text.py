"""Reading headlines without a network: a finance word list, topics and red flags.

The same lists as the phone app, so a headline scores the same on both. Small
and transparent on purpose — the screen highlights exactly the words that
moved a score.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

POSITIVE = {
    "beat": 1.0, "beats": 1.0, "tops": 1.0, "topped": 1.0, "surge": 1.0, "surges": 1.0, "surged": 1.0,
    "soar": 1.0, "soars": 1.0, "soared": 1.0, "jump": 0.8, "jumps": 0.8, "jumped": 0.8, "rally": 0.8,
    "rallies": 0.8, "rallied": 0.8, "record": 0.6, "upgrade": 1.0, "upgrades": 1.0, "upgraded": 1.0,
    "outperform": 0.8, "outperforms": 0.8, "raises": 0.7, "raised": 0.6, "strong": 0.7, "stronger": 0.7,
    "strongest": 0.7, "growth": 0.5, "grows": 0.6, "grew": 0.6, "gain": 0.6, "gains": 0.6, "gained": 0.6,
    "rise": 0.5, "rises": 0.5, "rose": 0.5, "rising": 0.4, "higher": 0.4, "bullish": 0.9, "rebound": 0.7,
    "rebounds": 0.7, "boost": 0.7, "boosts": 0.7, "boosted": 0.7, "wins": 0.7, "won": 0.5, "approval": 0.8,
    "approves": 0.8, "approved": 0.8, "breakthrough": 0.9, "exceeds": 0.9, "exceeded": 0.9, "accelerates": 0.7,
    "accelerating": 0.6, "expands": 0.5, "expansion": 0.4, "buyback": 0.6, "upbeat": 0.8, "optimistic": 0.7,
    "robust": 0.6, "solid": 0.5, "momentum": 0.4, "partnership": 0.4, "launches": 0.3, "profitable": 0.6,
    "climbs": 0.6, "climbed": 0.6, "highs": 0.5, "doubles": 0.6, "dividend": 0.3, "recovers": 0.6,
}
NEGATIVE = {
    "miss": 1.0, "misses": 1.0, "missed": 1.0, "plunge": 1.0, "plunges": 1.0, "plunged": 1.0,
    "slump": 0.9, "slumps": 0.9, "slumped": 0.9, "tumble": 0.9, "tumbles": 0.9, "tumbled": 0.9,
    "fall": 0.6, "falls": 0.6, "fell": 0.6, "falling": 0.6, "drop": 0.6, "drops": 0.6, "dropped": 0.6,
    "sink": 0.8, "sinks": 0.8, "sank": 0.8, "slide": 0.6, "slides": 0.6, "slid": 0.6,
    "downgrade": 1.0, "downgrades": 1.0, "downgraded": 1.0, "cut": 0.6, "cuts": 0.6, "lowers": 0.7,
    "lowered": 0.7, "weak": 0.8, "weaker": 0.8, "weakness": 0.8, "warning": 0.9, "warns": 0.9, "warned": 0.9,
    "lawsuit": 0.8, "sues": 0.7, "sued": 0.7, "probe": 0.7, "investigation": 0.7, "fraud": 1.0, "recall": 0.8,
    "recalls": 0.8, "layoffs": 0.6, "halt": 0.9, "halted": 0.9, "delay": 0.5, "delays": 0.5, "delayed": 0.5,
    "bankruptcy": 1.0, "bankrupt": 1.0, "default": 0.9, "decline": 0.6, "declines": 0.6, "declined": 0.6,
    "loss": 0.6, "losses": 0.6, "loses": 0.6, "bearish": 0.9, "selloff": 0.8, "concern": 0.5, "concerns": 0.5,
    "fears": 0.6, "worries": 0.6, "antitrust": 0.6, "fined": 0.8, "penalty": 0.7, "subpoena": 0.8,
    "dilution": 0.8, "crash": 1.0, "crashes": 1.0, "slowdown": 0.7, "slowing": 0.5, "underperform": 0.8,
    "disappoints": 0.9, "disappointing": 0.9, "disappointed": 0.8, "shortfall": 0.8, "headwinds": 0.6,
    "tariffs": 0.4, "ban": 0.6, "banned": 0.7, "lawsuits": 0.8, "slashes": 0.9, "plummets": 1.0,
    "plummeted": 1.0, "retreats": 0.5, "lows": 0.5, "sell-off": 0.8,
}
NEGATORS = {"not", "no", "never", "without", "fails", "failed", "fail"}

_TOKEN = re.compile(r"[^a-z0-9'-]+")


@dataclass(frozen=True)
class Hit:
    word: str
    weight: float


def tokens(text: str) -> list[str]:
    return [t for t in _TOKEN.split(text.lower()) if t]


def hits(text: str) -> list[Hit]:
    """The words that moved a score: positive weights good, negative bad.
    "not", "no" or "fails" flips the next two words."""
    out: list[Hit] = []
    flip = 0
    for t in tokens(text):
        if t in NEGATORS:
            flip = 2
            continue
        w = POSITIVE.get(t)
        if w is None and t in NEGATIVE:
            w = -NEGATIVE[t]
        if w is not None:
            out.append(Hit(t, -w if flip > 0 else w))
        if flip > 0:
            flip -= 1
    return out


def score(headline: str, summary: str = "") -> float:
    """−1 (bad) to +1 (good). The headline counts twice, the summary once."""
    pos = neg = 0.0
    for text, weight in ((headline, 2.0), (summary, 1.0)):
        for h in hits(text):
            if h.weight > 0:
                pos += h.weight * weight
            else:
                neg += -h.weight * weight
    return (pos - neg) / (pos + neg + 1.0)


# Whole words and phrases only: "chip" must not match "Chipotle".
TOPICS: dict[str, list[str]] = {
    "EARNINGS": ["earnings", "results", "estimates", "sales", "quarter", "quarterly", "eps", "revenue", "guidance", "outlook", "forecast", "profit", "profits"],
    "AI_CHIPS": ["ai", "artificial intelligence", "gpu", "gpus", "chip", "chips", "chipmaker", "semiconductor", "semiconductors", "data center", "data centers"],
    "CLOUD": ["cloud", "azure", "aws", "enterprise", "saas", "software", "subscription", "subscriptions"],
    "PRODUCT": ["launch", "launches", "unveil", "unveils", "release", "releases", "iphone", "product", "products", "device", "vehicle", "feature"],
    "ANALYSTS": ["upgrade", "upgrades", "downgrade", "downgrades", "price target", "analyst", "analysts", "rating", "overweight", "underweight", "outperform"],
    "DEALS": ["acquire", "acquires", "acquisition", "merger", "deal", "stake", "partnership", "invest", "invests", "buyout", "takeover"],
    "CAPITAL": ["buyback", "dividend", "offering", "bond", "bonds", "notes", "stock split", "repurchase", "debt"],
    "LEGAL": ["lawsuit", "lawsuits", "sued", "sues", "court", "settlement", "verdict", "litigation", "judge", "jury"],
    "REGULATION": ["antitrust", "regulator", "regulators", "ftc", "doj", "european commission", "sec", "probe", "investigation", "fine", "fined"],
    "SUPPLY": ["supply", "supply chain", "shortage", "factory", "production", "export", "exports", "tariff", "tariffs", "inventory"],
    "MACRO": ["fed", "federal reserve", "inflation", "interest rate", "interest rates", "jobs report", "cpi", "economy", "recession", "treasury"],
    "LEADERSHIP": ["ceo", "cfo", "chief executive", "steps down", "resigns", "appoints", "board", "founder"],
}


def topics(text: str) -> set[str]:
    t = " " + re.sub(r"[^a-z0-9]+", " ", text.lower()) + " "
    return {name for name, words in TOPICS.items() if any(f" {w} " in t for w in words)}


# kind -> (severe, hours it stays fresh)
FLAG_KINDS: dict[str, tuple[bool, int]] = {
    "HALT": (True, 72), "BANKRUPTCY": (True, 72), "FRAUD": (True, 72), "DELISTING": (True, 72),
    "OFFERING": (True, 72), "ACCOUNTING": (True, 96), "GUIDANCE_CUT": (False, 48), "EARNINGS_SOON": (False, 36),
    "REGULATOR": (False, 48), "RECALL": (False, 48),
}

FLAG_PATTERNS: dict[str, list[str]] = {
    "HALT": ["trading halt", "halts trading", "trading halted", "halted trading"],
    "BANKRUPTCY": ["bankruptcy", "chapter 11", "insolvency", "insolvent"],
    "FRAUD": ["accused of fraud", "fraud charges", "securities fraud", "fraud allegations", "accounting fraud",
              "charged with fraud", "accounting irregular", "restates earnings", "restatement", "sec charges", "charged by the sec"],
    "DELISTING": ["delist"],
    "OFFERING": ["public offering", "secondary offering", "stock offering", "share offering",
                 "at-the-market offering", "prices offering", "dilutive offering"],
    "GUIDANCE_CUT": ["cuts guidance", "lowers guidance", "lowered guidance", "cut its guidance", "slashes forecast",
                     "cuts forecast", "lowers outlook", "cuts outlook", "profit warning", "warns on profit", "cuts full-year"],
    "EARNINGS_SOON": ["earnings preview", "ahead of earnings", "earnings on deck", "to report earnings",
                      "earnings tomorrow", "reports after the bell", "reports before the bell", "what to expect from", "earnings scheduled"],
    "REGULATOR": ["antitrust", "subpoena", "regulators probe", "opens probe", "launches probe",
                  "under investigation", "opens investigation", "launches investigation"],
    "RECALL": ["recall"],
}


def severe(kind: str) -> bool:
    return FLAG_KINDS.get(kind, (False, 0))[0]


def flag_hours(kind: str) -> int:
    return FLAG_KINDS.get(kind, (False, 48))[1]


def blocks_buys(kind: str) -> bool:
    """Whether a fresh flag of this kind alone keeps the bot from buying."""
    return severe(kind) or kind in ("GUIDANCE_CUT", "EARNINGS_SOON")


def red_flags(headline: str, summary: str = "") -> list[str]:
    text = (headline + " " + summary).lower()
    return [kind for kind, patterns in FLAG_PATTERNS.items() if any(p in text for p in patterns)]
