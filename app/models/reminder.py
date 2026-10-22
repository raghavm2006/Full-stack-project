from datetime import datetime, timezone

from app.extensions import db


class Reminder(db.Model):
    """A deadline/reminder extracted from an email (Phase 8: deadline detection)."""

    __tablename__ = "reminders"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    email_id = db.Column(db.Integer, db.ForeignKey("emails.id"), nullable=False, index=True)

    description = db.Column(db.String(512), nullable=True)
    deadline_at = db.Column(db.DateTime, nullable=False, index=True)
    is_dismissed = db.Column(db.Boolean, default=False, nullable=False)

    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    def __repr__(self):
        return f"<Reminder id={self.id} deadline_at={self.deadline_at}>"
