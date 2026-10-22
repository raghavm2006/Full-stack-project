from datetime import datetime, timedelta, timezone
import csv
import io
import pytest

from tests.test_review_fixes import app, seed_email, authenticated_client


def scan_client(app):
    from app.extensions import db
    user, email = seed_email()
    email.body = "Please send the report by Friday at 3 PM."
    db.session.commit()
    client = authenticated_client(app, user)
    assert client.get("/commitments").status_code == 200
    with client.session_transaction() as session:
        token = session["commitment_csrf"]
    return user, email, client, token


def test_scan_idempotence_evidence_and_confirmation(app):
    from app.models import Commitment
    from app.blueprints.commitments.service import scan_commitments
    user, email, client, token = scan_client(app)
    assert scan_commitments(user) == 1
    assert scan_commitments(user) == 0
    item = Commitment.query.one()
    assert item.status == "proposed"
    assert item.responsible == "me"
    assert item.evidence == email.body
    assert item.deadline_at.hour == 15
    assert client.post(f"/commitments/{item.id}", data={"status": "active"}).status_code == 400
    assert client.post(f"/commitments/{item.id}", data={"status": "active", "csrf_token": token}).status_code == 302
    assert item.status == "active"
    assert client.post(f"/commitments/{item.id}", data={"status": "completed", "csrf_token": token}).status_code == 302
    scan_commitments(user)
    assert item.status == "completed"
    assert Commitment.query.count() == 1


def test_changes_do_not_replace_without_confirmation(app):
    from app.extensions import db
    from app.models import Commitment, Email
    from app.blueprints.commitments.service import scan_commitments
    user, email, client, token = scan_client(app)
    scan_commitments(user)
    original = Commitment.query.one()
    original.status = "active"
    reply = Email(user_id=user.id, gmail_message_id="changed", thread_id=email.thread_id,
                  sender=email.sender, body="Please send the report by Thursday instead.",
                  timestamp=email.timestamp + timedelta(hours=1))
    db.session.add(reply)
    db.session.commit()
    scan_commitments(user)
    change = Commitment.query.filter_by(source_email_id=reply.id).one()
    assert change.is_change and change.status == "proposed"
    assert change.deadline_at is not None
    assert change.deadline_at.weekday() == 3
    assert original.status == "active"
    response = client.post(f"/commitments/{change.id}", data={"status": "active", "csrf_token": token,
                                                                  "supersedes_id": original.id})
    assert response.status_code == 302
    assert original.status == "superseded"
    assert change.supersedes_id == original.id
    assert client.get(f"/commitments/thread/{email.id}").status_code == 200


def test_user_isolation_and_overdue_count(app):
    from app.extensions import db
    from app.models import Commitment, User
    from app.blueprints.commitments.service import scan_commitments
    user, email, client, token = scan_client(app)
    scan_commitments(user)
    item = Commitment.query.one()
    item.status = "active"
    item.deadline_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)
    other = User(google_id="outsider", email="outsider@example.com")
    db.session.add(other)
    db.session.commit()
    other_client = authenticated_client(app, other)
    other_client.get("/commitments")
    with other_client.session_transaction() as session:
        other_token = session["commitment_csrf"]
    assert other_client.post(f"/commitments/{item.id}", data={"status": "completed", "csrf_token": other_token}).status_code == 404
    assert other_client.get(f"/commitments/thread/{email.id}").status_code == 404
    assert other_client.get("/dashboard/stats").get_json()["overdue_commitments"] == 0
    assert client.get("/dashboard/stats").get_json()["overdue_commitments"] == 1
    assert b"report" in client.get("/commitments?view=overdue").data


@pytest.mark.parametrize("sender,body,responsible", [
    ("user@example.com", "I will send the report by tomorrow.", "me"),
    ("sender@example.com", "I'll send the report by tomorrow.", "other"),
    ("user@example.com", "Could you send the report by Friday?", "other"),
    ("sender@example.com", "Please do not send the report.", None),
    ("sender@example.com", "I will not send the report.", None),
])
def test_responsibility_and_negation(app, sender, body, responsible):
    from app.blueprints.commitments.service import extract_commitments
    user, email = seed_email()
    email.sender, email.body = sender, body
    result = extract_commitments(email, user.email)
    if responsible:
        assert result[0]["responsible"] == responsible
    else:
        assert result == []


def test_review_export_has_blank_labels_and_no_other_user_data(app):
    user, email, client, token = scan_client(app)
    response = client.get("/ml/review-sample.csv")
    rows = list(csv.DictReader(io.StringIO(response.get_data(as_text=True))))
    assert len(rows) == 1
    assert rows[0]["body"] == email.body
    assert rows[0]["category"] == rows[0]["priority"] == rows[0]["spam_label"] == ""
    assert response.headers["Cache-Control"] == "no-store"


