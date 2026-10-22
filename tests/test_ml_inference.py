"""
Phase 7 verification tests.

Run with: pytest tests/test_ml_inference.py -v

Real trained models aren't available in every environment (they're
produced by running Phase 6's scripts against real datasets), so these
tests verify the parts that don't require one:
  - the predict_proba/decision_function confidence-extraction logic,
    using small hand-built mock estimators that mimic sklearn's interface
  - ModelNotTrainedError is raised (not a crash) when artifacts are missing
  - classify_email() correctly wires predictions onto an Email row
  - the /ml/classify/* routes, with predictions mocked out
"""

import os
from datetime import datetime, timedelta, timezone

import numpy as np
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


def make_email(app, user_id, gmail_message_id, subject="Subject", body="Body", category=None):
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
            category=category,
        )
        db.session.add(email)
        db.session.commit()
        return email.id


def login(client, user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


# --- _predict_with_confidence: the algorithm-agnostic confidence logic ---

class _ProbaModel:
    """Mimics LogisticRegression/MultinomialNB: has predict_proba + classes_."""
    classes_ = np.array(["LOW", "MEDIUM", "HIGH"])

    def predict_proba(self, X):
        return np.array([[0.1, 0.2, 0.7]])


class _BinaryDecisionModel:
    """Mimics LinearSVC on a binary task (spam): one scalar score per sample."""
    classes_ = np.array([0, 1])

    def decision_function(self, X):
        return np.array([1.5])  # positive score -> favors class 1


class _MulticlassDecisionModel:
    """Mimics LinearSVC on a multiclass task (categorization): one-vs-rest scores."""
    classes_ = np.array(["Other", "Personal", "Work"])

    def decision_function(self, X):
        return np.array([[0.1, 0.2, 0.9]])  # highest score -> "Work"


def test_predict_with_confidence_uses_predict_proba_when_available():
    from app.blueprints.ml_inference.predictors import _predict_with_confidence

    label, confidence = _predict_with_confidence(_ProbaModel(), X=None)
    assert label == "HIGH"
    assert confidence == pytest.approx(0.7)


def test_predict_with_confidence_handles_binary_decision_function():
    from app.blueprints.ml_inference.predictors import _predict_with_confidence

    label, confidence = _predict_with_confidence(_BinaryDecisionModel(), X=None)
    assert label == 1
    assert 0.5 < confidence <= 1.0


def test_predict_with_confidence_handles_multiclass_decision_function():
    from app.blueprints.ml_inference.predictors import _predict_with_confidence

    label, confidence = _predict_with_confidence(_MulticlassDecisionModel(), X=None)
    assert label == "Work"
    assert 0 < confidence <= 1.0


# --- ModelNotTrainedError ---

def test_predict_category_raises_clear_error_when_untrained(app, tmp_path):
    from app.blueprints.ml_inference import predictors

    with app.app_context():
        app.config["MODELS_DIR"] = str(tmp_path)  # empty dir — no models here
        predictors.clear_cache()
        with pytest.raises(predictors.ModelNotTrainedError):
            predictors.predict_category("some text")


# --- classify_email() wiring ---

def test_classify_email_sets_fields_from_predictions(app, monkeypatch):
    from app.blueprints.ml_inference import classifier
    from app.models import Email

    monkeypatch.setattr(classifier, "predict_category", lambda text: ("Work", 0.9))
    monkeypatch.setattr(classifier, "predict_spam", lambda text: (False, 0.95))
    monkeypatch.setattr(classifier, "predict_priority", lambda subject, body, sender: ("HIGH", 0.8))

    email = Email(subject="Meeting", body="Let's sync tomorrow", sender="a@b.com")
    ran = classifier.classify_email(email)

    assert ran == {"category": True, "spam": True, "priority": True}
    assert email.category == "Work"
    assert email.category_confidence == 0.9
    assert email.spam_label is False
    assert email.spam_probability == 0.95
    assert email.priority == "HIGH"
    assert email.priority_confidence == 0.8


def test_classify_email_survives_partial_model_availability(app, monkeypatch):
    """If only some models are trained, the others should stay None, not crash."""
    from app.blueprints.ml_inference import classifier
    from app.blueprints.ml_inference.predictors import ModelNotTrainedError
    from app.models import Email

    monkeypatch.setattr(classifier, "predict_category", lambda text: ("Work", 0.9))

    def _raise(*args, **kwargs):
        raise ModelNotTrainedError("not trained")

    monkeypatch.setattr(classifier, "predict_spam", _raise)
    monkeypatch.setattr(classifier, "predict_priority", _raise)

    email = Email(subject="s", body="b", sender="a@b.com")
    ran = classifier.classify_email(email)

    assert ran == {"category": True, "spam": False, "priority": False}
    assert email.category == "Work"
    assert email.spam_label is None
    assert email.priority is None


# --- routes ---

def test_classify_one_requires_login(client):
    response = client.post("/ml/classify/1")
    assert response.status_code == 401


def test_classify_one_blocks_other_users_email(app, client, monkeypatch):
    from app.blueprints.ml_inference import classifier

    monkeypatch.setattr(classifier, "predict_category", lambda text: ("Work", 0.9))

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
    response = client.post(f"/ml/classify/{other_email_id}")
    assert response.status_code == 404


def test_classify_one_returns_503_when_no_models_trained(app, client, monkeypatch):
    from app.blueprints.ml_inference import classifier
    from app.blueprints.ml_inference.predictors import ModelNotTrainedError

    def _raise(*args, **kwargs):
        raise ModelNotTrainedError("not trained")

    monkeypatch.setattr(classifier, "predict_category", _raise)
    monkeypatch.setattr(classifier, "predict_spam", _raise)
    monkeypatch.setattr(classifier, "predict_priority", _raise)

    user_id = make_user(app)
    email_id = make_email(app, user_id, "m1")
    login(client, user_id)

    response = client.post(f"/ml/classify/{email_id}")
    assert response.status_code == 503


def test_classify_one_success_updates_and_returns_email(app, client, monkeypatch):
    from app.blueprints.ml_inference import classifier

    monkeypatch.setattr(classifier, "predict_category", lambda text: ("Personal", 0.6))
    monkeypatch.setattr(classifier, "predict_spam", lambda text: (True, 0.99))
    monkeypatch.setattr(classifier, "predict_priority", lambda subject, body, sender: ("LOW", 0.5))

    user_id = make_user(app)
    email_id = make_email(app, user_id, "m1")
    login(client, user_id)

    response = client.post(f"/ml/classify/{email_id}")
    assert response.status_code == 200
    data = response.get_json()
    assert data["ran"] == {"category": True, "spam": True, "priority": True}
    assert data["email"]["category"] == "Personal"
    assert data["email"]["spam_label"] is True


def test_classify_all_skips_fully_classified_emails(app, client, monkeypatch):
    from app.blueprints.ml_inference import classifier
    from app.extensions import db
    from app.models import Email

    calls = []

    def _track_category(text):
        calls.append(text)
        return "Work", 0.9

    monkeypatch.setattr(classifier, "predict_category", _track_category)
    monkeypatch.setattr(classifier, "predict_spam", lambda text: (False, 0.9))
    monkeypatch.setattr(classifier, "predict_priority", lambda subject, body, sender: ("LOW", 0.9))

    user_id = make_user(app)
    done_id = make_email(app, user_id, "already-done", category="Work")
    with app.app_context():
        done = db.session.get(Email, done_id)
        done.priority = "LOW"
        done.spam_label = False
        db.session.commit()
    make_email(app, user_id, "needs-classification", category=None)
    login(client, user_id)

    response = client.post("/ml/classify-all")
    assert response.status_code == 200
    data = response.get_json()
    assert data["classified"] == 1
    assert len(calls) == 1  # only the uncategorized one was classified
