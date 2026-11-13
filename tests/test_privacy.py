"""Desktop 10.1: who may use the dashboard, what leaves the PC, and your data."""
from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient

from app.privacy import data as mydata
from app.privacy import hosts as hostlist
from app.privacy import minimize
from app.privacy.prefs import Prefs
from app.web.auth import Auth, Lockout, same_origin
from tests.test_scalper import scalp_engine

ROOT = Path(__file__).resolve().parent.parent
TOKEN = "t" * 40


# --------------------------------------------------- the list of servers

def _hosts_in_sources() -> dict[str, str]:
    url = re.compile(r"https?://[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]+")
    found: dict[str, str] = {}
    for base in (ROOT / "app", ROOT / "android" / "app" / "src" / "main"):
        for p in base.rglob("*"):
            if p.suffix not in {".py", ".js", ".html", ".kt", ".xml", ".json", ".webmanifest"}:
                continue
            if "__pycache__" in p.parts or "build" in p.parts or not p.is_file():
                continue
            if p.name in ("hosts.py", "docs.py") and p.parent.name == "privacy" or p.name == "privacy.html":
                continue            # the list, and the policy made from it, name each service's privacy page
            for m in url.finditer(p.read_text(encoding="utf-8", errors="ignore")):
                host = urlparse(m.group(0).rstrip(".,)\"'")).hostname
                if host:
                    found.setdefault(host, str(p.relative_to(ROOT)))
    return found


def test_every_address_in_the_sources_is_declared_in_the_host_list():
    """The privacy page is written from hosts.py. A new connection must be added there."""
    undeclared = {h: where for h, where in _hosts_in_sources().items() if h not in hostlist.known()}
    assert not undeclared, f"declare these in app/privacy/hosts.py: {undeclared}"


def test_the_host_list_has_no_server_that_the_app_no_longer_names():
    named = set(_hosts_in_sources())
    stale = [h.host for h in hostlist.HOSTS if h.when != "library" and h.host not in named]
    assert not stale, f"no longer in the sources, remove from hosts.py: {stale}"


def test_there_is_no_server_of_ours_and_no_ad_or_tracker_host():
    names = " ".join(h.host for h in hostlist.HOSTS)
    for word in ("bofstudio", "google-analytics", "googletagmanager", "doubleclick", "segment", "sentry",
                 "mixpanel", "amplitude", "facebook", "lemonsqueezy"):
        assert word not in names


def test_every_host_says_what_goes_there_in_both_languages_and_when():
    for h in hostlist.HOSTS:
        assert h.what and h.wat and h.who
        assert h.when in {"always", "keys", "update", "link", "local", "library"}
        assert not h.policy or h.policy.startswith("https://")


# ----------------------------------------------------------- the choices

def test_a_new_install_is_closed_to_the_network_and_an_old_one_keeps_its_phone_until_asked(tmp_path):
    new = Prefs(tmp_path / "a.json", existing_install=False)
    assert new.get("lan") is False and new.get("lan_asked") is True
    old = Prefs(tmp_path / "b.json", existing_install=True)
    assert old.get("lan") is True and old.get("lan_asked") is False
    old.update({"lan": False})
    assert old.get("lan_asked") is True
    again = Prefs(tmp_path / "b.json", existing_install=True)
    assert again.get("lan") is False, "the owner's answer is kept over the first-run rule"


def test_choices_are_checked_and_survive_a_restart(tmp_path):
    p = Prefs(tmp_path / "p.json")
    with pytest.raises(ValueError):
        p.update({"ai_level": "everything-and-more"})
    with pytest.raises(ValueError):
        p.update({"nope": True})
    with pytest.raises(ValueError):
        p.update({"log_days": 3})
    p.update({"ai_level": "percent", "remember_chat": False, "log_days": 7})
    q = Prefs(tmp_path / "p.json")
    assert (q.get("ai_level"), q.get("remember_chat"), q.get("log_days")) == ("percent", False, 7)
    (tmp_path / "p.json").write_text("{broken", encoding="utf-8")
    assert Prefs(tmp_path / "p.json").get("lan") is False, "a broken file falls back to the safe defaults"


# ------------------------------------------------------ what the AI sees

CONTEXT = {
    "mode": "paper", "market": {"is_open": True, "countdown": "1h"},
    "equity": 55.2, "balance": {"total": 55.2, "available": 20.0},
    "risk": {"daily_loss": 1.2, "armed": False},
    "open_positions": [{"symbol": "AAPL", "qty": 3, "market_value": 570.0, "unrealized_pnl": 4.0,
                        "unrealized_pnl_pct": 0.7, "current_price": 190.0}],
    "recent_trades": [{"symbol": "MSFT", "qty": 2, "pnl": 1.5, "pnl_pct": 0.4}],
    "stats": {"total_pnl": 3.2, "win_rate": 55.0},
}


