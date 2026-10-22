from datetime import datetime, timezone

from app.extensions import db


class User(db.Model):
    """A registered EmailOrbit user, tied to one Google account."""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    google_id = db.Column(db.String(255), unique=True, nullable=False, index=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    name = db.Column(db.String(255), nullable=True)
    profile_picture_url = db.Column(db.String(512), nullable=True)

    # OAuth tokens are stored encrypted at rest starting Phase 2.
    # Columns are declared now so the schema doesn't need to change later.
    oauth_token_encrypted = db.Column(db.Text, nullable=True)
    oauth_refresh_token_encrypted = db.Column(db.Text, nullable=True)
    oauth_token_expiry = db.Column(db.DateTime, nullable=True)

    # True once the user has completed the SEPARATE, incremental consent
    # for Gmail access (Phase 3) on top of the Phase 2 login scopes.
    gmail_scope_granted = db.Column(db.Boolean, default=False, nullable=False)
    gmail_send_granted = db.Column(db.Boolean, default=False, nullable=False)
    gmail_drafts_granted = db.Column(db.Boolean, default=False, nullable=False)

    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    last_synced_at = db.Column(db.DateTime, nullable=True)

    emails = db.relationship(
        "Email", backref="user", lazy=True, cascade="all, delete-orphan"
    )
    actions = db.relationship(
        "Action", backref="user", lazy=True, cascade="all, delete-orphan"
    )
    reminders = db.relationship(
        "Reminder", backref="user", lazy=True, cascade="all, delete-orphan"
    )
    feedback_entries = db.relationship(
        "UserFeedback", backref="user", lazy=True, cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<User id={self.id} email={self.email}>"
