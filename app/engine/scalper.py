"""Money Ter Ter Ter: the scalper (8.0).

Only very short trades. The bot reads one-minute candles, looks every ten
seconds at the latest trade price, and holds a position for minutes:

  research  every look ranks ~25 of the most traded US stocks and funds, plus
            the watchlist and whatever the news reflex just flagged, on the
            one-minute chart.
  entry     a dip: RSI(7) at 30 or under, the price at least 1.5 one-minute
            ATRs under today's VWAP, and the last trade above the last
            candle's close (it has started to turn). The deepest dip wins;
            two scalps at most at once, ~48% of the account each, 20 a day.
            Nothing before 9:45 or after 15:40 New York.
  exit      stop 2.5 one-minute ATRs (0.35% to 1.2%), target 1.5x the stop,
            30 minutes at most, everything flat at 15:52.
  guard     after six scalps in a day, if they lost 0.15% each on average,
            no new scalps that day.
  news      a headline does not buy by itself here: it lifts the stock up the
            radar for 30 minutes and the chart has to confirm.

Why dips and not breakouts: replayed on five real days (21-27 Oct 2026, 24
stocks, 0.03% cost a trade), chasing one-minute breakouts lost on every
variant tried (-0.03% to -0.13% a trade); buying the stretched dip back
toward VWAP came out about even (+0.02% a trade). Neither is an edge to
count on: the guard and the daily loss limit are there for the bad days.

A broker refusal for the day-trade rule stops new scalps for the day.
Every buy still passes Stop, the market clock, the sector limit, the safety
pauses, the daily loss limit, arming and the owner's autonomy choice.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

import numpy as np

from app.engine.books import atr_pct, rsi_series

log = logging.getLogger(__name__)

NY = ZoneInfo("America/New_York")
PREFIX = "Scalp: "
BOOK = "scalp"

# The most traded names: tight spreads, real one-minute volume.
UNIVERSE = [
    "SPY", "QQQ", "IWM", "SMH",
    "NVDA", "TSLA", "AMD", "AAPL", "MSFT", "META", "AMZN", "GOOGL", "AVGO", "NFLX",
    "PLTR", "MU", "SMCI", "COIN", "MSTR", "UBER", "SOFI", "HOOD", "INTC", "ARM",
]

SLOTS = 2                    # scalps open at once
ALLOC = 0.48                 # of the account per scalp
RSI_MAX, DIP_ATR = 30, 1.5   # how oversold, and how far under VWAP in one-minute ATRs
STOP_ATR, STOP_MIN, STOP_MAX = 2.5, 0.35, 1.2
RR = 1.5
MAX_HOLD_MIN = 30
START, LAST_ENTRY, FLAT = dtime(9, 45), dtime(15, 40), dtime(15, 52)
MAX_ENTRIES = 20             # scalps a day
GUARD_MIN, GUARD_AVG = 6, -0.15
TIP_MINUTES = 30
FRESH_SECONDS = 240          # a candle older than this is not a live chart
HISTORY_BARS = 150
SCAN_SECONDS = 10


def apply_scalp(config) -> None:
    """The scalper's pace: one-minute candles, a look every ten seconds, and
    pauses sized for minutes instead of hours."""
    config.timeframe = "1m"
    config.scan_interval_seconds = SCAN_SECONDS
    p = config.protections
    p.cooldown_minutes = min(p.cooldown_minutes, 10)
    p.stoploss_guard_lookback_minutes = 60
    p.stoploss_guard_trades = max(p.stoploss_guard_trades, 4)
    p.stoploss_guard_stop_minutes = 30


def ema(x: np.ndarray, n: int) -> np.ndarray:
    a = 2.0 / (n + 1)
    out = np.empty(len(x))
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out


def read_chart(frame, now: datetime | None = None) -> dict | None:
    """The one-minute picture of one stock, or None without enough of today."""
    if frame is None or len(frame) < 25:
        return None
    now = now or datetime.now(NY)
    index = frame.index.tz_convert(NY)
    session = (index.date == now.date()) & (index.time >= dtime(9, 30))
    if session.sum() < 10:
        return None
    close = frame["close"].to_numpy(float)
    high = frame["high"].to_numpy(float)
    low = frame["low"].to_numpy(float)
    vol = frame["volume"].to_numpy(float)

    sc, sh, sl, sv = close[session], high[session], low[session], vol[session]
    typical = (sh + sl + sc) / 3
    vwap = float((typical * sv).sum() / sv.sum()) if sv.sum() > 0 else float(typical.mean())
    e9, e20 = ema(close, 9), ema(close, 20)
    r = rsi_series(close, 7)
    base = vol[-65:-5]
    relvol = float(vol[-5:].mean() / base.mean()) if len(base) and base.mean() > 0 else 1.0
    last = float(close[-1])
    return {
        "price": last, "vwap": vwap, "ema9": float(e9[-1]), "ema20": float(e20[-1]),
        "rsi": None if np.isnan(r[-1]) else float(r[-1]),
        "atr_pct": atr_pct(high, low, close) or 0.0,
        "relvol": relvol,
        "mom15": float(last / close[-16] - 1) * 100 if close[-16] > 0 else 0.0,
        "prev": float(close[-2]),
        "age": (now - index[-1].to_pydatetime()).total_seconds(),
    }


def score(c: dict, tipped: bool) -> tuple[float, str] | None:
    """(score, setup) for a long scalp, or None when the chart says no."""
    rsi = c["rsi"]
    if rsi is None or rsi > RSI_MAX:
        return None
    if not 0.04 <= c["atr_pct"] <= 1.5 or c["age"] > FRESH_SECONDS:
        return None
    if dip_of(c) < DIP_ATR or c["price"] <= c["prev"]:
        return None
    return dip_of(c) + (1.5 if tipped else 0.0), "dip"


def dip_of(c: dict) -> float:
    """How far under today's VWAP, in one-minute ATRs."""
    return (c["vwap"] / c["price"] - 1) * 100 / c["atr_pct"] if c["atr_pct"] > 0 and c["price"] > 0 else 0.0


