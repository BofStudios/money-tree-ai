"""Desktop 6.0: memory that survives restarts and updates, learning from news
results, the readiness card, the Modes routes and the security fixes."""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.brain.news_memory import MIN_CASES, NewsMemory, kind_of
from app.common import home
from app.common.activity import Monitor
from app.common.journal import Journal, Keeper
from app.common.models import ClosedTrade, Side
from app.config import ProtectionsConfig, RiskConfig
from app.engine.readiness import readiness
from app.risk.protections import Protections
from app.risk.risk_manager import RiskManager
from tests.test_portfolio_engine import FakeMarket, build


# ------------------------------------------------------------- data home


def _old_install(tmp_path):
    legacy = tmp_path / "old"
    (legacy / "data" / "brain").mkdir(parents=True)
    (legacy / "data" / "keys.dat").write_bytes(b"secret")
    (legacy / "data" / "brain" / "brain.json").write_text("{}", encoding="utf-8")
    (legacy / "data" / "brain" / "brain.tmp").write_text("half", encoding="utf-8")
    db = sqlite3.connect(legacy / "data" / "trading.db")
    db.execute("create table t (x)")
    db.execute("insert into t values (7)")
    db.commit()
    db.close()
    (legacy / "config").mkdir()
    (legacy / "config" / "config.yaml").write_text("mode: live\n", encoding="utf-8")
    (legacy / ".env").write_text("GROQ_API_KEY=x\n", encoding="utf-8")
    return legacy


def test_first_start_copies_the_old_folder_and_leaves_it_alone(tmp_path):
    legacy = _old_install(tmp_path)
    new_home = tmp_path / "home"
    copied = home.migrate(new_home, legacy)
    assert (new_home / "data" / "keys.dat").read_bytes() == b"secret"
    assert (new_home / "config" / "config.yaml").exists() and (new_home / ".env").exists()
    assert not (new_home / "data" / "brain" / "brain.tmp").exists()
    rows = sqlite3.connect(new_home / "data" / "trading.db").execute("select x from t").fetchall()
    assert rows == [(7,)]
    assert (legacy / "data" / "keys.dat").exists(), "the old copy is never moved"
    assert copied
    # Once set up, a second start copies nothing, even if the old folder changed.
    (legacy / "data" / "keys.dat").write_bytes(b"newer")
    assert home.migrate(new_home, legacy) == []
    assert (new_home / "data" / "keys.dat").read_bytes() == b"secret"


def test_a_home_with_its_own_data_is_never_overwritten(tmp_path):
    legacy = _old_install(tmp_path)
    new_home = tmp_path / "home"
    (new_home / "data").mkdir(parents=True)
    (new_home / "data" / "keys.dat").write_bytes(b"mine")
    home.migrate(new_home, legacy)
    assert (new_home / "data" / "keys.dat").read_bytes() == b"mine"


def test_a_source_run_never_copies_the_repository(monkeypatch):
    monkeypatch.setattr(home, "FROZEN", False)
    assert home.migrate() == []


# ---------------------------------------------------------------- journal


def test_journal_counts_a_whole_life_across_restarts(tmp_path):
    clock = [1_000_000.0]
    path = tmp_path / "journal.json"
    j = Journal(path, now=lambda: clock[0])
    j.started()
    j.add("looks", 3)
    j.event("rule", "Learned a rule")
    clock[0] += 3600
    j.save()
    again = Journal(path, now=lambda: clock[0])
    again.started()
    assert again.starts == 2
    assert again.count("looks") == 3
    assert again.uptime == pytest.approx(3600)
    assert again.events[0]["title"] == "Learned a rule"
    again.set_max("strategies_tested", 10)
    again.set_max("strategies_tested", 4)
    assert again.count("strategies_tested") == 10


def test_keeper_runs_every_job_at_stop_even_if_one_fails():
    ran = []
    keeper = Keeper(every=999)
    keeper.add("bad", lambda: 1 / 0)
    keeper.add("good", lambda: ran.append(1))
    keeper.start()
    keeper.stop()
    assert ran == [1]


