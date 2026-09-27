"""The Live feed: steps open before the work and close after it, for real."""
from __future__ import annotations

import pytest

from app.common import activity
from app.common.activity import Monitor
from app.common.events import EventBus


def test_a_step_runs_then_finishes_with_its_result():
    monitor = Monitor()
    handle = monitor.begin(activity.BARS, "Fetching")
    assert monitor.snapshot()[0]["state"] == activity.RUNNING

    handle.done("8 of 8 ready", ["AAPL ok"])
    step = monitor.snapshot()[0]
    assert step["state"] == activity.DONE
    assert step["detail"] == "8 of 8 ready"
    assert step["lines"] == ["AAPL ok"]
    assert step["ended_at"] >= step["started_at"]


def test_progress_shows_what_is_in_flight_but_never_rewrites_a_finished_step():
    monitor = Monitor()
    handle = monitor.begin(activity.BARS, "Fetching")
    handle.progress("NVDA · 3/8")
    assert monitor.snapshot()[0]["detail"] == "NVDA · 3/8"

    handle.done("8 of 8 ready")
    handle.progress("late")
    assert monitor.snapshot()[0]["detail"] == "8 of 8 ready"


def test_the_context_manager_marks_failures_and_reraises():
    monitor = Monitor()
    with pytest.raises(RuntimeError):
        with monitor.step(activity.ACCOUNT, "Reading"):
            raise RuntimeError("401 unauthorized")

    step = monitor.snapshot()[0]
    assert step["state"] == activity.FAILED
    assert step["detail"] == "401 unauthorized"


def test_a_block_that_returns_normally_is_closed_not_left_spinning():
    monitor = Monitor()
    with monitor.step(activity.CLOCK, "Checking"):
        pass
    assert monitor.snapshot()[0]["state"] == activity.DONE


def test_every_change_is_published_for_the_web_socket():
    bus = EventBus()
    seen = []
    bus.subscribe(lambda e: seen.append(e) if e["type"] == "step" else None)
    monitor = Monitor(bus)

    handle = monitor.begin(activity.ORDER, "Placing")
    handle.progress("sent")
    handle.done("filled")

    states = [e["step"]["state"] for e in seen]
    assert states == [activity.RUNNING, activity.RUNNING, activity.DONE]


def test_the_feed_is_capped():
    monitor = Monitor(cap=5)
    for i in range(12):
        monitor.info(activity.INFO, f"note {i}")
    titles = [s["title"] for s in monitor.snapshot()]
    assert titles == [f"note {i}" for i in range(7, 12)]
