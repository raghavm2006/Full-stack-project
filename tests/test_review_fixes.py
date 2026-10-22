"""Regressions for the project review's concrete failure cases."""
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest


@pytest.fixture
def app():
    from app import create_app
    from app.extensions import db

    application = create_app("testing")
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


def seed_email():
    from app.extensions import db
    from app.models import Email, User

    user = User(google_id="review", email="user@example.com")
    db.session.add(user)
    db.session.flush()
    email = Email(user_id=user.id, gmail_message_id="m1", thread_id="thread",
                  sender="other@example.com", subject="Question", body="Can you confirm?",
                  timestamp=datetime(2026, 1, 1, 12, tzinfo=timezone.utc))
    db.session.add(email)
    db.session.commit()
    return user, email


def authenticated_client(app, user):
    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = user.id
    return client


def test_display_name_reply_clears_follow_up(app):
    from app.extensions import db
    from app.models import Email
    from app.blueprints.followup.service import detect_pending_follow_ups

    user, email = seed_email()
    db.session.add(Email(user_id=user.id, gmail_message_id="reply", thread_id=email.thread_id,
                         sender="User Name <user@example.com>", body="Confirmed.",
                         timestamp=email.timestamp + timedelta(days=1)))
    db.session.commit()
    detect_pending_follow_ups(user.id, reference_time=email.timestamp + timedelta(days=5))
    assert email.needs_follow_up is False


def test_relative_deadline_uses_received_date(app):
    from app.blueprints.nlp_features.service import process_email_nlp

    _, email = seed_email()
    email.body = "Please send the report by tomorrow."
    process_email_nlp(email)
    assert len(email.reminders) == 1
    assert email.reminders[0].deadline_at.date() == email.timestamp.date() + timedelta(days=1)


@pytest.mark.parametrize("payload", [
    ["unexpected"], "unexpected", 42,
    {"feedback_type": "priority", "corrected_value": "BANANA"},
    {"feedback_type": "category", "corrected_value": "x" * 100},
])
def test_feedback_rejects_invalid_payloads(app, payload):
    user, email = seed_email()
    response = authenticated_client(app, user).post(f"/emails/{email.id}/feedback", json=payload)
    assert response.status_code == 400
    assert email.priority is None


def test_sync_refreshes_read_status_without_reprocessing(app):
    from app.blueprints.gmail.sync_service import sync_user_emails

    user, email = seed_email()
    with patch("app.blueprints.gmail.sync_service.list_message_ids", return_value=(["m1"], None)), \
         patch("app.blueprints.gmail.sync_service.get_full_message", return_value={"labelIds": []}), \
         patch("app.blueprints.gmail.sync_service.process_email_nlp") as process:
        result = sync_user_emails(user, Mock())
    assert email.is_read is True
    assert result["synced"] == 0
    process.assert_not_called()


def test_backfill_preserves_feedback_and_fills_missing_predictions(app):
    from app.extensions import db
    from app.models import UserFeedback

    user, email = seed_email()
    email.category = "Personal"
    db.session.add(UserFeedback(user_id=user.id, email_id=email.id,
                                feedback_type="category", corrected_value="Personal"))
    db.session.commit()

    def classify(target):
        target.category = "Work"
        target.priority = "HIGH"
        target.spam_label = False
        return {"category": True, "priority": True, "spam": True}

    with patch("app.blueprints.ml_inference.routes.classify_email", side_effect=classify):
        response = authenticated_client(app, user).post("/ml/classify-all")
    assert response.status_code == 200
    assert response.get_json()["classified"] == 1
    assert email.category == "Personal"
    assert email.priority == "HIGH"
    assert email.spam_label is False


def test_dashboard_excludes_past_deadlines(app):
    from app.extensions import db
    from app.models import Reminder

    user, email = seed_email()
    now = datetime.now(timezone.utc)
    for offset in (-1, 1):
        db.session.add(Reminder(user_id=user.id, email_id=email.id,
                                deadline_at=now + timedelta(days=offset)))
    db.session.commit()
    response = authenticated_client(app, user).get("/dashboard/stats")
    assert response.get_json()["upcoming_deadlines"] == 1


def test_stored_expiry_triggers_token_refresh(app):
    from app.blueprints.gmail.gmail_client import get_credentials_for_user
    from app.utils.crypto import encrypt_token

    user, _ = seed_email()
    user.gmail_scope_granted = True
    user.oauth_token_encrypted = encrypt_token("expired-token")
    user.oauth_refresh_token_encrypted = encrypt_token("refresh-token")
    user.oauth_token_expiry = datetime(2020, 1, 1)

    def refresh(credentials, request):
        credentials.token = "new-token"
        credentials.expiry = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1)

    with patch("google.oauth2.credentials.Credentials.refresh", autospec=True, side_effect=refresh) as mocked:
        credentials = get_credentials_for_user(user, "client", "secret")
    mocked.assert_called_once()
    assert credentials.token == "new-token"


def test_valid_stored_token_is_not_refreshed(app):
    from app.blueprints.gmail.gmail_client import get_credentials_for_user
    from app.utils.crypto import encrypt_token

    user, _ = seed_email()
    user.gmail_scope_granted = True
    user.oauth_token_encrypted = encrypt_token("valid-token")
    user.oauth_refresh_token_encrypted = encrypt_token("refresh-token")
    user.oauth_token_expiry = datetime.now(timezone.utc) + timedelta(hours=1)
    with patch("google.oauth2.credentials.Credentials.refresh") as refresh:
        credentials = get_credentials_for_user(user, "client", "secret")
    refresh.assert_not_called()
    assert credentials.token == "valid-token"


def test_mysql_large_email_columns(app):
    from sqlalchemy.dialects.mysql import dialect
    from app.models import Email

    for name in ("body", "raw_payload"):
        assert Email.__table__.columns[name].type.compile(dialect=dialect()) == "LONGTEXT"


def test_migration_chain_builds_current_schema(app):
    from pathlib import Path
    from flask_migrate import upgrade, downgrade
    from sqlalchemy import inspect
    from app.extensions import db

    db.session.remove()
    db.drop_all()
    directory = str(Path(__file__).resolve().parents[1] / "migrations")
    upgrade(directory=directory)
    inspector = inspect(db.engine)
    for table in db.metadata.sorted_tables:
        assert {column["name"] for column in inspector.get_columns(table.name)} == set(table.columns.keys())
    downgrade(directory=directory, revision="base")
    assert not (set(db.metadata.tables) & set(inspect(db.engine).get_table_names()))
