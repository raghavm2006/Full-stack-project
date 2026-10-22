"""JSON shaping for Email rows — kept separate from routes.py for reuse in Phase 5's UI."""

import json

SNIPPET_LENGTH = 160


def to_summary_dict(email) -> dict:
    """Compact shape for inbox list views — no full body, no raw_payload."""
    body = email.body or ""
    snippet = body[:SNIPPET_LENGTH] + ("…" if len(body) > SNIPPET_LENGTH else "")

    return {
        "id": email.id,
        "gmail_message_id": email.gmail_message_id,
        "thread_id": email.thread_id,
        "sender": email.sender,
        "subject": email.subject,
        "snippet": snippet,
        "timestamp": email.timestamp.isoformat(),
        "category": email.category,
        "category_confidence": email.category_confidence,
        "priority": email.priority,
        "priority_confidence": email.priority_confidence,
        "spam_label": email.spam_label,
        "is_read": email.is_read,
        "needs_follow_up": email.needs_follow_up,
        "is_duplicate": email.is_duplicate,
    }


def to_detail_dict(email) -> dict:
    """Full shape for a single email view — everything except raw_payload."""
    return {
        "id": email.id,
        "gmail_message_id": email.gmail_message_id,
        "thread_id": email.thread_id,
        "sender": email.sender,
        "receiver": email.receiver,
        "subject": email.subject,
        "body": email.body,
        "timestamp": email.timestamp.isoformat(),
        "category": email.category,
        "category_confidence": email.category_confidence,
        "priority": email.priority,
        "priority_confidence": email.priority_confidence,
        "spam_label": email.spam_label,
        "spam_probability": email.spam_probability,
        "summary": email.summary,
        "is_read": email.is_read,
        "actions": [
            {"id": a.id, "description": a.description, "is_completed": a.is_completed}
            for a in email.actions
        ],
        "reminders": [
            {
                "id": r.id,
                "description": r.description,
                "deadline_at": r.deadline_at.isoformat(),
                "is_dismissed": r.is_dismissed,
            }
            for r in email.reminders
        ],
        "smart_replies": json.loads(email.smart_replies) if email.smart_replies else [],
        "smart_reply_source": email.smart_reply_source,
        "needs_follow_up": email.needs_follow_up,
        "is_duplicate": email.is_duplicate,
        "duplicate_of_email_id": email.duplicate_of_email_id,
    }