def test_live_feed_comes_back_after_a_restart(tmp_path):
    m = Monitor()
    m.info("info", "first")
    handle = m.begin("bars", "half done")
    path = tmp_path / "feed.json"
    m.save(path)
    handle.done()
    again = Monitor()
    again.info("info", "new run")
    assert again.restore(path, "not finished") == 2
    titles = [s["title"] for s in again.snapshot()]
    assert titles == ["first", "half done", "new run"]
    assert again.snapshot()[1]["state"] == "failed"


# ------------------------------------------------- risk and pause memory


def _trade(pnl, reason="stop-loss", minutes_ago=1):
    now = datetime.now(timezone.utc)
    return ClosedTrade("AAPL", Side.BUY, 1.0, 100.0, 100.0 + pnl, now - timedelta(hours=1),
                       now - timedelta(minutes=minutes_ago), pnl, reason)


def test_a_restart_never_resets_the_daily_loss_limit(tmp_path):
    path = tmp_path / "risk_day.json"
    config = RiskConfig(max_daily_loss_pct=5.0)
    risk = RiskManager(config, mode="live", state_path=path)
    risk.arm()
    risk.record_closed_trade(_trade(-30.0), 1000.0)
    assert risk.daily_realized_pnl == -30.0
    again = RiskManager(config, mode="live", state_path=path)
    assert again.daily_realized_pnl == -30.0
    assert not again.armed, "arming is never remembered"


def test_yesterdays_loss_does_not_count_today(tmp_path):
    path = tmp_path / "risk_day.json"
    path.write_text(json.dumps({"day": "2020-01-01", "daily_realized_pnl": -99.0, "daily_start_equity": 50.0}))
    risk = RiskManager(RiskConfig(), mode="live", state_path=path)
    assert risk.daily_realized_pnl == 0.0


def test_a_restart_does_not_lift_a_safety_pause(tmp_path):
    path = tmp_path / "protections.json"
    config = ProtectionsConfig(cooldown_minutes=30)
    p = Protections(config, state_path=path)
    p.record_trade(_trade(-1.0), 1000.0)
    assert p.blocked("AAPL")
    again = Protections(config, state_path=path)
    assert again.blocked("AAPL")
    assert len(again._closed) == 1


# -------------------------------------------------------- engine memory


def test_watchlist_changes_survive_a_restart(tmp_path):
    state = tmp_path / "engine_state.json"
    engine = build(tmp_path, state_path=state)
    engine.add_symbol("AMD")
    engine.remove_symbol("MSFT")
    again = build(tmp_path, state_path=state)
    again.set_watchlist(["AAPL", "MSFT", "NVDA"])
    again.apply_saved_watchlist()
    assert again.symbols == ["AAPL", "NVDA", "AMD"]


def test_practice_money_keeps_what_earlier_runs_made(tmp_path):
    engine = build(tmp_path)
    engine.repo.save_closed_trade(_trade(25.0, "take-profit"), "paper", engine.executor.name)
    again = build(tmp_path)
    again.executor.restore_result(again.repo.realised_pnl("paper", again.executor.name))
    assert again.executor.get_balance().total == pytest.approx(10_025.0)


def test_readiness_says_real_money_is_not_armed(tmp_path):
    engine = build(tmp_path, mode="live")
    engine.executor.broker = "alpaca_live"
    engine._thread = type("T", (), {"is_alive": lambda self: True})()
    r = readiness(engine)
    assert r["verdict"] == "watching"
    assert r["fix"] == "arm"
    assert any(c["id"] == "money" and c["state"] == "bad" for c in r["checks"])
    engine.risk.arm()
    assert readiness(engine)["fix"] is None


