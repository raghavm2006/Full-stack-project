"""
Bridges app/blueprints/ml_inference/predictors.py (pure ML, no DB
knowledge) to the Email model. Kept separate from routes.py so this same
function can be called from two places: gmail/sync_service.py (classify
automatically the moment an email is synced) and ml_inference/routes.py
(manual/backfill re-classification for emails synced before Phase 7
existed, or after retraining a model).
"""

from app.blueprints.ml_inference.predictors import ModelNotTrainedError, predict_category, predict_priority, predict_spam


def classify_email(email) -> dict:
    """
    Mutates `email` in place with category/priority/spam predictions.
    Does NOT commit — callers decide when to commit (a sync loop commits
    once at the end; a single manual reclassify commits immediately).

    Returns which of the three predictions actually ran, so callers can
    tell "no models trained yet" apart from "ran but nothing changed".
    """
    text = f"{email.subject or ''}\n{email.body or ''}"
    ran = {"category": False, "spam": False, "priority": False}

    try:
        category, confidence = predict_category(text)
        email.category = category
        email.category_confidence = confidence
        ran["category"] = True
    except ModelNotTrainedError:
        pass

    try:
        is_spam, confidence = predict_spam(text)
        email.spam_label = is_spam
        email.spam_probability = confidence
        ran["spam"] = True
    except ModelNotTrainedError:
        pass

    try:
        priority, confidence = predict_priority(email.subject or "", email.body or "", email.sender or "")
        email.priority = priority
        email.priority_confidence = confidence
        ran["priority"] = True
    except ModelNotTrainedError:
        pass

    from app.blueprints.feedback.service import apply_feedback_rules
    apply_feedback_rules(email)
    return ran
