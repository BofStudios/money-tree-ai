import pytest

from app.common import licensing
from app.common.licensing import License, Unreachable

DAY = 24 * 3600


@pytest.fixture(autouse=True)
def product(monkeypatch):
    monkeypatch.setattr(licensing, "STORE_ID", 11)
    monkeypatch.setattr(licensing, "PRODUCT_ID", 22)


def ours(**extra):
    return {"meta": {"store_id": 11, "product_id": 22, "customer_name": "Ada"},
            "instance": {"id": "inst-1"}, **extra}


class Server:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    def __call__(self, path, data):
        self.calls.append((path, data))
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


class Clock:
    def __init__(self):
        self.now = 1_000_000.0

    def __call__(self):
        return self.now


def make(tmp_path, *answers):
    server, clock = Server(*answers), Clock()
    return License(tmp_path / "license.json", post=server, clock=clock), server, clock


def test_activation_saves_the_instance(tmp_path):
    lic, server, _ = make(tmp_path, ours(activated=True))
    verdict = lic.activate("  KEY-1  ")
    assert verdict.ok and verdict.customer == "Ada"
    assert server.calls[0][0] == "activate"
    assert server.calls[0][1]["license_key"] == "KEY-1"
    assert lic.check().ok  # trusted without asking again the same day
    assert len(server.calls) == 1


def test_key_from_another_product_is_refused(tmp_path):
    other = ours(activated=True)
    other["meta"]["product_id"] = 99
    lic, _, _ = make(tmp_path, other)
    assert lic.activate("KEY-1").reason == "other_product"
    assert not lic.check().ok


def test_activation_limit_is_explained(tmp_path):
    lic, _, _ = make(tmp_path, {"activated": False, "error": "This license key has reached the activation limit."})
    assert lic.activate("KEY-1").reason == "limit"


def test_empty_and_offline_activation(tmp_path):
    lic, _, _ = make(tmp_path, Unreachable("down"))
    assert lic.activate("   ").reason == "empty"
    assert lic.activate("KEY-1").reason == "offline"


def test_never_activated_has_no_reason(tmp_path):
    lic, server, _ = make(tmp_path)
    verdict = lic.check()
    assert not verdict.ok and verdict.reason == ""
    assert server.calls == []


def test_revalidates_after_a_day(tmp_path):
    lic, server, clock = make(tmp_path, ours(activated=True), ours(valid=True))
    lic.activate("KEY-1")
    clock.now += DAY + 1
    assert lic.check().ok
    assert server.calls[1] == ("validate", {"license_key": "KEY-1", "instance_id": "inst-1"})


def test_offline_grace_then_stale(tmp_path):
    lic, _, clock = make(tmp_path, ours(activated=True), Unreachable("x"), Unreachable("x"))
    lic.activate("KEY-1")
    clock.now += 5 * DAY
    assert lic.check().ok
    clock.now += 10 * DAY
    assert lic.check().reason == "stale"


def test_refunded_licence_is_forgotten(tmp_path):
    lic, _, clock = make(tmp_path, ours(activated=True), {"valid": False, "error": "license_key is disabled"})
    lic.activate("KEY-1")
    clock.now += 2 * DAY
    assert lic.check().reason == "disabled"
    assert not (tmp_path / "license.json").exists()


def test_deactivate_frees_the_machine(tmp_path):
    lic, server, _ = make(tmp_path, ours(activated=True), {"deactivated": True})
    lic.activate("KEY-1")
    assert lic.deactivate()
    assert server.calls[1][0] == "deactivate"
    assert not (tmp_path / "license.json").exists()


def test_unconfigured_product(monkeypatch):
    monkeypatch.setattr(licensing, "STORE_ID", 0)
    assert not licensing.configured()