def test_the_percent_level_removes_the_owners_money_and_keeps_symbols_and_percentages():
    out = minimize.apply(CONTEXT, "percent")
    text = json.dumps(out)
    assert "AAPL" in text and "0.7" in text and "190.0" in text, "market prices and percentages stay"
    for gone in ("55.2", "570.0", "1.5", "3.2", "daily_loss", "market_value", "qty", "unrealized_pnl\""):
        assert gone not in text, gone
    assert CONTEXT["equity"] == 55.2, "the original is not changed"


def test_the_none_level_sends_nothing_about_the_account():
    out = minimize.apply(CONTEXT, "none")
    assert "AAPL" not in json.dumps(out) and out["market"] == {"is_open": True}
    assert minimize.apply(CONTEXT, "full") is CONTEXT


def test_the_note_after_a_buy_follows_the_level():
    args = ("AAPL", 190.0, "dip", 3.0, 4.5, 188.0, 194.0)
    full = minimize.trade_facts(*args, "full")
    assert "Bought 3 AAPL" in full and "4.50 USD" in full
    percent = minimize.trade_facts(*args, "percent")
    assert "Bought AAPL at 190.00" in percent and "USD" not in percent and " 3 " not in percent
    assert minimize.trade_facts(*args, "none") == "Bought AAPL. Rule that fired: dip. "


def test_the_ai_gets_the_level_chat_memory_off_and_a_readable_record(tmp_path):
    from app.config import MentorConfig
    from app.mentor import providers
    from app.mentor.ai import AIMentor

    seen = []

    class Fake:
        name, model = "fake", "m"

        def available(self):
            return True

        def chat(self, system, messages, max_tokens):
            seen.append(messages)
            return providers.Reply("ok", "fake", "m")

    mentor = AIMentor(MentorConfig(enabled=False), keys={}, memory_path=tmp_path / "mem.json")
    mentor.provider = Fake()
    mentor.config.enabled = True
    mentor.privacy = Prefs(tmp_path / "p.json")
    mentor.privacy.update({"ai_level": "percent", "remember_chat": False})
    assert mentor.answer("how are we doing?", CONTEXT) == "ok"
    assert "55.2" not in seen[0][-1]["content"] and "AAPL" in seen[0][-1]["content"]
    assert not (tmp_path / "mem.json").exists() or "how are we doing" not in (tmp_path / "mem.json").read_text(encoding="utf-8")
    assert mentor.last_sent and "how are we doing?" in mentor.last_sent[0]["text"]
    mentor.privacy.update({"remember_chat": True})
    mentor.answer("and now?", CONTEXT)
    assert len(seen[1]) == 1, "the first question was never kept, so no history is sent"
    assert "and now?" in (tmp_path / "mem.json").read_text(encoding="utf-8")


# ------------------------------------------------------------- your data

def _home(tmp_path):
    home = tmp_path / "home"
    (home / "data" / "brain").mkdir(parents=True)
    (home / "logs").mkdir()
    for rel, text in (("data/keys.dat", "SECRETKEY"), (".env", "ALPACA=SECRET"), ("data/dashboard.token", "SECRETTOKEN"),
                      ("data/mentor_memory.json", "{}"), ("data/trading.db", "db"), ("data/lab.json", "{}"),
                      ("data/brain/news_memory.json", "{}"), ("logs/bot.log", "x")):
        (home / rel).write_text(text, encoding="utf-8")
    return home


def test_the_inventory_marks_secrets_and_the_export_never_holds_them(tmp_path):
    home = _home(tmp_path)
    rows = {r["path"]: r for r in mydata.inventory(home)}
    assert rows["data/keys.dat"]["secret"] and not rows["data/keys.dat"]["in_export"]
    assert rows["data/lab.json"]["in_export"] and not rows["data/live_feed.json"]["exists"]
    out = mydata.export_zip(home, [{"symbol": "AAPL", "pnl": 1.0, "qty": 2}])
    with zipfile.ZipFile(out) as z:
        names = set(z.namelist())
        body = b"".join(z.read(n) for n in names)
    assert {"trades.csv", "README.txt", "data/lab.json", "data/brain/news_memory.json"} <= names
    assert not names & {"data/keys.dat", ".env", "data/dashboard.token", "data/trading.db"}
    for secret in (b"SECRETKEY", b"SECRET", b"SECRETTOKEN"):
        assert secret not in body
    assert b"AAPL" in body


