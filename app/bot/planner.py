"""Orion's planning round (12.0): the AI reads Ultra's best charts and may hold some back.

Off until the owner turns it on. While the market is open and Ultra trades,
every ten minutes at most: a short state (the best charts, open trades as
percentages, the pace, what blocked trades today) goes to the AI provider the
owner chose, and the answer is read with app/bot/protocol.py. Three words
are allowed for a chart on the list:

    keep    nothing changes
    shrink  a buy of it in the next ten minutes is half the size
    skip    it is not bought in the next ten minutes

Nothing else is done with the answer: it cannot start a buy, make one bigger,
name a symbol that was not on the list, or touch a limit. No answer, a broken
answer or a used-up quota changes nothing: the bot trades on its rules.
Never sent: money amounts beyond what the privacy level allows, keys, and
anything the owner typed (so "stop" or "dur" never reach the AI).
"""
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.bot.protocol import parse_action

log = logging.getLogger(__name__)
NY = ZoneInfo("America/New_York")
EVERY_S = 600
HOLD_S = 600
DAILY_CALLS = 60
ACTIONS = ("keep", "shrink", "skip")

SYSTEM = (
    "You are Orion, the planner of a small US stock day-trading bot. You never place orders. "
    "You see the bot's best one-minute dip setups right now and may advise, for each, one of: "
    "keep (no change), shrink (half size), skip (do not buy it for ten minutes). "
    "Skip or shrink only with a concrete reason from the data (for example: the vote is weak, the dip is very deep, "
    "today's trades in this kind of setup lost, too many positions in one direction). "
    "Answer with JSON only, no other text: "
    '{"thought": "one short sentence", "action": "plan", "args": {"note": "at most two short sentences for the log", '
    '"ideas": [{"symbol": "AAPL", "action": "keep|shrink|skip", "why": "short reason"}]}}'
)


