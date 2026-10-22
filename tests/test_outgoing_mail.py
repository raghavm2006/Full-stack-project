import base64
import io
import json
from email import message_from_bytes
from email.policy import default
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from tests.test_review_fixes import app, seed_email, authenticated_client


def setup_mail(app, permissions=True):
    from app.extensions import db
    user, email = seed_email()
    user.gmail_send_granted = permissions
    user.gmail_drafts_granted = permissions
    email.raw_payload = json.dumps({"payload": {"headers": [
        {"name": "Message-ID", "value": "<original@example.com>"},
        {"name": "Reply-To", "value": "recruiter@example.com"},
        {"name": "References", "value": "<older@example.com>"}]}})
    email.smart_replies = json.dumps(["Thank you. I can attend."])
    db.session.commit()
    client = authenticated_client(app, user)
    assert client.get("/mail/compose").status_code == 200
    with client.session_transaction() as session:
        token = session["mail_csrf"]
    return user, email, client, token


def prepare(client, token, **values):
    fields = {"csrf_token": token, "to": "recipient@example.com", "cc": "copy@example.com",
              "bcc": "hidden@example.com", "subject": "Project update", "body": "Please review the report."}
    fields.update(values)
    return client.post("/mail/prepare", data=fields, content_type="multipart/form-data")


def gmail_stub(monkeypatch):
    from app.blueprints.mail import routes
    service = Mock()
    monkeypatch.setattr(routes, "get_credentials_for_user", lambda *args: object())
    monkeypatch.setattr(routes, "build_gmail_service", lambda credentials: service)
    return service


def test_compose_preview_attachments_and_headers(app):
    from app.models import OutgoingMessage
    user, email, client, token = setup_mail(app)
    response = prepare(client, token, attachments=(io.BytesIO(b"test file"), "report.txt"))
    assert response.status_code == 302
    message = OutgoingMessage.query.one()
    mime = message_from_bytes(base64.urlsafe_b64decode(message.raw_message), policy=default)
    assert str(mime["From"]) == user.email
    assert str(mime["Cc"]) == "copy@example.com" and str(mime["Bcc"]) == "hidden@example.com"
    assert list(mime.iter_attachments())[0].get_payload(decode=True) == b"test file"
    preview = client.get(response.headers["Location"])
    assert preview.status_code == 200 and b"report.txt" in preview.data
    assert message.status == "prepared" and message.gmail_message_id is None


def test_reply_headers_and_suggestions(app):
    from app.models import OutgoingMessage
    user, email, client, token = setup_mail(app)
    page = client.get(f"/mail/compose?reply_to={email.id}")
    assert b"recruiter@example.com" in page.data
    assert b"compose-suggestion" in page.data
    response = prepare(client, token, reply_email_id=str(email.id), subject="Re: " + email.subject)
    assert response.status_code == 302
    message = OutgoingMessage.query.one()
    mime = message_from_bytes(base64.urlsafe_b64decode(message.raw_message), policy=default)
    assert str(mime["In-Reply-To"]) == "<original@example.com>"
    assert "<older@example.com> <original@example.com>" == str(mime["References"])
    assert message.thread_id == email.thread_id


def test_send_requires_permission_csrf_confirmation_and_is_once(app, monkeypatch):
    from app.extensions import db
    from app.models import OutgoingMessage, Email
    user, email, client, token = setup_mail(app, permissions=False)
    service = gmail_stub(monkeypatch)
    prepare(client, token)
    message = OutgoingMessage.query.one()
    target = f"/mail/{message.id}/send"
    assert client.post(target, data={"csrf_token": token, "confirm": "yes"}).status_code == 403
    user.gmail_send_granted = True
    db.session.commit()
    assert client.post(target, data={"confirm": "yes"}).status_code == 400
    assert client.post(target, data={"csrf_token": token}).status_code == 400
    service.users().messages().send().execute.return_value = {"id": "sent-message", "threadId": "sent-thread"}
    assert client.post(target, data={"csrf_token": token, "confirm": "yes"}).status_code == 302
    assert message.status == "sent"
    assert Email.query.filter_by(user_id=user.id, gmail_message_id="sent-message").count() == 1
    assert client.post(target, data={"csrf_token": token, "confirm": "yes"}).status_code == 409
    assert service.users().messages().send().execute.call_count == 1


def test_uncertain_send_is_not_retried(app, monkeypatch):
    from app.models import OutgoingMessage
    user, email, client, token = setup_mail(app)
    service = gmail_stub(monkeypatch)
    prepare(client, token)
    message = OutgoingMessage.query.one()
    service.users().messages().send().execute.side_effect = TimeoutError("Network timed out")
    target = f"/mail/{message.id}/send"
    client.post(target, data={"csrf_token": token, "confirm": "yes"})
    assert message.status == "uncertain"
    assert client.post(target, data={"csrf_token": token, "confirm": "yes"}).status_code == 409
    assert service.users().messages().send().execute.call_count == 1