def test_key_information_restrictions_and_ambiguous_dates(app):
    from app.blueprints.nlp_features.insights import key_information
    from app.blueprints.nlp_features.action_extractor import extract_action_items
    user, email = seed_email()
    email.body = "Please submit the form by 03/04/2026.\nDo not send original documents."
    info = key_information(email)
    assert info["actions"] == ["Please submit the form by 03/04/2026."]
    assert info["restrictions"] == ["Do not send original documents."]
    assert info["deadlines"][0]["deadline_at"] is None
    assert extract_action_items("Please do not send originals.") == []
    assert extract_action_items("The task was completed.\nPlease review the invoice.") == ["Please review the invoice."]


def test_missing_artifacts_do_not_break_detail(app, monkeypatch):
    from app.extensions import db
    from app.blueprints.ml_inference.predictors import clear_cache
    user, email, client, token = scan_client(app)
    email.category, email.category_confidence = "Work", 0.5
    db.session.commit()
    clear_cache()
    monkeypatch.setitem(app.config, "MODELS_DIR", "nonexistent-test-models")
    response = client.get(f"/inbox/{email.id}")
    assert response.status_code == 200
    assert b"Key information" in response.data
    assert b"Review recommended" in response.data
    clear_cache()


def test_edits_preserve_evidence_and_reject_invalid_updates(app):
    from app.models import Commitment
    from app.blueprints.commitments.service import scan_commitments
    user, email, client, token = scan_client(app)
    scan_commitments(user)
    item = Commitment.query.one()
    evidence = item.evidence
    response = client.post(f"/commitments/{item.id}", data={"csrf_token": token,
        "status": "active", "description": "Send reviewed report", "responsible": "other",
        "deadline": "2026-10-20T12:00+05:30"})
    assert response.status_code == 302
    assert item.description == "Send reviewed report" and item.evidence == evidence
    assert item.deadline_at.hour == 6 and item.deadline_at.minute == 30
    assert client.post(f"/commitments/{item.id}", data={"csrf_token": token,
        "status": "active", "deadline": "invalid"}).status_code == 400
    assert item.deadline_at.hour == 6


def test_open_excludes_expired_active_and_proposed_tasks(app):
    from app.extensions import db
    from app.models import Commitment
    from app.blueprints.commitments.service import scan_commitments
    user, email, client, token = scan_client(app)
    scan_commitments(user)
    item = Commitment.query.one()
    item.description = "Expired distinctive task"
    item.deadline_at = datetime(2020, 1, 1)
    db.session.commit()
    for status in ("proposed", "active"):
        item.status = status
        db.session.commit()
        assert b"Expired distinctive task" not in client.get("/commitments").data
        assert b"Expired distinctive task" in client.get("/commitments?view=overdue").data
        assert client.get("/dashboard/stats").get_json()["overdue_commitments"] == 1
    item.status = "completed"
    db.session.commit()
    assert b"Expired distinctive task" not in client.get("/commitments?view=overdue").data
    assert b"Expired distinctive task" in client.get("/commitments?view=all").data


def test_interview_context_expiry_without_changing_stored_dates(app):
    from app.extensions import db
    from app.models import Commitment
    from app.blueprints.commitments.service import scan_commitments
    from app.blueprints.commitments.timing import commitment_timing
    user, email, client, token = scan_client(app)
    email.body = ('Interview Date and Time: 14 October, 2020 | 03:30 PM- 05:30 PM\n'
                  'Upload your resume at least 1 day prior to the scheduled interview time.\n'
                  'Please upload a text-based resume without images.')
    db.session.commit()
    scan_commitments(user)
    item = Commitment.query.one()
    assert item.deadline_at is None
    timing = commitment_timing(item)
    assert timing["kind"] == "inferred_deadline"
    assert timing["at"] == datetime(2020, 10, 13, 10)
    assert b"Please upload a text-based resume" not in client.get("/commitments").data
    response = client.get("/commitments?view=overdue")
    assert b"Please upload a text-based resume" in response.data
    assert b"date passed" in response.data and b"assumed IST" in response.data
    assert item.status == "proposed" and item.deadline_at is None
    item.description = "Complete the interview"
    assert commitment_timing(item)["kind"] == "event_end"
    assert commitment_timing(item)["at"] == datetime(2020, 10, 14, 12)
    item.deadline_at = datetime(2099, 1, 1)
    assert commitment_timing(item)["at"] == datetime(2099, 1, 1)
