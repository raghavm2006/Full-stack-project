"""
Phase 4: read-only + read-status JSON endpoints over the Email table.

  GET   /emails                 -> paginated inbox list for the logged-in user
  GET   /emails/<id>             -> full detail for one email (with parsed body)
  PATCH /emails/<id>/read        -> mark an email read/unread
  POST  /emails/<id>/feedback    -> Phase 10: correct a category/priority
                                     prediction (personalization)

These are plain JSON APIs — Phase 5 builds the Bootstrap inbox UI that
calls them. Every route here scopes queries to the logged-in user's own
emails (rule #17): looking up someone else's email id returns 404, not
someone else's data.
"""

from flask import Blueprint, jsonify, request, session

from app.blueprints.auth.decorators import login_required
from app.blueprints.emails.serializers import to_detail_dict, to_summary_dict
from app.extensions import db
from app.models import Email, UserFeedback
from app.utils.validators import ValidationError, parse_bool_param, parse_pagination

emails_bp = Blueprint("emails", __name__, url_prefix="/emails")


def _current_user_id():
    return session["user_id"]


@emails_bp.route("")
@login_required
def list_emails():
    try:
        page, per_page = parse_pagination(request.args)
        is_read = parse_bool_param(request.args, "is_read")
        spam_label = parse_bool_param(request.args, "spam_label")
    except ValidationError as exc:
        return jsonify({"error": exc.message}), 400

    query = Email.query.filter_by(user_id=_current_user_id())

    category = request.args.get("category")
    if category:
        query = query.filter_by(category=category)

    priority = request.args.get("priority")
    if priority:
        query = query.filter_by(priority=priority)

    if is_read is not None:
        query = query.filter_by(is_read=is_read)
    if spam_label is not None:
        query = query.filter_by(spam_label=spam_label)

    try:
        needs_follow_up = parse_bool_param(request.args, "needs_follow_up")
        is_duplicate = parse_bool_param(request.args, "is_duplicate")
    except ValidationError as exc:
        return jsonify({"error": exc.message}), 400

    if needs_follow_up is not None:
        query = query.filter_by(needs_follow_up=needs_follow_up)

    if is_duplicate is not None:
        query = query.filter_by(is_duplicate=is_duplicate)

    search = request.args.get("q", "").strip()[:200]
    if search:
        query = query.filter(db.or_(
            Email.sender.contains(search, autoescape=True),
            Email.subject.contains(search, autoescape=True),
            Email.body.contains(search, autoescape=True),
        ))
    sort = request.args.get("sort", "newest")
    if sort == "oldest":
        query = query.order_by(Email.timestamp.asc(), Email.id.asc())
    elif sort == "priority":
        query = query.order_by(db.case((Email.priority == "HIGH", 0),
                                      (Email.priority == "MEDIUM", 1), else_=2),
                               Email.timestamp.desc(), Email.id.desc())
    else:
        query = query.order_by(Email.timestamp.desc(), Email.id.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        "emails": [to_summary_dict(e) for e in pagination.items],
        "page": page,
        "per_page": per_page,
        "total": pagination.total,
        "total_pages": pagination.pages,
    })


@emails_bp.route("/<int:email_id>")
@login_required
def get_email(email_id):
    email = Email.query.filter_by(id=email_id, user_id=_current_user_id()).first()
    if email is None:
        return jsonify({"error": "Email not found"}), 404

    return jsonify(to_detail_dict(email))


@emails_bp.route("/<int:email_id>/read", methods=["PATCH"])
@login_required
def set_read_status(email_id):
    email = Email.query.filter_by(id=email_id, user_id=_current_user_id()).first()
    if email is None:
        return jsonify({"error": "Email not found"}), 404

    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400
    if "is_read" not in payload or not isinstance(payload["is_read"], bool):
        return jsonify({"error": "Request body must include boolean 'is_read'"}), 400

    email.is_read = payload["is_read"]
    db.session.commit()

    return jsonify(to_detail_dict(email))


@emails_bp.route("/<int:email_id>/feedback", methods=["POST"])
@login_required
def submit_feedback(email_id):
    """
    Phase 10 personalization: records a user's correction to a
    category/priority prediction (rule #20 — testable independently of
    any model retraining) AND applies it immediately to this email, so
    the user sees their own correction reflected right away rather than
    waiting for some future retrain that may never happen in this
    project's scope.
    """
    email = Email.query.filter_by(id=email_id, user_id=_current_user_id()).first()
    if email is None:
        return jsonify({"error": "Email not found"}), 404

    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400
    feedback_type = payload.get("feedback_type")
    corrected_value = payload.get("corrected_value")
    apply_to_sender = payload.get("apply_to_sender", False)
    if not isinstance(apply_to_sender, bool):
        return jsonify({"error": "apply_to_sender must be a boolean"}), 400

    if feedback_type not in ("category", "priority"):
        return jsonify({"error": "feedback_type must be 'category' or 'priority'"}), 400
    if not corrected_value or not isinstance(corrected_value, str):
        return jsonify({"error": "corrected_value is required"}), 400
    allowed_values = {
        "category": ("Work", "Education", "Personal", "Finance", "Shopping", "Travel", "Social", "Promotions", "Other"),
        "priority": ("HIGH", "MEDIUM", "LOW"),
    }
    if corrected_value not in allowed_values[feedback_type]:
        return jsonify({"error": "Invalid corrected_value for " + feedback_type}), 400

    original_value = email.category if feedback_type == "category" else email.priority

    feedback = UserFeedback(
        user_id=_current_user_id(),
        email_id=email.id,
        feedback_type=feedback_type,
        original_value=original_value,
        corrected_value=corrected_value,
        apply_to_sender=apply_to_sender,
    )
    db.session.add(feedback)

    if feedback_type == "category":
        email.category = corrected_value
    else:
        email.priority = corrected_value

    db.session.commit()

    return jsonify({"feedback_id": feedback.id, "email": to_detail_dict(email)})
