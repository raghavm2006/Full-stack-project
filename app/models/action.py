from datetime import datetime, timezone

from app.extensions import db


class Action(db.Model):
    """An action item extracted from an email (Phase 8: action extraction)."""

    __tablename__ = "actions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    email_id = db.Column(db.Integer, db.ForeignKey("emails.id"), nullable=False, index=True)

    description = db.Column(db.Text, nullable=False)
    is_completed = db.Column(db.Boolean, default=False, nullable=False)

    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    def __repr__(self):
        return f"<Action id={self.id} email_id={self.email_id}>"
