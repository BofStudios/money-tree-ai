"""Money Bot 12.0: the Time Machine can only hold an Ultra buy back."""
from __future__ import annotations

from datetime import datetime, timedelta

from app.engine.timemachine import BARS, NY, TimeMachine, leans_to_stop, pool_from, replay, slot_of


def sessions(n=25, drift=0.0, wick=0.004, start=datetime(2026, 9, 1, 9, 30, tzinfo=NY)):
    """n full sessions of 5-minute bars; drift per bar, symmetric wicks."""
    out, price, day = [], 100.0, start
    while len({t.date() for t, *_ in out}) < n:
        if day.weekday() < 5:
            for k in range(BARS):
                t = day + timedelta(minutes=5 * k)
                o = price
                c = o * (1 + drift)
                out.append((t, o, max(o, c) * (1 + wick), min(o, c) * (1 - wick), c))
                price = c
        day += timedelta(days=1)
    return out


def test_the_pool_keeps_only_full_sessions_and_counts_them():
    bars = sessions(22)
    bars += [(datetime(2026, 10, 30, 9, 30, tzinfo=NY), 1, 1, 1, 1)]      # a half day is left out
    pool, n = pool_from(bars)
    assert n == 22 and len(pool) == BARS and all(pool[s] for s in range(1, BARS))
    assert slot_of(datetime(2026, 11, 18, 9, 31, tzinfo=NY)) == 0
    assert slot_of(datetime(2026, 11, 18, 15, 55, tzinfo=NY)) == 77


def test_falling_bars_hit_the_stop_and_are_held_back_rising_ones_are_not():
    down, _ = pool_from(sessions(25, drift=-0.003))
    odds = replay(down, 100, 99.5, 100.75, 10, 6)
    assert odds["stop"] > 0.9 and leans_to_stop(odds)
    up, _ = pool_from(sessions(25, drift=0.003))
    odds = replay(up, 100, 99.5, 100.75, 10, 6)
    assert odds["target"] > 0.9 and not leans_to_stop(odds)
    assert replay(up, 100, 99.5, 100.75, 10, 6) == odds                    # the seed repeats


def test_check_needs_a_pool_and_respects_the_hold_and_the_close():
    tm = TimeMachine(fetch=lambda s: sessions(25, drift=-0.003))
    morning = datetime(2026, 11, 18, 10, 2, tzinfo=NY)
    assert tm.check("AAPL", 100, 0.5, 1.5, morning) is None               # no pool yet: never holds back
    assert tm.load(["AAPL"]) == 1
    odds = tm.check("aapl", 100, 0.5, 1.5, morning)
    assert odds["hold"] and odds["bars"] == 6 and odds["sessions"] == 25  # 30 minutes = six bars
    late = tm.check("AAPL", 100, 0.5, 1.5, datetime(2026, 11, 18, 15, 41, tzinfo=NY))
    assert late["bars"] == 2                                              # flat at 15:52
    assert tm.check("AAPL", 100, 0.5, 1.5, datetime(2026, 11, 18, 16, 1, tzinfo=NY)) is None


def test_ultra_skips_a_buy_the_replays_lean_against(tmp_path, monkeypatch):
    from app.engine import scalper as S
    from tests.test_scalper import NOW, VOTE, frame, scalp_engine

    monkeypatch.setattr(S, "dip_confluence", lambda *a, **k: dict(VOTE))
    engine = scalp_engine(tmp_path)
    engine.timemachine = TimeMachine(engine, fetch=lambda s: sessions(25, drift=-0.003))
    engine.timemachine.load(["AAPL"])
    engine.scalper.tick({"AAPL": frame()}, now=NOW)
    assert engine.position_for("AAPL") is None
    assert engine.funnel.view()["blocked"][0]["gate"] == "odds"

    fresh = scalp_engine(tmp_path / "up")
    fresh.timemachine = TimeMachine(fresh, fetch=lambda s: sessions(25, drift=0.003, wick=0.001))
    fresh.timemachine.load(["AAPL"])
    fresh.scalper.tick({"AAPL": frame()}, now=NOW)
    assert fresh.position_for("AAPL") is not None
