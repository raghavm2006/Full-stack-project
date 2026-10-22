"""
Phase 3 verification tests.

Run with: pytest tests/test_gmail_sync.py -v

The Gmail API itself is faked out with an in-memory stub (no real network
calls, no real Google credentials needed) so these can run anywhere.
"""

import json
import os

import pytest

os.environ.setdefault("FLASK_ENV", "testing")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("ENCRYPTION_KEY", "kx6Qv6VU6m2yjcVQ2rC0j0y3Q1sV2v9b2b5h1z2m4kA=")
# Sync logic is verified against a throwaway SQLite DB instead of requiring
# a live MySQL server — see the TEST_DATABASE_URI note in app/config.py.
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


def make_user(app, gmail_connected=False):
    from app.extensions import db
    from app.models import User

    with app.app_context():
        user = User(
            google_id="google-123",
            email="student@example.com",
            name="Test Student",
            gmail_scope_granted=gmail_connected,
            oauth_token_encrypted="placeholder",
            oauth_refresh_token_encrypted="placeholder" if gmail_connected else None,
        )
        db.session.add(user)
        db.session.commit()
        return user.id


def login(client, user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


# --- extract_basic_fields ---

def _b64url(text):
    import base64

    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def sample_message(msg_id="m1", subject="Hello", unread=True, body_text="Body text."):
    return {
        "id": msg_id,
        "threadId": f"thread-{msg_id}",
        "internalDate": "1700000000000",  # ms epoch
        "labelIds": ["UNREAD"] if unread else ["INBOX"],
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "From", "value": "sender@example.com"},
                {"name": "To", "value": "student@example.com"},
                {"name": "Subject", "value": subject},
            ],
            "body": {"data": _b64url(body_text)},
        },
    }


def test_extract_basic_fields_reads_headers_and_date():
    from app.blueprints.gmail.sync_service import extract_basic_fields

    fields = extract_basic_fields(sample_message())
    assert fields["sender"] == "sender@example.com"
    assert fields["receiver"] == "student@example.com"
    assert fields["subject"] == "Hello"
    assert fields["is_read"] is False  # UNREAD label present


def test_extract_basic_fields_marks_read_when_no_unread_label():
    from app.blueprints.gmail.sync_service import extract_basic_fields

    fields = extract_basic_fields(sample_message(unread=False))
    assert fields["is_read"] is True


class FakeMessagesResource:
    """Stands in for service.users().messages() from the Gmail API client."""

    def __init__(self, messages_by_id):
        self._messages_by_id = messages_by_id

    def list(self, userId, maxResults, pageToken=None, q=None):  # noqa: N803
        ids = list(self._messages_by_id.keys())[:maxResults]
        return _Executable({"messages": [{"id": i} for i in ids]})

    def get(self, userId, id, format):  # noqa: N803, A002
        return _Executable(self._messages_by_id[id])


class _Executable:
    def __init__(self, payload):
        self._payload = payload

    def execute(self):
        return self._payload


class FakeGmailService:
    def __init__(self, messages_by_id):
        self._messages = FakeMessagesResource(messages_by_id)

    def users(self):
        return self


    def messages(self):
        return self._messages


# --- sync_user_emails ---

def test_sync_stores_new_emails_and_dedupes_on_rerun(app):
    from app.blueprints.gmail.sync_service import sync_user_emails
    from app.extensions import db
    from app.models import Email, User

    with app.app_context():
        user_id = make_user(app, gmail_connected=True)
        user = db.session.get(User, user_id)

        service = FakeGmailService({
            "m1": sample_message("m1", subject="First"),
            "m2": sample_message("m2", subject="Second"),
        })

        result = sync_user_emails(user, service, max_results=10)
        assert result == {
            "total_fetched": 2,
            "synced": 2,
            "skipped_existing": 0,
            "duplicates_found": 0,  # different subjects -> different content hashes
            "needs_follow_up": 0,
        }
        assert Email.query.filter_by(user_id=user.id).count() == 2

        # Re-running sync with the same messages should not create duplicates.
        result_again = sync_user_emails(user, service, max_results=10)
        assert result_again == {
            "total_fetched": 2,
            "synced": 0,
            "skipped_existing": 2,
            "duplicates_found": 0,
            "needs_follow_up": 0,
        }
        assert Email.query.filter_by(user_id=user.id).count() == 2


def test_sync_stores_raw_payload_for_later_parsing(app):
    from app.blueprints.gmail.sync_service import sync_user_emails
    from app.extensions import db
    from app.models import Email, User

    with app.app_context():
        user_id = make_user(app, gmail_connected=True)
        user = db.session.get(User, user_id)
        service = FakeGmailService({"m1": sample_message("m1")})

        sync_user_emails(user, service, max_results=10)

        stored = Email.query.filter_by(user_id=user.id, gmail_message_id="m1").first()
        assert stored is not None
        assert stored.body == "Body text."  # decoded by Phase 4's parser during sync
        assert json.loads(stored.raw_payload)["id"] == "m1"


