"""Ten bots at once: a swarm of strategy-evolving processes, and the arena that judges them.

Each bot is a separate process (an "island") with its own population, its own
family focus and its own random seed, breeding and replaying strategies on
months of real candles as fast as its CPU core allows — the "mining". Every
couple of seconds it reports its best to the arena in the main process.

The arena is where caution lives. A bot's best only becomes the strategy
the real account trades with if it beats the current one on data no bot
trained on, by a margin, over enough trades, and holds up on a second unseen
stretch — the same bar as the phone. One real trader; ten competing minds.

Every bot also paper-trades its current best on the live candles each scan,
so the leaderboard shows how each would be doing right now, not just in the past.
"""
from __future__ import annotations

import json
import logging
import multiprocessing as mp
import os
import queue
import random
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from app.brain.genome import (
    DEFAULT, FAMILIES, Genome, Score, Series, crossover, mutate, random_genome, replay, signals,
)

log = logging.getLogger(__name__)

MARGIN = 0.08
MIN_VALID_TRADES = 15
MIN_CONFIRM_TRADES = 10
MIN_GAP = 30 * 60.0
TRAIN, VALID = 0.6, 0.8   # train on [0, 60%), validate on [60, 80%), confirm on [80, 100%)
POPULATION, PARENTS, IMMIGRANTS = 32, 10, 4
REPORT_EVERY = 2.0
MIN_TRADES = 12

# The ten bots: a name, the family each one specialises in (None = all three), and how boldly it mutates.
BOTS = [
    ("Hawk", "TREND", 1.0), ("Viper", "BREAKOUT", 1.0), ("Raven", "PULLBACK", 1.0),
    ("Titan", "TREND", 0.6), ("Comet", "BREAKOUT", 1.6), ("Blaze", None, 1.4),
    ("Specter", "PULLBACK", 0.6), ("Nova", None, 1.0), ("Onyx", "TREND", 1.6), ("Fang", None, 2.0),
]


def fitness(train: Score) -> float:
    """The training score with a penalty for few trades: a lower bound, not a best case."""
    if train.trades < MIN_TRADES:
        return -1.0 + train.trades * 0.01
    return train.expectancy - 1.0 / (train.trades ** 0.5)


def score_window(g: Genome, data: list[Series], lo_f: float, hi_f: float, min_stop: float, max_stop: float) -> Score:
    total = Score()
    for s in data:
        total = total + replay(g, s, int(s.size * lo_f), int(s.size * hi_f), min_stop, max_stop, signals(g, s))
    return total


def unseen(g: Genome, data: list[Series], min_stop: float, max_stop: float) -> tuple[Score, Score]:
    return (score_window(g, data, TRAIN, VALID, min_stop, max_stop),
            score_window(g, data, VALID, 1.0, min_stop, max_stop))


# ===================================================================== island

def _lower_priority() -> None:
    """Below-normal priority, so ten busy bots never make the PC itself stutter."""
    try:
        if os.name == "nt":
            import ctypes
            ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x00004000)
        else:
            os.nice(10)
    except Exception:
        pass


def island_main(index: int, family: str | None, strength: float, arrays: list[dict],
                min_stop: float, max_stop: float, seed: int, champion: dict | None,
                out: "mp.Queue", stop: "mp.Event", duty: "mp.Value") -> None:
    """One bot, in its own process: breed, replay on the training stretch, report."""
    _lower_priority()
    rng = random.Random(seed)
    data = [Series(a["symbol"], a["open"], a["high"], a["low"], a["close"], a["volume"]) for a in arrays]
    lo_hi = [(0, int(s.size * TRAIN)) for s in data]

    def trial(g: Genome) -> tuple[Genome, Score]:
        total = Score()
        for s, (lo, hi) in zip(data, lo_hi):
            total = total + replay(g, s, lo, hi, min_stop, max_stop, signals(g, s))
        return g, total

    pop: list[tuple[Genome, Score]] = []
    seeds = [DEFAULT.clamped()]
    if champion:
        seeds.append(Genome.from_dict(champion))
    for g in seeds:
        if family is None or g.family == family:
            pop.append(trial(g))
    while len(pop) < POPULATION:
        pop.append(trial(random_genome(rng, family)))
    tested, generations, last = len(pop), 0, time.time()
    rate = 0.0
    while not stop.is_set():
        started = time.time()
        parents = sorted(pop, key=lambda p: fitness(p[1]), reverse=True)[:PARENTS]
        children = []
        for _ in range(POPULATION - IMMIGRANTS):
            a = rng.choice(parents)[0]
            b = rng.choice(parents)[0]
            child = crossover(a, b, rng) if rng.random() < 0.5 else a
            child = mutate(child, rng, strength, family)
            children.append(trial(child))
        for _ in range(IMMIGRANTS):
            children.append(trial(random_genome(rng, family)))
        seen: dict[Genome, tuple[Genome, Score]] = {}
        for p in pop + children:
            seen.setdefault(p[0], p)
        pop = sorted(seen.values(), key=lambda p: fitness(p[1]), reverse=True)[:POPULATION]
        tested += len(children)
        generations += 1
        took = time.time() - started
        if took > 0:
            rate = rate * 0.8 + len(children) / took * 0.2
        if time.time() - last >= REPORT_EVERY:
            best, score = pop[0]
            try:
                out.put_nowait({"index": index, "tested": tested, "generations": generations, "rate": rate,
                                "best": best.to_dict(), "train": score.to_dict(), "fitness": fitness(score)})
            except Exception:
                pass
            last = time.time()
        # Duty below 1.0 rests between generations (light mode); 1.0 runs flat out.
        d = max(0.05, min(1.0, duty.value))
        if d < 1.0:
            stop.wait(took * (1 - d) / d)


