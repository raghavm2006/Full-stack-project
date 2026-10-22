"""
Phase 10 verification tests: user feedback / personalization.

Run with: pytest tests/test_feedback.py -v
"""

import os
from datetime import datetime, timedelta, timezone

import pytest

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


def make_user(app):
    from app.extensions import db
    from app.models import User

    with app.app_context():
        user = User(google_id="google-a", email="a@example.com")
        db.session.add(user)
        db.session.commit()
        return user.id


def make_email(app, user_id, gmail_message_id, category=None, priority=None):
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
            category=category,
            priority=priority,
        )
        db.session.add(email)
        db.session.commit()
        return email.id


def login(client, user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


def test_submit_feedback_requires_login(client):
    response = client.post("/emails/1/feedback")
    assert response.status_code == 401


def test_submit_feedback_blocks_other_users_email(app, client):
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
    response = client.post(
        f"/emails/{other_email_id}/feedback",
        json={"feedback_type": "category", "corrected_value": "Work"},
    )
    assert response.status_code == 404


def test_submit_feedback_rejects_invalid_feedback_type(app, client):
    user_id = make_user(app)
    email_id = make_email(app, user_id, "m1")
    login(client, user_id)

    response = client.post(
        f"/emails/{email_id}/feedback",
        json={"feedback_type": "spam", "corrected_value": "yes"},
    )
    assert response.status_code == 400


def test_submit_feedback_rejects_missing_corrected_value(app, client):
    user_id = make_user(app)
    email_id = make_email(app, user_id, "m1")
    login(client, user_id)

    response = client.post(
        f"/emails/{email_id}/feedback",
        json={"feedback_type": "category"},
    )
    assert response.status_code == 400


def test_submit_category_feedback_records_and_applies_correction(app, client):
    from app.models import Email, UserFeedback

    user_id = make_user(app)
    email_id = make_email(app, user_id, "m1", category="Personal")
    login(client, user_id)

    response = client.post(
        f"/emails/{email_id}/feedback",
        json={"feedback_type": "category", "corrected_value": "Work"},
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["email"]["category"] == "Work"

    with app.app_context():
        from app.extensions import db

        email = db.session.get(Email, email_id)
        assert email.category == "Work"  # personalization applied immediately

        feedback = UserFeedback.query.filter_by(email_id=email_id).first()
        assert feedback.feedback_type == "category"
        assert feedback.original_value == "Personal"
        assert feedback.corrected_value == "Work"


def test_submit_priority_feedback_records_and_applies_correction(app, client):
    from app.models import Email

    user_id = make_user(app)
    email_id = make_email(app, user_id, "m1", priority="LOW")
    login(client, user_id)

    response = client.post(
        f"/emails/{email_id}/feedback",
        json={"feedback_type": "priority", "corrected_value": "HIGH"},
    )
    assert response.status_code == 200

    with app.app_context():
        from app.extensions import db

        email = db.session.get(Email, email_id)
        assert email.priority == "HIGH"


def test_list_emails_filters_by_needs_follow_up(app, client):
    from app.extensions import db
    from app.models import Email

    user_id = make_user(app)
    flagged_id = make_email(app, user_id, "m1")
    make_email(app, user_id, "m2")

    with app.app_context():
        email = db.session.get(Email, flagged_id)
        email.needs_follow_up = True
        db.session.commit()

    login(client, user_id)
    response = client.get("/emails?needs_follow_up=true")
    data = response.get_json()
    assert len(data["emails"]) == 1
    assert data["emails"][0]["id"] == flagged_id
