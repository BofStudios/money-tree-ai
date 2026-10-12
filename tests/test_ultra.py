"""Ultra mode: the world's feeds, faster reads, every core, and back again."""
from types import SimpleNamespace

from app.brain.brain import Brain, BrainSettings
from app.brain.wires import FEEDS, ULTRA_FEEDS, Feed, WireReader


def test_ultra_reads_the_world_faster_and_stops_when_off():
    reader = WireReader(now=lambda: 0.0, get=lambda url, etag: (304, b"", None))
    base = len(reader.feeds)
    reader.set_ultra(True)
    assert len(reader.feeds) == base + len(ULTRA_FEEDS)
    assert {"ECB", "Pentagon", "FDA", "Apple newsroom"} <= set(reader.state)
    assert reader._every(Feed("x", "u", "gov", 30)) == 10.0          # never faster than every 10 s
    reader.set_ultra(False)
    assert len(reader.feeds) == base and "ECB" not in reader.state


def test_ultra_uses_every_core_and_puts_things_back():
    brain = Brain.__new__(Brain)
    brain.settings = BrainSettings(bots=2, power="light", news_max_positions=2)
    on = brain._ultra_changes(True)
    assert on["power"] == "full" and on["bots"] >= 2 and on["news_max_positions"] == 4
    assert on["before_ultra"] == {"bots": 2, "power": "light", "news_max_positions": 2, "self_improve": True}
    brain.settings.before_ultra = on["before_ultra"]
    off = brain._ultra_changes(False)
    assert off["bots"] == 2 and off["power"] == "light" and off["before_ultra"] == {}


def test_engine_scans_every_15_seconds_in_ultra(tmp_path):
    from tests.test_portfolio_engine import build

    engine = build(tmp_path)
    normal = engine.config.scan_interval_seconds
    engine.set_ultra(True)
    assert engine.config.scan_interval_seconds == 15 and engine.status()["ultra"]
    engine.set_ultra(False)
    assert engine.config.scan_interval_seconds == normal