def test_old_logs_are_pruned_and_the_new_one_stays(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    old, new = logs / "bot.log.3", logs / "bot.log"
    old.write_text("a")
    new.write_text("b")
    import os
    import time

    past = time.time() - 40 * 86400
    os.utime(old, (past, past))
    assert mydata.prune_logs(logs, 14) == 1 and new.exists() and not old.exists()


# ------------------------------------------------------- who may come in

class Conn:
    def __init__(self, query="", header="", cookie="", host="1.2.3.4"):
        from starlette.requests import Request

        headers = []
        if header:
            headers.append((b"authorization", header.encode()))
        if cookie:
            headers.append((b"cookie", f"mt_session={cookie}".encode()))
        self.req = Request({"type": "http", "headers": headers, "query_string": query.encode(),
                            "client": (host, 5000), "method": "GET", "path": "/"})


def test_the_password_is_accepted_from_the_url_a_header_or_the_cookie():
    a = Auth(TOKEN)
    assert a.check(Conn(query=f"token={TOKEN}").req)
    assert a.check(Conn(header=f"Bearer {TOKEN}").req)
    assert a.check(Conn(cookie=TOKEN).req)
    assert not a.check(Conn().req), "no credential: refused, not counted as a try"
    assert a.lockout.left("1.2.3.4") == 0


def test_five_wrong_tries_lock_the_address_and_the_wait_doubles():
    now = [1000.0]
    a = Auth(TOKEN, clock=lambda: now[0])
    bad = lambda: a.check(Conn(query="token=wrong").req)           # noqa: E731
    from fastapi import HTTPException

    for _ in range(5):
        assert bad() is False
    with pytest.raises(HTTPException) as e:
        a.check(Conn(query=f"token={TOKEN}").req)
    assert e.value.status_code == 429 and e.value.headers["Retry-After"] == "60", "even the right password waits"
    now[0] += 61
    assert a.check(Conn(query=f"token={TOKEN}").req), "after the wait the right password works again"
    for _ in range(5):
        bad()
    assert a.lockout.left("1.2.3.4") == 60, "the right password reset the count"


def test_lockout_wait_grows_to_a_limit():
    now = [0.0]
    lock = Lockout(clock=lambda: now[0])
    waits = []
    for _ in range(8):
        for _ in range(5):
            lock.fail("x")
        waits.append(lock.left("x"))
        now[0] += waits[-1] + 1
    assert waits[:4] == [60, 120, 240, 480] and max(waits) == 900


def test_only_the_pages_own_origin_may_change_things():
    assert same_origin("http://127.0.0.1:8765", "127.0.0.1:8765")
    assert not same_origin("http://evil.example", "127.0.0.1:8765")
    assert not same_origin("null", "127.0.0.1:8765") and not same_origin("", "x")


# --------------------------------------------------------- the whole app

@pytest.fixture()
def client(tmp_path, monkeypatch):
    from app.config import MentorConfig
    from app.mentor.ai import AIMentor
    from app.web import privacy_routes as PR
    from app.web.server import create_app

    home = _home(tmp_path)
    monkeypatch.setattr(PR, "data_home", lambda: home)
    monkeypatch.setattr(PR, "DATA_DIR", home / "data")
    monkeypatch.setattr(PR, "LOG_DIR", home / "logs")
    (home / "data" / "dashboard.token").write_text(TOKEN, encoding="utf-8")
    engine = scalp_engine(tmp_path)
    engine.privacy = Prefs(home / "data" / "privacy.json")
    claude = AIMentor(MentorConfig(enabled=False), keys={"groq": "g"}, memory_path=home / "data" / "mentor_memory.json")
    claude.privacy = engine.privacy
    app = create_app(engine, engine.repo, engine.mentor, claude, engine.events, TOKEN)
    c = TestClient(app, base_url="http://127.0.0.1:8765")
    c.engine, c.claude, c.home = engine, claude, home
    return c


def test_the_first_visit_becomes_a_cookie_and_a_clean_address(client):
    r = client.get(f"/?token={TOKEN}&x=1", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/?x=1"
    cookie = r.headers["set-cookie"]
    assert "mt_session=" in cookie and "HttpOnly" in cookie and "SameSite=strict" in cookie.replace("samesite", "SameSite")
    client.cookies.clear()
    assert client.get("/api/status").status_code == 401, "without the cookie the page's calls are refused"
    client.cookies.set("mt_session", TOKEN)
    assert client.get("/api/status").status_code == 200
    wrong = client.get("/?token=wrong", follow_redirects=False)
    assert wrong.status_code == 200 and "set-cookie" not in wrong.headers


def test_a_foreign_origin_cannot_change_anything_even_with_the_cookie(client):
    client.cookies.set("mt_session", TOKEN)
    body = {"remember_chat": False}
    bad = client.patch("/api/privacy", json=body, headers={"Origin": "http://evil.example"})
    assert bad.status_code == 403
    ok = client.patch("/api/privacy", json=body, headers={"Origin": "http://127.0.0.1:8765"})
    assert ok.status_code == 200 and ok.json()["choices"]["remember_chat"] is False


def test_every_answer_carries_the_security_headers(client):
    r = client.get("/api/status")
    assert r.status_code == 401
    csp = r.headers["content-security-policy"]
    assert "script-src 'self'" in csp and "'unsafe-inline'" not in csp.split("style-src")[0]
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "no-referrer"
    page = client.get("/")
    assert page.status_code == 200 and "content-security-policy" in page.headers


def test_no_page_runs_an_inline_script_or_handler():
    """The policy allows scripts from the app's own files only."""
    for html in (ROOT / "app" / "web" / "static").glob("*.html"):
        text = html.read_text(encoding="utf-8")
        for tag in re.findall(r"<script\b[^>]*>", text):
            assert "src=" in tag, f"{html.name}: inline script"
        assert not re.search(r"\son(click|change|submit|load|error)\s*=", text), f"{html.name}: inline handler"


def test_the_privacy_screen_api(client):
    client.cookies.set("mt_session", TOKEN)
    got = client.get("/api/privacy").json()
    assert got["choices"]["lan"] is False and got["phone"]["asked"] is True
    assert any(h["host"] == "api.groq.com" for h in got["hosts"]) and got["can_look"]
    assert not any(h["platform"] == "android" for h in got["hosts"])
    assert client.patch("/api/privacy", json={"ai_level": "x"}).status_code == 400
    r = client.patch("/api/privacy", json={"lan": True}).json()
    assert r["restart_needed"] is True and r["choices"]["lan"] is True

    out = client.post("/api/privacy/export").json()
    assert Path(out["path"]).exists() and Path(out["path"]).parent == client.home / "exports"


def test_clearing_goes_through_the_app_and_all_needs_the_word(client):
    client.cookies.set("mt_session", TOKEN)
    client.claude.memory.remember("my fact")
    assert client.post("/api/privacy/clear", json={"group": "nope"}).status_code == 400
    assert client.post("/api/privacy/clear", json={"group": "all"}).status_code == 400
    assert client.post("/api/privacy/clear", json={"group": "all", "confirm": "no"}).status_code == 400
    assert client.claude.memory.facts(), "nothing was cleared without the word"
    done = client.post("/api/privacy/clear", json={"group": "all", "confirm": "Delete"}).json()
    assert set(done["cleared"]) >= {"chat", "lab"} and not client.claude.memory.facts()
    assert (client.home / "data" / "trading.db").exists() and (client.home / "data" / "keys.dat").exists(), \
        "trades and keys are never cleared from here"


def test_a_new_password_replaces_the_file_and_the_old_one_stops_working(client):
    client.cookies.set("mt_session", TOKEN)
    r = client.post("/api/privacy/password")
    assert r.status_code == 200
    fresh = (client.home / "data" / "dashboard.token").read_text(encoding="utf-8")
    assert fresh != TOKEN and len(fresh) >= 40
    client.cookies.clear()
    client.cookies.set("mt_session", TOKEN)
    assert client.get("/api/status").status_code == 401
    client.cookies.set("mt_session", fresh)
    assert client.get("/api/status").status_code == 200


def test_the_screens_text_exists_in_both_languages():
    text = (ROOT / "app" / "web" / "static" / "i18n.js").read_text(encoding="utf-8")
    en, tr = text.split('\n  tr: {', 1) if "\n  tr: {" in text else text.split("\r\n  tr: {", 1)
    for prefix in ("priv.", "lab."):
        a = set(re.findall(rf'"({re.escape(prefix)}[^"]+)":', en))
        b = set(re.findall(rf'"({re.escape(prefix)}[^"]+)":', tr))
        assert a and a == b, (prefix, a ^ b)
    ids = set(re.findall(r'data-i18n="([^"]+)"', (ROOT / "app" / "web" / "static" / "index.html").read_text(encoding="utf-8")))
    known = set(re.findall(r'"([A-Za-z0-9_.]+)":', en))
    assert not (ids - known), ids - known


# ------------------------------------------------------------ the policy

def test_the_written_policy_is_the_one_the_code_makes():
    """PRIVACY.md, PRIVACY.tr.md and /privacy.html are generated from the host and file lists."""
    from app.privacy import docs

    for path, text in docs.outputs().items():
        written = path.read_text(encoding="utf-8").replace(chr(13) + chr(10), chr(10))
        assert written == text, f"{path.name} is out of date: run python scripts/gen_privacy.py"


def test_the_policy_names_every_server_and_holds_no_personal_detail():
    from app.privacy import docs

    en = docs.markdown("en")
    for h in hostlist.HOSTS:
        assert f"`{h.host}`" in en
    for text in (en, docs.markdown("tr"), docs.page()):
        assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text), "no e-mail address belongs in the policy"
        assert "ozuysal" not in text.lower()
