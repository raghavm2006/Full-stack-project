"""
Phase 9: LLM-backed smart reply generation (the Anthropic API), with a
deterministic template fallback in templates.py used whenever this
module can't produce a result.

This is a live network call, not a local model — unlike Phases 6-7's
scikit-learn models, there's no local artifact to load and nothing is
ever trained here. Every failure mode (no API key configured, network
error, rate limit, malformed response) is normalized into a single
LLMUnavailableError so callers (service.py) can catch one exception type
and fall back to templates rather than let a flaky third-party API break
Gmail sync.
"""

import json
import os

_CLIENT = None


class LLMUnavailableError(Exception):
    """
    Raised whenever an LLM reply couldn't be produced for any reason —
    missing/invalid API key, request failure, or an unparseable
    response. Callers should catch this and fall back to
    templates.generate_template_replies(), never let it surface as a
    500 or break email sync.
    """


def _get_client():
    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise LLMUnavailableError("ANTHROPIC_API_KEY is not set")

    try:
        import anthropic
    except ImportError as exc:
        raise LLMUnavailableError("the 'anthropic' package is not installed") from exc

    _CLIENT = anthropic.Anthropic(api_key=api_key)
    return _CLIENT


def clear_cache():
    """Test hook — forces the next call to rebuild the client (e.g. after
    monkeypatching the API key or the anthropic import)."""
    global _CLIENT
    _CLIENT = None


_PROMPT_TEMPLATE = """You are drafting quick reply suggestions for a personal email inbox app.

Email details:
From: {sender}
Subject: {subject}
Body:
{body}

Write {max_replies} short, distinct reply suggestions (max ~25 words each) the recipient could send back, in a professional and friendly tone. Respond with ONLY a JSON array of strings and nothing else, e.g. ["reply one", "reply two"]."""


def generate_llm_replies(subject, body, sender, max_replies: int = 3, model=None) -> list:
    """
    Returns up to `max_replies` short reply strings from the configured
    LLM. Always raises LLMUnavailableError (never a raw requests/SDK
    exception) on any failure — missing key, network error, rate limit,
    or a response that isn't a clean JSON array of strings.
    """
    client = _get_client()
    model = model or os.environ.get("SMART_REPLY_MODEL", "claude-3-5-haiku-latest")

    prompt = _PROMPT_TEMPLATE.format(
        sender=sender or "unknown",
        subject=subject or "(no subject)",
        body=(body or "")[:4000],  # keep prompts small — cheaper and faster
        max_replies=max_replies,
    )

    try:
        response = client.messages.create(
            model=model,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        raw_text = response.content[0].text
    except LLMUnavailableError:
        raise
    except Exception as exc:  # noqa: BLE001 - any API/network failure must fall back, never crash sync
        raise LLMUnavailableError(f"LLM request failed: {exc}") from exc

    replies = _parse_reply_list(raw_text)
    if not replies:
        raise LLMUnavailableError("LLM response did not contain a usable reply list")

    return replies[:max_replies]


def _parse_reply_list(raw_text: str) -> list:
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if "\n" in cleaned:
            cleaned = cleaned.split("\n", 1)[1]

    try:
        parsed = json.loads(cleaned)
    except (ValueError, TypeError):
        return []

    if not isinstance(parsed, list):
        return []

    return [str(item).strip() for item in parsed if str(item).strip()]
