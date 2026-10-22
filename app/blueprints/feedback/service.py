"""Explicit, per-user sender rules; no training inside web requests."""
from email.utils import parseaddr

from app.models import Email, UserFeedback


def apply_feedback_rules(email):
    if not getattr(email, "user_id", None):
        return
    sender = parseaddr(email.sender or "")[1].lower()
    if not sender:
        return
    rules = (UserFeedback.query.join(Email, UserFeedback.email_id == Email.id)
             .filter(UserFeedback.user_id == email.user_id,
                     Email.user_id == email.user_id)
             .order_by(UserFeedback.id.asc()).all())
    latest = {}
    for rule in rules:
        if (parseaddr(rule.email.sender or "")[1].lower() == sender
                and rule.feedback_type in ("category", "priority")):
            latest[rule.feedback_type] = rule
    for rule in latest.values():
        if rule.apply_to_sender:
            setattr(email, rule.feedback_type, rule.corrected_value)
            setattr(email, rule.feedback_type + "_confidence", None)
