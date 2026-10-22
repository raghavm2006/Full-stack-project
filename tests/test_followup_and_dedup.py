"""
Phase 10 verification tests: follow-up detection + duplicate detection.

Run with: pytest tests/test_followup_and_dedup.py -v
"""

import os
from datetime import datetime, timedelta, timezone

import pytest

os.environ["TEST_DATABASE_URI"] = "sqlite:///:memory:"

_REF = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)


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


def make_user(app, email="user@example.com"):
    from app.extensions import db
    from app.models import User

    with app.app_context():
        user = User(google_id=f"google-{email}", email=email)
        db.session.add(user)
        db.session.commit()
        return user.id


def make_email(app, user_id, gmail_message_id, **kwargs):
    from app.extensions import db
    from app.models import Email

    defaults = {
        "thread_id": f"thread-{gmail_message_id}",
        "sender": "sender@example.com",
        "subject": "Subject",
        "body": "Body",
        "timestamp": _REF - timedelta(hours=1),
        "spam_label": False,
    }
    defaults.update(kwargs)

    with app.app_context():
        email = Email(user_id=user_id, gmail_message_id=gmail_message_id, **defaults)
        db.session.add(email)
        db.session.commit()
        return email.id


def login(client, user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


# --- followup/detector.py (pure functions) ---

class _FakeEmail:
    def __init__(self, subject="", body="", priority=None, actions=None, timestamp=None):
        self.subject = subject
        self.body = body
        self.priority = priority
        self.actions = actions or []
        self.timestamp = timestamp


def test_needs_response_true_for_question():
    from app.blueprints.followup.detector import needs_response

    assert needs_response(_FakeEmail(body="Are you available Monday?")) is True


def test_needs_response_true_for_high_priority():
    from app.blueprints.followup.detector import needs_response

    assert needs_response(_FakeEmail(body="FYI.", priority="HIGH")) is True


def test_needs_response_false_for_plain_statement():
    from app.blueprints.followup.detector import needs_response

    assert needs_response(_FakeEmail(body="Thanks, all good.")) is False


def test_is_stale_true_when_older_than_threshold():
    from app.blueprints.followup.detector import is_stale

    old_email = _FakeEmail(timestamp=_REF - timedelta(days=5))
    assert is_stale(old_email, reference_time=_REF, threshold_days=2) is True


def test_is_stale_false_when_recent():
    from app.blueprints.followup.detector import is_stale

    recent_email = _FakeEmail(timestamp=_REF - timedelta(hours=1))
    assert is_stale(recent_email, reference_time=_REF, threshold_days=2) is False


# --- followup/service.py (DB-backed batch detection) ---

def test_detect_pending_follow_ups_flags_stale_unanswered_question(app):
    from app.blueprints.followup.service import detect_pending_follow_ups

    user_id = make_user(app)
    email_id = make_email(
        app, user_id, "m1",
        body="Can you confirm the budget numbers?",
        timestamp=_REF - timedelta(days=5),
    )

    with app.app_context():
        from app.extensions import db
        from app.models import Email

        result = detect_pending_follow_ups(user_id, reference_time=_REF)
        assert result["flagged"] == 1

        email = db.session.get(Email, email_id)
        assert email.needs_follow_up is True


def test_detect_pending_follow_ups_clears_flag_once_user_replied(app):
    from app.blueprints.followup.service import detect_pending_follow_ups
    from app.models import Email

    user_id = make_user(app, email="user@example.com")
    thread_id = "shared-thread"
    email_id = make_email(
        app, user_id, "m1", thread_id=thread_id,
        body="Can you confirm the budget numbers?",
        timestamp=_REF - timedelta(days=5),
    )
    # The user's own reply in the same thread, sent AFTER the question.
    make_email(
        app, user_id, "m2", thread_id=thread_id,
        sender="user@example.com", body="Confirmed.",
        timestamp=_REF - timedelta(days=4),
    )

    with app.app_context():
        from app.extensions import db

        detect_pending_follow_ups(user_id, reference_time=_REF)
        email = db.session.get(Email, email_id)
        assert email.needs_follow_up is False


def test_detect_pending_follow_ups_ignores_spam(app):
    from app.blueprints.followup.service import detect_pending_follow_ups
    from app.models import Email

    user_id = make_user(app)
    email_id = make_email(
        app, user_id, "m1",
        body="Can you confirm?", spam_label=True,
        timestamp=_REF - timedelta(days=5),
    )

    with app.app_context():
        from app.extensions import db

        detect_pending_follow_ups(user_id, reference_time=_REF)
        email = db.session.get(Email, email_id)
        assert email.needs_follow_up is False


def test_followup_detect_route_requires_login(client):
    response = client.post("/followups/detect")
    assert response.status_code == 401


def test_followup_detect_route_returns_counts(app, client):
    user_id = make_user(app)
    make_email(app, user_id, "m1", body="Can you confirm?", timestamp=_REF - timedelta(days=5))
    login(client, user_id)

    response = client.post("/followups/detect")
    assert response.status_code == 200
    data = response.get_json()
    assert data["flagged"] >= 1


# --- deduplication/hashing.py ---

def test_compute_content_hash_matches_after_normalization():
    from app.blueprints.deduplication.hashing import compute_content_hash

    hash_a = compute_content_hash("Hello!", "Please review this.")
    hash_b = compute_content_hash("hello", "please review this")
    assert hash_a == hash_b


def test_compute_content_hash_differs_for_different_content():
    from app.blueprints.deduplication.hashing import compute_content_hash

    assert compute_content_hash("A", "one thing") != compute_content_hash("B", "another thing")


def test_compute_content_hash_returns_none_for_empty_input():
    from app.blueprints.deduplication.hashing import compute_content_hash

    assert compute_content_hash("", "") is None


# --- deduplication/service.py ---

def test_detect_duplicate_emails_flags_exact_repeats(app):
    from app.blueprints.deduplication.service import detect_duplicate_emails
    from app.models import Email

    user_id = make_user(app)
    original_id = make_email(
        app, user_id, "m1", subject="Newsletter", body="Weekly update.",
        timestamp=_REF - timedelta(days=2),
    )
    dupe_id = make_email(
        app, user_id, "m2", subject="Newsletter", body="Weekly update.",
        timestamp=_REF - timedelta(days=1),
    )

    with app.app_context():
        from app.extensions import db

        result = detect_duplicate_emails(user_id)
        assert result["duplicates_found"] == 1

        original = db.session.get(Email, original_id)
        dupe = db.session.get(Email, dupe_id)
        assert original.is_duplicate is False
        assert dupe.is_duplicate is True
        assert dupe.duplicate_of_email_id == original.id


def test_detect_duplicate_emails_leaves_distinct_emails_alone(app):
    from app.blueprints.deduplication.service import detect_duplicate_emails
    from app.models import Email

    user_id = make_user(app)
    id_a = make_email(app, user_id, "m1", subject="A", body="First message")
    id_b = make_email(app, user_id, "m2", subject="B", body="Second message")

    with app.app_context():
        from app.extensions import db

        result = detect_duplicate_emails(user_id)
        assert result["duplicates_found"] == 0
        assert db.session.get(Email, id_a).is_duplicate is False
        assert db.session.get(Email, id_b).is_duplicate is False


def test_duplicates_detect_route_requires_login(client):
    response = client.post("/duplicates/detect")
    assert response.status_code == 401


def test_duplicates_detect_route_returns_counts(app, client):
    user_id = make_user(app)
    make_email(app, user_id, "m1", subject="X", body="Same content", timestamp=_REF - timedelta(days=2))
    make_email(app, user_id, "m2", subject="X", body="Same content", timestamp=_REF - timedelta(days=1))
    login(client, user_id)

    response = client.post("/duplicates/detect")
    assert response.status_code == 200
    data = response.get_json()
    assert data["duplicates_found"] == 1
