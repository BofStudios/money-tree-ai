"""The language models the mentor can speak through.

Every provider takes the same three things — a system prompt, a list of
``{"role", "content"}`` turns, and a token ceiling — and returns text or None.
None always means "this one could not answer"; the caller falls back to the
rule-based narrator rather than showing an error.

Four backends, ordered by what they cost you:

    ollama     free, runs on this machine, needs no account at all
    gemini     free tier at aistudio.google.com, needs a free key
    groq       free tier at console.groq.com, needs a free key
    anthropic  paid, the best of the four

Only ``anthropic`` uses an SDK; the rest are small JSON APIs and go over plain
HTTP so the project does not grow three more dependencies.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

log = logging.getLogger(__name__)

TIMEOUT = 60.0
# A local model has to be read off disk into memory on the first call after a
# cold start, which takes far longer than any hosted API round trip.
LOCAL_TIMEOUT = 300.0

# What each provider is called in config, and the model it uses by default.
DEFAULT_MODELS = {
    "ollama": "llama3.2",
    "gemini": "gemini-2.0-flash",
    # Groq retired llama-3.3-70b-versatile; gpt-oss-120b is its current
    # free-tier flagship (verified live against /v1/models on 2026-09-12).
    "groq": "openai/gpt-oss-120b",
    "anthropic": "claude-opus-5",
}

FREE = ("ollama", "gemini", "groq")


@dataclass
class Reply:
    """What came back, and which model said it."""

    text: str
    provider: str
    model: str


class ProviderError(Exception):
    """Raised for a configuration mistake worth showing the owner."""


# --------------------------------------------------------------------- ollama


class OllamaProvider:
    """A model running on this machine. No key, no account, no per-token cost.

    Needs Ollama installed and a model pulled (`ollama pull llama3.2`). If the
    daemon is not running every call returns None and the narrator carries on.
    """

    name = "ollama"
    needs_key = False

    def __init__(self, model: str = "", host: str = "http://127.0.0.1:11434") -> None:
        self.model = model or DEFAULT_MODELS["ollama"]
        self.host = host.rstrip("/")

    def available(self) -> bool:
        try:
            r = httpx.get(f"{self.host}/api/tags", timeout=3.0)
            if r.status_code != 200:
                return False
            names = [m.get("name", "") for m in r.json().get("models", [])]
        except Exception:
            return False
        # Being installed is not the same as having a model pulled.
        return any(n == self.model or n.startswith(f"{self.model}:") for n in names)

    def chat(self, system: str, messages: list[dict], max_tokens: int) -> Reply | None:
        try:
            r = httpx.post(
                f"{self.host}/api/chat",
                json={
                    "model": self.model,
                    "messages": [{"role": "system", "content": system}] + messages,
                    "stream": False,
                    "options": {"num_predict": max_tokens},
                },
                timeout=LOCAL_TIMEOUT,
            )
            r.raise_for_status()
            text = (r.json().get("message") or {}).get("content", "").strip()
        except Exception:
            log.exception("ollama call failed")
            return None
        return Reply(text, self.name, self.model) if text else None


# --------------------------------------------------------------------- gemini


class GeminiProvider:
    """Google's free tier. Get a key at aistudio.google.com — no card needed."""

    name = "gemini"
    needs_key = True
    BASE = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self, api_key: str, model: str = "") -> None:
        self.api_key = api_key
        self.model = model or DEFAULT_MODELS["gemini"]

    def available(self) -> bool:
        return bool(self.api_key)

    def chat(self, system: str, messages: list[dict], max_tokens: int) -> Reply | None:
        # Gemini calls the assistant "model" and keeps the system prompt apart.
        contents = [
            {
                "role": "model" if m["role"] == "assistant" else "user",
                "parts": [{"text": m["content"]}],
            }
            for m in messages
        ]
        try:
            r = httpx.post(
                f"{self.BASE}/{self.model}:generateContent",
                params={"key": self.api_key},
                json={
                    "systemInstruction": {"parts": [{"text": system}]},
                    "contents": contents,
                    "generationConfig": {"maxOutputTokens": max_tokens},
                },
                timeout=TIMEOUT,
            )
            if r.status_code == 429:
                log.warning("gemini: free-tier rate limit hit, skipping this one")
                return None
            r.raise_for_status()
            candidates = r.json().get("candidates") or []
            if not candidates:
                return None
            parts = candidates[0].get("content", {}).get("parts") or []
            text = "".join(p.get("text", "") for p in parts).strip()
        except Exception:
            log.exception("gemini call failed")
            return None
        return Reply(text, self.name, self.model) if text else None


