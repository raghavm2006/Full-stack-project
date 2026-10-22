"""
Phase 11: end-to-end pipeline integration test.

Every earlier phase has its own unit tests that mock out its neighbors
(classify_email() tests monkeypatch predict_category, etc.) — that's
deliberate (rule #20, independently testable features) but it means no
single test proves the phases actually compose correctly when wired
together for a real sync. This file does that: it trains tiny (but
real) scikit-learn models on the fly, points the app at them, fakes out
the Gmail API, and runs one real `sync_user_emails()` call end to end,
then asserts every phase's field actually got populated on the
resulting Email row — categorization/spam/priority (Phase 7), summary/
actions/reminders (Phase 8), smart replies (Phase 9, template fallback
since no API key is configured here), and follow-up/duplicate flags
(Phase 10).

Run with: pytest tests/test_integration_pipeline.py -v
"""

import base64
import json
import os

import joblib
import numpy as np
import pytest
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

os.environ.setdefault("FLASK_ENV", "testing")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("ENCRYPTION_KEY", "kx6Qv6VU6m2yjcVQ2rC0j0y3Q1sV2v9b2b5h1z2m4kA=")
os.environ["TEST_DATABASE_URI"] = "sqlite:///:memory:"


def _b64url(text):
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def sample_message(msg_id, subject, body_text):
    return {
        "id": msg_id,
        "threadId": f"thread-{msg_id}",
        "internalDate": "1700000000000",
        "labelIds": ["UNREAD"],
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "From", "value": "colleague@example.com"},
                {"name": "To", "value": "student@example.com"},
                {"name": "Subject", "value": subject},
            ],
            "body": {"data": _b64url(body_text)},
        },
    }


class _FakeMessagesResource:
    def __init__(self, messages_by_id):
        self._messages_by_id = messages_by_id

    def list(self, userId, maxResults, pageToken=None, q=None):  # noqa: N803 - matches Gmail API's actual param casing
        ids = list(self._messages_by_id.keys())
        return _FakeExecutable({"messages": [{"id": i} for i in ids]})

    def get(self, userId, id, format):  # noqa: N803,A002 - matches Gmail API's actual signature
        return _FakeExecutable(self._messages_by_id[id])


class _FakeExecutable:
    def __init__(self, payload):
        self._payload = payload

    def execute(self):
        return self._payload


class FakeGmailService:
    def __init__(self, messages_by_id):
        self._messages = _FakeMessagesResource(messages_by_id)

    def users(self):
        return self

    def messages(self):
        return self._messages


def _build_priority_artifacts(model_dir):
    """
    Trains a tiny (real, not mocked) TF-IDF + LogisticRegression +
    StandardScaler pipeline on a handful of hand-labeled examples — just
    enough for predict_priority() to run its real code path end to end,
    not a stand-in for Phase 6's actual training quality.
    """
    from ml.priority_detection.feature_engineering import extract_features
    from ml.priority_detection.preprocess import FEATURE_COLUMNS

    texts = [
        "urgent please respond asap deadline today",
        "urgent action required immediately",
        "let's catch up sometime no rush",
        "fyi sharing this for your records",
    ]
    labels = ["HIGH", "HIGH", "LOW", "LOW"]
    subjects = ["URGENT", "URGENT: action needed", "Catch up", "FYI"]

    vectorizer = TfidfVectorizer()
    text_matrix = vectorizer.fit_transform(texts)

    numeric_rows = [
        [extract_features(subj, text, "colleague@example.com")[col] for col in FEATURE_COLUMNS]
        for subj, text in zip(subjects, texts)
    ]
    scaler = StandardScaler()
    numeric_scaled = scaler.fit_transform(np.array(numeric_rows))

    from scipy.sparse import hstack

    X = hstack([text_matrix, numeric_scaled]).tocsr()
    model = LogisticRegression(max_iter=1000)
    model.fit(X, labels)

    os.makedirs(model_dir, exist_ok=True)
    joblib.dump(model, os.path.join(model_dir, "production_model.joblib"))
    joblib.dump(vectorizer, os.path.join(model_dir, "vectorizer.joblib"))
    joblib.dump(scaler, os.path.join(model_dir, "scaler.joblib"))


def _build_text_classifier_artifacts(model_dir, texts, labels):
    """Shared by categorization (Work/Personal) and spam (0/1): a tiny
    TF-IDF + LogisticRegression pair saved under the production_* names
    predictors.py loads."""
    vectorizer = TfidfVectorizer()
    X = vectorizer.fit_transform(texts)
    model = LogisticRegression(max_iter=1000)
    model.fit(X, labels)

    os.makedirs(model_dir, exist_ok=True)
    joblib.dump(model, os.path.join(model_dir, "production_model.joblib"))
    joblib.dump(vectorizer, os.path.join(model_dir, "production_vectorizer.joblib"))