# ====================================================================== arena

@dataclass
class Bot:
    index: int
    name: str
    family: str | None
    strength: float
    tested: int = 0
    generations: int = 0
    rate: float = 0.0
    best: Genome | None = None
    train: dict | None = None
    fitness: float | None = None
    valid: Score | None = None
    confirm: Score | None = None
    checked_genome: Genome | None = None
    # Paper-trading the bot's best on live candles.
    open: dict = field(default_factory=dict)       # symbol -> {"entry", "stop", "target", "at"}
    closed_r: list = field(default_factory=list)    # recent R results
    live_trades: int = 0

    def to_dict(self) -> dict:
        r = self.closed_r
        return {
            "index": self.index, "name": self.name, "family": self.family or "ALL", "tested": self.tested,
            "generations": self.generations, "rate": round(self.rate, 1),
            "best": self.best.to_dict() if self.best else None, "train": self.train, "fitness": self.fitness,
            "valid": self.valid.to_dict() if self.valid else None,
            "confirm": self.confirm.to_dict() if self.confirm else None,
            "live": {"open": [{"symbol": k, **v} for k, v in self.open.items()], "trades": self.live_trades,
                     "sum_r": round(sum(r), 3), "wins": sum(1 for x in r if x > 0)},
        }


@dataclass
class Promotion:
    version: int
    at: float
    bot: str
    before: Genome
    after: Genome
    unseen_before: float
    unseen_after: float
    trades: int
    rollback: bool = False

    def to_dict(self) -> dict:
        return {"version": self.version, "at": self.at, "bot": self.bot, "before": self.before.to_dict(),
                "after": self.after.to_dict(), "unseen_before": self.unseen_before,
                "unseen_after": self.unseen_after, "trades": self.trades, "rollback": self.rollback}

    @staticmethod
    def from_dict(d: dict) -> "Promotion":
        return Promotion(d["version"], d["at"], d.get("bot", ""), Genome.from_dict(d["before"]), Genome.from_dict(d["after"]),
                         d.get("unseen_before", 0.0), d.get("unseen_after", 0.0), d.get("trades", 0), d.get("rollback", False))