# --- routes ---


def test_sync_preserves_multi_recipient_header(app, monkeypatch):
    from app.blueprints.gmail import sync_service
    from app.extensions import db
    from app.models import Email, User
    from sqlalchemy.dialects.mysql import dialect

    monkeypatch.setattr(sync_service, "classify_email", lambda email: {})
    recipients = ", ".join(f"Recipient {i} <recipient{i}@example.com>" for i in range(30))
    message = sample_message()
    for header in message["payload"]["headers"]:
        if header["name"] == "To":
            header["value"] = recipients
    user = db.session.get(User, make_user(app))
    result = sync_service.sync_user_emails(user, FakeGmailService({"m1": message}))
    assert result["synced"] == 1
    assert Email.query.filter_by(user_id=user.id).one().receiver == recipients
    assert Email.__table__.columns.receiver.type.compile(dialect=dialect()) == "LONGTEXT"

def test_gmail_connect_requires_login(client):
    response = client.get("/gmail/connect")
    assert response.status_code == 401


def test_gmail_connect_requests_incremental_gmail_scope(app, client, monkeypatch):
    monkeypatch.setitem(app.config, "GOOGLE_CLIENT_ID", "fake-id")
    monkeypatch.setitem(app.config, "GOOGLE_CLIENT_SECRET", "fake-secret")
    monkeypatch.setitem(app.config, "GOOGLE_REDIRECT_URI", "http://localhost:5000/auth/callback")

    user_id = make_user(app)
    login(client, user_id)

    response = client.get("/gmail/connect")
    assert response.status_code == 302
    assert "gmail.readonly" in response.headers["Location"]
    from urllib.parse import parse_qs, urlsplit
    params = parse_qs(urlsplit(response.headers["Location"]).query)
    assert params["redirect_uri"] == ["http://localhost:5000/auth/callback"]
    with client.session_transaction() as sess:
        assert params["state"] == [sess["gmail_oauth_state"]]


def test_gmail_callback_exchanges_token_with_gmail_redirect(app, client, monkeypatch):
    from unittest.mock import Mock
    from app.blueprints.gmail import routes

    monkeypatch.setitem(app.config, "GOOGLE_REDIRECT_URI", "http://127.0.0.1:5000/auth/callback")
    user_id = make_user(app)
    login(client, user_id)
    with client.session_transaction() as sess:
        sess["gmail_oauth_state"] = "gmail-state"
    flow = Mock()
    build = Mock(return_value=flow)
    monkeypatch.setattr(routes, "build_flow", build)
    monkeypatch.setattr(routes, "fetch_google_user_info", lambda credentials: {"sub": "another-account"})
    response = client.get("/auth/callback?state=gmail-state&code=test-code")
    assert response.status_code == 400
    assert "does not match" in response.get_json()["error"]
    assert build.call_args.kwargs["redirect_uri"] == "http://127.0.0.1:5000/auth/callback"
    assert build.call_args.kwargs["state"] == "gmail-state"
    flow.fetch_token.assert_called_once()


def test_shared_callback_rejects_unknown_gmail_state(app, client):
    login(client, make_user(app))
    with client.session_transaction() as sess:
        sess["gmail_oauth_state"] = "expected-gmail-state"
    response = client.get("/auth/callback?state=wrong-state&code=test-code")
    assert response.status_code == 400
    assert "state" in response.get_json()["error"].lower()


def test_shared_gmail_callback_requires_login(client):
    with client.session_transaction() as sess:
        sess["gmail_oauth_state"] = "gmail-state"
    response = client.get("/auth/callback?state=gmail-state&code=test-code")
    assert response.status_code == 401


def test_sync_without_gmail_connected_returns_clear_error(app, client):
    user_id = make_user(app, gmail_connected=False)
    login(client, user_id)

    response = client.post("/gmail/sync")
    assert response.status_code == 400
    assert "connect" in response.get_json()["error"].lower()


def test_gmail_callback_requires_login(client):
    response = client.get("/gmail/callback?state=x&code=y")
    assert response.status_code == 401


def test_gmail_callback_rejects_mismatched_state(app, client):
    user_id = make_user(app)
    login(client, user_id)
    with client.session_transaction() as sess:
        sess["gmail_oauth_state"] = "expected-state"

    response = client.get("/gmail/callback?state=wrong-state&code=abc123")
    assert response.status_code == 400
    assert "state" in response.get_json()["error"].lower()


def test_gmail_sync_rejects_out_of_range_max_results(app, client):
    user_id = make_user(app, gmail_connected=True)
    login(client, user_id)

    response = client.post("/gmail/sync?max_results=500")
    assert response.status_code == 400