def test_draft_save_edit_update_and_send(app, monkeypatch):
    from app.models import OutgoingMessage
    user, email, client, token = setup_mail(app)
    service = gmail_stub(monkeypatch)
    prepare(client, token, attachments=(io.BytesIO(b"keep this"), "report.txt"))
    first = OutgoingMessage.query.one()
    service.users().drafts().create().execute.return_value = {"id": "draft-id"}
    assert client.post(f"/mail/{first.id}/draft", data={"csrf_token": token, "confirm": "yes"}).status_code == 302
    assert first.status == "draft"
    assert service.users().messages().send.call_args is None
    page = client.get(f"/mail/compose?edit={first.id}")
    assert b"keep_attachments" in page.data
    prepare(client, token, edit_id=str(first.id), keep_attachments="1", body="Updated content")
    second = OutgoingMessage.query.order_by(OutgoingMessage.id.desc()).first()
    assert first.status == "replaced" and second.gmail_draft_id == "draft-id"
    service.users().drafts().update().execute.return_value = {"id": "draft-id"}
    client.post(f"/mail/{second.id}/draft", data={"csrf_token": token, "confirm": "yes"})
    assert second.status == "draft"
    service.users().drafts().send().execute.return_value = {"id": "sent-draft", "threadId": "thread"}
    client.post(f"/mail/{second.id}/send", data={"csrf_token": token, "confirm": "yes"})
    assert second.status == "sent"
    sent_args = service.users().drafts().send.call_args.kwargs
    assert sent_args["body"]["id"] == "draft-id"
    mime = message_from_bytes(base64.urlsafe_b64decode(sent_args["body"]["message"]["raw"]), policy=default)
    assert "Updated content" in mime.get_body(preferencelist=("plain",)).get_content()
    assert len(list(mime.iter_attachments())) == 1


@pytest.mark.parametrize("fields", [
    {"to": "invalid"}, {"cc": "a@example.com\r\nBcc: evil@example.com"},
    {"subject": "Bad\nHeader"}, {"body": " "},
    {"attachments": (io.BytesIO(b"x" * (10 * 1024 * 1024 + 1)), "huge.bin")},
])
def test_invalid_messages_never_get_prepared(app, fields):
    from app.models import OutgoingMessage
    user, email, client, token = setup_mail(app)
    assert prepare(client, token, **fields).status_code == 400
    assert OutgoingMessage.query.count() == 0


def test_outgoing_and_reply_ownership(app):
    from app.extensions import db
    from app.models import User, OutgoingMessage
    user, email, client, token = setup_mail(app)
    prepare(client, token)
    message = OutgoingMessage.query.one()
    other = User(google_id="other-mail", email="other@example.com")
    db.session.add(other)
    db.session.commit()
    outsider = authenticated_client(app, other)
    outsider.get("/mail/compose")
    with outsider.session_transaction() as session:
        other_token = session["mail_csrf"]
    assert outsider.get(f"/mail/preview/{message.id}").status_code == 404
    assert outsider.get(f"/mail/compose?reply_to={email.id}").status_code == 404
    assert outsider.post(f"/mail/{message.id}/send", data={"csrf_token": other_token, "confirm": "yes"}).status_code == 404
    assert prepare(outsider, other_token, reply_email_id=str(email.id)).status_code == 404


def test_opt_in_permissions_do_not_widen_read_connection(app, monkeypatch):
    from urllib.parse import parse_qs, urlsplit
    user, email, client, token = setup_mail(app, permissions=False)
    app.config.update(GOOGLE_CLIENT_ID="fake", GOOGLE_CLIENT_SECRET="fake", GOOGLE_REDIRECT_URI="https://example.com/auth/callback")
    for mode, scope in [("read", "gmail.readonly"), ("send", "gmail.send"), ("drafts", "gmail.compose")]:
        response = client.get(f"/gmail/connect?mode={mode}")
        scopes = parse_qs(urlsplit(response.headers["Location"]).query)["scope"][0]
        assert scope in scopes
        if mode == "read":
            assert "gmail.send" not in scopes and "gmail.compose" not in scopes


def test_completeness_check_is_advisory(app):
    from app.blueprints.mail.service import check_reply
    user, email, client, token = setup_mail(app)
    email.body = "Can you confirm attendance?\nPlease provide your availability."
    checks = check_reply(email, "I can attend.")
    assert len(checks) == 2
    assert checks[0]["status"].startswith("Possibly addressed")
    assert checks[1]["status"] == "Not clearly addressed"


def test_sent_reply_clears_followup_in_same_thread(app, monkeypatch):
    from app.extensions import db
    from app.models import OutgoingMessage
    user, email, client, token = setup_mail(app)
    email.needs_follow_up = True
    db.session.commit()
    service = gmail_stub(monkeypatch)
    prepare(client, token, reply_email_id=str(email.id), subject="Re: " + email.subject)
    message = OutgoingMessage.query.one()
    service.users().messages().send().execute.return_value = {"id": "my-reply", "threadId": email.thread_id}
    client.post(f"/mail/{message.id}/send", data={"csrf_token": token, "confirm": "yes"})
    assert message.status == "sent"
    assert email.needs_follow_up is False


def test_permission_flags_use_actual_credentials_scopes(app):
    from app.blueprints.auth.oauth import update_mail_permissions
    user, email, client, token = setup_mail(app, permissions=False)
    update_mail_permissions(user, SimpleNamespace(granted_scopes=app.config["GOOGLE_DRAFT_SCOPES"], scopes=None))
    assert user.gmail_send_granted and user.gmail_drafts_granted
    update_mail_permissions(user, SimpleNamespace(granted_scopes=app.config["GOOGLE_GMAIL_SCOPES"], scopes=None))
    assert not user.gmail_send_granted and not user.gmail_drafts_granted
