"""
Bridges detector.py's pure signals to the Email table.

Batch-oriented like deduplication/service.py, not per-email like
classify_email()/process_email_nlp(): whether an email still "needs
follow-up" depends on whether the user later replied ANYWHERE in the
same thread, which can only be answered by looking at the user's whole
mailbox at once. gmail/sync_service.py calls this once at the end of
every sync (after all new emails for that sync are committed), and it's
also exposed as its own route for on-demand rechecking.
"""

from email.utils import parseaddr

from app.blueprints.followup.detector import is_stale, needs_response
from app.extensions import db
from app.models import Email, User


def detect_pending_follow_ups(user_id, reference_time=None, threshold_days: int = 2) -> dict:
    """
    Recomputes `needs_follow_up` for every email belonging to `user_id`.
    An email is flagged when: it wasn't sent by the user themselves, it
    isn't spam, its content suggests it needs a response
    (detector.needs_response), it's older than `threshold_days`
    (detector.is_stale), AND no message from the user in the same
    thread came after it. Flags are cleared (set back to False) the same
    way, so an email correctly un-flags itself once the user does reply.
    Commits.
    """
    user = db.session.get(User, user_id)
    if user is None:
        return {"flagged": 0, "cleared": 0, "emails_scanned": 0}

    emails = Email.query.filter_by(user_id=user_id).order_by(Email.timestamp.asc()).all()
    user_email = (user.email or "").lower()

    # Latest timestamp at which the user themselves sent a message, per
    # thread — used to tell "nobody has replied yet" apart from "the
    # user already handled it".
    last_user_reply_at = {}
    for email in emails:
        if email.sender and parseaddr(email.sender)[1].lower() == user_email:
            existing = last_user_reply_at.get(email.thread_id)
            if existing is None or email.timestamp > existing:
                last_user_reply_at[email.thread_id] = email.timestamp

    flagged = 0
    cleared = 0

    for email in emails:
        is_own_message = bool(email.sender) and parseaddr(email.sender)[1].lower() == user_email
        reply_exists = (
            email.thread_id in last_user_reply_at
            and last_user_reply_at[email.thread_id] > email.timestamp
        )

        should_flag = (
            not is_own_message
            and not email.spam_label
            and needs_response(email)
            and is_stale(email, reference_time=reference_time, threshold_days=threshold_days)
            and not reply_exists
        )

        if should_flag and not email.needs_follow_up:
            flagged += 1
        elif not should_flag and email.needs_follow_up:
            cleared += 1

        email.needs_follow_up = should_flag

    db.session.commit()

    return {"flagged": flagged, "cleared": cleared, "emails_scanned": len(emails)}
