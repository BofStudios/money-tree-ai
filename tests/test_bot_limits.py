"""Money Bot 12.0 M3: the owner's limits and the pace."""
from __future__ import annotations

import pytest

from app.bot import pace as P
from app.bot.settings import BotSettings, NeedsConfirm, limit_buy
from app.engine import scalper as S
from tests.test_bot import chart
from tests.test_privacy import TOKEN, client  # noqa: F401  (the full app, sandboxed)

AUTH = {"Authorization": f"Bearer {TOKEN}"}


def test_limits_are_checked_clamped_and_kept(tmp_path):
    s = BotSettings(tmp_path / "s.json")
    assert s.all() == {"budget": None, "per_trade_pct": None, "daily_loss": None, "max_positions": None, "pace": "balanced"}
    values, clamped = s.update({"budget": 50_000, "per_trade_pct": 9, "daily_loss": 900, "max_positions": 7},
                               equity=2_000, live=False)
    assert values["budget"] == 2_000 and values["per_trade_pct"] == 5 and values["max_positions"] == 5
    assert values["daily_loss"] == 400                     # at most 20% of the budget
    assert set(clamped) == {"budget", "per_trade_pct", "daily_loss", "max_positions"}
    assert BotSettings(tmp_path / "s.json").get("budget") == 2_000
    with pytest.raises(ValueError):
        s.update({"pace": "yolo"}, equity=2_000, live=False)
    with pytest.raises(ValueError):
        s.update({"budget": "lots"}, equity=2_000, live=False)


def test_on_real_money_only_tightening_goes_without_confirm():
    s = BotSettings(None)
    s.update({"budget": 500, "daily_loss": 20}, equity=2_000, live=True)      # adding limits tightens
    s.update({"budget": 300}, equity=2_000, live=True)                        # lowering tightens
    for loosen in ({"budget": 800}, {"daily_loss": None}, {"pace": "aggressive"}):
        with pytest.raises(NeedsConfirm):
            s.update(loosen, equity=2_000, live=True)
    s.update({"budget": 800}, equity=2_000, live=True, confirm=True)
    assert s.get("budget") == 800
    s.update({"pace": "aggressive"}, equity=2_000, live=False)                # practice money: no question


def test_limit_buy_only_refuses_or_shrinks():
    s = BotSettings(None)
    kw = dict(equity=10_000, invested=0, open_count=0, realized_today=0, stop_pct=0.5, fallback_stop_pct=6)
    assert limit_buy(s, **kw) == (None, None)                                 # nothing set: as before
    s.update({"budget": 1_000}, equity=10_000, live=False)
    assert limit_buy(s, **{**kw, "invested": 700}) == (None, 300)
    s.update({"per_trade_pct": 1}, equity=10_000, live=False)                 # $10 at risk, 0.5% stop -> $2,000
    assert limit_buy(s, **kw) == (None, 1_000)
    assert limit_buy(s, **{**kw, "stop_pct": 2}) == (None, 500)
    s.update({"daily_loss": 25, "max_positions": 2}, equity=10_000, live=False)
    assert limit_buy(s, **{**kw, "realized_today": -25})[0] == "daily_loss"
    assert limit_buy(s, **{**kw, "open_count": 2})[0] == "cap"


def test_the_budget_really_shrinks_a_buy_and_stop_still_wins(tmp_path):
    from tests.test_scalper import scalp_engine

    engine = scalp_engine(tmp_path)
    engine.bot_settings.update({"budget": 120}, equity=engine.executor.get_balance().total, live=False)
    assert engine.book_buy("AAPL", "scalp", "Scalp: test", 4_000, 0.5, 1.5) == "bought"
    assert engine.position_for("AAPL").market_value <= 120 + 1e-6
    assert engine.book_buy("MSFT", "scalp", "Scalp: test", 4_000, 0.5, 1.5) != "bought"   # the budget is used
    assert engine.blocked_today()["budget"]["count"] >= 1

    engine.bot_settings.update({"budget": None}, equity=10_000, live=False)
    engine._halted = True
    assert engine.book_buy("NVDA", "scalp", "Scalp: test", 500, 0.5, 1.5) != "bought"
    assert engine.position_for("NVDA") is None


def test_the_daily_loss_limit_stops_new_buys(tmp_path):
    from tests.test_scalper import scalp_engine

    engine = scalp_engine(tmp_path)
    engine.bot_settings.update({"daily_loss": 10}, equity=engine.executor.get_balance().total, live=False)
    engine.risk._daily_realized_pnl = -10.0
    assert engine.book_buy("AAPL", "scalp", "Scalp: test", 500, 0.5, 1.5) != "bought"
    assert engine.blocked_today()["daily_loss"]["count"] == 1


def test_balanced_is_exactly_9_0_and_the_other_paces_move_only_thresholds(monkeypatch):
    b = P.balanced()
    assert (b.conf_min, b.rsi_max, b.dip_atr, b.max_entries) == (S.CONF_MIN, S.RSI_MAX, S.DIP_ATR, S.MAX_ENTRIES)
    monkeypatch.setattr(S, "CONF_MIN", 0.5)
    assert P.balanced().conf_min == 0.5                                       # read when used, not copied
    assert S.chart_gate(chart(conf={"score": 0.625, "veto": False}), P.CALM) == "confluence"
    assert S.chart_gate(chart(rsi=38.0), P.AGGRESSIVE) is None
    assert S.chart_gate(chart(rsi=38.0)) == S.NO_SIGNAL
    assert P.widest_rsi() >= P.AGGRESSIVE.rsi_max


def test_the_owner_can_lower_ultras_slots_and_the_pace_its_day(tmp_path):
    from tests.test_scalper import scalp_engine

    engine = scalp_engine(tmp_path)
    assert engine.scalper.slots() == S.SLOTS
    engine.bot_settings.update({"max_positions": 1, "pace": "calm"}, equity=10_000, live=False)
    assert engine.scalper.slots() == 1 and engine.scalper.pace().max_entries == P.CALM.max_entries


def test_the_console_api_for_limits_and_paces(client):
    r = client.post("/api/bot/risk", json={"budget": 10**9, "daily_loss": 5}, headers=AUTH)
    assert r.status_code == 200 and "budget" in r.json()["clamped"] and r.json()["risk"]["daily_loss"] == 5
    assert client.post("/api/bot/risk", json={"leverage": 10}, headers=AUTH).status_code == 400
    r = client.post("/api/bot/pace", json={"pace": "calm"}, headers=AUTH)
    assert r.status_code == 200 and r.json()["values"]["pace"] == "calm" and "proof" in r.json()
    paces = client.get("/api/bot/paces", headers=AUTH).json()
    assert [p["id"] for p in paces["paces"]] == ["calm", "balanced", "aggressive"] and paces["pace"] == "calm"
    assert client.get("/api/bot", headers=AUTH).json()["risk"]["pace"] == "calm"
    bad = client.post("/api/bot/pace", json={"pace": "calm"}, headers={**AUTH, "Origin": "https://evil.example"})
    assert bad.status_code in (400, 403)
