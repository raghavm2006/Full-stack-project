"""
Phase 9: deterministic template-based smart replies.

This is the fallback path used whenever the LLM in llm_client.py isn't
configured or fails (see service.py) — same rationale as Phase 8's rule-
based action extractor: transparent, needs no training data or network
call, and always available, at the cost of sounding more generic than an
LLM-written reply.
"""

import re

_QUESTION_PATTERN = re.compile(r"\?")

_TEMPLATES = {
    "acknowledge": "Thanks for the note — I've seen this and will follow up shortly.",
    "confirm": "Sounds good, confirmed on my end.",
    "request_info": "Thanks for reaching out — could you share a bit more detail on this?",
    "will_review": "Got it, I'll review this and get back to you.",
    "deadline_ack": "Understood — I'll make sure this is taken care of by the deadline.",
    "decline_busy": "Thanks for thinking of me — I'm tied up right now, but I'll circle back when I can.",
}


def generate_template_replies(email, max_replies: int = 3) -> list:
    """
    Scores a fixed pool of reply templates against signals already
    computed by earlier phases (whether the email has a question, action
    items, a detected deadline, or HIGH priority) and returns the top
    `max_replies` distinct templates, rendered as plain text, highest-
    scoring first.
    """
    text = f"{email.subject or ''}\n{email.body or ''}"
    has_question = bool(_QUESTION_PATTERN.search(text))
    has_actions = bool(getattr(email, "actions", None))
    has_deadline = bool(getattr(email, "reminders", None))
    is_high_priority = getattr(email, "priority", None) == "HIGH"

    scored = [("acknowledge", 1.0)]  # always a safe baseline option

    if has_question:
        scored.append(("request_info", 2.0))

    if has_deadline:
        scored.append(("deadline_ack", 2.5))
    elif has_actions:
        scored.append(("will_review", 1.8))

    if is_high_priority and not has_deadline:
        scored.append(("confirm", 1.5))

    if not has_question and not has_actions and not is_high_priority:
        scored.append(("decline_busy", 0.5))

    best_by_key = {}
    for key, score in scored:
        if key not in best_by_key or score > best_by_key[key]:
            best_by_key[key] = score

    ranked_keys = sorted(best_by_key, key=lambda k: best_by_key[k], reverse=True)
    return [_TEMPLATES[key] for key in ranked_keys[:max_replies]]
