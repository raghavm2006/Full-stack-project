from datetime import datetime, timezone
from sqlalchemy.dialects.mysql import LONGTEXT

from app.extensions import db


class Email(db.Model):
    """
    One synced Gmail message plus all ML/AI-derived fields.

    gmail_message_id is unique PER USER (a user can only have one row for a
    given Gmail message), which is what rule #13 (avoid duplicate storage)
    and rule #17 (never expose one user's mail to another) both rely on.
    """

    __tablename__ = "emails"
    __table_args__ = (
        db.UniqueConstraint(
            "user_id", "gmail_message_id", name="uq_user_gmail_message"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)

    # --- Gmail identifiers ---
    gmail_message_id = db.Column(db.String(64), nullable=False, index=True)
    thread_id = db.Column(db.String(64), nullable=False, index=True)

    # --- Raw email fields ---
    sender = db.Column(db.String(320), nullable=False)
    # To headers can contain many recipients, not just one address.
    receiver = db.Column(db.Text().with_variant(LONGTEXT(), "mysql"), nullable=True)
    subject = db.Column(db.String(998), nullable=True)  # RFC 2822 max header length
    body = db.Column(db.Text().with_variant(LONGTEXT(), "mysql"), nullable=True)
    timestamp = db.Column(db.DateTime, nullable=False, index=True)

    # --- Traditional ML: categorization (Phase 7) ---
    category = db.Column(db.String(32), nullable=True, index=True)
    category_confidence = db.Column(db.Float, nullable=True)

    # --- Traditional ML: priority (Phase 7) ---
    priority = db.Column(db.String(16), nullable=True, index=True)  # HIGH / MEDIUM / LOW
    priority_confidence = db.Column(db.Float, nullable=True)

    # --- Traditional ML: spam (Phase 7) ---
    spam_label = db.Column(db.Boolean, nullable=True, index=True)
    spam_probability = db.Column(db.Float, nullable=True)

    # --- AI / NLP (Phase 8) ---
    summary = db.Column(db.Text, nullable=True)

    # --- Smart replies (Phase 9) ---
    # smart_replies is a JSON-encoded list of short reply strings (decoded
    # via the `fromjson` Jinja filter in templates / json.loads elsewhere).
    # smart_reply_source records how they were produced ("llm" or
    # "template") so it's visible which path generated them.
    smart_replies = db.Column(db.Text, nullable=True)
    smart_reply_source = db.Column(db.String(16), nullable=True)

    # --- Follow-up detection (Phase 10) ---
    # True if this (received, non-spam) email looks like it needs a
    # response and no later message from the user exists in the same
    # thread. Recomputed in batch by app/blueprints/followup/service.py,
    # not per-email during sync — see that module's docstring for why.
    needs_follow_up = db.Column(db.Boolean, default=False, nullable=False)

    # --- Duplicate detection (Phase 10) ---
    # content_hash is a hash of normalized subject+body, set once per
    # email (cheap, no DB needed). is_duplicate/duplicate_of_email_id are
    # set in batch by app/blueprints/deduplication/service.py, which
    # compares every email against every other email with the same hash.
    content_hash = db.Column(db.String(64), nullable=True, index=True)
    is_duplicate = db.Column(db.Boolean, default=False, nullable=False)
    duplicate_of_email_id = db.Column(
        db.Integer, db.ForeignKey("emails.id"), nullable=True
    )

    # --- Mailbox state ---
    is_read = db.Column(db.Boolean, default=False, nullable=False)

    # --- Internal staging field (Phase 3 -> Phase 4 bridge) ---
    # The raw Gmail API message resource (JSON-encoded), captured during
    # sync so the Phase 4 parser can decode the MIME body from it without
    # re-fetching from Gmail. Not part of the spec's required fields list;
    # it exists purely as a handoff between sync and parsing.
    raw_payload = db.Column(db.Text().with_variant(LONGTEXT(), "mysql"), nullable=True)

    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    actions = db.relationship(
        "Action", backref="email", lazy=True, cascade="all, delete-orphan"
    )
    reminders = db.relationship(
        "Reminder", backref="email", lazy=True, cascade="all, delete-orphan"
    )
    feedback_entries = db.relationship(
        "UserFeedback", backref="email", lazy=True, cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Email id={self.id} gmail_message_id={self.gmail_message_id}>"
