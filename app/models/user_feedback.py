from datetime import datetime, timezone

from app.extensions import db


class UserFeedback(db.Model):
    """
    A user correction to a category or priority prediction (rule #11/#20 —
    every major feature must be independently testable, and this table is
    what lets us evaluate/retrain models later using real corrections).
    """

    __tablename__ = "user_feedback"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    email_id = db.Column(db.Integer, db.ForeignKey("emails.id"), nullable=False, index=True)

    feedback_type = db.Column(db.String(16), nullable=False)  # "category" or "priority"
    original_value = db.Column(db.String(32), nullable=True)
    corrected_value = db.Column(db.String(32), nullable=False)
    apply_to_sender = db.Column(db.Boolean, default=False, nullable=False)

    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    def __repr__(self):
        return f"<UserFeedback id={self.id} type={self.feedback_type}>"
