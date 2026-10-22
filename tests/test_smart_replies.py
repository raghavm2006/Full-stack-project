"""
Phase 9 verification tests.

Run with: pytest tests/test_smart_replies.py -v

No real ANTHROPIC_API_KEY is used anywhere here — the LLM client is
tested against a hand-built fake "client" object that mimics the small
slice of the anthropic SDK's interface this module actually calls
(client.messages.create(...).content[0].text), so these tests never
make a network call and never cost anything to run.
"""

import json
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


def make_email(app, user_id, gmail_message_id, subject="Subject", body="Body", smart_replies=None):
    from app.extensions import db
    from app.models import Email

    with app.app_context():
        email = Email(
            user_id=user_id,
            gmail_message_id=gmail_message_id,
            thread_id=f"thread-{gmail_message_id}",
            sender="sender@example.com",
            subject=subject,
            body=body,
            timestamp=datetime.now(timezone.utc) - timedelta(hours=1),
            smart_replies=smart_replies,
        )
        db.session.add(email)
        db.session.commit()
        return email.id


def login(client, user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


# --- templates.py ---

class _FakeEmail:
    """Bare stand-in for an Email row — templates.py only reads a few attributes."""

    def __init__(self, subject="", body="", priority=None, actions=None, reminders=None):
        self.subject = subject
        self.body = body
        self.priority = priority
        self.actions = actions or []
        self.reminders = reminders or []


def test_generate_template_replies_always_includes_acknowledge():
    from app.blueprints.smart_replies.templates import generate_template_replies

    replies = generate_template_replies(_FakeEmail(subject="FYI", body="Just a note."))
    assert any("follow up shortly" in r for r in replies)


def test_generate_template_replies_favors_request_info_for_questions():
    from app.blueprints.smart_replies.templates import generate_template_replies

    replies = generate_template_replies(_FakeEmail(body="Are you free tomorrow?"), max_replies=1)
    assert replies == ["Thanks for reaching out — could you share a bit more detail on this?"]


def test_generate_template_replies_favors_deadline_ack_when_reminders_present():
    from app.blueprints.smart_replies.templates import generate_template_replies

    replies = generate_template_replies(
        _FakeEmail(body="Please finish this by Friday.", reminders=["fake-reminder"]),
        max_replies=1,
    )
    assert replies == ["Understood — I'll make sure this is taken care of by the deadline."]


def test_generate_template_replies_respects_max_replies():
    from app.blueprints.smart_replies.templates import generate_template_replies

    replies = generate_template_replies(
        _FakeEmail(body="Are you free?", priority="HIGH", actions=["x"], reminders=["y"]),
        max_replies=2,
    )
    assert len(replies) == 2


# --- llm_client.py ---

class _FakeContentBlock:
    def __init__(self, text):
        self.text = text


class _FakeResponse:
    def __init__(self, text):
        self.content = [_FakeContentBlock(text)]


class _FakeMessages:
    def __init__(self, text=None, exc=None):
        self._text = text
        self._exc = exc

    def create(self, **kwargs):
        if self._exc:
            raise self._exc
        return _FakeResponse(self._text)


class _FakeClient:
    def __init__(self, text=None, exc=None):
        self.messages = _FakeMessages(text=text, exc=exc)


def test_get_client_raises_when_no_api_key(monkeypatch):
    from app.blueprints.smart_replies import llm_client

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    llm_client.clear_cache()

    with pytest.raises(llm_client.LLMUnavailableError):
        llm_client._get_client()


def test_generate_llm_replies_parses_clean_json_array(monkeypatch):
    from app.blueprints.smart_replies import llm_client

    fake_client = _FakeClient(text='["Sure, works for me.", "Can you resend the attachment?"]')
    monkeypatch.setattr(llm_client, "_get_client", lambda: fake_client)

    replies = llm_client.generate_llm_replies(subject="s", body="b", sender="a@b.com")
    assert replies == ["Sure, works for me.", "Can you resend the attachment?"]


def test_generate_llm_replies_strips_markdown_code_fence(monkeypatch):
    from app.blueprints.smart_replies import llm_client

    fenced = '```json\n["Reply A", "Reply B"]\n```'
    fake_client = _FakeClient(text=fenced)
    monkeypatch.setattr(llm_client, "_get_client", lambda: fake_client)

    replies = llm_client.generate_llm_replies(subject="s", body="b", sender="a@b.com")
    assert replies == ["Reply A", "Reply B"]


def test_generate_llm_replies_raises_on_unparseable_response(monkeypatch):
    from app.blueprints.smart_replies import llm_client

    fake_client = _FakeClient(text="not json at all")
    monkeypatch.setattr(llm_client, "_get_client", lambda: fake_client)

    with pytest.raises(llm_client.LLMUnavailableError):
        llm_client.generate_llm_replies(subject="s", body="b", sender="a@b.com")


def test_generate_llm_replies_raises_on_api_error(monkeypatch):
    from app.blueprints.smart_replies import llm_client

    fake_client = _FakeClient(exc=RuntimeError("rate limited"))
    monkeypatch.setattr(llm_client, "_get_client", lambda: fake_client)

    with pytest.raises(llm_client.LLMUnavailableError):
        llm_client.generate_llm_replies(subject="s", body="b", sender="a@b.com")


# --- service.py: LLM-first with template fallback ---

def test_generate_smart_replies_uses_llm_when_available(app, monkeypatch):
    from app.blueprints.smart_replies import service
    from app.models import Email

    monkeypatch.setattr(service, "generate_llm_replies", lambda **kwargs: ["LLM reply one"])

    with app.app_context():
        email = Email(user_id=1, subject="s", body="b", sender="a@b.com")
        result = service.generate_smart_replies(email)

        assert result == {"replies": ["LLM reply one"], "source": "llm"}
        assert json.loads(email.smart_replies) == ["LLM reply one"]
        assert email.smart_reply_source == "llm"


def test_generate_smart_replies_falls_back_to_templates_on_llm_failure(app, monkeypatch):
    from app.blueprints.smart_replies import service
    from app.blueprints.smart_replies.llm_client import LLMUnavailableError
    from app.models import Email

    def _raise(**kwargs):
        raise LLMUnavailableError("no key configured")

    monkeypatch.setattr(service, "generate_llm_replies", _raise)

    with app.app_context():
        email = Email(user_id=1, subject="FYI", body="Just checking in.", sender="a@b.com")
        result = service.generate_smart_replies(email)

        assert result["source"] == "template"
        assert len(result["replies"]) > 0
        assert email.smart_reply_source == "template"


# --- routes ---

def test_generate_one_requires_login(client):
    response = client.post("/replies/generate/1")
    assert response.status_code == 401


def test_generate_one_blocks_other_users_email(app, client, monkeypatch):
    from app.blueprints.smart_replies import service

    monkeypatch.setattr(service, "generate_llm_replies", lambda **kwargs: ["hi"])

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
    response = client.post(f"/replies/generate/{other_email_id}")
    assert response.status_code == 404


def test_generate_one_success_returns_replies(app, client, monkeypatch):
    from app.blueprints.smart_replies import service
    from app.blueprints.smart_replies.llm_client import LLMUnavailableError

    def _raise(**kwargs):
        raise LLMUnavailableError("no key")

    monkeypatch.setattr(service, "generate_llm_replies", _raise)

    user_id = make_user(app)
    email_id = make_email(app, user_id, "m1", body="Are you around this week?")
    login(client, user_id)

    response = client.post(f"/replies/generate/{email_id}")
    assert response.status_code == 200
    data = response.get_json()
    assert data["result"]["source"] == "template"
    assert len(data["email"]["smart_replies"]) > 0
    assert data["email"]["smart_reply_source"] == "template"


def test_generate_all_skips_emails_that_already_have_smart_replies(app, client, monkeypatch):
    from app.blueprints.smart_replies import service

    monkeypatch.setattr(service, "generate_llm_replies", lambda **kwargs: ["reply"])

    user_id = make_user(app)
    make_email(app, user_id, "already-done", smart_replies=json.dumps(["existing reply"]))
    make_email(app, user_id, "needs-replies")
    login(client, user_id)

    response = client.post("/replies/generate-all")
    assert response.status_code == 200
    data = response.get_json()
    assert data["processed"] == 1
