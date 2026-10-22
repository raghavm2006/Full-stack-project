from datetime import datetime, timezone
from app.extensions import db
from sqlalchemy.dialects.mysql import LONGTEXT


class OutgoingMessage(db.Model):
    """Reviewed outgoing MIME and a durable guard against repeated submissions."""
    __tablename__ = "outgoing_messages"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    reply_email_id = db.Column(db.Integer, db.ForeignKey("emails.id"), nullable=True)
    recipients = db.Column(db.Text, nullable=False)
    cc = db.Column(db.Text, nullable=False, default="")
    bcc = db.Column(db.Text, nullable=False, default="")
    subject = db.Column(db.String(998), nullable=False)
    body = db.Column(db.Text().with_variant(LONGTEXT(), "mysql"), nullable=False)
    raw_message = db.Column(db.Text().with_variant(LONGTEXT(), "mysql"), nullable=False)
    attachments = db.Column(db.Text, nullable=False, default="[]")
    thread_id = db.Column(db.String(64), nullable=True)
    status = db.Column(db.String(20), nullable=False, default="prepared")
    gmail_message_id = db.Column(db.String(64), nullable=True)
    gmail_draft_id = db.Column(db.String(64), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
