"""
Bridges the pure text-processing functions (summarizer.py/
action_extractor.py/deadline_extractor.py — no DB, no Flask) to the
Email/Action/Reminder models. Same split as Phase 7's ml_inference
blueprint: predictors/extractors stay unit-testable in isolation, and
this module is the only place that touches SQLAlchemy.
"""

import json
from datetime import timezone
from email.utils import parsedate_to_datetime

from app.utils.email_text import current_message_text
from app.blueprints.nlp_features.action_extractor import extract_action_items
from app.blueprints.nlp_features.deadline_extractor import extract_deadlines
from app.blueprints.nlp_features.summarizer import summarize_text
from app.models import Action, Reminder


def process_email_nlp(email) -> dict:
    """
    Mutates `email` in place: sets `summary`, and appends new Action/
    Reminder rows onto its `actions`/`reminders` relationships. SQLAlchemy
    fills in `email_id` (and `user_id`, since it's set explicitly here
    too) once `email` is flushed/committed, so this works whether `email`
    has already been added to the session or not. Does NOT commit —
    callers decide when (mirrors classify_email() in Phase 7).

    Only ever ADDS rows — call this once per email. Calling it again on
    an already-processed email (without first clearing its existing
    actions/reminders) would duplicate them, which is why both the sync
    loop and /nlp/process-all skip emails that already have a summary.
    """
    text = f"{email.subject or ''}\n{current_message_text(email.body)}"

    email.summary = summarize_text(text)

    action_descriptions = extract_action_items(text)
    for description in action_descriptions:
        email.actions.append(Action(user_id=email.user_id, description=description))

    reference_time = email.timestamp
    # Preserve the sender's explicit Date offset for relative phrases.
    try:
        payload = json.loads(email.raw_payload or "{}")
        headers = payload.get("payload", {}).get("headers", [])
        date_header = next(h["value"] for h in headers if h.get("name", "").lower() == "date")
        dated = parsedate_to_datetime(date_header)
        if dated.tzinfo is not None:
            reference_time = dated
    except (ValueError, TypeError, KeyError, StopIteration, AttributeError, OverflowError):
        pass
    deadlines = extract_deadlines(text, reference_time=reference_time)
    for deadline in deadlines:
        email.reminders.append(
            Reminder(
                user_id=email.user_id,
                description=deadline["description"],
                deadline_at=(deadline["deadline_at"].astimezone(timezone.utc)
                             if deadline["deadline_at"].tzinfo else deadline["deadline_at"]),
            )
        )

    return {
        "summary_set": bool(email.summary),
        "actions_found": len(action_descriptions),
        "deadlines_found": len(deadlines),
    }