class Planner:
    def __init__(self, engine, path: Path | None = None, now=time.time) -> None:
        self.engine = engine
        self.path = path
        self._now = now
        self._lock = threading.Lock()
        self._advice: dict[str, tuple[str, float, str]] = {}     # symbol -> (action, until, why)
        self._last_at = 0.0
        self._running = False
        self._quota = {"day": "", "calls": 0}
        self._load()

    # ------------------------------------------------------------- the switch

    def enabled(self) -> bool:
        s = getattr(self.engine, "bot_settings", None)
        return bool(s.get("planner")) if s is not None else False

    def _ai(self):
        return getattr(self.engine, "explainer", None)

    def _level(self) -> str:
        ai = self._ai()
        try:
            return ai._level() if ai is not None else "none"
        except Exception:
            return "full"

    def calls_left(self) -> int:
        with self._lock:
            self._roll()
            return max(DAILY_CALLS - self._quota["calls"], 0)

    def _roll(self) -> None:
        day = datetime.fromtimestamp(self._now(), NY).strftime("%Y-%m-%d")
        if self._quota["day"] != day:
            self._quota = {"day": day, "calls": 0}

    # ------------------------------------------------------------- reading advice

    def advice_for(self, symbol: str) -> str | None:
        with self._lock:
            got = self._advice.get(symbol)
            if not got or got[1] < self._now():
                return None
            return got[0]

    def advice(self) -> list[dict]:
        now = self._now()
        with self._lock:
            return [{"symbol": s, "action": a, "why": w, "until": int(u * 1000)}
                    for s, (a, u, w) in self._advice.items() if u >= now and a != "keep"]

    # ------------------------------------------------------------- the round

    def due(self) -> bool:
        eng = self.engine
        if not self.enabled() or self._running or self._level() == "none":
            return False
        if self._now() - self._last_at < EVERY_S or self.calls_left() <= 0:
            return False
        if not getattr(eng, "ultra", False) or getattr(eng, "halted", False):
            return False
        try:
            if not eng.clock.state().is_open:
                return False
        except Exception:
            return False
        sc = getattr(eng, "scalper", None)
        return bool(sc is not None and getattr(sc, "radar", None) and self._ai() is not None)

    def maybe_run(self) -> bool:
        if not self.due():
            return False
        self._running = True
        self._last_at = self._now()
        threading.Thread(target=self._safe_run, name="planner", daemon=True).start()
        return True

    def _safe_run(self) -> None:
        try:
            self.run()
        except Exception:
            log.exception("the planner round failed")
        finally:
            self._running = False

    def context(self) -> dict:
        """What the AI sees: no owner text, no keys; money only as the privacy level allows."""
        eng = self.engine
        sc = eng.scalper
        radar = [{k: r.get(k) for k in ("symbol", "score", "vote", "dip", "rsi", "relvol", "stop_pct", "tip")}
                 for r in list(sc.radar)[:5]]
        with eng._lock:
            held = [{"symbol": p.symbol, "pnl_pct": round(float(p.unrealized_pnl_pct or 0), 2)}
                    for p in eng._positions.values()]
        funnel = getattr(eng, "funnel", None)
        blocked = [{"gate": b["gate"], "n": b["n"]} for b in (funnel.view()["blocked"][:4] if funnel else [])]
        try:
            today = [round(float(t.get("pnl_pct") or 0), 2) for t in eng.scalper.today_trades()][:10]
        except Exception:
            today = []
        pace = eng.bot_settings.get("pace") if getattr(eng, "bot_settings", None) else "balanced"
        ctx = {"pace": pace, "setups": radar, "open_trades": held, "todays_trade_results_pct": today,
               "blocked_today": blocked, "time_ny": datetime.now(NY).strftime("%H:%M")}
        if self._level() == "none":
            return {}
        return ctx                           # no dollar amounts in it at any level

    def run(self) -> dict | None:
        ai = self._ai()
        ctx = self.context()
        if ai is None or not ctx or not ctx["setups"]:
            return None
        with self._lock:
            self._roll()
            self._quota["calls"] += 1
        self._save()
        reply = ai._chat(SYSTEM, [{"role": "user", "content": json.dumps(ctx, ensure_ascii=False)}], 400)
        text = getattr(reply, "text", None) if reply is not None else None
        return self.apply(text, {s["symbol"] for s in ctx["setups"]})

    def apply(self, text: str | None, allowed: set[str]) -> dict | None:
        got = parse_action(text)
        if not got or got["action"] != "plan":
            return None
        args = got["args"]
        until = self._now() + HOLD_S
        kept: list[dict] = []
        for idea in args.get("ideas") or []:
            if not isinstance(idea, dict):
                continue
            symbol = str(idea.get("symbol") or "").strip().upper()
            action = str(idea.get("action") or "").strip().lower()
            if symbol not in allowed or action not in ACTIONS:
                continue                     # not on the list, or not one of the three words
            why = str(idea.get("why") or "")[:160]
            with self._lock:
                self._advice[symbol] = (action, until, why)
            kept.append({"symbol": symbol, "action": action, "why": why})
        note = str(args.get("note") or got.get("thought") or "")[:240]
        held = [f"{k['symbol']} {k['action']}" for k in kept if k["action"] != "keep"]
        text_line = note + (f" · {', '.join(held)}" if held else "")
        events = getattr(self.engine, "events", None)
        if events is not None and (text_line or kept):
            events.publish("bot_plan", {"text": text_line or "No change.", "ideas": kept})
        return {"note": note, "ideas": kept}

    # ------------------------------------------------------------- the quota file

    def _load(self) -> None:
        if not self.path or not self.path.exists():
            return
        try:
            q = json.loads(self.path.read_text(encoding="utf-8"))
            self._quota = {"day": str(q.get("day") or ""), "calls": int(q.get("calls") or 0)}
        except (OSError, ValueError, TypeError):
            pass

    def _save(self) -> None:
        if not self.path:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self._lock:
                text = json.dumps(self._quota)
            self.path.write_text(text, encoding="utf-8")
        except OSError:
            pass
