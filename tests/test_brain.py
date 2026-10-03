"""The desktop brain: headlines, the five checks, SEC parsing, strategies, the swarm's arena, learning."""
import json
import random

import numpy as np
import pandas as pd
import pytest

from app.brain import quality, sources, swarm as swarm_mod, text
from app.brain.genome import (
    DEFAULT, FAMILIES, Genome, Score, Series, crossover, mutate, random_genome, replay, signals,
)
from app.brain.learning import Features, Learner, Sample
from app.brain.radar import NewsItem, NewsRadar
from app.brain.swarm import Swarm

NOW = 1_790_000_000.0


# ------------------------------------------------------------------- text

def test_headline_scores_follow_the_words():
    assert text.score("Apple beats estimates and raises guidance") > 0
    assert text.score("Tesla plunges after earnings miss") < 0
    assert text.score("Company did not beat estimates") < text.score("Company beat estimates")


def test_red_flags_and_what_they_block():
    assert "BANKRUPTCY" in text.red_flags("Retailer files for Chapter 11 protection")
    assert "OFFERING" in text.red_flags("Biotech prices offering of 10M shares")
    assert text.red_flags("Apple launches a new phone") == []
    assert text.blocks_buys("HALT") and text.blocks_buys("EARNINGS_SOON")
    assert not text.blocks_buys("RECALL")


def test_topics():
    assert "MACRO" in text.topics("Fed holds interest rates as inflation cools")


# ------------------------------------------------------------------- radar

def item(i, headline, symbols=("AAPL",), hours_ago=1.0, **kw):
    return NewsItem(i, headline, "", "test", list(symbols), NOW - hours_ago * 3600, **kw)


def test_radar_mood_flags_and_ai_reading_survive_updates():
    radar = NewsRadar(now=lambda: NOW)
    assert radar.ingest([item(1, "Apple beats estimates"), item(2, "Apple surges to a record")]) == 2
    assert radar.mood("AAPL") > 0
    assert radar.mood("MSFT") is None
    radar.apply_scores({1: -0.9})
    assert radar.ingest([item(1, "Apple beats estimates")]) == 0
    assert next(n for n in radar.all() if n.id == 1).ai_score == -0.9
    radar.ingest([item(3, "Apple faces trading halt", hours_ago=2)])
    assert [f.kind for f in radar.flags("AAPL")] == ["HALT"]


def test_given_flags_are_kept_and_round_trip():
    n = item(9, "SEC 8-K: results of operations", flags=[], topics=["EARNINGS"])
    assert n.flags == [] and n.topics == ["EARNINGS"]
    back = NewsItem.from_dict(json.loads(json.dumps(n.to_dict())))
    assert back.flags == [] and back.topics == ["EARNINGS"] and back.score == n.score


def test_wire_keeps_one_day_and_the_snapshot_serialises():
    radar = NewsRadar(now=lambda: NOW)
    radar.ingest_wire([item(10, "Nvidia rallies", ("NVDA",)), item(11, "Old news", ("NVDA",), hours_ago=30)])
    snap = radar.snapshot(["AAPL", "NVDA"])
    assert snap["wire_size"] == 1
    json.dumps(snap)


# ---------------------------------------------------------------- quality

def year(end, revenue, ni, **kw):
    base = dict(gross_profit=revenue * 0.6, operating_income=revenue * 0.3, equity=ni * 4, debt=ni,
                operating_cash_flow=ni * 1.2, capex=ni * 0.2, shares=1_000.0, interest=revenue * 0.01, cash=ni)
    base.update(kw)
    return quality.FiscalYear(end, revenue, ni, **base)


def great_company():
    years = [year(f"20{y}-12-31", 1000 * 1.1 ** i, 250 * 1.1 ** i) for i, y in enumerate(range(20, 26))]
    return quality.Filings("GOOD", "Good Co", "USD", False, False, years, NOW)


def test_a_great_business_at_a_fair_price_is_a_buy_zone():
    f = great_company()
    value = quality.value_per_listing(f, 1.0, None, quality.cagr([y.revenue for y in f.years]))
    report = quality.evaluate("GOOD", f, value * 0.8, 1.0, None, [])
    assert [c.verdict for c in report.checks[:4]] == ["PASS", "PASS", "PASS", "PASS"]
    assert report.decision == "BUY_ZONE"
    json.dumps(report.to_dict())


def test_the_same_business_too_expensive_waits():
    f = great_company()
    value = quality.value_per_listing(f, 1.0, None, quality.cagr([y.revenue for y in f.years]))
    report = quality.evaluate("GOOD", f, value * 2.0, 1.0, None, [])
    assert report.check("VALUE").verdict == "FAIL"
    assert report.decision == "WAIT"


def test_a_severe_flag_fails_risk_and_avoids():
    from app.brain.radar import RedFlag
    report = quality.evaluate("GOOD", great_company(), 1.0, 1.0, None, [RedFlag("FRAUD", "GOOD", NOW, "x")])
    assert report.check("RISK").verdict == "FAIL"
    assert report.decision == "AVOID"