def test_buys_that_did_not_happen_are_counted_by_reason(tmp_path):
    engine = build(tmp_path, mode="live")
    engine._scan(FakeMarket())
    missed = engine.blocked_today()
    assert missed["not_armed"]["count"] >= 1
    r = readiness(engine)
    assert r["missed_total"] >= 1 and r["missed"][0]["key"] == "not_armed"


# ------------------------------------------------------------ news memory


class Bars:
    """15-minute candles that rise 0.1% a bar from 100."""

    def __init__(self, start):
        self.start = start

    def get_ohlcv(self, symbol, timeframe, limit=400):
        idx = pd.DatetimeIndex([self.start + timedelta(minutes=15 * i) for i in range(60)], tz="UTC")
        close = 100 * np.power(1.001, np.arange(60))
        return pd.DataFrame({"open": close, "high": close, "low": close, "close": close,
                             "volume": np.ones(60)}, index=idx)


def test_kinds_of_news():
    assert kind_of("Barclays Upgrades Viking Holdings to Overweight, Raises Price Target to $102") == "upgrade"
    assert kind_of("JP Morgan Downgrades Allient to Neutral") == "downgrade"
    assert kind_of("Acme beats estimates and raises full-year guidance") == "guidance_up"
    assert kind_of("FDA approves Acme's new drug") == "approval"
    assert kind_of("Fly-E Group Shares Halted On Circuit Breaker") == "halt"
    assert kind_of("Acme to present at a conference") == "company"


def test_news_is_graded_against_the_real_price_and_trusted_from_it(tmp_path):
    start = datetime(2026, 10, 1, 13, 30, tzinfo=timezone.utc)
    clock = [start.timestamp() + 3 * 86400]
    memory = NewsMemory(tmp_path / "news.json", Bars(start), now=lambda: clock[0])
    for i in range(8):
        memory.note(f"AB{chr(65 + i)}", "upgrade", +1, 0.6, start.timestamp() + 60 * i, "wire")
    memory.note("DOWN", "downgrade", -1, 0.6, start.timestamp(), "wire")
    assert memory.grade(force=True) >= 4          # a few stocks per round, to spare the data API
    while memory.grade(force=True):
        pass
    st = memory.stats("upgrade")
    assert st["n"] >= MIN_CASES and st["avg"] > 0 and st["hit"] == 1.0
    assert memory.trust("upgrade") > 1.0
    assert memory.stats("downgrade")["avg"] < 0, "a fall was expected and it rose"
    raised, _ = memory.adjust("upgrade", 0.6)
    assert 0.6 < raised <= 0.6 * 1.3 + 1e-9
    assert "Analyst upgrade" in memory.brief(["upgrade"])
    memory.save()
    again = NewsMemory(tmp_path / "news.json", None)
    assert again.stats("upgrade")["n"] == st["n"]


def test_too_few_cases_change_nothing(tmp_path):
    memory = NewsMemory(None, None)
    memory.note("ABC", "beat", +1, 0.7, 1.0)
    assert memory.trust("beat") == 1.0


# ------------------------------------------------- routes and security


def test_foreign_host_names_are_refused():
    from app.web.server import _host_allowed

    assert _host_allowed("127.0.0.1:8765") and _host_allowed("192.168.1.20:8765")
    assert _host_allowed("localhost:8765") and _host_allowed("[::1]:8765")
    assert not _host_allowed("evil.example.com:8765")
    assert not _host_allowed("")


def test_dashboard_password_is_made_once_and_kept(tmp_path):
    from app.main import local_token

    first = local_token(tmp_path / "dashboard.token")
    assert len(first) >= 32
    assert local_token(tmp_path / "dashboard.token") == first


def _modes_client(tmp_path):
    from app.brain.brain import Brain
    from app.web.mode_routes import build_mode_router

    engine = build(tmp_path)
    brain = Brain(tmp_path / "brain", engine.data)
    brain._restart_swarm = lambda: None
    engine.brain = brain
    brain.on_ultra = engine.set_ultra
    app = FastAPI()
    app.include_router(build_mode_router(engine, "tok"))
    return TestClient(app), engine, brain


