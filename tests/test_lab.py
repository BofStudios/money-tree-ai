"""Desktop 10.0: the Lab (replay, metrics, edge filter), analytics and screenshots in the chat."""
from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.engine import lab as LAB
from app.engine import scalper as S
from app.engine.analytics import analyse, book_of, streaks
from app.strategy import confluence as C
from tests.test_scalper import NOW, VOTE, frame, scalp_engine


def day_bars(days=2, seed=1, start="2026-11-02"):
    """Random-walk one-minute bars for whole New York sessions (9:30-16:00)."""
    rng = np.random.default_rng(seed)
    frames = []
    d = pd.Timestamp(start)
    while len(frames) < days:
        if d.weekday() < 5:
            idx = pd.date_range(d + pd.Timedelta(hours=9, minutes=30), periods=390, freq="1min", tz=S.NY)
            frames.append(idx)
        d += pd.Timedelta(days=1)
    idx = frames[0].append(frames[1:]) if len(frames) > 1 else frames[0]
    n = len(idx)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.0012, n)))
    openp = np.r_[close[0], close[:-1]]
    high = np.maximum(openp, close) * (1 + rng.uniform(0, 0.0008, n))
    low = np.minimum(openp, close) * (1 - rng.uniform(0, 0.0008, n))
    vol = rng.uniform(800, 1500, n)
    return pd.DataFrame({"open": openp, "high": high, "low": low, "close": close, "volume": vol},
                        index=idx.tz_convert("UTC"))


# ------------------------------------------------------------ no peeking

