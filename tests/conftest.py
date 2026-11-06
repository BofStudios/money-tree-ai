import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def pytest_configure(config):
    config.addinivalue_line("markers", "real_vote: run Ultra's real confluence vote, not the fixed one")
    config.addinivalue_line("markers", "real_pace: keep the calm start and the one-buy-at-a-time pace")


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _no_pace(request, monkeypatch):
    """Most tests buy several times in a row; the pace (calm start, one buy
    at a time) is tested on its own with the real_pace marker."""
    if "real_pace" in request.keywords:
        return
    from app.engine import portfolio_engine as PE

    monkeypatch.setattr(PE, "CALM_SECONDS", 0)
    monkeypatch.setattr(PE, "BUY_GAP", {"portfolio": 0, "scalp": 0})
