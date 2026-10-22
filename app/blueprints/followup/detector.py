"""
Phase 10: pure signal functions for follow-up detection.

Deliberately split from service.py: whether an email "needs follow-up"
also depends on whether the user has already replied somewhere else in
the same thread, which requires comparing against sibling emails in the
database — these two functions only need the one email object, so they
stay easy to unit test in isolation.
"""

import re
from app.utils.email_text import current_message_text
from datetime import datetime, timedelta, timezone

_QUESTION_PATTERN = re.compile(r"\?")


def needs_response(email) -> bool:
    """
    True if the email's content suggests someone is waiting on a reply:
    it contains a question, has an extracted action item (Phase 8), or
    was flagged HIGH/MEDIUM priority (Phase 7).
    """
    text = f"{email.subject or ''}\n{current_message_text(email.body)}"
    if _QUESTION_PATTERN.search(text):
        return True
    if getattr(email, "actions", None):
        return True
    if getattr(email, "priority", None) in ("HIGH", "MEDIUM"):
        return True
    return False


def is_stale(email, reference_time: datetime = None, threshold_days: int = 2) -> bool:
    """
    True if the email is older than `threshold_days` relative to
    `reference_time` (defaults to now). `reference_time` is an
    injectable parameter — never `datetime.now()` baked in — so tests
    are deterministic (same pattern as Phase 8's deadline_extractor).
    """
    if email.timestamp is None:
        return False

    reference_time = reference_time or datetime.now(timezone.utc)
    if reference_time.tzinfo is None:
        reference_time = reference_time.replace(tzinfo=timezone.utc)
    timestamp = email.timestamp
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)

    return reference_time - timestamp > timedelta(days=threshold_days)
