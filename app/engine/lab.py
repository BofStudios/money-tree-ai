"""The Lab (10.0): Ultra's rules replayed on the last days of real one-minute bars.

Ideas taken from the open-source bots (Freqtrade's backtesting, Edge and
lookahead analysis; Jesse's metrics and charts), built for Money Tree:

  replay    every symbol Ultra watches, minute by minute, with the same
            read_chart / score / stop_for the live scalper uses. Two rule
            sets side by side: 8.0 (the old dip rule) and 9.0 (the vote).
  no peeking  the decision at minute i reads only the bars up to i; the
            trade starts at the next minute's open. Inside a minute the stop
            is checked before the target (the worse case). 0.03% cost a trip.
  portfolio the same money rules as live: two trades at once, about half
            the account each, all of it on a strong vote, 30 a day.
  metrics   trades, win rate, average, profit factor, max drawdown, Sharpe,
            Sortino, exits, per symbol.
  edge      a symbol that lost on average in the replay (8+ trades, -0.15%
            a trade or worse) is skipped by Ultra until the next run. The
            owner can turn this off. It only ever removes buys.

The Lab never trades. It runs in its own thread about every 18 hours, or
when the owner presses Run, and writes data/lab.json.
"""
from __future__ import annotations

import json
import logging
import math
import threading
import time
from datetime import datetime, time as dtime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from app.engine import scalper as S
from app.engine.books import rsi_series

log = logging.getLogger(__name__)

COST = 0.03                 # % per round trip (spread and slippage)
EDGE_MIN_TRADES = 8
EDGE_MAX_AVG = -0.15        # % a trade: at or under this, the symbol is skipped
EVERY_HOURS = 18
START_CASH = 55.0
WINDOW = S.HISTORY_BARS


# ------------------------------------------------------------------ rules

def entry_80(ch: dict) -> bool:
    """8.0: RSI(7) at 30 or under, 1.5 ATRs under VWAP, turning up."""
    if ch["rsi"] is None or ch["rsi"] > 30 or not 0.04 <= ch["atr_pct"] <= 1.5:
        return False
    return S.dip_of(ch) >= 1.5 and ch["price"] > ch["prev"]


def entry_90(ch: dict) -> bool:
    """9.0: the live rule (RSI 35, 1.2 ATRs, the 5-of-8 vote, the vetoes)."""
    return S.score(ch, False) is not None


RULES = {"8.0": entry_80, "9.0": entry_90}


# ----------------------------------------------------------------- replay

def session_vwap(index, high, low, close, vol) -> np.ndarray:
    """Today's VWAP up to and including each minute (NaN before the open)."""
    out = np.full(len(close), np.nan)
    typical = (high + low + close) / 3
    day, num, den = None, 0.0, 0.0
    for i, t in enumerate(index):
        if t.date() != day:
            day, num, den = t.date(), 0.0, 0.0
        if t.time() < dtime(9, 30):
            continue
        num += typical[i] * vol[i]
        den += vol[i]
        out[i] = num / den if den > 0 else typical[i]
    return out


def entries(df: pd.DataFrame, entry) -> list[tuple[int, dict]]:
    """Every minute where the rule says buy, ignoring open trades: (i, chart).
    Reads only df.iloc[: i + 1] for minute i (the lookahead test checks it)."""
    if df is None or len(df) < WINDOW + 2:
        return []
    idx = df.index.tz_convert(S.NY)
    c = df["close"].to_numpy(float)
    r7 = rsi_series(c, 7)
    out = []
    for i in range(WINDOW, len(df) - 1):
        t = idx[i]
        if not (S.START <= t.time() < S.LAST_ENTRY) or np.isnan(r7[i]) or r7[i] > S.RSI_MAX:
            continue
        ch = S.read_chart(df.iloc[i - WINDOW + 1: i + 1], (t + pd.Timedelta(seconds=65)).to_pydatetime())
        if ch is not None and entry(ch):
            out.append((i, ch))
    return out


