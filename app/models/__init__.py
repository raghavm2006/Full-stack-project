"""
Import all models here so that Flask-Migrate / SQLAlchemy metadata sees
every table when `flask db migrate` or `db.create_all()` runs.
"""

from app.models.user import User
from app.models.email import Email
from app.models.action import Action
from app.models.reminder import Reminder
from app.models.user_feedback import UserFeedback
from app.models.commitment import Commitment
from app.models.outgoing_message import OutgoingMessage

__all__ = ["User", "Email", "Action", "Reminder", "UserFeedback", "Commitment", "OutgoingMessage"]
