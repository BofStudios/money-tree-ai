"""Reading what a language model sends back, and how long a provider wants us to wait.

Two ideas carried over from Hustle HQ's agent runtime (12.0), rewritten in
Python:

  parse_action  a model asked for {"action": ..., "args": ...} JSON rarely sends
                only that: there is a code fence, a sentence before it, a
                <think> block, a trailing comma, a raw newline in a string.
                This finds the first balanced object and reads it. It never
                raises: anything it cannot read is None, and the caller then
                does nothing (the bot keeps its plain rules).
  wait_from     a rate limit says how long to wait in different places: the
                Retry-After header, x-ratelimit-reset-*, "try again in 7m12s",
                "retryDelay": "30s". The longest of them wins; a daily quota
                waits until midnight UTC (at most 12 hours).
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timedelta, timezone

_THINK = re.compile(r"<think>.*?</think>", re.S | re.I)
_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S | re.I)
_TRAILING = re.compile(r",\s*([}\]])")
_DUR = re.compile(r"(\d+(?:\.\d+)?)\s*(ms|h|m|s)")
_DAILY = re.compile(r"per[ _-]?day|PerDay|daily|RPD|TPD|quota.*day", re.I)


def _first_object(s: str) -> str | None:
    start = s.find("{")
    if start < 0:
        return None
    depth, in_str, esc = 0, False, False
    for i in range(start, len(s)):
        c = s[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return s[start:i + 1]
    return None


def _load(chunk: str):
    try:
        return json.loads(chunk)
    except ValueError:
        pass
    fixed = _TRAILING.sub(r"\1", chunk)
    fixed = "".join("\\n" if ch == "\n" else (" " if ord(ch) < 32 else ch) for ch in fixed)
    try:
        return json.loads(fixed)
    except ValueError:
        return None


def parse_action(text) -> dict | None:
    """{"thought", "action", "args"} from a model's answer, or None."""
    try:
        s = _THINK.sub("", str(text or "")).strip()
        fence = _FENCE.search(s)
        if fence:
            s = fence.group(1).strip()
        chunk = _first_object(s)
        obj = _load(chunk) if chunk else None
        if not isinstance(obj, dict):
            return None
        action = obj.get("action") or obj.get("tool") or obj.get("name")
        if not isinstance(action, str) or not action.strip():
            return None
        args = obj.get("args") or obj.get("arguments") or obj.get("parameters") or obj.get("input") or {}
        return {"thought": str(obj.get("thought") or obj.get("reasoning") or ""),
                "action": action.strip(), "args": args if isinstance(args, dict) else {}}
    except Exception:
        return None


def parse_duration(value) -> float | None:
    """'1m30.5s', '2.5s', '120ms', '7m12s', '1h2m' or '30' -> seconds."""
    if value is None:
        return None
    s = str(value).strip()
    if re.fullmatch(r"\d+(\.\d+)?", s):
        return float(s)
    parts = _DUR.findall(s)
    if not parts:
        return None
    return sum(float(n) * {"ms": 0.001, "s": 1, "m": 60, "h": 3600}[u] for n, u in parts)


def _until_midnight_utc(now: float) -> float:
    t = datetime.fromtimestamp(now, timezone.utc)
    nxt = (t + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return (nxt - t).total_seconds()


def wait_from(headers=None, body: str = "", default: float = 90.0, now: float | None = None) -> tuple[float, bool]:
    """(seconds to wait, is it a daily quota) for a 429 answer."""
    h = {str(k).lower(): v for k, v in dict(headers or {}).items()}
    body = body or ""
    found = [x for x in (
        parse_duration(h.get("retry-after")),
        parse_duration(h.get("x-ratelimit-reset-requests")),
        parse_duration(h.get("x-ratelimit-reset-tokens")),
        parse_duration((re.search(r"try again in\s+([\dhms.]+)", body, re.I) or [None, None])[1]),
        parse_duration((re.search(r'"retryDelay"\s*:\s*"([\d.]+s)"', body) or [None, None])[1]),
    ) if x is not None and x > 0]
    wait = max(found) if found else default
    daily = bool(_DAILY.search(body))
    if daily:
        wait = max(wait, min(_until_midnight_utc(now if now is not None else time.time()), 12 * 3600))
    return min(wait, 12 * 3600), daily