def test_modes_change_style_and_speed(tmp_path):
    client, engine, brain = _modes_client(tmp_path)
    assert client.get("/api/modes").status_code == 401
    r = client.post("/api/modes?token=tok", json={"style": "bold"}).json()
    assert r["style"] == "bold" and brain.settings.quality_mode == "OFF"
    assert client.post("/api/modes?token=tok", json={"speed": "ultra"}).status_code == 400
    r = client.post("/api/modes?token=tok", json={"speed": "ultra", "confirm": True}).json()
    assert r["speed"] == "ultra" and engine.config.scan_interval_seconds == 15
    assert len(engine.watched_symbols()) > 10
    r = client.post("/api/modes?token=tok", json={"speed": "eco"}).json()
    assert r["speed"] == "eco" and not brain.settings.ultra and brain.settings.power == "light"
    r = client.post("/api/modes?token=tok", json={"news_trading": False}).json()
    assert r["switches"]["news_trading"] is False
    assert client.get("/api/readiness?token=tok").json()["checks"]
    assert client.get("/api/memory?token=tok").json()["level"] >= 1


def test_a_falling_daily_chart_halves_the_buy_but_does_not_block_it(tmp_path):
    from app.brain.brain import Brain

    brain = Brain(tmp_path / "brain", None)
    close = np.linspace(200, 100, 120)               # a clear downtrend
    brain.daily["AAA"] = {"close": close, "high": close, "low": close}
    idx = pd.DatetimeIndex([datetime(2026, 10, 1, 14, tzinfo=timezone.utc) + timedelta(minutes=15 * i) for i in range(30)])
    frame = pd.DataFrame({"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 1.0}, index=idx)
    r = brain.research("AAA", frame, {"price": 100.0}, True)
    assert r.daily_up is False and r.trend_ok and r.size <= 0.5
    brain.settings.quality_mode = "STRICT"
    assert not brain.research("AAA", frame, {"price": 100.0}, True).trend_ok


def test_auto_eco_slows_the_bots_while_the_pc_is_in_use(tmp_path):
    from app.brain.brain import Brain

    brain = Brain(tmp_path / "brain", None)
    duties = []
    brain.swarm.set_duty = duties.append
    idle = [5.0]
    brain.idle_fn = lambda: idle[0]
    assert brain.govern() and duties[-1] == 0.25
    idle[0] = 600.0
    assert brain.govern() and duties[-1] == 1.0
    idle[0] = 5.0
    brain.settings.ultra = True
    assert not brain.govern(), "ultra always runs full"
    brain.settings.ultra = False
    brain.settings.auto_eco = False
    assert not brain.govern()


def test_scorecard_compares_the_bot_with_holding_spy(tmp_path):
    from app.engine import scorecard as sc

    engine = build(tmp_path)
    now = datetime.now(timezone.utc)
    engine.repo.equity_curve = lambda mode, days=90: [
        {"time": int((now - timedelta(days=20)).timestamp()), "value": 100.0},
        {"time": int(now.timestamp()), "value": 102.0}]

    class Spy:
        def get_ohlcv(self, symbol, timeframe, limit=100):
            idx = pd.DatetimeIndex([now - timedelta(days=30 - i) for i in range(31)])
            close = np.linspace(100, 110, 31)
            return pd.DataFrame({"open": close, "high": close, "low": close, "close": close, "volume": 1.0}, index=idx)

    engine.data = Spy()
    sc._cache.clear()
    assert sc.scorecard(engine)["verdict"] == "idle", "no trades: only cash against SPY"
    engine.repo.save_closed_trade(_trade(2.0, "take-profit"), "paper", engine.executor.name)
    card = sc.scorecard(engine)
    assert card["bot_pct"] == 2.0
    assert card["spy_pct"] > 2.0 and card["verdict"] == "behind"
    assert "behind SPY" in card["headline"]
