"""The words the owner can type to stop or start the bot.

They never go to the AI. A model can write "I stopped the bot" and do nothing,
so the commands that touch money are matched here and done here.

Stop is matched generously, because stopping by mistake costs nothing. Start
is matched only on the exact phrases below, because starting by mistake can.
"""
from __future__ import annotations

import re

STOP_PHRASES = {
    "stop", "halt", "pause", "stop bot", "stop the bot", "stop trading", "stop it", "stop now",
    "stop buying", "stop everything", "kill", "kill it",
    "dur", "durdur", "durdur botu", "botu durdur", "bot dur", "dur bot", "botu kapat", "kapat",
    "işlemi durdur", "işlemleri durdur", "alımı durdur", "hemen durdur", "dur artık", "durdur hemen",
}
START_PHRASES = {
    "start", "resume", "start bot", "start the bot", "start trading",
    "başlat", "botu başlat", "başla", "devam", "devam et", "işleme başla",
}
_STOP_WORDS = {"stop", "halt", "durdur", "dur"}
_QUESTION_WORDS = {"why", "when", "did", "does", "neden", "niye", "ne", "mi", "mı", "mu", "mü", "nasıl"}


def normalise(text: str) -> str:
    text = text.replace("İ", "i").replace("I", "ı") if _turkish_caps(text) else text
    text = text.lower().replace("i̇", "i")
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())


def _turkish_caps(text: str) -> bool:
    return any(c in text for c in "İŞĞÜÖÇ")


def command(text: str) -> str | None:
    """"stop", "start" or None."""
    t = normalise(text)
    if not t:
        return None
    if t in STOP_PHRASES:
        return "stop"
    if t in START_PHRASES:
        return "start"
    words = t.split()
    if len(words) <= 4 and words[0] in _STOP_WORDS and not _QUESTION_WORDS & set(words):
        return "stop"
    return None
