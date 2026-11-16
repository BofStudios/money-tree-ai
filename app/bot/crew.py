"""The crew: seven names for seven jobs the bot does.

Six of them are the desk's agents (app/engine/desk.py); Rigel is new and owns
the research: Lab runs, the edge list, what the swarm learned.
"""
from __future__ import annotations

# id, name, role, (English, Turkish) label
CREW: tuple[tuple[str, str, str, tuple[str, str]], ...] = (
    ("orion", "Orion", "planner", ("Plans", "Planlar")),
    ("atlas", "Atlas", "scout", ("Scans", "Tarar")),
    ("vega", "Vega", "news", ("Reads the news", "Haberi okur")),
    ("titan", "Titan", "trader", ("Trades", "İşlem yapar")),
    ("luna", "Luna", "exits", ("Exits", "Çıkışı yönetir")),
    ("nova", "Nova", "risk", ("Guards", "Korur")),
    ("rigel", "Rigel", "research", ("Researches", "Araştırır")),
)
IDS = tuple(c[0] for c in CREW)

# The only verbs a log line may carry: the page ties a label to each.
VERBS = (
    "scan", "signal", "news", "thesis", "wait", "order", "fill", "partial", "exit", "stop", "target",
    "veto", "pause", "resume", "arm", "disarm", "plan", "lab", "learn", "error", "note",
)
LEVELS = ("info", "good", "bad", "warn", "error")
ORDER_VERBS = ("order", "fill", "partial", "exit", "stop", "target")
RISK_VERBS = ("veto", "pause", "resume", "arm", "disarm")

# A finished step of this kind (app/common/activity.py) belongs to this agent.
STEP_OWNER: dict[str, tuple[str, str]] = {
    "bars": ("atlas", "scan"),
    "analyse": ("orion", "signal"),
    "news": ("vega", "news"),
    "order": ("titan", "order"),
    "approval": ("titan", "wait"),
    "wait": ("titan", "wait"),
    "sell": ("luna", "exit"),
    "trail": ("luna", "note"),
    "positions": ("luna", "note"),
    "ai": ("orion", "plan"),
    "warn": ("nova", "note"),
    "clock": ("nova", "note"),
    "account": ("nova", "note"),
    "learn": ("rigel", "learn"),
    "research": ("rigel", "lab"),
    "info": ("orion", "note"),
}
