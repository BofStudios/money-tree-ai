import httpx
import pytest

from app.mentor import providers
from app.mentor.providers import (
    DEFAULT_MODELS,
    GeminiProvider,
    GroqProvider,
    OllamaProvider,
    ProviderError,
    build,
)

MESSAGES = [{"role": "user", "content": "how are we doing?"}]


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("boom", request=None, response=None)


# ------------------------------------------------------------------ picking


def test_auto_prefers_free_providers_over_the_paid_one(monkeypatch):
    monkeypatch.setattr(OllamaProvider, "available", lambda self: False)
    keys = {"gemini": "g", "groq": "q", "anthropic": "a"}

    assert build("auto", keys).name == "gemini"


def test_auto_falls_through_to_the_next_free_one(monkeypatch):
    monkeypatch.setattr(OllamaProvider, "available", lambda self: False)

    assert build("auto", {"groq": "q"}).name == "groq"


def test_auto_reaches_the_paid_one_only_when_nothing_free_is_set(monkeypatch):
    monkeypatch.setattr(OllamaProvider, "available", lambda self: False)

    assert build("auto", {"anthropic": "a"}).name == "anthropic"


def test_a_local_model_needs_no_key_at_all(monkeypatch):
    monkeypatch.setattr(OllamaProvider, "available", lambda self: True)

    provider = build("auto", {})
    assert provider.name == "ollama"
    assert provider.needs_key is False


def test_nothing_configured_means_no_provider(monkeypatch):
    monkeypatch.setattr(OllamaProvider, "available", lambda self: False)

    assert build("auto", {}) is None


def test_naming_a_provider_overrides_the_order(monkeypatch):
    monkeypatch.setattr(OllamaProvider, "available", lambda self: True)

    assert build("groq", {"groq": "q"}).name == "groq"


def test_a_named_provider_is_returned_even_when_it_has_no_key():
    """Better to report it as unavailable than to silently use a different one."""
    provider = build("gemini", {})

    assert provider.name == "gemini"
    assert provider.available() is False


def test_an_unknown_provider_is_refused():
    with pytest.raises(ProviderError):
        build("chatgpt", {})


def test_auto_gives_each_provider_its_own_default_model(monkeypatch):
    """A model name belongs to whichever provider was named, not to auto."""
    monkeypatch.setattr(OllamaProvider, "available", lambda self: False)

    provider = build("auto", {"groq": "q"}, model="gemini-2.0-flash")
    assert provider.model == DEFAULT_MODELS["groq"]


# ------------------------------------------------------------------ talking


def test_gemini_reads_the_reply_out_of_its_own_shape(monkeypatch):
    captured = {}

    def fake_post(url, **kwargs):
        captured.update(kwargs)
        return FakeResponse({"candidates": [{"content": {"parts": [{"text": "all quiet"}]}}]})

    monkeypatch.setattr(providers.httpx, "post", fake_post)
    reply = GeminiProvider("key").chat("be brief", MESSAGES, 100)

    assert reply.text == "all quiet"
    assert reply.provider == "gemini"
    # Gemini keeps the system prompt apart and calls the assistant "model".
    assert captured["json"]["systemInstruction"]["parts"][0]["text"] == "be brief"
    assert captured["json"]["contents"][0]["role"] == "user"


def test_gemini_renames_the_assistant_role(monkeypatch):
    captured = {}

    def fake_post(url, **kwargs):
        captured.update(kwargs)
        return FakeResponse({"candidates": [{"content": {"parts": [{"text": "ok"}]}}]})

    monkeypatch.setattr(providers.httpx, "post", fake_post)
    GeminiProvider("key").chat("s", [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ], 100)

    assert [c["role"] for c in captured["json"]["contents"]] == ["user", "model"]


def test_groq_sends_the_system_prompt_as_a_message(monkeypatch):
    captured = {}

    def fake_post(url, **kwargs):
        captured.update(kwargs)
        return FakeResponse({"choices": [{"message": {"content": "steady"}}]})

    monkeypatch.setattr(providers.httpx, "post", fake_post)
    reply = GroqProvider("key").chat("be brief", MESSAGES, 100)

    assert reply.text == "steady"
    assert captured["json"]["messages"][0] == {"role": "system", "content": "be brief"}


def test_a_rate_limited_free_tier_answers_nothing_rather_than_raising(monkeypatch):
    monkeypatch.setattr(providers.httpx, "post", lambda url, **kw: FakeResponse({}, 429))

    assert GroqProvider("key").chat("s", MESSAGES, 100) is None
    assert GeminiProvider("key").chat("s", MESSAGES, 100) is None


def test_a_network_failure_answers_nothing_rather_than_raising(monkeypatch):
    def explode(url, **kwargs):
        raise httpx.ConnectError("no route")

    monkeypatch.setattr(providers.httpx, "post", explode)

    assert GroqProvider("key").chat("s", MESSAGES, 100) is None
    assert OllamaProvider().chat("s", MESSAGES, 100) is None


def test_an_empty_reply_counts_as_no_reply(monkeypatch):
    monkeypatch.setattr(
        providers.httpx, "post",
        lambda url, **kw: FakeResponse({"choices": [{"message": {"content": "   "}}]}),
    )

    assert GroqProvider("key").chat("s", MESSAGES, 100) is None


def test_ollama_talks_to_the_local_daemon(monkeypatch):
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse({"message": {"content": "running locally"}})

    monkeypatch.setattr(providers.httpx, "post", fake_post)
    reply = OllamaProvider().chat("be brief", MESSAGES, 100)

    assert reply.text == "running locally"
    assert captured["url"].startswith("http://127.0.0.1:11434")
