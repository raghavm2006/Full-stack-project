"""
Phase 10: exact-content duplicate detection.

A batch operation over a user's whole mailbox rather than a per-email
check during sync (like classify_email()/process_email_nlp()) —
detecting a duplicate inherently means comparing an email against OTHER
emails, including ones synced in the very same batch, which only gives
correct results once every email in that batch is committed. sync_
service.py calls this once at the end of each sync, after its own
commit, rather than inside the per-message loop.
"""

from app.blueprints.deduplication.hashing import compute_content_hash
from app.extensions import db
from app.models import Email


def detect_duplicate_emails(user_id) -> dict:
    """
    Recomputes content_hash for any email missing one, groups the user's
    emails by that hash, and flags every email except the earliest
    (by timestamp) in each group as a duplicate — is_duplicate=True,
    duplicate_of_email_id pointing at that earliest email. Also clears
    the flag on any email that no longer belongs to a duplicate group
    (e.g. its only "duplicate" was actually a different, now-hash-
    mismatched email). Commits.
    """
    emails = Email.query.filter_by(user_id=user_id).order_by(Email.timestamp.asc()).all()

    groups = {}
    for email in emails:
        if not email.content_hash:
            email.content_hash = compute_content_hash(email.subject, email.body)
        if not email.content_hash:
            continue
        groups.setdefault(email.content_hash, []).append(email)

    duplicates_found = 0
    for group in groups.values():
        original, *rest = group  # already ordered oldest-first
        original.is_duplicate = False
        original.duplicate_of_email_id = None

        for email in rest:
            email.is_duplicate = True
            email.duplicate_of_email_id = original.id
            duplicates_found += 1

    db.session.commit()

    return {"emails_scanned": len(emails), "duplicates_found": duplicates_found}
