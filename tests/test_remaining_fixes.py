from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest

from tests.test_review_fixes import app, seed_email, authenticated_client


def test_older_sync_uses_and_returns_page_tokens(app):
    from app.blueprints.gmail.sync_service import sync_user_emails
    from unittest.mock import Mock

    user, _ = seed_email()
    with patch("app.blueprints.gmail.sync_service.list_message_ids", return_value=([], "third-page")) as listing:
        result = sync_user_emails(user, Mock(), page_token="second-page")
    assert listing.call_args.kwargs["page_token"] == "second-page"
    assert result["next_page_token"] == "third-page"


def test_sender_rule_is_opt_in_and_user_scoped(app):
    from app.extensions import db
    from app.models import Email, User
    from app.blueprints.feedback.service import apply_feedback_rules

    user, email = seed_email()
    client = authenticated_client(app, user)
    assert client.post(f"/emails/{email.id}/feedback", json={
        "feedback_type": "category", "corrected_value": "Finance",
    }).status_code == 200
    future = Email(user_id=user.id, sender="Other <other@example.com>", category="Work")
    apply_feedback_rules(future)
    assert future.category == "Work"
    assert client.post(f"/emails/{email.id}/feedback", json={
        "feedback_type": "category", "corrected_value": "Finance", "apply_to_sender": True,
    }).status_code == 200
    apply_feedback_rules(future)
    assert future.category == "Finance"
    other_user = User(google_id="other-user", email="second@example.com")
    db.session.add(other_user)
    db.session.flush()
    unrelated = Email(user_id=other_user.id, sender="other@example.com", category="Work")
    apply_feedback_rules(unrelated)
    assert unrelated.category == "Work"
    assert client.post(f"/emails/{email.id}/feedback", json={
        "feedback_type": "category", "corrected_value": "Personal", "apply_to_sender": False,
    }).status_code == 200
    future.category = "Work"
    apply_feedback_rules(future)
    assert future.category == "Work"


def test_quoted_question_does_not_trigger_followup():
    from types import SimpleNamespace
    from app.blueprints.followup.detector import needs_response
    email = SimpleNamespace(subject="Update", body="Confirmed.\nOn Monday Alex wrote:\nCan you confirm?",
                            actions=[], priority="LOW")
    assert needs_response(email) is False


def test_relative_time_and_sender_timezone(app):
    import json
    from app.blueprints.nlp_features.service import process_email_nlp

    _, email = seed_email()
    email.body = "Send the report by tomorrow at 3:30 pm."
    email.raw_payload = json.dumps({"payload": {"headers": [
        {"name": "Date", "value": "Thu, 01 Jan 2026 12:00:00 +0530"},
    ]}})
    process_email_nlp(email)
    assert email.reminders[0].deadline_at == datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc)


def test_eod_tomorrow_uses_next_day():
    from app.blueprints.nlp_features.deadline_extractor import extract_deadlines
    reference = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    deadlines = extract_deadlines("Please finish by EOD tomorrow.", reference_time=reference)
    assert deadlines[0]["deadline_at"] == reference.replace(hour=17) + timedelta(days=1)


def test_human_review_evaluation_counts_errors():
    from ml.evaluate_reviewed import evaluate_rows
    rows = [{"priority": "HIGH"}, {"priority": "LOW"}]
    report = evaluate_rows(rows, {"priority": lambda row: "LOW"})
    assert report["tasks"]["priority"]["accuracy"] == 0.5
    with pytest.raises(ValueError):
        evaluate_rows([{"spam_label": "maybe"}], {})