@pytest.fixture
def app(tmp_path):
    from app import create_app
    from app.blueprints.ml_inference import predictors
    from app.extensions import db

    application = create_app("testing")
    application.config["MODELS_DIR"] = str(tmp_path)

    _build_text_classifier_artifacts(
        os.path.join(str(tmp_path), "categorization"),
        texts=["project deadline meeting report", "project deadline meeting report",
               "family dinner weekend plans", "family dinner weekend plans"],
        labels=["Work", "Work", "Personal", "Personal"],
    )
    _build_text_classifier_artifacts(
        os.path.join(str(tmp_path), "spam"),
        texts=["win a free prize now click here", "win a free prize now click here",
               "let's meet for the quarterly review", "let's meet for the quarterly review"],
        labels=[1, 1, 0, 0],
    )
    _build_priority_artifacts(os.path.join(str(tmp_path), "priority"))

    predictors.clear_cache()

    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()

    predictors.clear_cache()


def make_user_id(app):
    """
    Creates the user in its own short-lived app context and returns just
    the id — callers re-fetch inside their own already-open app context
    with db.session.get(). Returning the ORM object itself would leave
    it DetachedInstanceError-prone once this function's own context pops
    (Flask-SQLAlchemy tears the session down on app context pop).
    """
    from app.extensions import db
    from app.models import User

    with app.app_context():
        user = User(
            google_id="google-123",
            email="student@example.com",
            gmail_scope_granted=True,
            oauth_token_encrypted="placeholder",
            oauth_refresh_token_encrypted="placeholder",
        )
        db.session.add(user)
        db.session.commit()
        return user.id


def test_full_sync_pipeline_populates_every_phases_fields(app):
    """
    One real sync, through every phase's real code (only the three ML
    models are swapped for tiny ones — everything else is production
    code): classification, NLP extraction, smart replies, and follow-up/
    duplicate detection should all leave their mark on the stored Email.
    """
    from app.blueprints.gmail.sync_service import sync_user_emails
    from app.extensions import db
    from app.models import Email, User

    user_id = make_user_id(app)

    with app.app_context():
        user = db.session.get(User, user_id)

        service = FakeGmailService({
            "m1": sample_message(
                "m1",
                subject="URGENT: project deadline",
                body_text=(
                    "This is urgent, please respond asap. "
                    "Can you send the report by tomorrow? "
                    "Let me know if you have questions."
                ),
            ),
        })

        result = sync_user_emails(user, service, max_results=10)
        assert result["synced"] == 1

        email = Email.query.filter_by(user_id=user.id, gmail_message_id="m1").first()
        assert email is not None

        # Phase 7: categorization + spam + priority all ran.
        assert email.category in ("Work", "Personal")
        assert email.category_confidence is not None
        assert email.spam_label in (True, False)
        assert email.priority in ("HIGH", "MEDIUM", "LOW")

        # Phase 8: summary + at least one action item + one deadline —
        # this email's text was written specifically to trigger both.
        assert email.summary
        assert len(email.actions) >= 1
        assert len(email.reminders) >= 1

        # Phase 9: smart replies ran using the template fallback (no
        # ANTHROPIC_API_KEY configured in the test environment).
        assert email.smart_replies
        assert json.loads(email.smart_replies)
        assert email.smart_reply_source == "template"

        # Phase 10: sample_message() uses a fixed 2023 internalDate, so
        # this email is well past the 2-day staleness threshold — since
        # it contains a question and nobody has replied, it SHOULD be
        # flagged for follow-up. It's the only email synced, so it can't
        # be a duplicate of anything.
        assert email.needs_follow_up is True
        assert email.is_duplicate is False
        assert result["duplicates_found"] == 0
        assert result["needs_follow_up"] == 1


def test_full_sync_pipeline_flags_exact_duplicate_within_same_batch(app):
    """
    Duplicate detection runs once at the end of the whole sync batch
    (see sync_service.py's docstring) specifically so that two identical
    emails arriving in the SAME sync are still caught — this proves that
    design choice actually works, not just duplicates found across
    separate syncs.
    """
    from app.blueprints.gmail.sync_service import sync_user_emails
    from app.extensions import db
    from app.models import Email, User

    user_id = make_user_id(app)

    with app.app_context():
        user = db.session.get(User, user_id)

        same_body = "Quarterly newsletter — nothing urgent here."
        service = FakeGmailService({
            "m1": sample_message("m1", subject="Newsletter", body_text=same_body),
            "m2": sample_message("m2", subject="Newsletter", body_text=same_body),
        })

        result = sync_user_emails(user, service, max_results=10)
        assert result["duplicates_found"] == 1

        emails = Email.query.filter_by(user_id=user.id).order_by(Email.gmail_message_id).all()
        assert emails[0].is_duplicate is False
        assert emails[1].is_duplicate is True
        assert emails[1].duplicate_of_email_id == emails[0].id
