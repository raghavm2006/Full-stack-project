from datetime import datetime, timezone
from app.extensions import db


class Commitment(db.Model):
    __tablename__ = "commitments"
    __table_args__ = (db.UniqueConstraint("user_id", "source_email_id", "fingerprint",
                                         name="uq_commitment_source"),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    source_email_id = db.Column(db.Integer, db.ForeignKey("emails.id"), nullable=False)
    thread_id = db.Column(db.String(64), nullable=False, index=True)
    fingerprint = db.Column(db.String(64), nullable=False)
    description = db.Column(db.Text, nullable=False)
    evidence = db.Column(db.Text, nullable=False)
    responsible = db.Column(db.String(16), nullable=False)  # me / other
    deadline_at = db.Column(db.DateTime, nullable=True)
    deadline_note = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(16), nullable=False, default="proposed")
    is_change = db.Column(db.Boolean, nullable=False, default=False)
    supersedes_id = db.Column(db.Integer, db.ForeignKey("commitments.id"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    source_email = db.relationship("Email", foreign_keys=[source_email_id])
