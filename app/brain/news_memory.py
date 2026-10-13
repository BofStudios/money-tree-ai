"""What past news did to prices: the news reflex's own track record.

Every idea the reflex weighs while the market is open — bought, skipped or
below the bar — is written down as a case: the stock, the kind of news (an
analyst upgrade, a contract, a tariff theme...), which way the reflex expected
the price to go, and when the news came out. Later the grader looks at the
price two trading hours and one trading day after the news.

Over weeks this becomes a table: for each kind of news, how often the price
went the expected way and by how much. The reflex then trusts each kind more
or less — at most 30% either way, and only after enough cases — and the AI
sees the table before it judges a new headline. That is how the bot gets
better the longer it runs.

Nothing here can start a buy. It only moves confidence; every buy still needs
the price to agree, the risk rules, arming and the position caps.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

import numpy as np

log = logging.getLogger(__name__)

MAX_CASES = 3000
MIN_CASES = 4            # trust stays 1.0 below this
MAX_SHIFT = 0.30         # trust moves confidence at most this much either way
SHRINK = 12              # cases before the record counts in full
FULL_MOVE = 1.0          # an average move of this many % (the expected way) counts as full evidence
BARS_2H, BARS_1D = 8, 26  # 15-minute bars: two trading hours, one trading day
GRADE_EVERY = 60.0
GRADE_SYMBOLS = 4        # price fetches per grading round

# Kinds of company news, first match wins. (key, pattern, English, Turkish)
KINDS: tuple[tuple[str, str, str, str], ...] = (
    ("halt", r"\bhalt(ed|s)?\b|circuit breaker", "Trading halt", "İşlem durdurma"),
    ("downgrade", r"\bdowngrade[sd]?\b|(cuts?|lowers?|reduces?) (its )?(price target|pt\b)|price target (cut|lowered)",
     "Analyst downgrade", "Analist not düşürmesi"),
    ("upgrade", r"\bupgrade[sd]?\b|(raises?|boosts?|lifts?) (its )?(price target|pt\b)|price target raised|"
                r"initiates? .{0,40}\b(buy|outperform|overweight)\b", "Analyst upgrade", "Analist not yükseltmesi"),
    ("guidance_down", r"(cuts?|lowers?|slashes?|withdraws?|reduces?) (its )?(\S+ )?(guidance|outlook|forecast)",
     "Guidance cut", "Tahmin düşürüldü"),
    ("guidance_up", r"(raises?|boosts?|lifts?|increases?) (its )?(\S+ )?(guidance|outlook|forecast)",
     "Guidance raised", "Tahmin yükseltildi"),
    ("miss", r"\bmiss(es|ed)?\b|falls? short|below (estimates|expectations)|worse.than.expected",
     "Results miss", "Beklentinin altında sonuç"),
    ("beat", r"\bbeats?\b|\btops? (estimates|expectations)|record (revenue|quarter|results|sales)|better.than.expected",
     "Results beat", "Beklentiyi aşan sonuç"),
    ("offering", r"\boffering\b|private placement|dilut|convertible (notes|senior)", "Share offering", "Hisse arzı"),
    ("legal", r"lawsuit|\bsued\b|investigation|\bprobe\b|subpoena|recall|fraud|charges", "Legal trouble", "Hukuki sorun"),
    ("approval", r"\bfda\b.{0,40}(approv|clear)|\bapprov(al|es|ed)\b|clearance|authoriz", "Approval", "Onay"),
    ("deal", r"\bacquir|\bto buy\b|\bmerger\b|takeover|buyout", "Merger or takeover", "Birleşme ya da satın alma"),
    ("contract", r"\bcontract\b|\bawarded\b|\border (for|worth)\b|\bwins?\b.{0,40}\b(deal|order)", "Contract won",
     "Kazanılan sözleşme"),
    ("buyback", r"buyback|repurchase|(raises?|increases?) (its )?(quarterly )?dividend|special dividend",
     "Buyback or dividend", "Geri alım ya da temettü"),
    ("leadership", r"\bceo\b|\bcfo\b|resign|steps? down|appoint", "Leadership change", "Yönetim değişikliği"),
    ("partnership", r"partner(ship|s with)|collaborat|teams? up|alliance", "Partnership", "Ortaklık"),
    ("product", r"\blaunch|unveil|introduc", "Product launch", "Ürün lansmanı"),
)
_COMPILED = [(k, re.compile(p, re.I), en, tr) for k, p, en, tr in KINDS]
LABELS = {k: (en, tr) for k, _, en, tr in KINDS} | {"company": ("Other company news", "Diğer şirket haberi")}


def kind_of(title: str) -> str:
    for key, pattern, _, _ in _COMPILED:
        if pattern.search(title or ""):
            return key
    return "company"


def label(kind: str, turkish: bool = False) -> str:
    if kind.startswith("theme:"):
        from app.brain import ripples

        key = kind.split(":", 1)[1]
        theme = next((t for t in ripples.THEMES if t.key == key), None)
        if theme is not None:
            return (theme.name_tr if turkish else theme.name) + (" (dalga)" if turkish else " (ripple)")
        return key
    en, tr = LABELS.get(kind, (kind, kind))
    return tr if turkish else en


@dataclass
class Case:
    id: str
    symbol: str
    kind: str
    effect: int              # +1 expected up, -1 expected down
    confidence: float
    published: float
    source: str = ""
    bought: bool = False
    entry: float | None = None
    r2h: float | None = None     # % move the expected way, two trading hours later
    r1d: float | None = None     # % move the expected way, one trading day later
    done: bool = False
    noted_at: float = 0.0

    @property
    def score(self) -> float | None:
        return self.r1d if self.r1d is not None else self.r2h


class NewsMemory:
    def __init__(self, path: Path | None, data=None, now: Callable[[], float] = time.time) -> None:
        self.path = path
        self.data = data
        self._now = now
        self._lock = threading.RLock()
        self.cases: list[Case] = []
        self._graded_at = 0.0
        self.on_lesson: Callable[[str, dict], None] | None = None
        self._announced: dict[str, int] = {}      # kind -> case count when last announced
        self._load()

    # ----------------------------------------------------------- record

    def note(self, symbol: str, kind: str, effect: int, confidence: float, published: float,
             source: str = "", bought: bool = False) -> None:
        if effect not in (1, -1) or not re.fullmatch(r"[A-Z]{1,5}", symbol or ""):
            return
        cid = f"{symbol}|{kind}|{int(published)}"
        with self._lock:
            for c in self.cases:
                if c.id == cid:
                    c.bought = c.bought or bought
                    c.confidence = max(c.confidence, confidence)
                    return
            self.cases.append(Case(cid, symbol, kind, effect, round(float(confidence), 3), float(published),
                                   source[:40], bought, noted_at=self._now()))
            if len(self.cases) > MAX_CASES:
                graded = [c for c in self.cases if c.done]
                drop = graded[: len(self.cases) - MAX_CASES] or self.cases[: len(self.cases) - MAX_CASES]
                ids = {c.id for c in drop}
                self.cases = [c for c in self.cases if c.id not in ids]

    def mark_bought(self, symbol: str, published: float) -> None:
        with self._lock:
            for c in self.cases:
                if c.symbol == symbol and abs(c.published - published) < 1:
                    c.bought = True

    # ------------------------------------------------------------ grade

    def grade(self, force: bool = False) -> int:
        """Look at the price after older cases. Returns how many got a result."""
        now = self._now()
        if self.data is None or (not force and now - self._graded_at < GRADE_EVERY):
            return 0
        self._graded_at = now
        with self._lock:
            due = [c for c in self.cases if not c.done and now - c.published > 2.5 * 3600]
        by_symbol: dict[str, list[Case]] = {}
        for c in sorted(due, key=lambda c: c.published):
            by_symbol.setdefault(c.symbol, []).append(c)
        graded = 0
        for symbol in list(by_symbol)[:GRADE_SYMBOLS]:
            try:
                bars = self.data.get_ohlcv(symbol, "15m", limit=400)
            except Exception as exc:
                log.debug("could not grade %s: %s", symbol, exc)
                continue
            for c in by_symbol[symbol]:
                if self._grade_one(c, bars, now):
                    graded += 1
        if graded:
            self._check_lessons()
            self.save()
        return graded

    def _grade_one(self, c: Case, bars, now: float) -> bool:
        if bars is None or len(bars) < 2:
            if now - c.published > 10 * 86400:
                c.done = True
            return False
        stamps = np.array([t.timestamp() for t in bars.index])
        after = np.nonzero(stamps >= c.published - 60)[0]
        if not len(after):
            return False
        i = int(after[0])
        if stamps[0] > c.published:          # the news is older than the candles we have
            c.done = True
            return False
        entry = float(bars["open"].iloc[i])
        if entry <= 0:
            c.done = True
            return False
        changed = False
        c.entry = entry
        if c.r2h is None and i + BARS_2H < len(bars):
            c.r2h = round(c.effect * (float(bars["close"].iloc[i + BARS_2H]) / entry - 1) * 100, 3)
            changed = True
        if c.r1d is None and i + BARS_1D < len(bars):
            c.r1d = round(c.effect * (float(bars["close"].iloc[i + BARS_1D]) / entry - 1) * 100, 3)
            c.done = True
            changed = True
        if not c.done and now - c.published > 10 * 86400:
            c.done = True
        return changed

    # ------------------------------------------------------------ learn

    def stats(self, kind: str) -> dict:
        with self._lock:
            scores = [c.score for c in self.cases if c.kind == kind and c.score is not None]
        n = len(scores)
        if not n:
            return {"kind": kind, "n": 0, "avg": None, "hit": None, "trust": 1.0}
        avg = float(np.mean(scores))
        hit = float(np.mean([s > 0 for s in scores]))
        return {"kind": kind, "n": n, "avg": round(avg, 3), "hit": round(hit, 3), "trust": round(self._trust(n, avg, hit), 3)}

    @staticmethod
    def _trust(n: int, avg: float, hit: float) -> float:
        if n < MIN_CASES:
            return 1.0
        move = max(min(avg / FULL_MOVE, 1.0), -1.0)
        often = max(min((hit - 0.5) * 4, 1.0), -1.0)
        weight = n / (n + SHRINK)
        return 1.0 + MAX_SHIFT * (0.5 * move + 0.5 * often) * weight

    def trust(self, kind: str) -> float:
        return self.stats(kind)["trust"]

    def adjust(self, kind: str, confidence: float) -> tuple[float, dict]:
        """Confidence after the record for this kind of news, and the record."""
        st = self.stats(kind)
        return float(min(max(confidence * st["trust"], 0.0), 0.95)), st

    def brief(self, kinds: list[str], turkish: bool = False) -> str:
        """The record for the AI, as data: one line per kind with enough cases."""
        lines = []
        for k in dict.fromkeys(kinds):
            st = self.stats(k)
            if st["n"] >= MIN_CASES:
                lines.append(f"- {label(k)}: {st['n']} past cases; one trading day later the price moved the expected "
                             f"way {st['hit']:.0%} of the time, average {st['avg']:+.2f}%.")
        return "\n".join(lines)

    def lessons(self, turkish: bool = False, limit: int = 12) -> list[dict]:
        with self._lock:
            kinds = {c.kind for c in self.cases}
        rows = [self.stats(k) for k in kinds]
        rows = [r for r in rows if r["n"]]
        rows.sort(key=lambda r: (-r["n"], r["kind"]))
        for r in rows:
            r["label"] = label(r["kind"], turkish)
        return rows[:limit]

    def totals(self) -> dict:
        with self._lock:
            return {"cases": len(self.cases), "graded": sum(1 for c in self.cases if c.score is not None),
                    "waiting": sum(1 for c in self.cases if not c.done),
                    "bought": sum(1 for c in self.cases if c.bought)}

    def _check_lessons(self) -> None:
        """Tell the growth line when a kind of news reaches 5, 10, 25, 50... cases."""
        if self.on_lesson is None:
            return
        with self._lock:
            kinds = {c.kind for c in self.cases}
        for k in kinds:
            st = self.stats(k)
            step = next((m for m in (100, 50, 25, 10, 5) if st["n"] >= m), 0)
            if step and self._announced.get(k, 0) < step:
                self._announced[k] = step
                try:
                    self.on_lesson(k, st)
                except Exception:
                    log.exception("lesson callback failed")

    # ---------------------------------------------------------- storage

    def save(self) -> None:
        if self.path is None:
            return
        with self._lock:
            doc = {"cases": [asdict(c) for c in self.cases], "announced": self._announced}
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(doc), encoding="utf-8")
            tmp.replace(self.path)
        except OSError:
            log.exception("could not save the news memory")

    def _load(self) -> None:
        if self.path is None:
            return
        try:
            doc = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except (OSError, ValueError):
            log.warning("the news memory is unreadable; starting a new one")
            return
        fields = Case.__dataclass_fields__
        for row in doc.get("cases", []):
            try:
                self.cases.append(Case(**{k: v for k, v in row.items() if k in fields}))
            except TypeError:
                continue
        self._announced = {str(k): int(v) for k, v in (doc.get("announced") or {}).items()}
