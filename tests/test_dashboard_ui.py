"""
Phase 5 verification tests: dashboard/inbox page rendering and the
/dashboard/stats JSON endpoint the dashboard's Chart.js code reads.

Run with: pytest tests/test_dashboard_ui.py -v
"""

from datetime import datetime, timedelta, timezone

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


@pytest.fixture
def client(app):
    return app.test_client()


def make_user(app, gmail_connected=False):
    from app.extensions import db
    from app.models import User

    with app.app_context():
        user = User(
            google_id="google-123",
            email="student@example.com",
            name="Test Student",
            gmail_scope_granted=gmail_connected,
        )
        db.session.add(user)
        db.session.commit()
        return user.id


def make_email(app, user_id, gmail_message_id, priority=None, category=None, is_read=False):
    from app.extensions import db
    from app.models import Email

    with app.app_context():
        email = Email(
            user_id=user_id,
            gmail_message_id=gmail_message_id,
            thread_id=f"thread-{gmail_message_id}",
            sender="sender@example.com",
            subject="Subject",
            body="Body",
            timestamp=datetime.now(timezone.utc) - timedelta(hours=1),
            is_read=is_read,
            priority=priority,
            category=category,
        )
        db.session.add(email)
        db.session.commit()
        return email.id


def login(client, user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


def test_dashboard_page_requires_login(client):
    response = client.get("/dashboard")
    assert response.status_code == 401


def test_dashboard_page_renders_for_logged_in_user(app, client):
    user_id = make_user(app)
    login(client, user_id)

    response = client.get("/dashboard")
    assert response.status_code == 200
    assert b"Dashboard" in response.data
    # No Gmail connected yet -> should show the "Connect Gmail" CTA, not sync.
    assert b"Connect Gmail" in response.data


def test_dashboard_page_shows_sync_button_when_gmail_connected(app, client):
    user_id = make_user(app, gmail_connected=True)
    login(client, user_id)

    response = client.get("/dashboard")
    assert response.status_code == 200
    assert b"Sync Gmail" in response.data


def test_dashboard_stats_counts_are_scoped_to_current_user(app, client):
    user_a = make_user(app)
    from app.extensions import db
    from app.models import User

    with app.app_context():
        user_b = User(google_id="google-b", email="b@example.com")
        db.session.add(user_b)
        db.session.commit()
        user_b_id = user_b.id

    make_email(app, user_a, "a1", priority="HIGH", is_read=False)
    make_email(app, user_a, "a2", priority="LOW", is_read=True)
    make_email(app, user_b_id, "b1", priority="HIGH")  # belongs to a different user

    login(client, user_a)
    response = client.get("/dashboard/stats")
    assert response.status_code == 200

    data = response.get_json()
    assert data["total_emails"] == 2
    assert data["unread_emails"] == 1
    assert data["high_priority_emails"] == 1  # only user_a's HIGH email counts


def test_dashboard_stats_groups_null_category_as_uncategorized(app, client):
    user_id = make_user(app)
    make_email(app, user_id, "m1", category=None)
    make_email(app, user_id, "m2", category="Work")

    login(client, user_id)
    response = client.get("/dashboard/stats")
    breakdown = response.get_json()["category_breakdown"]

    assert breakdown["Uncategorized"] == 1
    assert breakdown["Work"] == 1


def test_inbox_page_requires_login(client):
    response = client.get("/inbox")
    assert response.status_code == 401


def test_inbox_page_renders_for_logged_in_user(app, client):
    user_id = make_user(app)
    login(client, user_id)

    response = client.get("/inbox")
    assert response.status_code == 200
    assert b"Inbox" in response.data


def test_email_detail_page_renders_with_body(app, client):
    user_id = make_user(app)
    email_id = make_email(app, user_id, "m1")
    login(client, user_id)

    response = client.get(f"/inbox/{email_id}")
    assert response.status_code == 200
    assert b"Body" in response.data


def test_email_detail_page_redirects_for_other_users_email(app, client):
    user_a = make_user(app)
    from app.extensions import db
    from app.models import User

    with app.app_context():
        user_b = User(google_id="google-b", email="b@example.com")
        db.session.add(user_b)
        db.session.commit()
        user_b_id = user_b.id

    other_email_id = make_email(app, user_b_id, "b1")

    login(client, user_a)
    response = client.get(f"/inbox/{other_email_id}", follow_redirects=False)
    assert response.status_code == 302
    assert "/inbox" in response.headers["Location"]


def test_email_detail_page_redirects_for_nonexistent_email(app, client):
    user_id = make_user(app)
    login(client, user_id)

    response = client.get("/inbox/99999", follow_redirects=False)
    assert response.status_code == 302
