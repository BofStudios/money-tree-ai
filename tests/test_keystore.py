"""Keys typed into the app: encrypted at rest, never echoed back in full."""
from __future__ import annotations

import sys

import pytest

from app.common.keystore import KeyStore

SECRET = "PKTEST1234567890ABCDEFGH"


def test_a_saved_key_survives_a_restart(tmp_path):
    path = tmp_path / "keys.json"
    KeyStore(path).set("alpaca_paper_key", SECRET)

    assert KeyStore(path).get("alpaca_paper_key") == SECRET


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="DPAPI is Windows-only")
def test_the_file_on_disk_never_contains_the_key(tmp_path):
    path = tmp_path / "keys.json"
    KeyStore(path).set("alpaca_paper_secret", SECRET)

    raw = path.read_bytes()
    assert SECRET.encode() not in raw
    assert SECRET[-8:].encode() not in raw


def test_the_dashboard_only_sees_presence_and_the_last_four(tmp_path):
    store = KeyStore(tmp_path / "keys.json")
    store.set("groq_api_key", SECRET)

    described = store.describe()
    assert described["groq_api_key"] == {"set": True, "tail": "EFGH"}
    assert described["alpaca_live_key"] == {"set": False, "tail": None}
    assert SECRET not in str(described)


def test_whitespace_is_trimmed_and_empty_deletes(tmp_path):
    store = KeyStore(tmp_path / "keys.json")
    store.set("alpaca_live_key", f"  {SECRET}\n")
    assert store.get("alpaca_live_key") == SECRET

    store.set("alpaca_live_key", "   ")
    assert store.get("alpaca_live_key") is None


def test_unknown_names_are_refused(tmp_path):
    with pytest.raises(ValueError):
        KeyStore(tmp_path / "keys.json").set("telegram_token", "x")


def test_a_damaged_file_starts_empty_instead_of_crashing(tmp_path):
    path = tmp_path / "keys.json"
    path.write_text("{ not json", encoding="utf-8")

    assert KeyStore(path).get("alpaca_paper_key") is None


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="DPAPI is Windows-only")
def test_a_blob_that_cannot_be_opened_is_skipped_not_fatal(tmp_path):
    path = tmp_path / "keys.json"
    path.write_text('{"alpaca_paper_key": "bm90IGEgZHBhcGkgYmxvYg=="}', encoding="utf-8")

    store = KeyStore(path)
    assert store.get("alpaca_paper_key") is None
