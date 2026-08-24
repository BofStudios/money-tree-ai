from datetime import datetime, timedelta, timezone

import pytest

from app.catalysts.manager import ARMED, HOLDING, WATCHING, CatalystManager, parse_date
from app.common.events import EventBus
from app.storage.db import create_session_factory


@pytest.fixture
def manager(tmp_path):
    return CatalystManager(create_session_factory(tmp_path / "cat.db"), EventBus())


def in_days(days: int) -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=days)


# -------------------------------------------------------------- date parsing


def test_a_full_date_is_taken_as_written():
    assert parse_date("2026-11-19").date().isoformat() == "2026-11-19"


def test_a_bare_month_means_the_end_of_that_month():
    """Release windows are often "November 2026" and nothing more precise."""
    assert parse_date("2026-11").date().isoformat() == "2026-11-30"


def test_february_month_end_handles_the_short_month():
    assert parse_date("2026-02").date().isoformat() == "2026-02-28"


def test_nonsense_dates_are_refused():
    with pytest.raises(ValueError):
        parse_date("next christmas")


# ------------------------------------------------------------------- adding


def test_a_catalyst_starts_out_watching(manager):
    c = manager.add("GTA 6 launch", "ttwo", in_days(200), entry_days_before=45)

    assert c.status == WATCHING
    assert c.symbol == "TTWO"          # normalised
    assert c.days_away == 200
    assert c.in_entry_window is False
    assert c.window_opens_in == 155


def test_a_catalyst_inside_the_window_reports_it(manager):
    c = manager.add("Film opens", "DIS", in_days(20), entry_days_before=45)

    assert c.in_entry_window is True
    assert c.window_opens_in == 0


def test_a_past_event_is_flagged(manager):
    c = manager.add("Already happened", "AAPL", in_days(-3))

    assert c.is_past is True
    assert c.in_entry_window is False


def test_a_catalyst_needs_a_title_and_a_ticker(manager):
    with pytest.raises(ValueError):
        manager.add("", "TTWO", in_days(30))
    with pytest.raises(ValueError):
        manager.add("Something", "  ", in_days(30))


def test_bad_conviction_is_refused(manager):
    with pytest.raises(ValueError):
        manager.add("Thing", "TTWO", in_days(30), conviction="certain")


def test_bad_exit_rule_is_refused(manager):
    with pytest.raises(ValueError):
        manager.add("Thing", "TTWO", in_days(30), exit_rule="whenever")


# ------------------------------------------------------------------ listing


def test_open_catalysts_are_listed_in_date_order(manager):
    manager.add("Later", "AAPL", in_days(120))
    manager.add("Sooner", "MSFT", in_days(10))

    assert [c.title for c in manager.all()] == ["Sooner", "Later"]


def test_finished_catalysts_are_hidden_by_default(manager):
    c = manager.add("Done", "AAPL", in_days(30))
    manager.update(c.id, status="closed")

    assert manager.all() == []
    assert len(manager.all(include_finished=True)) == 1


def test_symbols_lists_each_open_ticker_once(manager):
    manager.add("One", "TTWO", in_days(30))
    manager.add("Two", "TTWO", in_days(60))
    manager.add("Three", "DIS", in_days(90))

    assert manager.symbols() == ["DIS", "TTWO"]


# ------------------------------------------------------------------ windows


def test_refresh_arms_a_catalyst_that_entered_its_window(manager):
    manager.add("Close now", "DIS", in_days(20), entry_days_before=45)

    opened = manager.refresh_windows()
    assert [c.title for c in opened] == ["Close now"]
    assert manager.all()[0].status == ARMED


def test_a_window_is_only_announced_once(manager):
    manager.add("Close now", "DIS", in_days(20), entry_days_before=45)

    manager.refresh_windows()
    assert manager.refresh_windows() == []


def test_a_distant_catalyst_is_left_alone(manager):
    manager.add("Far off", "TTWO", in_days(300), entry_days_before=45)

    assert manager.refresh_windows() == []
    assert manager.all()[0].status == WATCHING


def test_a_position_you_took_is_not_re_armed(manager):
    c = manager.add("Close now", "DIS", in_days(20), entry_days_before=45)
    manager.update(c.id, status=HOLDING)

    assert manager.refresh_windows() == []
    assert manager.all()[0].status == HOLDING


# ------------------------------------------------------------------- edits


def test_a_catalyst_can_be_removed(manager):
    c = manager.add("Mistake", "AAPL", in_days(30))

    assert manager.remove(c.id) is True
    assert manager.all() == []
    assert manager.remove(c.id) is False


def test_updating_an_unknown_catalyst_returns_nothing(manager):
    assert manager.update(999, status=HOLDING) is None


def test_the_dashboard_shape_has_what_it_needs(manager):
    c = manager.add("GTA 6", "TTWO", in_days(90), thesis="Take-Two makes it.")
    data = c.to_dict()

    assert set(data) >= {
        "id", "title", "symbol", "event_date", "days_away",
        "in_entry_window", "window_opens_in", "status", "conviction", "thesis",
    }
    assert data["event_date"].count("-") == 2