@pytest.mark.real_vote
def test_the_replay_never_looks_at_the_future():
    """Freqtrade's lookahead analysis: cutting the future off changes no decision."""
    df = day_bars(2, seed=7)
    loose = lambda ch: ch["rsi"] is not None and ch["rsi"] <= S.RSI_MAX     # many entries to compare
    full = LAB.entries(df, loose)
    assert len(full) > 10
    for cut in (len(df) // 2, len(df) - 120):
        part = LAB.entries(df.iloc[:cut], loose)
        a = [(i, round(ch["price"], 6), ch["conf"]["score"]) for i, ch in full if i < cut - 1]
        b = [(i, round(ch["price"], 6), ch["conf"]["score"]) for i, ch in part]
        assert a == b


def test_inside_one_minute_the_stop_is_checked_before_the_target():
    df = day_bars(1, seed=3)
    i = 200
    entry = df["open"].iloc[i + 1]
    df.iloc[i + 1, df.columns.get_loc("high")] = entry * 1.05     # target and stop in the same minute
    df.iloc[i + 1, df.columns.get_loc("low")] = entry * 0.95
    ch = {"atr_pct": 0.2, "conf": {"score": 0.7}}
    trades = LAB.replay_symbol("X", df, lambda c: True, charts=[(i, ch)])
    assert trades[0]["why"] == "stop"
    assert trades[0]["pnl"] == pytest.approx(-S.stop_for(ch) - LAB.COST, abs=1e-3)


def test_one_trade_at_a_time_per_symbol_and_an_unfinished_trade_is_not_counted():
    df = day_bars(1, seed=5)
    ch = {"atr_pct": 0.2, "conf": {"score": 0.7}}
    charts = [(i, ch) for i in range(160, 380)]
    trades = LAB.replay_symbol("X", df, lambda c: True, charts=charts)
    outs = [t["out"] for t in trades]
    ats = [t["at"] for t in trades]
    assert all(a > o for a, o in zip(ats[1:], outs[:-1])), "a new trade only after the last one ended"
    assert all(t["why"] in ("stop", "target", "time", "early", "close") for t in trades)


# --------------------------------------------------------------- numbers

def test_metrics_profit_factor_and_win_rate():
    m = LAB.metrics([1.0, -0.5, 0.5, -0.5])
    assert m["trades"] == 4 and m["win_rate"] == 50.0
    assert m["profit_factor"] == 1.5 and m["avg"] == pytest.approx(0.125)
    assert LAB.metrics([])["trades"] == 0
    assert LAB.max_drawdown([100, 110, 99, 120]) == -10.0
    assert LAB.ratios([1.0, -1.0])["sharpe"] is None, "two days say nothing"


def test_the_account_uses_ultras_money_rules():
    t = lambda at, out, pnl, sym, vote=0.625: {"at": at, "out": out, "pnl": pnl, "symbol": sym, "vote": vote}
    trades = [
        t("2026-11-02T10:00", "2026-11-02T10:20", 1.0, "A"),
        t("2026-11-02T10:01", "2026-11-02T10:30", 1.0, "B"),
        t("2026-11-02T10:02", "2026-11-02T10:10", 5.0, "C"),          # both slots busy: skipped
        t("2026-11-02T11:00", "2026-11-02T11:05", 10.0, "D", vote=0.75),   # strong vote, nothing open: all in
    ]
    sim = LAB.simulate(trades, 100.0)
    assert sim["taken"] == 3 and sim["skipped"] == 1
    half = 100 * S.ALLOC                       # A and B: about half the account each
    mid = 100 + 2 * half * 0.01                # both made 1%
    assert sim["end"] == pytest.approx(mid + mid * S.ALL_IN * 0.10, abs=0.02)
    assert sim["curve"][-1]["value"] == sim["end"]


def test_the_edge_rule_skips_only_clear_losers():
    rows = [{"key": "A", "trades": 8, "avg": -0.15}, {"key": "B", "trades": 7, "avg": -0.9},
            {"key": "C", "trades": 20, "avg": -0.1}, {"key": "D", "trades": 9, "avg": None}]
    assert LAB.edge_blocked(rows) == ["A"]


# ------------------------------------------------------------------- lab

def fake_frames(_symbols):
    return {"AAA": day_bars(2, seed=11), "BBB": day_bars(2, seed=12)}


def test_a_lab_run_is_saved_and_the_edge_switch_is_kept(tmp_path, monkeypatch):
    path = tmp_path / "lab.json"
    lab = LAB.Lab(path=path, fetch=fake_frames)
    assert lab.due() and lab.status()["report"] is None
    assert lab.run()["ok"]
    saved = json.loads(path.read_text(encoding="utf-8"))
    rep = saved["report"]
    assert set(rep["rules"]) == {"8.0", "9.0"} and rep["symbols_n"] == 2 and not lab.due()
    assert rep["rules"]["9.0"]["portfolio"]["start"] == LAB.START_CASH

    lab._blocked = {"AAA"}
    assert lab.edge_blocked("AAA") and not lab.edge_blocked("BBB")
    lab.set_edge(False)
    assert not lab.edge_blocked("AAA")
    again = LAB.Lab(path=path)
    assert again.edge_on is False, "the switch survives a restart"


def test_a_failed_download_is_reported_not_raised(tmp_path):
    lab = LAB.Lab(path=tmp_path / "lab.json", fetch=lambda s: {})
    got = lab.run()
    assert not got["ok"] and "bars" in lab.status()["error"] and not lab.running


def test_ultra_skips_a_symbol_the_lab_lost_on(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "dip_confluence", lambda *a, **k: dict(VOTE))   # the vote fixed at 5 of 8
    engine = scalp_engine(tmp_path)
    engine.lab._loaded = True
    engine.lab._blocked = {"AAPL"}
    rows = engine.scalper.tick({"AAPL": frame(), "MSFT": frame()}, now=NOW)
    assert [r["symbol"] for r in rows if r["action"] == "buy"] == ["MSFT"]
    assert engine.scalper.snapshot()["edge_skipped"] == ["AAPL"]
    engine.lab._settings["edge"] = False
    assert engine.scalper.snapshot()["edge_skipped"] == []


# ------------------------------------------------------- the faster vote

def _old_sma(x, n):
    out = np.full(len(x), np.nan)
    for i in range(n - 1, len(x)):
        w = x[i - n + 1:i + 1]
        if not np.any(np.isnan(w)):
            out[i] = w.mean()
    return out


def _old_cci(h, l, c, n=20):
    tp = (h + l + c) / 3
    out = np.full(len(tp), np.nan)
    for i in range(n - 1, len(tp)):
        w = tp[i - n + 1:i + 1]
        dev = np.abs(w - w.mean()).mean()
        out[i] = 0.0 if dev == 0 else (tp[i] - w.mean()) / (0.015 * dev)
    return out


def test_the_vectorised_indicators_give_the_same_numbers():
    df = day_bars(1, seed=21)
    h, l, c = (df[k].to_numpy(float) for k in ("high", "low", "close"))
    np.testing.assert_allclose(C._sma(c, 5), _old_sma(c, 5), equal_nan=True, rtol=1e-12)
    np.testing.assert_allclose(C.cci(h, l, c), _old_cci(h, l, c), equal_nan=True, rtol=1e-9)
    flat = np.full(40, 10.0)
    assert np.nanmax(C.bollinger_pctb(flat)) == 0.5 and np.nanmax(C.williams_r(flat, flat, flat)) == -50.0
    k, d = C.stoch_rsi(c)
    assert np.nanmin(k) >= 0 and np.nanmax(k) <= 100 and np.isnan(k[:27]).all()


# ------------------------------------------------------------- analytics

def _t(pnl, reason="Scalp: dip", opened="2026-11-02T15:00:00", closed="2026-11-02T15:20:00", sym="AAPL"):
    return {"symbol": sym, "side": "long", "pnl": pnl, "pnl_pct": pnl, "entry_reason": reason,
            "opened_at": opened, "closed_at": closed}


def test_analytics_of_real_trades():
    trades = [
        _t(2.0), _t(-1.0, closed="2026-11-02T16:00:00"), _t(-1.0, "Long-term: quality", closed="2026-11-03T15:00:00"),
        _t(3.0, "Swing: pullback", opened="2026-11-03T18:00:00", closed="2026-11-03T19:00:00", sym="MSFT"),
    ]
    curve = [{"time": int(datetime(2026, 11, d, 21, tzinfo=timezone.utc).timestamp()), "value": v}
             for d, v in ((2, 100.0), (3, 101.0), (4, 99.0), (5, 102.0))]
    a = analyse(trades, curve)
    assert a["money"]["trades"] == 4 and a["money"]["net"] == 3.0
    assert a["money"]["profit_factor"] == 2.5 and a["money"]["expectancy"] == 0.75
    assert {r["key"] for r in a["books"]} == {"ultra", "long", "swing"}
    assert [r["key"] for r in a["hours"]] == [10, 13], "hours are New York hours of the entry"
    assert a["risk"]["max_drawdown"] == pytest.approx(-1.98, abs=0.01) and a["risk"]["sharpe"] is not None
    assert a["streaks"] == {"longest_wins": 1, "longest_losses": 2, "current": 1}
    assert [d["day"] for d in a["days"]] == ["2026-11-02", "2026-11-03"]
    assert analyse([], [])["money"]["trades"] == 0


def test_book_and_streaks():
    assert book_of({"entry_reason": "Scalp: x"}) == "ultra"
    assert book_of({"entry_reason": "EMA cross", "side": "short"}) == "short"
    assert book_of({"entry_reason": "EMA cross", "side": "long"}) == "strategy"
    assert streaks([1, 1, 1, -1, -1]) == {"longest_wins": 3, "longest_losses": 2, "current": -2}


# ---------------------------------------------------------------- routes

def _lab_client(tmp_path):
    from app.web.lab_routes import build_lab_router

    engine = scalp_engine(tmp_path)
    engine.lab = LAB.Lab(engine, path=tmp_path / "lab.json", fetch=fake_frames)
    app = FastAPI()
    app.include_router(build_lab_router(engine, engine.repo, "tok"))
    return TestClient(app), engine


def test_lab_routes(tmp_path):
    client, engine = _lab_client(tmp_path)
    assert client.get("/api/lab").status_code == 401
    got = client.get("/api/lab?token=tok").json()
    assert got["edge"] is True and got["report"] is None
    assert client.post("/api/lab/edge?token=tok", json={"on": "no"}).status_code == 400
    assert client.post("/api/lab/edge?token=tok", json={"on": False}).json()["edge"] is False
    assert client.post("/api/lab/edge", json={"on": True}).status_code == 401
    a = client.get("/api/analytics?token=tok").json()
    assert a["money"]["trades"] == 0 and a["mode"] == engine.mode


# ------------------------------------------------------- chat screenshots

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 64).decode()


