"""Keys, money mode and the money screen, through the HTTP routes.

Alpaca itself is replaced by a stand-in: no request leaves the machine.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.common.keystore import KeyStore
from app.config import Secrets, Settings
from app.web import money_routes
from app.web.money_routes import build_money_router
from test_portfolio_engine import FakeMarket, build, make_config

PAPER_KEY, PAPER_SECRET = "PKTESTKEY1234WXYZ", "papersecretvalue0000"
LIVE_KEY, LIVE_SECRET = "AKLIVEKEY9876ABCD", "livesecretvalue11111"


class FakeRestarter:
    def __init__(self):
        self.requests = 0

    def request(self, delay: float = 0.8):
        self.requests += 1


@pytest.fixture
def setup(tmp_path, monkeypatch):
    accepted = {(PAPER_KEY, PAPER_SECRET, False), (LIVE_KEY, LIVE_SECRET, True)}

    def fake_check(key, secret, live):
        if (key, secret, live) not in accepted:
            raise PermissionError("401")
        return {"status": "ACTIVE", "equity": 12.5, "cash": 12.5, "currency": "USD", "blocked": False}

    monkeypatch.setattr(money_routes, "_check_alpaca", fake_check)

    engine = build(tmp_path)
    settings = Settings(app=make_config(), secrets=Secrets(_env_file=None))
    keystore = KeyStore(tmp_path / "keys.dat")
    restarter = FakeRestarter()
    config = tmp_path / "config.yaml"
    config.write_text("mode: paper   # practice\nmarket: us_stocks\n", encoding="utf-8")

    def client(host="testclient", token="", problems=None):
        app = FastAPI()
        app.include_router(build_money_router(
            engine, engine.repo, settings, keystore, restarter, token, config, problems))
        return TestClient(app, client=(host, 50000))

    return {"engine": engine, "settings": settings, "keystore": keystore, "restarter": restarter,
            "config": config, "client": client}


# -------------------------------------------------------------------- keys


def test_saved_keys_are_checked_encrypted_and_never_echoed(setup):
    api = setup["client"]()
    reply = api.post("/api/keys/alpaca", json={"account": "paper", "key": PAPER_KEY, "secret": PAPER_SECRET})

    assert reply.status_code == 200
    assert reply.json()["restart_needed"] is True
    assert PAPER_SECRET not in reply.text and PAPER_KEY not in reply.text
    assert setup["keystore"].get("alpaca_paper_secret") == PAPER_SECRET

    view = api.get("/api/keys").json()
    assert view["alpaca_paper"] == {"set": True, "tail": "WXYZ", "source": "app", "problem": None}
    assert view["alpaca_live"]["set"] is False
    assert PAPER_KEY not in str(view) and PAPER_SECRET not in str(view)


def test_refused_keys_are_not_saved_and_the_hint_says_why(setup):
    api = setup["client"]()
    # Paper keys pasted into the live slot.
    reply = api.post("/api/keys/alpaca", json={"account": "live", "key": PAPER_KEY, "secret": PAPER_SECRET})

    assert reply.status_code == 400
    assert "paper keys" in reply.json()["detail"]
    assert setup["keystore"].get("alpaca_live_key") is None


def test_keys_cannot_be_changed_from_another_device_without_the_token(setup):
    phone = setup["client"](host="192.168.1.50")
    reply = phone.post("/api/keys/alpaca", json={"account": "paper", "key": PAPER_KEY, "secret": PAPER_SECRET})

    assert reply.status_code == 403
    assert setup["keystore"].get("alpaca_paper_key") is None
    assert phone.get("/api/keys").status_code == 200   # reading is fine


def test_deleting_keys_forgets_both_halves(setup):
    api = setup["client"]()
    api.post("/api/keys/alpaca", json={"account": "paper", "key": PAPER_KEY, "secret": PAPER_SECRET})

    assert api.delete("/api/keys/alpaca/paper").status_code == 200
    assert setup["keystore"].get("alpaca_paper_key") is None
    assert setup["keystore"].get("alpaca_paper_secret") is None


# -------------------------------------------------------------- money mode


def test_real_money_needs_live_keys_and_a_confirmation(setup):
    api = setup["client"]()

    assert api.post("/api/mode", json={"mode": "live", "confirm": True}).status_code == 400
    api.post("/api/keys/alpaca", json={"account": "live", "key": LIVE_KEY, "secret": LIVE_SECRET})
    assert api.post("/api/mode", json={"mode": "live"}).status_code == 400
    assert setup["restarter"].requests == 0

    reply = api.post("/api/mode", json={"mode": "live", "confirm": True})
    assert reply.status_code == 200
    assert setup["config"].read_text(encoding="utf-8").startswith("mode: live   # practice")
    assert setup["restarter"].requests == 1


def test_practice_money_needs_no_confirmation(setup):
    api = setup["client"]()
    assert api.post("/api/mode", json={"mode": "paper"}).status_code == 200
    assert setup["restarter"].requests == 1


# ---------------------------------------------------------------- screens


def test_the_money_screen_reports_the_account_and_the_result(setup):
    engine = setup["engine"]
    engine._scan(FakeMarket())
    held = engine.status()["positions"][0]["symbol"]
    engine.close_position_now(held)

    money = setup["client"]().get("/api/money").json()

    assert money["broker"] == "simulation"
    assert money["real"] is False
    assert money["account"]["equity"] > 0
    assert money["made"]["trades"] == 1
    assert money["alpaca_url"].startswith("https://app.alpaca.markets/")


def test_the_live_feed_serves_every_step_so_far(setup):
    engine = setup["engine"]
    engine._scan(FakeMarket())

    feed = setup["client"]().get("/api/steps").json()

    assert feed["steps"] and feed["steps"][0]["kind"] == "clock"
    assert {"running", "focus", "next_look_at", "language"} <= set(feed)


def test_keys_alpaca_refused_at_startup_say_so_until_replaced(setup):
    setup["settings"].secrets.alpaca_api_key = "PKOLDREVOKED0000"
    setup["settings"].secrets.alpaca_api_secret = "oldsecret"
    api = setup["client"](problems={"paper": "HTTP 401"})

    before = api.get("/api/keys").json()["alpaca_paper"]
    assert before["set"] is True and before["problem"] == "HTTP 401"

    api.post("/api/keys/alpaca", json={"account": "paper", "key": PAPER_KEY, "secret": PAPER_SECRET})
    after = api.get("/api/keys").json()["alpaca_paper"]
    assert after["problem"] is None and after["source"] == "app"