def replay_symbol(symbol: str, df: pd.DataFrame, entry, charts: list | None = None) -> list[dict]:
    """The trades the rule would have made on one symbol, one at a time.
    charts: entries(df, any) already read, so two rule sets read them once."""
    found = entries(df, entry) if charts is None else [(i, ch) for i, ch in charts if entry(ch)]
    if not found:
        return []
    idx = df.index.tz_convert(S.NY)
    o, h, l, c, v = (df[k].to_numpy(float) for k in ("open", "high", "low", "close", "volume"))
    vwap = session_vwap(idx, h, l, c, v)
    r7 = rsi_series(c, 7)
    n = len(df)
    trades, free_from = [], 0
    for i, ch in found:
        if i < free_from:
            continue
        stop = S.stop_for(ch)
        entry_px = o[i + 1]
        if not entry_px > 0:
            continue
        sl, tp = entry_px * (1 - stop / 100), entry_px * (1 + stop * S.RR / 100)
        day = idx[i + 1].date()
        j, px, why = i + 1, None, ""
        while j < n and idx[j].date() == day:
            if l[j] <= sl:
                px, why = sl, "stop"
                break
            if h[j] >= tp:
                px, why = tp, "target"
                break
            if (idx[j] - idx[i + 1]).total_seconds() / 60 >= S.MAX_HOLD_MIN:
                px, why = c[j], "time"
                break
            if idx[j].time() >= S.FLAT:
                px, why = c[j], "close"
                break
            if j >= i + 2:
                gain = (c[j] / entry_px - 1) * 100
                if gain >= S.TAKE_MIN and ((not np.isnan(vwap[j]) and c[j] >= vwap[j])
                                           or (not np.isnan(r7[j]) and r7[j] >= S.TAKE_RSI)):
                    px, why = c[j], "early"
                    break
            j += 1
        if px is None:          # the data ends inside the trade: not counted
            break
        trades.append({
            "symbol": symbol,
            "at": idx[i + 1].isoformat(),
            "out": idx[j].isoformat(),
            "pnl": round((px / entry_px - 1) * 100 - COST, 4),
            "why": why,
            "vote": round(float((ch.get("conf") or {}).get("score", 0.0)), 3),
        })
        free_from = j + 1
    return trades


# ---------------------------------------------------------------- metrics

def metrics(pnls: list[float]) -> dict:
    """Per-trade statistics on % results."""
    n = len(pnls)
    if not n:
        return {"trades": 0, "win_rate": None, "avg": None, "median": None, "best": None, "worst": None,
                "profit_factor": None, "sum": 0.0, "avg_win": None, "avg_loss": None}
    a = np.asarray(pnls, float)
    wins, losses = a[a > 0], a[a <= 0]
    gross_loss = -losses.sum()
    return {
        "trades": n,
        "win_rate": round(100 * len(wins) / n, 1),
        "avg": round(float(a.mean()), 4),
        "median": round(float(np.median(a)), 4),
        "best": round(float(a.max()), 3),
        "worst": round(float(a.min()), 3),
        "profit_factor": round(float(wins.sum() / gross_loss), 2) if gross_loss > 0 else None,
        "sum": round(float(a.sum()), 3),
        "avg_win": round(float(wins.mean()), 3) if len(wins) else None,
        "avg_loss": round(float(losses.mean()), 3) if len(losses) else None,
    }


def max_drawdown(values: list[float]) -> float:
    """The deepest fall from a peak, in % (0 or negative)."""
    peak, worst = None, 0.0
    for v in values:
        peak = v if peak is None else max(peak, v)
        if peak and peak > 0:
            worst = min(worst, (v / peak - 1) * 100)
    return round(worst, 2)


def ratios(daily_returns: list[float]) -> dict:
    """Sharpe and Sortino of daily % returns, yearly (x sqrt(252)). None with
    fewer than three days: a number from two days means nothing."""
    r = np.asarray(daily_returns, float)
    if len(r) < 3:
        return {"sharpe": None, "sortino": None}
    sd = r.std(ddof=1)
    down = r[r < 0]
    dd = math.sqrt((down ** 2).mean()) if len(down) else 0.0
    k = math.sqrt(252)
    return {"sharpe": round(float(r.mean() / sd * k), 2) if sd > 0 else None,
            "sortino": round(float(r.mean() / dd * k), 2) if dd > 0 else None}