# ----------------------------------------------------------------------- groq


class GroqProvider:
    """Groq's free tier — an OpenAI-shaped API. Key at console.groq.com."""

    name = "groq"
    needs_key = True
    URL = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(self, api_key: str, model: str = "") -> None:
        self.api_key = api_key
        self.model = model or DEFAULT_MODELS["groq"]

    def available(self) -> bool:
        return bool(self.api_key)

    def chat(self, system: str, messages: list[dict], max_tokens: int) -> Reply | None:
        try:
            r = httpx.post(
                self.URL,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": [{"role": "system", "content": system}] + messages,
                    "max_tokens": max_tokens,
                },
                timeout=TIMEOUT,
            )
            if r.status_code == 429:
                log.warning("groq: free-tier rate limit hit, skipping this one")
                return None
            r.raise_for_status()
            choices = r.json().get("choices") or []
            text = choices[0]["message"]["content"].strip() if choices else ""
        except Exception:
            log.exception("groq call failed")
            return None
        return Reply(text, self.name, self.model) if text else None


# ------------------------------------------------------------------ anthropic


class AnthropicProvider:
    """Claude. The only paid option here, and the strongest."""

    name = "anthropic"
    needs_key = True

    def __init__(self, api_key: str, model: str = "") -> None:
        self.api_key = api_key
        self.model = model or DEFAULT_MODELS["anthropic"]
        self._client = None
        if api_key:
            try:
                from anthropic import Anthropic

                self._client = Anthropic(api_key=api_key)
            except Exception:
                log.exception("could not start the Anthropic client")

    def available(self) -> bool:
        return self._client is not None

    def chat(self, system: str, messages: list[dict], max_tokens: int) -> Reply | None:
        if not self._client:
            return None
        import anthropic

        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                # Grounded explanation of state we hand it, not deep reasoning —
                # low effort keeps the chat quick and the cost down.
                thinking={"type": "adaptive"},
                output_config={"effort": "low"},
                messages=messages,
            )
        except anthropic.AuthenticationError:
            log.warning("anthropic: the API key was rejected")
            return None
        except anthropic.RateLimitError:
            log.warning("anthropic: rate limited, skipping this one")
            return None
        except Exception:
            log.exception("anthropic call failed")
            return None

        if response.stop_reason == "refusal":
            return Reply("I would rather not answer that one.", self.name, self.model)
        text = "\n".join(b.text for b in response.content if getattr(b, "type", "") == "text").strip()
        return Reply(text, self.name, self.model) if text else None


# ---------------------------------------------------------------------- build


BUILDERS = {
    "ollama": lambda keys, model: OllamaProvider(model),
    "gemini": lambda keys, model: GeminiProvider(keys.get("gemini", ""), model),
    "groq": lambda keys, model: GroqProvider(keys.get("groq", ""), model),
    "anthropic": lambda keys, model: AnthropicProvider(keys.get("anthropic", ""), model),
}


def build(preference: str, keys: dict[str, str], model: str = ""):
    """Pick a provider.

    ``preference`` names one directly, or is "auto" to take the first that can
    actually answer. Auto tries the free options before the paid one, so nobody
    is billed by accident for a setting they did not choose.
    """
    if preference and preference != "auto":
        builder = BUILDERS.get(preference)
        if builder is None:
            raise ProviderError(
                f"unknown mentor provider {preference!r}; "
                f"expected one of: auto, {', '.join(BUILDERS)}"
            )
        provider = builder(keys, model)
        if not provider.available():
            log.warning("mentor provider %r is configured but not reachable", preference)
        return provider

    for name in (*FREE, "anthropic"):
        # A named model belongs to whichever provider was named, so under auto
        # every provider gets its own default instead.
        provider = BUILDERS[name](keys, "")
        if provider.available():
            log.info("mentor using %s (%s)", provider.name, provider.model)
            return provider
    return None
