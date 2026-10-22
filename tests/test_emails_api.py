"""
Phase 4 verification tests for the /emails JSON API.

Run with: pytest tests/test_emails_api.py -v

Uses the same throwaway in-memory SQLite pattern as test_gmail_sync.py.
"""

import os
from datetime import datetime, timedelta, timezone

import pytest

os.environ.setdefault("FLASK_ENV", "testing")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("ENCRYPTION_KEY", "kx6Qv6VU6m2yjcVQ2rC0j0y3Q1sV2v9b2b5h1z2m4kA=")
os.environ["TEST_DATABASE_URI"] = "sqlite:///:memory:"


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


@pytest.fixture
def client(app):
    return app.test_client()


def make_user(app, google_id, email):
    from app.extensions import db
    from app.models import User

    with app.app_context():
        user = User(google_id=google_id, email=email)
        db.session.add(user)
        db.session.commit()
        return user.id


def make_email(app, user_id, gmail_message_id, subject="Test subject", body="Test body", is_read=False):
    from app.extensions import db
    from app.models import Email

    with app.app_context():
        email = Email(
            user_id=user_id,
            gmail_message_id=gmail_message_id,
            thread_id=f"thread-{gmail_message_id}",
            sender="sender@example.com",
            receiver="user@example.com",
            subject=subject,
            body=body,
            timestamp=datetime.now(timezone.utc) - timedelta(hours=1),
            is_read=is_read,
        )
        db.session.add(email)
        db.session.commit()
        return email.id


def login(client, user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


def test_list_emails_requires_login(client):
    response = client.get("/emails")
    assert response.status_code == 401


def test_list_emails_returns_only_own_emails(app, client):
    user_a = make_user(app, "google-a", "a@example.com")
    user_b = make_user(app, "google-b", "b@example.com")
    make_email(app, user_a, "a-msg-1")
    make_email(app, user_b, "b-msg-1")

    login(client, user_a)
    response = client.get("/emails")
    assert response.status_code == 200
    data = response.get_json()
    assert data["total"] == 1
    assert data["emails"][0]["gmail_message_id"] == "a-msg-1"


def test_list_emails_snippet_does_not_leak_full_body(app, client):
    user_id = make_user(app, "google-a", "a@example.com")
    make_email(app, user_id, "m1", body="x" * 500)
    login(client, user_id)

    response = client.get("/emails")
    snippet = response.get_json()["emails"][0]["snippet"]
    assert len(snippet) < 500


def test_list_emails_rejects_invalid_pagination(app, client):
    user_id = make_user(app, "google-a", "a@example.com")
    login(client, user_id)

    response = client.get("/emails?page=0")
    assert response.status_code == 400

    response = client.get("/emails?per_page=9999")
    assert response.status_code == 400


def test_get_email_detail_includes_full_body(app, client):
    user_id = make_user(app, "google-a", "a@example.com")
    email_id = make_email(app, user_id, "m1", body="Full body content here.")
    login(client, user_id)

    response = client.get(f"/emails/{email_id}")
    assert response.status_code == 200
    assert response.get_json()["body"] == "Full body content here."


def test_get_email_detail_blocks_access_to_other_users_email(app, client):
    user_a = make_user(app, "google-a", "a@example.com")
    user_b = make_user(app, "google-b", "b@example.com")
    other_email_id = make_email(app, user_b, "b-msg-1")

    login(client, user_a)
    response = client.get(f"/emails/{other_email_id}")
    assert response.status_code == 404


def test_patch_read_status_updates_email(app, client):
    user_id = make_user(app, "google-a", "a@example.com")
    email_id = make_email(app, user_id, "m1", is_read=False)
    login(client, user_id)

    response = client.patch(f"/emails/{email_id}/read", json={"is_read": True})
    assert response.status_code == 200
    assert response.get_json()["is_read"] is True


def test_patch_read_status_rejects_non_boolean(app, client):
    user_id = make_user(app, "google-a", "a@example.com")
    email_id = make_email(app, user_id, "m1")
    login(client, user_id)

    response = client.patch(f"/emails/{email_id}/read", json={"is_read": "yes"})
    assert response.status_code == 400


def test_patch_read_status_blocks_other_users_email(app, client):
    user_a = make_user(app, "google-a", "a@example.com")
    user_b = make_user(app, "google-b", "b@example.com")
    other_email_id = make_email(app, user_b, "b-msg-1")

    login(client, user_a)
    response = client.patch(f"/emails/{other_email_id}/read", json={"is_read": True})
    assert response.status_code == 404
