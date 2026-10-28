"""Which bot this copy is.

portfolio  Money Tree (7.0): three books, the bot decides the horizon.
scalp      Money Ter Ter Ter (8.0): one-minute candles, a look every ten
           seconds, in and out within minutes, flat before the close
           (app/engine/scalper.py).

An exe carries it in app/_build.py (scripts/build_exe.py --scalp); a source
run reads MONEYTREE_STYLE. Both share the same data home and keys.
"""
from __future__ import annotations

import os

from app import _build

STYLE = os.environ.get("MONEYTREE_STYLE") or getattr(_build, "STYLE", "portfolio")
SCALP = STYLE == "scalp"
