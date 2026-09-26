"""What the app knows about how this person wants to be talked to.

Built during onboarding and editable afterwards. Two rules shape it:

* **Nothing is inferred silently.** Every field here was either chosen by the
  user or left at an explicit default. Settings shows the whole file, so there
  is no hidden profile being assembled behind their back.
* **"I don't know" is a real answer**, stored as `unknown` rather than coerced
  into a guess. The AI reads `unknown` as "explain this as we go", which is the
  behaviour a beginner actually needs.
"""
from __future__ import annotations

import json
import logging
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

# Every answer a question may carry. "unknown" is deliberately in each set.
CHOICES = {
    "goal": ["explore", "track", "opportunities", "learn", "analyze", "unknown"],
    "horizon": ["days", "weeks", "months", "1_3_years", "3_plus_years", "unknown"],
    "focus": ["growth", "stability", "dividends", "value", "momentum", "quality", "unknown"],
    "volatility": ["low", "moderate", "high", "unknown"],
    "detail": ["simple", "balanced", "deep", "everything"],
    "technical_level": ["beginner", "intermediate", "advanced"],
    "research_depth": ["quick", "standard", "deep", "full"],
    "attention": [
        "growth", "profitability", "valuation", "debt", "cash_flow", "dividends",
        "momentum", "news", "competition", "risks", "earnings", "ownership", "unknown",
    ],
    "language": ["en", "tr"],
    "tone": ["concise", "balanced", "detailed"],
    # These two drive the trading bot itself, not just how the AI talks:
    # horizon picks the candle size, autonomy who approves a buy.
    "trading_horizon": ["short", "medium", "long", "unknown"],
    "autonomy": ["manual", "semi", "full", "unknown"],
}

DEFAULTS = {
    "goal": "unknown",
    "horizon": "unknown",
    "focus": [],
    "volatility": "unknown",
    "detail": "balanced",
    "technical_level": "beginner",
    "research_depth": "standard",
    "attention": [],
    "language": "en",
    "tone": "balanced",
    "advanced_mode": False,
    "onboarded": False,
    "trading_horizon": "unknown",
    "autonomy": "unknown",
}

MULTI = ("focus", "attention")


@dataclass
class UserProfile:
    goal: str = "unknown"
    horizon: str = "unknown"
    focus: list[str] = field(default_factory=list)
    volatility: str = "unknown"
    detail: str = "balanced"
    technical_level: str = "beginner"
    research_depth: str = "standard"
    attention: list[str] = field(default_factory=list)
    language: str = "en"
    tone: str = "balanced"
    advanced_mode: bool = False
    onboarded: bool = False
    trading_horizon: str = "unknown"
    autonomy: str = "unknown"

    def to_dict(self) -> dict:
        return asdict(self)

    def as_prompt(self) -> str:
        """The profile as instructions the model can act on.

        Written as behaviour rather than data — "keep explanations short" lands
        better than "detail: simple" — and every `unknown` becomes an explicit
        instruction to explain rather than assume.
        """
        lines = []

        horizons = {
            "days": "holds positions for days",
            "weeks": "holds positions for weeks",
            "months": "holds positions for months",
            "1_3_years": "invests on a one to three year view",
            "3_plus_years": "invests on a horizon of three years or more",
        }
        if self.horizon in horizons:
            lines.append(f"They {horizons[self.horizon]}.")
        elif self.horizon == "unknown":
            lines.append("They have not settled on a holding period; do not assume one.")

        if self.focus:
            named = [f for f in self.focus if f != "unknown"]
            if named:
                lines.append("They care most about: " + ", ".join(named) + ".")

        volatility = {
            "low": "They are uncomfortable with large price swings — flag volatility clearly.",
            "moderate": "They accept moderate price swings.",
            "high": "They are comfortable with large price swings.",
        }
        if self.volatility in volatility:
            lines.append(volatility[self.volatility])

        levels = {
            "beginner": (
                "They are new to markets. Explain any financial term the first time "
                "you use it, in the same sentence. Never assume they know what a "
                "ratio means."
            ),
            "intermediate": "They know the common metrics but appreciate a short reminder of the unusual ones.",
            "advanced": "They are comfortable with technical and financial terminology; skip basic definitions.",
        }
        lines.append(levels.get(self.technical_level, levels["beginner"]))

        detail = {
            "simple": "Keep answers short and plain. Lead with the conclusion.",
            "balanced": "Give a readable answer with the key supporting numbers.",
            "deep": "Go into detail, including the numbers behind each judgement.",
            "everything": "Be thorough and show your reasoning across every section.",
        }
        lines.append(detail.get(self.detail, detail["balanced"]))

        if self.attention:
            named = [a for a in self.attention if a != "unknown"]
            if named:
                lines.append("When researching, pay particular attention to: " + ", ".join(named) + ".")

        if self.language == "tr":
            lines.append(
                "Reply in Turkish, using natural Turkish financial language rather "
                "than a literal translation of English terms."
            )

        return "\n".join(f"- {line}" for line in lines)


class ProfileStore:
    """Reads and writes the profile as one small JSON file."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self._profile = self._load()

    def _load(self) -> UserProfile:
        if not self.path.exists():
            return UserProfile()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            log.exception("could not read the user profile; starting fresh")
            return UserProfile()
        return self._coerce(raw)

    @staticmethod
    def _coerce(raw: dict) -> UserProfile:
        """Accept only values we recognise, so a hand-edited file cannot break the app."""
        clean = dict(DEFAULTS)
        for key, default in DEFAULTS.items():
            value = raw.get(key, default)
            if key in MULTI:
                allowed = CHOICES[key]
                clean[key] = [v for v in value if v in allowed] if isinstance(value, list) else []
            elif isinstance(default, bool):
                clean[key] = bool(value)
            elif key in CHOICES:
                clean[key] = value if value in CHOICES[key] else default
            else:
                clean[key] = value
        return UserProfile(**clean)

    def get(self) -> UserProfile:
        with self._lock:
            return UserProfile(**self._profile.to_dict())

    def update(self, changes: dict) -> UserProfile:
        with self._lock:
            merged = self._profile.to_dict()
            for key, value in (changes or {}).items():
                if key in DEFAULTS:
                    merged[key] = value
            self._profile = self._coerce(merged)
            self._save()
            return UserProfile(**self._profile.to_dict())

    def reset(self) -> UserProfile:
        with self._lock:
            self._profile = UserProfile()
            self._save()
            return self._profile

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._profile.to_dict(), indent=2), encoding="utf-8")
            tmp.replace(self.path)
        except Exception:
            log.exception("could not save the user profile")