def test_funds_are_judged_on_the_200_day_average():
    closes = np.linspace(100, 120, 260)
    daily = {"close": closes, "high": closes * 1.005, "low": closes * 0.995}
    report = quality.evaluate("SPY", None, 100.0, 1.0, daily, [])
    assert report.fund and report.check("VALUE").verdict == "PASS"


# ---------------------------------------------------------------- sources

def test_parse_facts_takes_annual_rows_and_the_latest_filing():
    def rows(vals, form="10-K"):
        return [{"start": f"{y - 1}-01-01", "end": f"{y - 1}-12-31", "val": v, "form": form, "filed": f"{y}-02-01"}
                for y, v in vals]
    doc = {"entityName": "Test Inc", "facts": {"us-gaap": {
        "Revenues": {"units": {"USD": rows([(2023, 100.0), (2024, 120.0), (2025, 150.0)])
                               + [{"start": "2024-10-01", "end": "2024-12-31", "val": 40.0, "form": "10-K", "filed": "2025-02-01"}]}},
        "NetIncomeLoss": {"units": {"USD": rows([(2023, 10.0), (2024, 12.0), (2025, 15.0)])}},
    }}}
    f = sources.parse_facts("TEST", doc, NOW)
    assert f.name == "Test Inc" and not f.foreign
    assert [y.revenue for y in f.years] == [100.0, 120.0, 150.0]
    assert f.years[-1].net_income == 15.0


def test_parse_events_reads_8k_items_insiders_and_results_rhythm():
    day = 86400
    dates = [NOW - d * day for d in (5, 96, 187, 278, 10)]
    doc = {"filings": {"recent": {
        "form": ["8-K", "8-K", "8-K", "8-K", "4"],
        "items": ["2.02", "2.02", "2.02", "2.02", ""],
        "acceptanceDateTime": [pd.Timestamp(d, unit="s", tz="UTC").isoformat() for d in dates],
        "filingDate": ["", "", "", "", ""],
        "accessionNumber": ["a", "b", "c", "d", "e"],
    }}}
    ev = sources.parse_events("TEST", doc, NOW)
    assert ev["insiders_30d"] == 1
    assert len(ev["results"]) == 4
    assert ev["next_results"] is not None and ev["next_results"] > NOW


def test_attention_ratio():
    assert sources.attention_ratio([100] * 28 + [300, 300]) == pytest.approx(3.0)
    assert sources.attention_ratio([1, 2]) is None


# ----------------------------------------------------------------- genome

def walk(n=1500, seed=1, drift=0.0):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(drift, 0.01, n)))
    high = close * (1 + rng.uniform(0, 0.006, n))
    low = close * (1 - rng.uniform(0, 0.006, n))
    open_ = np.concatenate([[close[0]], close[:-1]])
    high, low = np.maximum(high, open_), np.minimum(low, open_)
    return Series("SIM", open_, high, low, close, rng.uniform(1e5, 2e5, n))


def test_genomes_stay_in_bounds_through_mutation_and_crossover():
    rng = random.Random(3)
    g = random_genome(rng)
    for _ in range(300):
        g = crossover(mutate(g, rng, 2.0), random_genome(rng), rng)
        assert g == g.clamped() and g.family in FAMILIES and g.slow >= g.fast + 6
    assert Genome.from_dict(g.to_dict()) == g


def test_signals_never_fire_during_warmup():
    s = walk()
    for family in FAMILIES:
        g = Genome(family=family)
        entry, exit_ = signals(g, s)
        assert entry.shape == exit_.shape == (s.size,)
        assert not entry[: g.warmup].any()


def test_replay_charges_costs_and_returns_plain_floats():
    s = walk()
    score = replay(DEFAULT, s, 0, s.size, 0.8, 6.0)
    assert score.trades > 0
    assert type(score.sum_r) is float and type(score.wins) is int
    json.dumps(score.to_dict())
    # Each trade risks 1R and pays the cost; nothing loses much more than its stop.
    assert score.expectancy > -1.5


def test_a_gap_through_the_stop_fills_at_the_open():
    n = 200
    close = np.full(n, 100.0)
    close[100] = 101.0
    s = Series("GAP", close.copy(), close * 1.001, close * 0.999, close, np.full(n, 1e5))
    s.open[101], s.low[101], s.high[101], s.close[101] = 90.0, 89.0, 91.0, 90.0
    entry = np.zeros(n, dtype=bool)
    entry[100] = True
    score = replay(DEFAULT, s, 0, n, 0.8, 6.0, (entry, np.zeros(n, dtype=bool)))
    assert score.trades == 1
    risk = 101.0 - 101.0 * (1 - 0.008)
    assert score.sum_r == pytest.approx((90.0 - 101.0) / risk - 0.03)


