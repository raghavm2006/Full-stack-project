"""
Sync logic: pulls message metadata + body from Gmail and stores one Email
row per Gmail message, refreshing read status for messages already stored for this user
(gmail_message_id dedup, rule #13).

extract_basic_fields() only reads header fields Gmail itself already
parses out (From/To/Subject) plus internalDate/labelIds. The MIME body
itself is decoded by app.blueprints.emails.parser (Phase 4) — sync_service
calls that module rather than duplicating parsing logic here, but the
raw message JSON is still kept in Email.raw_payload in case the parser
needs to be re-run later (e.g. after a parsing bug fix) without re-fetching
from Gmail.

Phase 7 adds one more step per email: classify_email() sets category/
priority/spam fields using whatever production models exist. If none are
trained yet, classify_email() just leaves those fields None (exactly the
pre-Phase-7 behavior) — sync never fails because of missing models.

Phase 8 adds another: process_email_nlp() sets a summary and creates any
Action/Reminder rows the email's text implies (action items, deadlines).

Phase 9 adds smart replies: generate_smart_replies() sets suggested
quick-reply text (LLM-generated when ANTHROPIC_API_KEY is configured,
template-based otherwise/on failure). Skipped for emails classify_email()
already flagged as spam — nobody needs reply suggestions for spam, and
skipping avoids an LLM call (and its cost/latency) on every one.

Phase 10 adds two more steps, but run ONCE per sync rather than per
email like the ones above: detect_duplicate_emails() and
detect_pending_follow_ups() both need to compare an email against
OTHER emails (including ones from this very sync batch), so they only
give correct answers after every new email is already committed. Both
run after the main per-message loop and its commit, not inside it.
"""

import json
from datetime import datetime, timezone

from app.blueprints.deduplication.service import detect_duplicate_emails
from app.blueprints.emails.parser import parse_email_body
from app.blueprints.followup.service import detect_pending_follow_ups
from app.blueprints.gmail.gmail_client import get_full_message, list_message_ids
from app.blueprints.ml_inference.classifier import classify_email
from app.blueprints.nlp_features.service import process_email_nlp
from app.blueprints.smart_replies.service import generate_smart_replies
from app.extensions import db
from app.models import Email


def _extract_header(headers, name):
    for header in headers:
        if header.get("name", "").lower() == name.lower():
            return header.get("value")
    return None


def extract_basic_fields(message: dict) -> dict:
    headers = message.get("payload", {}).get("headers", [])
    internal_date_ms = int(message.get("internalDate", 0))

    return {
        "sender": _extract_header(headers, "From") or "unknown",
        "receiver": _extract_header(headers, "To"),
        "subject": _extract_header(headers, "Subject"),
        "timestamp": datetime.fromtimestamp(internal_date_ms / 1000, tz=timezone.utc)
        if internal_date_ms
        else datetime.now(timezone.utc),
        "is_read": "UNREAD" not in message.get("labelIds", []),
    }


def sync_user_emails(user, service, max_results=25, page_token=None) -> dict:
    """
    Fetches up to `max_results` recent message ids for `user`, stores any
    not already present, and updates user.last_synced_at.

    Returns a summary dict — useful both as an API response and for tests.
    """
    message_ids, next_page_token = list_message_ids(
        service, max_results=max_results, page_token=page_token
    )

    existing_emails = {
        row.gmail_message_id: row
        for row in Email.query.filter(
            Email.user_id == user.id, Email.gmail_message_id.in_(message_ids)
        ).all()
    }

    synced = 0
    for message_id in message_ids:
        if message_id in existing_emails:
            full_message = get_full_message(service, message_id)
            existing_emails[message_id].is_read = "UNREAD" not in full_message.get("labelIds", [])
            continue

        full_message = get_full_message(service, message_id)
        fields = extract_basic_fields(full_message)
        body = parse_email_body(full_message)

        email = Email(
            user_id=user.id,
            gmail_message_id=message_id,
            thread_id=full_message.get("threadId", message_id),
            sender=fields["sender"],
            receiver=fields["receiver"],
            subject=fields["subject"],
            body=body,
            timestamp=fields["timestamp"],
            is_read=fields["is_read"],
            raw_payload=json.dumps(full_message),
        )
        classify_email(email)  # sets category/priority/spam if models are trained
        process_email_nlp(email)  # sets summary + creates action/deadline rows
        if not email.spam_label:  # don't bother drafting replies to spam
            generate_smart_replies(email)
        db.session.add(email)
        synced += 1

    user.last_synced_at = datetime.now(timezone.utc)
    db.session.commit()

    # Both of these scan the user's whole mailbox, so they run once here
    # rather than per-message above (see module docstring).
    duplicate_result = detect_duplicate_emails(user.id)
    follow_up_result = detect_pending_follow_ups(user.id)
    from app.blueprints.commitments.service import scan_commitments
    scan_commitments(user)

    result = {
        "total_fetched": len(message_ids),
        "synced": synced,
        "skipped_existing": len(message_ids) - synced,
        "duplicates_found": duplicate_result["duplicates_found"],
        "needs_follow_up": follow_up_result["flagged"],
    }
    if next_page_token:
        result["next_page_token"] = next_page_token
    return result