def test_images_are_checked_before_anything_is_sent():
    from app.mentor.vision import ImageError, clean_images

    assert clean_images([f"data:image/png;base64,{PNG}"]) == [("image/png", PNG)]
    assert clean_images([{"type": "image/jpeg", "data": PNG}])[0][0] == "image/jpeg"
    for bad in ([f"data:text/html;base64,{PNG}"], ["data:image/png;base64,@@@"], [f"data:image/png;base64,{PNG}"] * 4,
                [{"type": "image/png", "data": base64.b64encode(b"0" * (4 * 1024 * 1024 + 1)).decode()}]):
        with pytest.raises(ImageError):
            clean_images(bad)


def test_vision_tries_groq_then_gemini_and_keeps_no_image(tmp_path, monkeypatch):
    from app.config import MentorConfig
    from app.mentor import vision
    from app.mentor.ai import AIMentor

    calls = []
    monkeypatch.setattr(vision, "ask_groq", lambda *a: calls.append("groq") or None)
    monkeypatch.setattr(vision, "ask_gemini", lambda key, q, st, imgs, tr: calls.append(("gemini", q, len(imgs))) or "I see AAPL.")
    mentor = AIMentor(MentorConfig(enabled=False), keys={"groq": "g", "gemini": "m"}, memory_path=tmp_path / "m.json")
    assert mentor.can_look()
    assert mentor.look("is this good?", [("image/png", PNG)], {}) == "I see AAPL."
    assert calls == ["groq", ("gemini", "is this good?", 1)]
    saved = (tmp_path / "m.json").read_text(encoding="utf-8")
    assert PNG not in saved and "screenshot" in saved
    assert not AIMentor(MentorConfig(enabled=False), keys={}, memory_path=tmp_path / "n.json").can_look()


def test_stop_in_the_chat_wins_even_with_a_screenshot(tmp_path):
    from types import SimpleNamespace

    from app.web.routes import build_router

    engine = scalp_engine(tmp_path)
    engine.mentor_context = lambda: {}
    looked = []
    claude = SimpleNamespace(can_look=lambda: True, look=lambda *a, **k: looked.append(a) or "ok",
                             answer=lambda *a: "text", available=True)
    app = FastAPI()
    app.include_router(build_router(engine, engine.repo, SimpleNamespace(lines=lambda n: []), claude, None, "tok"))
    client = TestClient(app)
    img = f"data:image/png;base64,{PNG}"
    got = client.post("/api/ask?token=tok", json={"question": "stop", "images": [img]}).json()
    assert got["action"] == "halted" and engine.halted and not looked
    assert client.post("/api/ask?token=tok", json={"question": "", "images": ["nope"]}).status_code == 400
    ok = client.post("/api/ask?token=tok", json={"question": "what is this", "images": [img]}).json()
    assert ok["answer"] == "ok" and looked
    assert client.post("/api/ask?token=tok", json={"question": " "}).status_code == 400
