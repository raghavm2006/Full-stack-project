"""
Bridges llm_client.py (network call, may fail) and templates.py
(deterministic, always succeeds) to the Email model — the only module
in this blueprint that touches SQLAlchemy. Mirrors Phase 7/8's
classifier.py/service.py split.
"""

import json

from app.blueprints.smart_replies.llm_client import LLMUnavailableError, generate_llm_replies
from app.blueprints.smart_replies.templates import generate_template_replies


def generate_smart_replies(email, max_replies: int = 3) -> dict:
    """
    Mutates `email` in place: sets `smart_replies` (JSON-encoded list of
    strings) and `smart_reply_source` ("llm" or "template"). Tries the
    LLM first; falls back to templates on ANY LLMUnavailableError — no
    API key configured, a failed/rate-limited request, or a response
    that couldn't be parsed — so a misconfigured or unreachable API
    never breaks Gmail sync. Does NOT commit — caller's job.
    """
    try:
        replies = generate_llm_replies(
            subject=email.subject,
            body=email.body,
            sender=email.sender,
            max_replies=max_replies,
        )
        source = "llm"
    except LLMUnavailableError:
        replies = generate_template_replies(email, max_replies=max_replies)
        source = "template"

    email.smart_replies = json.dumps(replies)
    email.smart_reply_source = source

    return {"replies": replies, "source": source}
