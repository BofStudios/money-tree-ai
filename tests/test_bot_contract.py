"""The console's contract (12.0): what /api/bot answers is what the fixture shows.

The page is built against tests/fixtures; if the two drift apart this fails.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.bot import log as botlog
from app.bot.crew import CREW, IDS, LEVELS, VERBS
from app.common.events import EventBus
from tests.test_privacy import TOKEN, client  # noqa: F401  (the full app, sandboxed)

FIXTURES = Path(__file__).parent / "fixtures"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def shape(v):
    """Keys and kinds, not values. None matches anything (a value not there yet)."""
    if isinstance(v, dict):
        return {k: shape(x) for k, x in sorted(v.items())}
    if isinstance(v, list):
        return [shape(v[0])] if v else []
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, (int, float)):
        return "num"
    return None if v is None else "str"


def same(a, b) -> bool:
    if a is None or b is None or a == [] or b == []:
        return True
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return same(a[0], b[0])
    return a == b


SNAPS = ("bot_snapshot.json", "bot_snapshot_closed.json")
LOGS = ("bot_log.jsonl", "bot_log_closed.jsonl")


@pytest.mark.parametrize("name", SNAPS)
def test_the_fixture_has_the_contract_keys(name):
    snap = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    assert set(snap) >= {"name", "version", "account", "market", "tiles", "crew", "queue", "funnel",
                         "focus", "risk", "proof", "log_head"}
    assert [c["id"] for c in snap["crew"]] == list(IDS)
    assert set(snap["tiles"]) == {"fills", "positions", "net", "capital"}


@pytest.mark.parametrize("name", LOGS)
def test_every_fixture_line_is_a_real_kind_of_line(name):
    rows = [json.loads(r) for r in (FIXTURES / name).read_text(encoding="utf-8").splitlines() if r.strip()]
    assert len(rows) >= 10
    numbers = [r["n"] for r in rows]
    assert numbers == sorted(numbers) and len(set(numbers)) == len(numbers)
    for r in rows:
        assert set(r) == {"n", "at", "agent", "verb", "text", "symbol", "level", "ref", "money"}
        assert r["agent"] in IDS and r["verb"] in VERBS and r["level"] in LEVELS


def test_the_snapshot_answers_in_the_fixture_shape(client):
    got = client.get("/api/bot", headers=AUTH).json()
    for name in SNAPS:
        want = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
        assert same(shape(got), shape(want)), name
    assert len(got["crew"]) == len(CREW)
    log = client.get("/api/bot/log", headers=AUTH).json()
    assert set(log) == {"head", "lines"}
    assert set(client.get("/api/bot/ledger?range=week", headers=AUTH).json()) == {"range", "fills", "sum", "curve"}


def test_no_event_no_line_and_numbers_go_on(tmp_path):
    events = EventBus()
    path = tmp_path / "bot" / "log.jsonl"
    log = botlog.AgentLog(path, events)
    assert log.lines() == []
    events.publish("status", {"running": True})          # not something an agent did
    events.publish("step", {"step": {"id": 1, "kind": "bars", "title": "Reading", "state": "running"}})
    assert log.lines() == []
    events.publish("step", {"step": {"id": 1, "kind": "bars", "title": "Read 25 charts", "state": "done"}})
    events.publish("trade_closed", {"symbol": "NVDA", "exit_reason": "stop_loss", "pnl": -1.5, "pnl_pct": -0.4, "id": 7})
    rows = log.lines()
    assert [r["n"] for r in rows] == [1, 2]
    assert (rows[0]["agent"], rows[0]["verb"]) == ("atlas", "scan")
    assert (rows[1]["agent"], rows[1]["verb"], rows[1]["level"]) == ("luna", "stop", "bad")
    assert rows[1]["money"] == {"pnl": -1.5, "pct": -0.4}
    assert log.lines(tab="orders") == [rows[1]]

    again = botlog.AgentLog(path, EventBus())            # the app was closed and opened
    assert again.head == 2 and len(again.lines()) == 2
