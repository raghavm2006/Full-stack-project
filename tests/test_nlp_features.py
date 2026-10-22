"""
Phase 8 verification tests.

Run with: pytest tests/test_nlp_features.py -v

Structured like Phase 7's test_ml_inference.py: the pure text-processing
functions (summarizer/action_extractor/deadline_extractor) are tested
directly with no DB or Flask involved, then process_email_nlp()'s DB
wiring, then the /nlp/process/* routes.
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


def make_email(app, user_id, gmail_message_id, subject="Subject", body="Body", summary=None):
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
            summary=summary,
        )
        db.session.add(email)
        db.session.commit()
        return email.id


def login(client, user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


# --- summarizer.py ---

def test_summarize_text_returns_empty_string_for_empty_input():
    from app.blueprints.nlp_features.summarizer import summarize_text

    assert summarize_text("") == ""
    assert summarize_text(None) == ""


def test_summarize_text_returns_everything_when_already_short():
    from app.blueprints.nlp_features.summarizer import summarize_text

    text = "Hi there. See you soon."
    assert summarize_text(text, max_sentences=3) == text


def test_summarize_text_picks_top_sentences_in_original_order():
    from app.blueprints.nlp_features.summarizer import summarize_text

    text = (
        "The quarterly budget review is scheduled for next week. "
        "I had coffee this morning. "
        "The budget review will cover marketing and engineering spend. "
        "The weather has been nice lately. "
        "Please prepare the budget spreadsheet before the review."
    )
    summary = summarize_text(text, max_sentences=2)
    # "budget"/"review" dominate word frequency, so budget-related
    # sentences should be favored over the unrelated filler ones.
    assert "budget" in summary.lower()
    assert "coffee" not in summary.lower()
    assert "weather" not in summary.lower()


# --- action_extractor.py ---

def test_extract_action_items_returns_empty_list_for_empty_input():
    from app.blueprints.nlp_features.action_extractor import extract_action_items

    assert extract_action_items("") == []


def test_extract_action_items_finds_please_and_can_you_requests():
    from app.blueprints.nlp_features.action_extractor import extract_action_items

    text = "Thanks for joining the call. Please send me the report by Friday. Can you also loop in Sam?"
    items = extract_action_items(text)
    assert any("please send me the report" in item.lower() for item in items)
    assert any("can you also loop in sam" in item.lower() for item in items)


def test_extract_action_items_finds_imperative_openers():
    from app.blueprints.nlp_features.action_extractor import extract_action_items

    text = "Review the attached document. It looks good otherwise."
    items = extract_action_items(text)
    assert any(item.startswith("Review") for item in items)


def test_extract_action_items_ignores_plain_statements():
    from app.blueprints.nlp_features.action_extractor import extract_action_items

    text = "The meeting went well. Everyone agreed on the plan."
    assert extract_action_items(text) == []


def test_extract_action_items_respects_max_items():
    from app.blueprints.nlp_features.action_extractor import extract_action_items

    text = " ".join(f"Please complete task {i}." for i in range(10))
    assert len(extract_action_items(text, max_items=3)) == 3


# --- deadline_extractor.py ---

_REF = datetime(2026, 8, 27, 9, 0, tzinfo=timezone.utc)  # a Thursday


def test_extract_deadlines_returns_empty_list_for_no_matches():
    from app.blueprints.nlp_features.deadline_extractor import extract_deadlines

    assert extract_deadlines("Just checking in, no action needed.", reference_time=_REF) == []


def test_extract_deadlines_handles_tomorrow():
    from app.blueprints.nlp_features.deadline_extractor import extract_deadlines

    results = extract_deadlines("Please reply by tomorrow.", reference_time=_REF)
    assert len(results) == 1
    assert results[0]["deadline_at"].date() == (_REF + timedelta(days=1)).date()


def test_extract_deadlines_handles_eod():
    from app.blueprints.nlp_features.deadline_extractor import extract_deadlines

    results = extract_deadlines("This is due EOD today.", reference_time=_REF)
    assert len(results) == 1
    assert results[0]["deadline_at"].hour == 17


def test_extract_deadlines_handles_next_weekday():
    from app.blueprints.nlp_features.deadline_extractor import extract_deadlines

    results = extract_deadlines("The report is due by next Monday.", reference_time=_REF)
    assert len(results) == 1
    deadline = results[0]["deadline_at"]
    assert deadline.weekday() == 0  # Monday
    assert deadline > _REF


def test_extract_deadlines_handles_explicit_date():
    from app.blueprints.nlp_features.deadline_extractor import extract_deadlines

    results = extract_deadlines("Submit the form before March 15, 2027.", reference_time=_REF)
    assert len(results) == 1
    assert results[0]["deadline_at"].year == 2027
    assert results[0]["deadline_at"].month == 3
    assert results[0]["deadline_at"].day == 15


def test_extract_deadlines_deduplicates_same_resolved_datetime():
    from app.blueprints.nlp_features.deadline_extractor import extract_deadlines

    text = "Due EOD today. Also make sure this is done by end of day."
    results = extract_deadlines(text, reference_time=_REF)
    assert len(results) == 1


# --- process_email_nlp() wiring ---

def test_process_email_nlp_sets_summary_and_creates_rows(app):
    from app.blueprints.nlp_features.service import process_email_nlp
    from app.models import Email

    with app.app_context():
        email = Email(
            user_id=1,
            subject="Budget review",
            body="Please send the budget spreadsheet by tomorrow. Thanks!",
            sender="a@b.com",
        )
        result = process_email_nlp(email)

        assert result["summary_set"] is True
        assert email.summary
        assert result["actions_found"] == 1
        assert len(email.actions) == 1
        assert result["deadlines_found"] == 1
        assert len(email.reminders) == 1


def test_process_email_nlp_handles_email_with_nothing_actionable(app):
    from app.blueprints.nlp_features.service import process_email_nlp
    from app.models import Email

    with app.app_context():
        email = Email(user_id=1, subject="FYI", body="No action needed here.", sender="a@b.com")
        result = process_email_nlp(email)

        assert result["actions_found"] == 0
        assert result["deadlines_found"] == 0
        assert email.actions == []
        assert email.reminders == []


# --- routes ---

def test_process_one_requires_login(client):
    response = client.post("/nlp/process/1")
    assert response.status_code == 401


def test_process_one_blocks_other_users_email(app, client):
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
    response = client.post(f"/nlp/process/{other_email_id}")
    assert response.status_code == 404


def test_process_one_success_sets_summary_and_returns_email(app, client):
    user_id = make_user(app)
    email_id = make_email(
        app, user_id, "m1", subject="Report",
        body="Please send the final report by tomorrow.",
    )
    login(client, user_id)

    response = client.post(f"/nlp/process/{email_id}")
    assert response.status_code == 200
    data = response.get_json()
    assert data["result"]["actions_found"] == 1
    assert data["email"]["summary"]
    assert len(data["email"]["actions"]) == 1
    assert len(data["email"]["reminders"]) == 1


def test_process_all_skips_emails_that_already_have_a_summary(app, client):
    user_id = make_user(app)
    make_email(app, user_id, "already-done", body="Please send it.", summary="Already summarized.")
    make_email(app, user_id, "needs-processing", body="Please review this by tomorrow.")
    login(client, user_id)

    response = client.post("/nlp/process-all")
    assert response.status_code == 200
    data = response.get_json()
    assert data["processed"] == 1
