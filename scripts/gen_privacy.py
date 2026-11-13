"""Write PRIVACY.md, PRIVACY.tr.md and app/web/static/privacy.html from app/privacy/docs.py.

    python scripts/gen_privacy.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.privacy.docs import outputs  # noqa: E402

for path, text in outputs().items():
    path.write_text(text, encoding="utf-8", newline="\n")
    print("wrote", path.name)