def simulate(trades: list[dict], start: float = START_CASH) -> dict:
    """The account through the replay with Ultra's money rules."""
    cash = float(start)
    open_: list[tuple[str, float, float, str]] = []      # (out, notional, pnl %, symbol)
    curve = [{"time": trades[0]["at"] if trades else None, "value": round(cash, 2)}]
    taken = skipped = 0
    per_day: dict[str, int] = {}

    def close_until(t: str | None) -> None:
        nonlocal cash
        for item in sorted(open_):
            if t is not None and item[0] > t:
                continue
            open_.remove(item)
            cash += item[1] * (1 + item[2] / 100)
            curve.append({"time": item[0], "value": round(float(cash + sum(x[1] for x in open_)), 2)})

    for tr in sorted(trades, key=lambda x: x["at"]):
        close_until(tr["at"])
        day = tr["at"][:10]
        if per_day.get(day, 0) >= S.MAX_ENTRIES or len(open_) >= S.SLOTS \
                or any(x[3] == tr["symbol"] for x in open_):
            skipped += 1
            continue
        equity = cash + sum(x[1] for x in open_)
        share = S.ALL_IN if (tr["vote"] >= S.ALL_IN_VOTE and not open_) else S.ALLOC
        notional = min(equity * share, cash)
        if notional < S.MIN_CASH:
            skipped += 1
            continue
        cash -= notional
        open_.append((tr["out"], notional, tr["pnl"], tr["symbol"]))
        per_day[day] = per_day.get(day, 0) + 1
        taken += 1
    close_until(None)

    by_day: dict[str, float] = {}
    for p in curve[1:]:
        by_day[p["time"][:10]] = p["value"]
    days, prev, daily = sorted(by_day), float(start), []
    for d in days:
        daily.append((by_day[d] / prev - 1) * 100 if prev > 0 else 0.0)
        prev = by_day[d]
    end = float(curve[-1]["value"])
    return {
        "start": round(float(start), 2), "end": round(end, 2),
        "profit": round(end - start, 2), "return_pct": round((end / start - 1) * 100, 2) if start else 0.0,
        "max_drawdown": float(max_drawdown([p["value"] for p in curve])),
        "taken": taken, "skipped": skipped,
        **ratios(daily),
        "curve": curve,
    }


def breakdown(trades: list[dict], key: str) -> list[dict]:
    groups: dict[str, list[float]] = {}
    for t in trades:
        groups.setdefault(t[key], []).append(t["pnl"])
    rows = []
    for k, p in groups.items():
        m = metrics(p)
        rows.append({"key": k, "trades": m["trades"], "win_rate": m["win_rate"], "avg": m["avg"], "sum": m["sum"]})
    return sorted(rows, key=lambda r: -r["trades"])


def edge_blocked(symbol_rows: list[dict]) -> list[str]:
    return sorted(r["key"] for r in symbol_rows
                  if r["trades"] >= EDGE_MIN_TRADES and r["avg"] is not None and r["avg"] <= EDGE_MAX_AVG)


def verdict(m: dict) -> str:
    if m["trades"] < 20:
        return "few"
    if (m["avg"] or 0) > 0.02 and (m["profit_factor"] or 0) > 1.1:
        return "positive"
    if (m["avg"] or 0) >= -0.02:
        return "flat"
    return "negative"


def run_replay(frames: dict[str, pd.DataFrame], start: float = START_CASH) -> dict:
    """Both rule sets on the same bars; the full report (no settings)."""
    t0 = time.time()
    frames = {s: f for s, f in frames.items() if f is not None and len(f) > WINDOW + 2}
    report: dict = {"rules": {}}
    trades_by_rule: dict[str, list[dict]] = {}
    charts: dict[str, list] = {}
    for symbol, df in frames.items():
        try:
            charts[symbol] = entries(df, lambda ch: True)
        except Exception:
            log.exception("lab: reading %s failed", symbol)
        time.sleep(0.01)        # let the live engine breathe
    for name, rule in RULES.items():
        trades: list[dict] = []
        for symbol, df in frames.items():
            if symbol not in charts:
                continue
            try:
                trades += replay_symbol(symbol, df, rule, charts[symbol])
            except Exception:
                log.exception("lab: replay of %s failed", symbol)
        trades_by_rule[name] = trades
        m = metrics([t["pnl"] for t in trades])
        sim = simulate(trades, start)
        report["rules"][name] = {**m, "verdict": verdict(m), "portfolio": {k: v for k, v in sim.items() if k != "curve"}}
        report.setdefault("curves", {})[name] = sim["curve"]
    live = trades_by_rule["9.0"]
    report["symbols"] = breakdown(live, "symbol")
    report["exits"] = breakdown(live, "why")
    report["blocked"] = edge_blocked(report["symbols"])
    report["recent"] = sorted(live, key=lambda t: t["at"], reverse=True)[:40]
    days = sorted({d for f in frames.values() for d in f.index.tz_convert(S.NY).date})
    report.update({
        "ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "took_s": round(time.time() - t0, 1),
        "days": [d.isoformat() for d in days],
        "symbols_n": len(frames),
        "bars": int(sum(len(f) for f in frames.values())),
        "cost_pct": COST,
        "start_cash": round(float(start), 2),
    })
    return report


# ------------------------------------------------------------------- data

