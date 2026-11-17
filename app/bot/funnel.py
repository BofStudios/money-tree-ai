"""Why the bot traded today, or why it did not: one counter per real decision.

  scanned   charts read (every look reads every chart: this one is large)
  signals   a dip appeared: RSI low enough and far enough under VWAP,
            counted once per symbol per minute (a look is every 10 seconds)
  passed    that dip also passed every chart rule (turn, vote, knife, depth, edge)
  orders    an order went to the broker ("intent")
  fills     the broker filled it ("trade_opened")

Every signal that did not become an order is counted under the gate that
stopped it. The counters only grow where the engine really decided something;
they reset at midnight New York and the last 30 days are kept.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)
NY = ZoneInfo("America/New_York")
DAYS = 30
STEPS = ("scanned", "signals", "passed", "orders", "fills")
STEP_LABELS = {
    "scanned": ("Charts read", "Okunan grafik"),
    "signals": ("Entry signals", "Giriş sinyali"),
    "passed": ("Passed every check", "Tüm kontrollerden geçti"),
    "orders": ("Orders sent", "Gönderilen emir"),
    "fills": ("Filled", "Dolan emir"),
}

# gate -> (owner agent, English, Turkish). The gate ids are fixed: the page ties
# a label to each, and a new gate is a contract change (docs/SYNC.md).
GATES: dict[str, tuple[str, str, str]] = {
    # the chart (Ultra's entry rule, app/engine/scalper.py)
    "turn": ("orion", "Price has not turned up yet", "Fiyat henüz dönmedi"),
    "quiet": ("atlas", "Chart too quiet, too wild or too old", "Grafik çok durgun, çok sert ya da eski"),
    "knife": ("orion", "Falling knife (ADX veto)", "Düşen bıçak (ADX vetosu)"),
    "too_deep": ("orion", "Dip too deep: usually news", "Düşüş çok derin: genelde haber"),
    "confluence": ("orion", "Vote under the threshold", "Oy eşiğin altında"),
    "edge": ("rigel", "Lab says this symbol loses", "Lab bu sembolde kaybettiğini söylüyor"),
    # the moment (Scalper._why_not_now)
    "halted": ("nova", "Stopped by you", "Senin tarafından durduruldu"),
    "closed": ("nova", "Market closed", "Piyasa kapalı"),
    "hours": ("nova", "Outside 9:45-15:40 New York", "New York 9:45-15:40 dışında"),
    "pdt": ("nova", "Broker refused a day trade today", "Aracı kurum bugün gün içi işlemi reddetti"),
    "bad_day": ("nova", "Today's trades lose on average", "Bugünkü işlemler ortalamada kaybediyor"),
    "entries": ("nova", "Daily trade limit reached", "Günlük işlem sınırı doldu"),
    "slots": ("nova", "Every trade slot is in use", "Bütün işlem yuvaları dolu"),
    "pace": ("titan", "Waiting between buys", "Alımlar arası bekleme"),
    "owned": ("titan", "Already holding it", "Zaten elde"),
    # the order path (PortfolioEngine.note_block keys)
    "cap": ("nova", "Position cap reached", "Pozisyon sınırı doldu"),
    "budget": ("nova", "Over the bot's budget", "Bot bütçesinin üstünde"),
    "not_armed": ("nova", "Real money is not armed", "Gerçek para silahlı değil"),
    "daily_loss": ("nova", "Daily loss limit reached", "Günlük zarar sınırı doldu"),
    "cash": ("nova", "Not enough cash", "Yeterli nakit yok"),
    "rules": ("nova", "Risk rules said no", "Risk kuralları reddetti"),
    "sector": ("nova", "Too many in one sector", "Bir sektörde çok fazla"),
    "paused": ("nova", "Safety pause", "Güvenlik molası"),
    "research": ("vega", "Research held it back", "Araştırma geri tuttu"),
    "too_small": ("titan", "Order too small", "Emir çok küçük"),
    "ai": ("orion", "The AI vetoed it", "Yapay zekâ veto etti"),
    "daytrade": ("nova", "Broker refused a day trade", "Aracı kurum gün içi işlemi reddetti"),
    "approval": ("titan", "Waiting for your OK", "Onayını bekliyor"),
}


def _day(now: float | None = None) -> str:
    return datetime.fromtimestamp(now if now is not None else time.time(), NY).strftime("%Y-%m-%d")


def _empty() -> dict:
    return {"steps": {s: 0 for s in STEPS}, "blocked": {}}


class Funnel:
    def __init__(self, path: Path | None = None, events=None, now=time.time) -> None:
        self.path = path
        self._now = now
        self._lock = threading.Lock()
        self._days: dict[str, dict] = {}
        self._seen: dict[str, int] = {}          # symbol -> minute of its last counted signal
        self._dirty_at = 0.0
        self._load()
        if events is not None:
            events.subscribe(self._on_event)

    # ------------------------------------------------------------- counting

    def _today(self) -> dict:
        day = _day(self._now())
        if day not in self._days:
            self._days[day] = _empty()
            for old in sorted(self._days)[:-DAYS]:
                del self._days[old]
            self._seen.clear()
        return self._days[day]

    def scanned(self, n: int) -> None:
        if n > 0:
            with self._lock:
                self._today()["steps"]["scanned"] += n
            self._save_soon()

    def signal(self, symbol: str) -> bool:
        """A dip on this symbol. True only the first time in this minute (then count it)."""
        minute = int(self._now() // 60)
        with self._lock:
            today = self._today()
            if self._seen.get(symbol) == minute:
                return False
            self._seen[symbol] = minute
            today["steps"]["signals"] += 1
        self._save_soon()
        return True

    def passed(self) -> None:
        with self._lock:
            self._today()["steps"]["passed"] += 1
        self._save_soon()

    def block(self, gate: str, symbol: str = "") -> None:
        gate = gate if gate in GATES else "rules"
        with self._lock:
            row = self._today()["blocked"].setdefault(gate, {"n": 0, "symbol": ""})
            row["n"] += 1
            row["symbol"] = symbol or row["symbol"]
        self._save_soon()

    def _on_event(self, event: dict) -> None:
        kind = event.get("type")
        if kind in ("intent", "trade_opened"):
            with self._lock:
                self._today()["steps"]["orders" if kind == "intent" else "fills"] += 1
            self._save_soon()

    # ------------------------------------------------------------- reading

    def view(self, turkish: bool = False) -> dict:
        i = 1 if turkish else 0
        with self._lock:
            day = _day(self._now())
            today = json.loads(json.dumps(self._days.get(day) or _empty()))
        steps = [{"id": s, "label": STEP_LABELS[s][i], "n": today["steps"].get(s, 0)} for s in STEPS]
        blocked = sorted(
            ({"gate": g, "label": GATES[g][1 + i], "n": r["n"], "by": GATES[g][0], "symbol": r.get("symbol") or None}
             for g, r in today["blocked"].items() if g in GATES),
            key=lambda r: -r["n"])
        return {"day": day, "steps": steps, "blocked": blocked}

    def history(self) -> dict:
        with self._lock:
            return json.loads(json.dumps(self._days))

    # ------------------------------------------------------------- the file

    def _load(self) -> None:
        if not self.path or not self.path.exists():
            return
        try:
            saved = json.loads(self.path.read_text(encoding="utf-8"))
            for day, row in (saved.get("days") or {}).items():
                if isinstance(row, dict):
                    self._days[str(day)] = {"steps": {s: int((row.get("steps") or {}).get(s, 0)) for s in STEPS},
                                            "blocked": {str(g): {"n": int(v.get("n", 0)), "symbol": str(v.get("symbol") or "")}
                                                        for g, v in (row.get("blocked") or {}).items() if isinstance(v, dict)}}
        except (OSError, ValueError, TypeError, AttributeError):
            log.warning("could not read the funnel; starting a new one", exc_info=True)

    def _save_soon(self) -> None:
        # The counters move every ten seconds; the file is written at most every 30.
        if self._now() - self._dirty_at >= 30:
            self.save()

    def save(self) -> None:
        if not self.path:
            return
        with self._lock:
            self._dirty_at = self._now()
            text = json.dumps({"days": self._days}, ensure_ascii=False)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(text, encoding="utf-8")
            tmp.replace(self.path)
        except OSError:
            log.debug("could not save the funnel", exc_info=True)

    def clear(self) -> None:
        with self._lock:
            self._days.clear()
            self._seen.clear()
        if self.path:
            try:
                self.path.unlink(missing_ok=True)
            except OSError:
                pass