class Swarm:
    """Starts the bots, listens to them, and decides what the real account trades with."""

    def __init__(self, path: Path, now=time.time) -> None:
        self._path = path
        self._now = now
        self._lock = threading.RLock()
        self.champion: Genome = DEFAULT
        self.version = 1
        self.history: list[Promotion] = []
        self.bots: list[Bot] = []
        self._data: list[Series] = []
        self._min_stop, self._max_stop = 0.8, 6.0
        self._champion_test: tuple[Score, Score] | None = None
        self._default_test: tuple[Score, Score] | None = None
        self._last_promotion = 0.0
        self._procs: list[mp.Process] = []
        self._queue = None
        self._stop = None
        self._duty = None
        self._listener: threading.Thread | None = None
        self.data_at: float | None = None
        self.started_at: float | None = None
        self.mode = "off"     # off / waiting / full / light
        self.on_promotion = None   # callback(Promotion)
        self._load()

    # ------------------------------------------------------------- lifecycle

    @property
    def running(self) -> bool:
        return any(p.is_alive() for p in self._procs)

    def set_data(self, data: list[Series], min_stop: float, max_stop: float) -> Promotion | None:
        """New history (once a day). Re-checks the current strategy on it and may roll it back."""
        with self._lock:
            self._data = [s for s in data if s.size >= 300]
            self._min_stop, self._max_stop = min_stop, max_stop
            self.data_at = self._now()
            if not self._data:
                return None
            c = unseen(self.champion, self._data, min_stop, max_stop)
            d = unseen(DEFAULT, self._data, min_stop, max_stop)
            self._champion_test, self._default_test = c, d
            for b in self.bots:
                b.checked_genome = None
            if self.champion != DEFAULT and (c[0] + c[1]).expectancy < (d[0] + d[1]).expectancy - MARGIN:
                p = Promotion(self.version + 1, self._now(), "daily re-check", self.champion, DEFAULT,
                              (c[0] + c[1]).expectancy, (d[0] + d[1]).expectancy, (d[0] + d[1]).trades, rollback=True)
                self._adopt(p, d)
                return p
            return None

    def start(self, count: int, duty: float = 1.0) -> None:
        """Start (or restart, with fresh data) `count` bot processes."""
        self.stop()
        with self._lock:
            if not self._data or count <= 0:
                self.mode = "waiting" if count > 0 else "off"
                return
            ctx = mp.get_context("spawn")
            self._queue = ctx.Queue(maxsize=1000)
            self._stop = ctx.Event()
            self._duty = ctx.Value("d", duty)
            arrays = [s.to_arrays() for s in self._data]
            self.bots = []
            base_seed = int(self._now()) & 0xFFFFFF
            for i, (name, family, strength) in enumerate(BOTS[:count]):
                self.bots.append(Bot(i, name, family, strength))
                p = ctx.Process(target=island_main, name=f"MoneyTree-{name}", daemon=True, args=(
                    i, family, strength, arrays, self._min_stop, self._max_stop, base_seed + i * 7919,
                    self.champion.to_dict(), self._queue, self._stop, self._duty))
                p.start()
                self._procs.append(p)
            self.started_at = self._now()
            self.mode = "full" if duty >= 1.0 else "light"
        self._listener = threading.Thread(target=self._listen, name="swarm-arena", daemon=True)
        self._listener.start()

    def set_duty(self, duty: float) -> None:
        if self._duty is not None:
            self._duty.value = duty
        if self.running:
            self.mode = "full" if duty >= 1.0 else "light"

    def stop(self) -> None:
        if self._stop is not None:
            self._stop.set()
        for p in self._procs:
            p.join(timeout=3)
            if p.is_alive():
                p.terminate()
        self._procs = []
        if self.mode in ("full", "light"):
            self.mode = "off"

    # ---------------------------------------------------------------- arena

    def _listen(self) -> None:
        while self.running:
            try:
                msg = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue
            except Exception:
                break
            self.receive(msg)

    def receive(self, msg: dict) -> Promotion | None:
        """One bot's report. Its best is judged on the unseen stretches."""
        with self._lock:
            if msg["index"] >= len(self.bots):
                return None
            b = self.bots[msg["index"]]
            b.tested, b.generations, b.rate = msg["tested"], msg["generations"], msg["rate"]
            b.best, b.train, b.fitness = Genome.from_dict(msg["best"]), msg["train"], msg["fitness"]
            if b.best == b.checked_genome or not self._data:
                return None
            b.checked_genome = b.best
            b.valid, b.confirm = unseen(b.best, self._data, self._min_stop, self._max_stop)
            promotion = self._consider(b)
        if promotion is not None and self.on_promotion:
            try:
                self.on_promotion(promotion)
            except Exception:
                log.exception("promotion callback failed")
        return promotion

    def _consider(self, b: Bot) -> Promotion | None:
        if b.best is None or b.best == self.champion or (b.train or {}).get("expectancy", 0) <= 0:
            return None
        if self._now() - self._last_promotion < MIN_GAP:
            return None
        v, c = b.valid, b.confirm
        cv, cc = self._champion_test or unseen(self.champion, self._data, self._min_stop, self._max_stop)
        ok = (v.trades >= MIN_VALID_TRADES and c.trades >= MIN_CONFIRM_TRADES
              and v.expectancy >= cv.expectancy + MARGIN
              and c.expectancy >= cc.expectancy and c.expectancy > 0)
        if not ok:
            return None
        p = Promotion(self.version + 1, self._now(), b.name, self.champion, b.best,
                      (cv + cc).expectancy, (v + c).expectancy, (v + c).trades)
        self._adopt(p, (v, c))
        return p

    def _adopt(self, p: Promotion, test: tuple[Score, Score]) -> None:
        self.champion = p.after
        self.version = p.version
        self._champion_test = test
        self._last_promotion = p.at
        self.history.insert(0, p)
        del self.history[40:]
        self._save()

    def reset(self) -> Promotion | None:
        with self._lock:
            if self.champion == DEFAULT:
                return None
            d = unseen(DEFAULT, self._data, self._min_stop, self._max_stop) if self._data else (Score(), Score())
            p = Promotion(self.version + 1, self._now(), "owner", self.champion, DEFAULT, 0.0,
                          (d[0] + d[1]).expectancy, (d[0] + d[1]).trades, rollback=True)
            self._adopt(p, d)
            return p

    # ------------------------------------------------- live paper trading

    def paper_trade(self, frames: dict) -> None:
        """Each bot trades its best on the latest candles, on paper: the live leaderboard."""
        with self._lock:
            bots = list(self.bots)
        for b in bots:
            g = b.best
            if g is None:
                continue
            for symbol, df in frames.items():
                if df is None or len(df) < g.warmup + 2:
                    continue
                s = Series.from_frame(symbol, df.tail(max(g.warmup + 50, 300)))
                entry, exit_ = signals(g, s)
                price, low, high = float(s.close[-1]), float(s.low[-1]), float(s.high[-1])
                pos = b.open.get(symbol)
                if pos is not None:
                    r = None
                    if low <= pos["stop"]:
                        r = (pos["stop"] - pos["entry"]) / (pos["entry"] - pos["stop"])
                    elif high >= pos["target"]:
                        r = (pos["target"] - pos["entry"]) / (pos["entry"] - pos["stop"])
                    elif exit_[-1]:
                        r = (price - pos["entry"]) / (pos["entry"] - pos["stop"])
                    if r is not None:
                        b.closed_r.append(float(r) - 0.03)
                        del b.closed_r[:-200]
                        b.live_trades += 1
                        del b.open[symbol]
                    else:
                        pos["now_r"] = float((price - pos["entry"]) / (pos["entry"] - pos["stop"]))
                elif entry[-1] and s.atr[-1] > 0:
                    pct = min(max(s.atr[-1] * g.atr_mult / price * 100, self._min_stop), self._max_stop) / 100
                    b.open[symbol] = {"entry": price, "stop": float(price * (1 - pct)),
                                      "target": float(price * (1 + pct * g.reward_risk)), "at": self._now(), "now_r": 0.0}

    # -------------------------------------------------------------- views

    def snapshot(self) -> dict:
        with self._lock:
            ct, dt = self._champion_test, self._default_test
            return {
                "running": self.running, "mode": self.mode, "bots": [b.to_dict() for b in self.bots],
                "tested": sum(b.tested for b in self.bots), "rate": round(sum(b.rate for b in self.bots), 1),
                "generations": sum(b.generations for b in self.bots),
                "champion": self.champion.to_dict(), "default": DEFAULT.to_dict(), "version": self.version,
                "champion_test": (ct[0] + ct[1]).to_dict() if ct else None,
                "default_test": (dt[0] + dt[1]).to_dict() if dt else None,
                "history": [p.to_dict() for p in self.history],
                "symbols": len(self._data), "bars": int(sum(s.size for s in self._data)),
                "data_at": self.data_at, "cpus": os.cpu_count(),
                "rules": {"margin": MARGIN, "min_valid": MIN_VALID_TRADES, "min_confirm": MIN_CONFIRM_TRADES,
                          "gap_minutes": MIN_GAP / 60},
            }

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"champion": self.champion.to_dict(), "version": self.version,
                                       "last_promotion": self._last_promotion,
                                       "history": [p.to_dict() for p in self.history]}), encoding="utf-8")
            tmp.replace(self._path)
        except Exception:
            log.exception("could not save the swarm")

    def _load(self) -> None:
        try:
            d = json.loads(self._path.read_text(encoding="utf-8"))
            self.champion = Genome.from_dict(d["champion"])
            self.version = int(d.get("version", 1))
            self._last_promotion = float(d.get("last_promotion", 0.0))
            self.history = [Promotion.from_dict(x) for x in d.get("history", [])]
        except FileNotFoundError:
            pass
        except Exception:
            log.warning("swarm state unreadable; starting from the original strategy")