def fetch_bars(symbols: list[str]) -> dict[str, pd.DataFrame]:
    """The last 7 days of one-minute bars from Yahoo (the most it gives).
    Its own download, so the live engine's bar cache is left alone."""
    import yfinance as yf

    out: dict[str, pd.DataFrame] = {}
    for s in symbols:
        try:
            df = yf.download(s, period="7d", interval="1m", progress=False, auto_adjust=False,
                             prepost=False, threads=False)
        except Exception:
            log.warning("lab: no bars for %s", s)
            continue
        if df is None or df.empty:
            continue
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.rename(columns=str.lower)
        if not {"open", "high", "low", "close", "volume"} <= set(df.columns):
            continue
        df = df[["open", "high", "low", "close", "volume"]].dropna()
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        out[s] = df
    return out


# -------------------------------------------------------------------- lab

def default_path() -> Path:
    from app.config import DATA_DIR

    return DATA_DIR / "lab.json"


class Lab:
    def __init__(self, engine=None, path: Path | None = None, fetch=None) -> None:
        self.engine = engine
        self._path = path
        self.fetch = fetch or fetch_bars
        self._lock = threading.Lock()
        self._report: dict | None = None
        self._settings: dict = {"edge": True}
        self._loaded = False
        self.running = False
        self.error = ""
        self._blocked: set[str] = set()

    @property
    def path(self) -> Path:
        if self._path is None:
            self._path = default_path()
        return self._path

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self._report = raw.get("report")
            self._settings.update(raw.get("settings") or {})
            self._blocked = set((self._report or {}).get("blocked") or [])
        except FileNotFoundError:
            pass
        except Exception:
            log.warning("lab: could not read %s", self.path)

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"settings": self._settings, "report": self._report}), encoding="utf-8")
            tmp.replace(self.path)
        except Exception:
            log.exception("lab: could not save")

    # ------------------------------------------------------------ settings
    @property
    def edge_on(self) -> bool:
        self._load()
        return bool(self._settings.get("edge", True))

    def set_edge(self, on: bool) -> None:
        with self._lock:
            self._load()
            self._settings["edge"] = bool(on)
            self._save()

    def edge_blocked(self, symbol: str) -> bool:
        """True when the last replay says Ultra loses on this symbol."""
        self._load()
        return self.edge_on and symbol in self._blocked

    # ----------------------------------------------------------------- run
    def due(self, now: float | None = None) -> bool:
        self._load()
        if not self._report or not self._report.get("ran_at"):
            return True
        try:
            ran = datetime.fromisoformat(self._report["ran_at"]).timestamp()
        except ValueError:
            return True
        return (now or time.time()) - ran >= EVERY_HOURS * 3600

    def _start_cash(self) -> float:
        try:
            eq = float(self.engine.scalper._equity()) if self.engine is not None else 0.0
        except Exception:
            eq = 0.0
        return eq if eq > 0 else START_CASH

    def run(self) -> dict:
        """Download, replay, save. Blocking; start() runs it in a thread."""
        with self._lock:
            if self.running:
                return {"ok": False, "why": "running"}
            self.running, self.error = True, ""
        try:
            symbols = list(S.UNIVERSE)
            frames = self.fetch(symbols)
            if not frames:
                raise RuntimeError("no one-minute bars could be downloaded")
            report = run_replay(frames, self._start_cash())
            with self._lock:
                self._load()
                self._report = report
                self._blocked = set(report["blocked"])
                self._save()
            log.info("lab: %s trades on %s symbols in %ss; skipped by edge: %s",
                     report["rules"]["9.0"]["trades"], report["symbols_n"], report["took_s"],
                     ", ".join(report["blocked"]) or "none")
            return {"ok": True}
        except Exception as exc:
            self.error = str(exc)
            log.exception("lab run failed")
            return {"ok": False, "why": str(exc)}
        finally:
            self.running = False

    def start(self) -> bool:
        if self.running:
            return False
        threading.Thread(target=self.run, name="lab", daemon=True).start()
        return True

    def maybe_run(self) -> bool:
        """Called by the engine's loop: a fresh replay about every 18 hours."""
        if self.running or not self.due():
            return False
        return self.start()

    def status(self) -> dict:
        self._load()
        nxt = None
        if self._report and self._report.get("ran_at"):
            try:
                nxt = (datetime.fromisoformat(self._report["ran_at"]) + timedelta(hours=EVERY_HOURS)).isoformat()
            except ValueError:
                nxt = None
        return {
            "running": self.running, "error": self.error, "edge": self.edge_on,
            "edge_rule": {"min_trades": EDGE_MIN_TRADES, "max_avg": EDGE_MAX_AVG},
            "every_hours": EVERY_HOURS, "next_run": nxt,
            "report": self._report,
        }
