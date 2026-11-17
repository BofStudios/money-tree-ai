"""Money Bot 12.0: Orion's planning round may only hold a chart back."""
from __future__ import annotations

import json

from app.bot.planner import DAILY_CALLS, Planner
from app.common.events import EventBus
from tests.test_bot import Clock
from tests.test_scalper import NOW, VOTE, frame, scalp_engine


class Reply:
    def __init__(self, text):
        self.text = text


class FakeAI:
    def __init__(self, text, level="full"):
        self.text, self.level, self.sent = text, level, []

    def _level(self):
        return self.level

    def _chat(self, system, messages, max_tokens):
        self.sent.append(messages[0]["content"])
        return Reply(self.text)


def plan(*ideas, note="ok"):
    return json.dumps({"thought": "t", "action": "plan", "args": {"note": note, "ideas": list(ideas)}})


def test_only_the_three_words_for_listed_symbols_are_kept():
    p = Planner(type("E", (), {"events": EventBus(), "bot_settings": None})(), now=Clock())
    got = p.apply(plan({"symbol": "aapl", "action": "skip", "why": "weak vote"},
                       {"symbol": "NVDA", "action": "buy", "why": "to the moon"},       # not one of the words
                       {"symbol": "TSLA", "action": "skip", "why": "not on the list"},  # not offered
                       {"symbol": "MSFT", "action": "SHRINK"}), {"AAPL", "MSFT", "NVDA"})
    assert got["ideas"] == [{"symbol": "AAPL", "action": "skip", "why": "weak vote"},
                            {"symbol": "MSFT", "action": "shrink", "why": ""}]
    assert p.advice_for("AAPL") == "skip" and p.advice_for("NVDA") is None and p.advice_for("TSLA") is None
    assert p.apply("buy everything now!!", {"AAPL"}) is None
    assert p.apply(json.dumps({"action": "raise_limits", "args": {"budget": 10**9}}), {"AAPL"}) is None


def test_advice_runs_out_after_ten_minutes():
    clock = Clock()
    p = Planner(type("E", (), {"events": None})(), now=clock)
    p.apply(plan({"symbol": "AAPL", "action": "skip"}), {"AAPL"})
    clock.t += 601
    assert p.advice_for("AAPL") is None and p.advice() == []


def test_skip_holds_a_buy_back_and_shrink_halves_it_and_nothing_grows(tmp_path, monkeypatch):
    from app.engine import scalper as S

    monkeypatch.setattr(S, "dip_confluence", lambda *a, **k: dict(VOTE))     # as test_scalper does
    engine = scalp_engine(tmp_path)
    frames = {"AAPL": frame()}
    engine.planner.apply(plan({"symbol": "AAPL", "action": "skip"}), {"AAPL"})
    engine.planner._now = lambda: NOW.timestamp()
    engine.planner._advice["AAPL"] = ("skip", NOW.timestamp() + 600, "")
    rows = engine.scalper.tick(frames, now=NOW)
    assert not [r for r in rows if r["action"] == "buy"] and engine.position_for("AAPL") is None

    engine.planner._advice["AAPL"] = ("shrink", NOW.timestamp() + 600, "")
    rows = engine.scalper.tick(frames, now=NOW)
    p = engine.position_for("AAPL")
    from app.engine import scalper as S

    equity = engine.executor.get_balance().total + p.market_value
    assert p.market_value <= equity * S.ALLOC * 0.5 * 1.05


def test_the_round_sends_no_owner_text_counts_its_calls_and_respects_none(tmp_path):
    engine = scalp_engine(tmp_path)
    engine.scalper.radar = [{"symbol": "AAPL", "score": 6.1, "vote": 6, "dip": 2.0, "rsi": 30, "relvol": 1.4,
                             "stop_pct": 0.5, "tip": False}]
    ai = FakeAI(plan({"symbol": "AAPL", "action": "shrink", "why": "deep"}))
    engine.explainer = ai
    engine.planner.run()
    assert engine.planner.advice_for("AAPL") == "shrink"
    sent = json.loads(ai.sent[0])
    assert set(sent) == {"pace", "setups", "open_trades", "todays_trade_results_pct", "blocked_today", "time_ny"}
    assert "stop" not in ai.sent[0].lower().replace("stop_pct", "")       # no owner text, no "stop"
    assert engine.planner.calls_left() == DAILY_CALLS - 1
    assert any(l["agent"] == "orion" and l["verb"] == "plan" for l in engine.agent_log.lines())

    ai.level = "none"
    assert engine.planner.context() == {} and engine.planner.due() is False


def test_it_is_off_until_the_owner_turns_it_on(tmp_path):
    engine = scalp_engine(tmp_path)
    engine.explainer = FakeAI(plan())
    assert engine.planner.enabled() is False and engine.planner.due() is False
    engine.bot_settings.update({"planner": True}, equity=10_000, live=True)    # no confirm needed: it only shrinks
    assert engine.planner.enabled() is True
    engine.planner._quota = {"day": engine.planner._quota["day"] or "x", "calls": DAILY_CALLS}
    engine.planner._roll()
    if engine.planner._quota["calls"] >= DAILY_CALLS:
        assert engine.planner.due() is False
