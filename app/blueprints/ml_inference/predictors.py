"""
Phase 7: loads Phase 6's trained .joblib artifacts and runs inference.

Rules #14/#15: this module NEVER trains anything — it only loads
`production_*.joblib` files that ml/<task>/train.py already produced, and
raises a clear error if they don't exist yet rather than silently
training on the fly during a web request.

Models are loaded once per process and cached in memory (joblib.load is
real disk I/O; doing it on every prediction would be wasteful and is
exactly the kind of per-request cost rule #15 asks us to avoid).
"""

import os

import joblib
import numpy as np
from flask import current_app
from scipy.sparse import hstack

# Feature order must exactly match ml/priority_detection/preprocess.py's
# FEATURE_COLUMNS — imported directly from there (not redefined here) so
# training and inference can never drift out of sync with each other.
from ml.priority_detection.preprocess import FEATURE_COLUMNS
from ml.priority_detection.feature_engineering import extract_features
from ml.common.text_cleaning import clean_for_vectorizer

_CACHE = {}


class ModelNotTrainedError(Exception):
    """Raised when a task's production model/vectorizer hasn't been produced yet."""


def _load_artifacts(task: str, filenames: dict) -> dict:
    if task in _CACHE:
        return _CACHE[task]

    task_dir = os.path.join(current_app.config["MODELS_DIR"], task)
    artifacts = {}
    for key, filename in filenames.items():
        path = os.path.join(task_dir, filename)
        if not os.path.exists(path):
            raise ModelNotTrainedError(
                f"No trained {task} model found at {path}. Run "
                f"`python -m ml.{task}.preprocess` and `python -m ml.{task}.train` first."
            )
        artifacts[key] = joblib.load(path)

    _CACHE[task] = artifacts
    return artifacts


def clear_cache():
    """Used by tests, and useful after retraining a model without restarting the app."""
    _CACHE.clear()


def _predict_with_confidence(model, X):
    """
    Returns (predicted_label, confidence in [0, 1]) regardless of which
    algorithm won a task's train.py comparison — LogisticRegression/
    NaiveBayes expose predict_proba, but LinearSVC only exposes
    decision_function, and this project's "best by F1" model varies by
    task and by dataset. Handling both here means routes.py never needs
    to know or care which algorithm is currently in production.
    """
    if hasattr(model, "predict_proba"):
        proba = model.predict_proba(X)[0]
        idx = int(np.argmax(proba))
        return model.classes_[idx], float(proba[idx])

    if hasattr(model, "decision_function"):
        scores = np.asarray(model.decision_function(X))[0]

        if np.ndim(scores) == 0 or np.asarray(scores).shape == ():
            # Binary LinearSVC: a single scalar score (distance from the
            # hyperplane toward classes_[1]) — squash it into a pseudo-
            # probability with a logistic function. This is NOT a
            # calibrated probability, just a monotonic confidence proxy.
            score = float(scores)
            prob_positive = 1 / (1 + np.exp(-score))
            idx = 1 if prob_positive >= 0.5 else 0
            confidence = prob_positive if idx == 1 else 1 - prob_positive
            return model.classes_[idx], float(confidence)

        # Multiclass one-vs-rest: softmax the per-class scores into
        # pseudo-probabilities that sum to 1, then take the max.
        exp_scores = np.exp(scores - np.max(scores))
        proba = exp_scores / exp_scores.sum()
        idx = int(np.argmax(proba))
        return model.classes_[idx], float(proba[idx])

    # No confidence signal available at all — shouldn't happen for any
    # model this project's train.py scripts produce, but fail soft.
    return model.predict(X)[0], 1.0


def predict_category(text: str):
    """Returns (category: str, confidence: float). Categories are Work/Personal/Other — see ml/categorization/preprocess.py's scope note."""
    artifacts = _load_artifacts("categorization", {
        "model": "production_model.joblib",
        "vectorizer": "production_vectorizer.joblib",
    })
    X = artifacts["vectorizer"].transform([clean_for_vectorizer(text)])
    return _predict_with_confidence(artifacts["model"], X)


def predict_spam(text: str):
    """Returns (is_spam: bool, confidence: float)."""
    artifacts = _load_artifacts("spam", {
        "model": "production_model.joblib",
        "vectorizer": "production_vectorizer.joblib",
    })
    X = artifacts["vectorizer"].transform([clean_for_vectorizer(text)])
    label, confidence = _predict_with_confidence(artifacts["model"], X)
    return bool(label == 1), confidence


def predict_priority(subject: str, body: str, sender: str):
    """
    Returns (priority: "HIGH"|"MEDIUM"|"LOW", confidence: float).

    Reminder (see ml/priority_detection/feature_engineering.py): this
    model was trained on heuristic pseudo-labels, not ground truth, so
    "confidence" here measures agreement with that heuristic rule, not
    real-world urgency judgment.
    """
    artifacts = _load_artifacts("priority", {
        "model": "production_model.joblib",
        "vectorizer": "vectorizer.joblib",
        "scaler": "scaler.joblib",
    })

    text = clean_for_vectorizer(f"{subject}\n{body}")
    text_matrix = artifacts["vectorizer"].transform([text])

    features = extract_features(subject, body, sender)
    numeric = np.array([[features[col] for col in FEATURE_COLUMNS]])
    numeric_scaled = artifacts["scaler"].transform(numeric)

    X = hstack([text_matrix, numeric_scaled]).tocsr()
    return _predict_with_confidence(artifacts["model"], X)
