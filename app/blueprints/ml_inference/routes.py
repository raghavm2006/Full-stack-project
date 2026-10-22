"""
Phase 7 JSON API:

  POST /ml/classify/<email_id>  -> (re)classify one email on demand
  POST /ml/classify-all         -> backfill every unclassified email for
                                    the logged-in user (e.g. emails synced
                                    before Phase 7's models existed, or
                                    after retraining with more data)

New emails synced from here on are classified automatically as part of
gmail/sync_service.sync_user_emails() — these routes exist for on-demand
re-classification and backfilling, and so this feature is independently
testable (rule #20) without needing a fresh Gmail sync.
"""

from flask import Blueprint, jsonify, session, Response

from app.blueprints.auth.decorators import login_required
from app.blueprints.ml_inference.classifier import classify_email
from app.blueprints.emails.serializers import to_detail_dict
from app.extensions import db
from app.models import Email, UserFeedback

ml_inference_bp = Blueprint("ml_inference", __name__, url_prefix="/ml")


@ml_inference_bp.get("/review-sample.csv")
@login_required
def review_sample():
    import csv
    import io
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(["subject", "body", "sender", "category", "priority", "spam_label"])
    def safe_cell(value):
        value = value or ""
        return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value
    for email in Email.query.filter_by(user_id=session["user_id"]).order_by(Email.timestamp.desc(), Email.id.desc()).limit(300):
        # Labels deliberately blank: predictions are not human ground truth.
        writer.writerow([safe_cell(email.subject), safe_cell(email.body), safe_cell(email.sender), "", "", ""])
    response = Response(stream.getvalue(), mimetype="text/csv")
    response.headers["Content-Disposition"] = 'attachment; filename="emailorbit-review.csv"'
    response.headers["Cache-Control"] = "no-store"
    return response


@ml_inference_bp.route("/classify/<int:email_id>", methods=["POST"])
@login_required
def classify_one(email_id):
    email = Email.query.filter_by(id=email_id, user_id=session["user_id"]).first()
    if email is None:
        return jsonify({"error": "Email not found"}), 404

    ran = classify_email(email)
    _restore_corrections(email)
    db.session.commit()

    if not any(ran.values()):
        return jsonify({
            "error": "No trained models found. Run the Phase 6 training scripts "
                     "(python -m ml.<task>.preprocess && python -m ml.<task>.train) first."
        }), 503

    return jsonify({"ran": ran, "email": to_detail_dict(email)})


@ml_inference_bp.route("/classify-all", methods=["POST"])
@login_required
def classify_all():
    emails = Email.query.filter_by(user_id=session["user_id"]).filter(
        db.or_(Email.category.is_(None), Email.priority.is_(None), Email.spam_label.is_(None))
    ).all()

    if not emails:
        return jsonify({"classified": 0, "message": "Nothing to classify — every email already has all predictions."})

    classified = 0
    any_model_ran = False
    for email in emails:
        existing = {field: (getattr(email, field), getattr(email, confidence))
                    for field, confidence in (("category", "category_confidence"),
                                              ("priority", "priority_confidence"),
                                              ("spam_label", "spam_probability"))}
        ran = classify_email(email)
        for field, confidence in (("category", "category_confidence"),
                                  ("priority", "priority_confidence"),
                                  ("spam_label", "spam_probability")):
            value, score = existing[field]
            if value is not None:
                setattr(email, field, value)
                setattr(email, confidence, score)
        _restore_corrections(email)
        if any(ran.values()):
            any_model_ran = True
            classified += 1

    db.session.commit()

    if not any_model_ran:
        return jsonify({
            "error": "No trained models found. Run the Phase 6 training scripts first.",
        }), 503

    return jsonify({"classified": classified, "total_considered": len(emails)})


def _restore_corrections(email):
    corrections = UserFeedback.query.filter_by(
        user_id=email.user_id, email_id=email.id
    ).order_by(UserFeedback.id.asc()).all()
    for correction in corrections:
        if correction.feedback_type in ("category", "priority"):
            setattr(email, correction.feedback_type, correction.corrected_value)