# ------------------------------------------------------------------ swarm

class Clock:
    def __init__(self):
        self.t = NOW

    def __call__(self):
        return self.t


def bot_msg(g: Genome, index=0):
    return {"index": index, "tested": 1000, "generations": 10, "rate": 500.0, "best": g.to_dict(),
            "train": {"expectancy": 0.4, "trades": 80}, "fitness": 0.3}


def test_the_arena_promotes_only_what_wins_on_unseen_data(tmp_path, monkeypatch):
    clock = Clock()
    sw = Swarm(tmp_path / "swarm.json", now=clock)
    sw.set_data([walk(seed=i) for i in range(2)], 0.8, 6.0)
    sw.bots = [swarm_mod.Bot(0, "Hawk", "TREND", 1.0)]
    better = Genome(fast=8, slow=30)
    champion = (Score(30, 0.0, 12), Score(20, 0.0, 8))
    good = (Score(30, 0.3 * 30, 15), Score(20, 0.2 * 20, 10))
    monkeypatch.setattr(swarm_mod, "unseen", lambda g, *a: good if g == better else champion)
    sw._champion_test = champion

    seen = []
    sw.on_promotion = seen.append
    p = sw.receive(bot_msg(better))
    assert p is not None and sw.champion == better and sw.version == 2 and seen == [p]

    # Persisted, and reloaded by the next start of the app.
    again = Swarm(tmp_path / "swarm.json", now=clock)
    assert again.champion == better and again.version == 2 and again.history[0].bot == "Hawk"

    # Too soon after the last change: nothing else is adopted.
    other = Genome(fast=9, slow=31)
    monkeypatch.setattr(swarm_mod, "unseen", lambda g, *a: good)
    assert sw.receive(bot_msg(other)) is None
    clock.t += swarm_mod.MIN_GAP + 1
    sw._champion_test = good
    assert sw.receive(bot_msg(Genome(fast=10, slow=32))) is None   # not better than the champion now


def test_the_arena_ignores_thin_evidence(tmp_path, monkeypatch):
    sw = Swarm(tmp_path / "swarm.json", now=Clock())
    sw.set_data([walk()], 0.8, 6.0)
    sw.bots = [swarm_mod.Bot(0, "Hawk", "TREND", 1.0)]
    lucky = (Score(4, 4.0, 4), Score(3, 3.0, 3))     # brilliant, on seven trades
    monkeypatch.setattr(swarm_mod, "unseen", lambda g, *a: lucky if g != DEFAULT else (Score(), Score()))
    sw._champion_test = (Score(), Score())
    assert sw.receive(bot_msg(Genome(fast=7, slow=40))) is None
    assert sw.champion == DEFAULT


def test_owner_reset_rolls_back_and_the_snapshot_serialises(tmp_path):
    sw = Swarm(tmp_path / "swarm.json", now=Clock())
    sw.set_data([walk()], 0.8, 6.0)
    sw.champion = Genome(fast=7, slow=40)
    p = sw.reset()
    assert p.rollback and sw.champion == DEFAULT
    json.dumps(sw.snapshot())


def test_paper_trading_the_leaderboard(tmp_path):
    sw = Swarm(tmp_path / "swarm.json", now=Clock())
    b = swarm_mod.Bot(0, "Hawk", "TREND", 1.0, best=DEFAULT)
    sw.bots = [b]
    s = walk(800, seed=4)
    df = pd.DataFrame({"open": s.open, "high": s.high, "low": s.low, "close": s.close, "volume": s.volume})
    for end in range(400, 800, 5):
        sw.paper_trade({"SIM": df.iloc[:end]})
    json.dumps(b.to_dict())
    assert b.live_trades >= 0


def test_no_bots_without_data(tmp_path):
    sw = Swarm(tmp_path / "swarm.json", now=Clock())
    sw.start(10)
    assert sw.mode == "waiting" and not sw.running
    sw.start(0)
    assert sw.mode == "off"


# --------------------------------------------------------------- learning

def test_the_learner_blocks_what_keeps_losing_and_keeps_what_works():
    learner = Learner()
    new_rules = []
    for i in range(30):
        new_rules += learner.add(Sample(Features(f"S{i % 5}", quality="AVOID", news=-0.5), -1.0, False, NOW))
        learner.add(Sample(Features(f"S{i % 5}", quality="BUY_ZONE", news=0.5), 1.0, False, NOW))
    assert any(r.key == "QUALITY" and r.value == "AVOID" for r in new_rules)
    bad = learner.verdict(Features("S9", quality="AVOID", news=-0.5))
    assert bad.blocked and bad.size == 0.5
    good = learner.verdict(Features("S9", quality="BUY_ZONE", news=0.5))
    assert not good.blocked and good.size == 1.0
    again = Learner()
    again.load(json.loads(json.dumps(learner.to_json())))
    assert again.verdict(Features("S9", quality="AVOID", news=-0.5)).blocked
