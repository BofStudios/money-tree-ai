"""How the engine starts.

Since 9.0 there is one app, Money Tree, with two modes the owner picks on
the Modes screen: Balanced (the portfolio books) and Ultra (the one-minute
trader, app/engine/scalper.py). The engine switches at run time
(PortfolioEngine.set_ultra); the choice is kept in the brain's settings.

STYLE only says how the engine starts before that choice is read:
"portfolio" always for a build. A source run may set MONEYTREE_STYLE=scalp
(the tests do). The 8.0 "scalp" build flag is read as portfolio.
"""
from __future__ import annotations

import os

STYLE = os.environ.get("MONEYTREE_STYLE") or "portfolio"
if STYLE not in ("portfolio", "scalp"):
    STYLE = "portfolio"
SCALP = STYLE == "scalp"
