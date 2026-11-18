"""Money Bot's console (12.0 M1): the funnel, the noise rule, the crew's states, the proof."""
from __future__ import annotations

import json

import pytest

from app.bot import log as botlog
from app.bot.crew import IDS
from app.bot.funnel import GATES, STEPS, Funnel
from app.bot.snapshot import crew_state, proof_of
from app.common.events import EventBus
from app.engine import scalper as S


class Clock:
    def __init__(self, t: float = 1_794_855_000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


# ----------------------------------------------------------------- the funnel

def test_a_dip_is_one_signal_a_minute_however_often_the_bot_looks(tmp_path):
    clock = Clock()
    f = Funnel(tmp_path / "funnel.json", now=clock)
    assert f.signal("NVDA") is True
    for _ in range(5):                      # five more looks in the same minute
        clock.t += 10
        assert f.signal("NVDA") is False
    clock.t += 60
    assert f.signal("NVDA") is True
    assert f.signal("AMD") is True
    view = f.view()
    assert {s["id"]: s["n"] for s in view["steps"]}["signals"] == 3


def test_orders_and_fills_come_only_from_real_events(tmp_path):
    events = EventBus()
    f = Funnel(None, events)
    events.publish("status", {})
    events.publish("intent", {"intent": {}})
    events.publish("trade_opened", {"position": {}})
    n = {s["id"]: s["n"] for s in f.view()["steps"]}
    assert (n["orders"], n["fills"], n["signals"]) == (1, 1, 0)


def test_blocks_are_counted_by_gate_with_labels_in_both_languages(tmp_path):
    f = Funnel(None)
    f.block("confluence", "AMD")
    f.block("confluence", "TSLA")
    f.block("not_armed", "NVDA")
    f.block("made_up_gate", "X")             # an unknown reason is still counted, as "rules"
    rows = f.view(turkish=True)["blocked"]
    assert rows[0] == {"gate": "confluence", "label": GATES["confluence"][2], "n": 2, "by": "orion", "symbol": "TSLA"}
    assert {r["gate"] for r in rows} == {"confluence", "not_armed", "rules"}
    for gate, (agent, en, tr) in GATES.items():
        assert agent in IDS and en and tr


def test_the_funnel_survives_a_restart_and_a_new_day_starts_at_zero(tmp_path):
    clock = Clock()
    path = tmp_path / "funnel.json"
    f = Funnel(path, now=clock)
    f.scanned(25)
    f.block("slots", "AMD")
    f.save()
    again = Funnel(path, now=clock)
    n = {s["id"]: s["n"] for s in again.view()["steps"]}
    assert n["scanned"] == 25 and again.view()["blocked"][0]["n"] == 1
    clock.t += 86_400
    assert all(s["n"] == 0 for s in again.view()["steps"]) and again.view()["blocked"] == []
    assert len(again.history()) <= 30 + 1


# ------------------------------------------------- Ultra's rule, gate by gate

def chart(**kw) -> dict:
    c = {"rsi": 30.0, "atr_pct": 0.2, "age": 30, "vwap": 101.0, "price": 100.0, "prev": 99.9,
         "relvol": 1.5, "conf": {"score": 0.75, "veto": False, "votes": {}}}
    c.update(kw)
    return c


@pytest.mark.parametrize("change,gate", [
    ({}, None),
    ({"rsi": 60.0}, S.NO_SIGNAL),
    ({"vwap": 100.1}, S.NO_SIGNAL),                      # not far enough under VWAP
    ({"age": 9999}, "quiet"),
    ({"prev": 100.5}, "turn"),
    ({"conf": {"score": 0.75, "veto": True}}, "knife"),
    ({"vwap": 103.0}, "too_deep"),
    ({"conf": {"score": 0.5, "veto": False}}, "confluence"),
])
def test_every_chart_gate_and_the_score_agree(change, gate):
    c = chart(**change)
    assert S.chart_gate(c) == gate
    assert (S.score(c, False) is None) == (gate is not None)    # the rule itself did not change


def test_the_noise_rule_folds_repeats_into_one_line(tmp_path):
    clock = Clock()
    events = EventBus()
    log = botlog.AgentLog(None, events, now=clock)
    veto = {"type": "not_armed", "symbol": "AMD"}
    for _ in range(4):
        events.publish("not_armed", {"symbol": "AMD"})
        clock.t += 5
    assert len(log.lines()) == 1
    clock.t += 60
    events.publish("not_armed", {"symbol": "AMD"})
    rows = log.lines()
    assert len(rows) == 2 and rows[1]["text"].endswith("(×4)")
    events.publish("trade_closed", {"symbol": "AMD", "exit_reason": "target", "pnl": 1, "pnl_pct": 0.2})
    events.publish("trade_closed", {"symbol": "AMD", "exit_reason": "target", "pnl": 1, "pnl_pct": 0.2})
    assert len(log.lines()) == 4             # trades are never folded
    assert veto


# ------------------------------------------------------------ the crew's states

class FakeEngine:
    def __init__(self, running=True):
        self._running = running

    def status_running(self):
        return self._running


def test_a_state_is_what_really_happened(tmp_path):
    clock = Clock()
    events = EventBus()
    log = botlog.AgentLog(None, events, now=clock)
    now = lambda: int(clock.t * 1000)        # noqa: E731
    assert crew_state(FakeEngine(False), log, "nova", [], now()) == "off"
    assert crew_state(FakeEngine(), log, "nova", [], now()) == "idle"
    events.publish("not_armed", {"symbol": "AMD"})
    assert crew_state(FakeEngine(), log, "nova", [], now()) == "veto"
    clock.t += 31
    assert crew_state(FakeEngine(), log, "nova", [], now()) == "idle"
    assert crew_state(FakeEngine(), log, "titan", [{"by": "titan"}], now()) == "wait"
    events.publish("trade_opened", {"position": {"symbol": "NVDA", "quantity": 1, "entry_price": 10}})
    assert crew_state(FakeEngine(), log, "titan", [], now()) == "work"


# --------------------------------------------------------------- the proof

class LabStub:
    def __init__(self, m, ran_at):
        self.m, self.ran_at = m, ran_at

    def status(self):
        return {"report": {"rules": {"9.0": self.m}, "ran_at": self.ran_at, "days": ["a", "b"]}}


class WithLab:
    def __init__(self, lab):
        self.lab = lab


def test_the_proof_says_lost_passed_untested_or_stale():
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    fresh, old = now.isoformat(), (now - timedelta(hours=60)).isoformat()
    assert proof_of(WithLab(None))["state"] == "untested"
    lost = proof_of(WithLab(LabStub({"trades": 311, "avg": -0.035, "profit_factor": 0.84}, fresh)))
    assert lost["state"] == "lost" and lost["trades"] == 311 and lost["days"] == 2
    assert proof_of(WithLab(LabStub({"trades": 90, "avg": 0.08, "profit_factor": 1.3}, fresh)))["state"] == "passed"
    assert proof_of(WithLab(LabStub({"trades": 20, "avg": 0.5, "profit_factor": 3}, fresh)))["state"] == "untested"
    assert proof_of(WithLab(LabStub({"trades": 311, "avg": -0.035, "profit_factor": 0.84}, old)))["state"] == "stale"


def test_steps_are_fixed():
    assert STEPS == ("scanned", "signals", "passed", "orders", "fills")
    assert json.dumps(Funnel(None).view())


# ---------------------------------------------- reading a model's answer (from HQ)

from app.bot.protocol import parse_action, parse_duration, wait_from  # noqa: E402

GOOD = {"thought": "t", "action": "skip", "args": {"symbol": "AMD"}}


@pytest.mark.parametrize("text", [
    '{"thought": "t", "action": "skip", "args": {"symbol": "AMD"}}',
    'Sure! Here it is:\n```json\n{"thought": "t", "action": "skip", "args": {"symbol": "AMD"}}\n```',
    '<think>hmm {not json}</think>{"thought": "t", "action": "skip", "args": {"symbol": "AMD"}}',
    '{"thought": "t", "action": "skip", "args": {"symbol": "AMD",},}',
    'before {"thought": "t", "action": "skip", "args": {"symbol": "AMD"}} after {"action": "other"}',
    '{"reasoning": "t", "tool": "skip", "arguments": {"symbol": "AMD"}}',
])
def test_a_messy_answer_is_still_read(text):
    assert parse_action(text) == GOOD


@pytest.mark.parametrize("text", [
    None, "", "no json here", "{", '{"thought": "only a thought"}', '{"action": ""}', "[1, 2, 3]",
    '{"action": "skip", "args": {"symbol": "AMD"', '{"action": 5}', "}{", '{"a": "}"', "```json\n```",
])
def test_an_unreadable_answer_is_none_and_never_an_exception(text):
    assert parse_action(text) is None


def test_a_raw_newline_in_a_string_and_odd_args():
    got = parse_action('{"action": "plan", "thought": "line one\nline two", "args": [1]}')
    assert got == {"thought": "line one\nline two", "action": "plan", "args": {}}
    assert parse_action('{"action": "plan", "thought": "say \\"hi\\" {x}"}')["thought"] == 'say "hi" {x}'


def test_how_long_a_provider_wants_us_to_wait():
    assert parse_duration("7m12s") == 432 and parse_duration("120ms") == 0.12 and parse_duration("30") == 30
    assert parse_duration("soon") is None
    assert wait_from({"Retry-After": "20"}, "") == (20, False)
    assert wait_from({}, 'Please try again in 1m30s.')[0] == 90
    assert wait_from({}, '"retryDelay": "45s"')[0] == 45
    assert wait_from({}, "", default=90) == (90, False)
    wait, daily = wait_from({"retry-after": "5"}, "Rate limit reached: tokens per day (TPD)", now=1_794_855_000.0)
    assert daily and 3600 < wait <= 12 * 3600


def test_scrolling_back_with_before(tmp_path):
    events = EventBus()
    log = botlog.AgentLog(None, events)
    for i in range(10):
        events.publish("trade_closed", {"symbol": f"S{i}", "exit_reason": "target", "pnl": 1, "pnl_pct": 0.1})
    assert [l["n"] for l in log.lines(limit=3)] == [8, 9, 10]
    assert [l["n"] for l in log.lines(before=8, limit=3)] == [5, 6, 7]
    assert [l["n"] for l in log.lines(after=2, limit=3)] == [3, 4, 5]
    assert [l["n"] for l in log.lines(after=2, before=5, limit=10)] == [3, 4]