def stop_for(c: dict) -> float:
    return round(min(max(c["atr_pct"] * STOP_ATR, STOP_MIN), STOP_MAX), 2)


class Scalper:
    def __init__(self, engine) -> None:
        self.engine = engine
        self.tips: dict[str, tuple[float, str]] = {}     # symbol -> (until, the headline)
        self.radar: list[dict] = []
        self.log: list[dict] = []
        self.state = ""                                  # why it is not buying right now, if it is not
        self.day = ""
        self.entries = 0
        self.pdt_day = ""

    # --------------------------------------------------------------- inputs
    def symbols(self) -> list[str]:
        now = time.time()
        tips = [s for s, (until, _) in self.tips.items() if until > now]
        return list(dict.fromkeys(tips + UNIVERSE))

    def news_tip(self, symbol: str, reason: str) -> str:
        self.tips[symbol] = (time.time() + TIP_MINUTES * 60, reason)
        self._note(symbol, "tip", reason)
        self.engine.scan_now()
        return "watching: the scalper buys it only if the one-minute chart confirms"

    def refused_for_day_trades(self, error: str) -> bool:
        text = (error or "").lower()
        if "pattern day" in text or "day trad" in text or "40310100" in text:
            self.pdt_day = self._today()
            return True
        return False

    # ----------------------------------------------------------------- tick
    def tick(self, frames: dict, live: dict | None = None, now: datetime | None = None) -> list[dict]:
        """One look: manage the open scalps, then maybe open one. Returns what it did."""
        eng = self.engine
        now = now or datetime.now(NY)
        live = live or {}
        if self._today(now) != self.day:
            self.day, self.entries = self._today(now), 0
        done: list[dict] = []

        charts: dict[str, dict] = {}
        for symbol, frame in frames.items():
            try:
                c = read_chart(frame, now)
            except Exception:
                log.exception("could not read the chart of %s", symbol)
                c = None
            if c is not None:
                if live.get(symbol):
                    c["price"] = float(live[symbol])
                charts[symbol] = c

        with eng._lock:
            held = {s: p for s, p in eng._positions.items() if eng.book_of(s) == BOOK}
        for symbol, p in held.items():
            why = self._exit_why(p, charts.get(symbol), now)
            if why:
                result = eng.book_sell(symbol, PREFIX + why)
                done.append(self._note(symbol, "sell" if result == "sold" else "wait", why if result == "sold"
                                       else f"{why} · {result}"))

        tipped = {s for s, (until, _) in self.tips.items() if until > time.time()}
        ranked = []
        for symbol, c in charts.items():
            got = score(c, symbol in tipped)
            if got is not None:
                ranked.append((got[0], symbol, got[1], c))
        ranked.sort(key=lambda r: -r[0])
        self.radar = [{"symbol": s, "score": round(sc, 2), "setup": setup, "price": c["price"],
                       "dip": round(dip_of(c), 1), "relvol": round(c["relvol"], 2), "rsi": round(c["rsi"] or 0),
                       "stop_pct": stop_for(c), "tip": s in tipped} for sc, s, setup, c in ranked[:8]]

        self.state = self._why_not_now(now, len(held))
        if self.state:
            return done
        with eng._lock:
            owned = set(eng._positions)
        equity = self._equity()
        for sc, symbol, setup, c in ranked:
            if symbol in owned or eng.protections.blocked(symbol):
                continue
            stop = stop_for(c)
            tip = self.tips.get(symbol)
            reason = (f"{PREFIX}{setup} · {dip_of(c):.1f} ATR under VWAP · RSI {c['rsi']:.0f} · "
                      f"volume {c['relvol']:.1f}x" + (f" · news: {tip[1]}" if symbol in tipped and tip else ""))
            result = eng.book_buy(symbol, BOOK, reason, equity * ALLOC, stop, RR, price=c["price"])
            if result == "bought":
                self.entries += 1
                done.append(self._note(symbol, "buy", reason[len(PREFIX):]))
            elif result == "waiting":
                done.append(self._note(symbol, "wait", "waiting for your OK"))
            else:
                done.append(self._note(symbol, "skip", result))
            break   # one new scalp per look: the next look re-reads the market
        return done

    def _exit_why(self, p, c: dict | None, now: datetime) -> str | None:
        minutes = (now.timestamp() - p.opened_at.timestamp()) / 60
        price = (c or {}).get("price") or p.current_price or p.entry_price
        gain = (price / p.entry_price - 1) * 100 if p.entry_price else 0.0
        if now.time() >= FLAT:
            return "flat before the close"
        if minutes >= MAX_HOLD_MIN:
            return f"time is up ({MAX_HOLD_MIN} min, {gain:+.2f}%)"
        return None

    def _why_not_now(self, now: datetime, open_scalps: int) -> str:
        eng = self.engine
        tr = getattr(eng, "language", "en") == "tr"

        def t(en: str, tr_: str) -> str:
            return tr_ if tr else en

        if eng.halted:
            return t("stopped: no new scalps", "durduruldu: yeni işlem yok")
        if not eng.clock.state().is_open:
            local = datetime.combine(now.date(), START, tzinfo=NY).astimezone(ZoneInfo("Europe/Istanbul"))
            return t(f"the market is closed: scalps start at 9:45 New York ({local:%H:%M} Türkiye)",
                     f"piyasa kapalı: işlemler New York 9:45'te (Türkiye {local:%H:%M}) başlar")
        if self.pdt_day == self._today(now):
            return t("the broker refused a day trade today (day-trade rule): no new scalps until tomorrow",
                     "aracı kurum bugün gün içi işlemi reddetti (day-trade kuralı): yarına kadar yeni işlem yok")
        if now.time() < START:
            return t("waiting for 9:45 New York: the first minutes are too wild",
                     "New York 9:45 bekleniyor (9:45): ilk dakikalar çok sert")
        if now.time() >= LAST_ENTRY:
            return t("no new scalps after 15:40 New York", "New York 15:40'tan sonra yeni işlem yok")
        if self._bad_day(now):
            return t(f"today's scalps lost {-GUARD_AVG:.2f}% or more on average: no new scalps today",
                     f"bugünkü işlemler ortalama %{-GUARD_AVG:.2f} ya da daha fazla kaybetti: bugün yeni işlem yok")
        if self.entries >= MAX_ENTRIES:
            return t(f"{MAX_ENTRIES} scalps today: that is the day's limit",
                     f"bugün {MAX_ENTRIES} işlem: günlük sınır bu")
        if open_scalps >= SLOTS:
            return t(f"{SLOTS} scalps open: waiting for one to finish",
                     f"{SLOTS} işlem açık (open): biri bitince yenisi")
        if not self.radar:
            return t("no chart passes right now: watching", "şu an kurallardan geçen grafik yok: izliyor")
        return ""

    def today_trades(self, now: datetime | None = None) -> list[dict]:
        today = self._today(now)
        try:
            return [t for t in self.engine.repo.recent_trades(self.engine.mode, limit=200)
                    if t.get("entry_reason", "").startswith(PREFIX) and _ny_date(t["closed_at"]) == today]
        except Exception:
            log.exception("could not read today's scalps")
            return []

    def _bad_day(self, now: datetime) -> bool:
        trades = self.today_trades(now)
        return len(trades) >= GUARD_MIN and sum(t["pnl_pct"] for t in trades) / len(trades) <= GUARD_AVG

    # ----------------------------------------------------------------- view
    def _equity(self) -> float:
        acct = getattr(self.engine, "_account", None)
        if acct is not None and getattr(acct, "equity", 0):
            return float(acct.equity)
        return float(self.engine.executor.get_balance().total)

    def _today(self, now: datetime | None = None) -> str:
        return (now or datetime.now(NY)).strftime("%Y-%m-%d")

    def _note(self, symbol: str, action: str, why: str) -> dict:
        row = {"at": time.time(), "book": BOOK, "symbol": symbol, "action": action, "why": why}
        if not (self.log and self.log[0]["symbol"] == symbol and self.log[0]["action"] == action
                and self.log[0]["why"] == why):
            self.log.insert(0, row)
            del self.log[80:]
        return row

    def snapshot(self) -> dict:
        eng = self.engine
        now = time.time()
        with eng._lock:
            items = [(s, p) for s, p in eng._positions.items() if eng.book_of(s) == BOOK]
        open_ = [{"symbol": s, "value": round((p.current_price or p.entry_price) * p.qty, 2),
                  "pnl_pct": round(p.unrealized_pnl_pct, 2), "pnl": round(p.unrealized_pnl, 2),
                  "minutes": round((now - p.opened_at.timestamp()) / 60, 1), "stop": p.stop_loss,
                  "target": p.take_profit, "reason": eng._entry_reasons.get(s, "")[len(PREFIX):]}
                 for s, p in items]
        trades = self.today_trades()
        wins = sum(1 for t in trades if t["pnl"] > 0)
        state = self.state
        if not state or not eng.clock.state().is_open or eng.halted:
            state = self._why_not_now(datetime.now(NY), len(open_))
        return {
            "style": "scalp",
            "open": open_, "radar": self.radar, "state": state, "log": self.log[:40],
            "today": {"scalps": len(trades), "wins": wins, "pnl": round(sum(t["pnl"] for t in trades), 2),
                      "entries": self.entries, "max": MAX_ENTRIES},
            "recent": [{"symbol": t["symbol"], "pnl": t["pnl"], "pnl_pct": t["pnl_pct"], "why": t["exit_reason"],
                        "at": t["closed_at"]} for t in trades[:12]],
            "rules": {"slots": SLOTS, "alloc": ALLOC, "stop_min": STOP_MIN, "stop_max": STOP_MAX, "rr": RR,
                      "rsi": RSI_MAX, "dip": DIP_ATR,
                      "max_hold": MAX_HOLD_MIN, "seconds": eng.config.scan_interval_seconds},
            "universe": len(self.symbols()),
        }


def _ny_date(iso: str) -> str:
    try:
        d = datetime.fromisoformat(iso)
    except ValueError:
        return ""
    if d.tzinfo is None:
        from datetime import timezone
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(NY).strftime("%Y-%m-%d")
