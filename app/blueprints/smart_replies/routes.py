"""
Phase 9 JSON API — mirrors Phases 7/8's route pattern:

  POST /replies/generate/<email_id>  -> (re)generate smart replies for
                                         one email
  POST /replies/generate-all         -> backfill every email that
                                         doesn't have smart replies yet

New, non-spam emails get replies generated automatically during Gmail
sync (see gmail/sync_service.py) — these routes exist for on-demand
regeneration and backfilling, and so this feature is independently
testable (rule #20) without a fresh Gmail sync or a configured API key.
"""

from flask import Blueprint, jsonify, session

from app.blueprints.auth.decorators import login_required
from app.blueprints.emails.serializers import to_detail_dict
from app.blueprints.smart_replies.service import generate_smart_replies
from app.extensions import db
from app.models import Email

smart_replies_bp = Blueprint("smart_replies", __name__, url_prefix="/replies")


@smart_replies_bp.route("/generate/<int:email_id>", methods=["POST"])
@login_required
def generate_one(email_id):
    email = Email.query.filter_by(id=email_id, user_id=session["user_id"]).first()
    if email is None:
        return jsonify({"error": "Email not found"}), 404

    result = generate_smart_replies(email)
    db.session.commit()

    return jsonify({"result": result, "email": to_detail_dict(email)})


@smart_replies_bp.route("/generate-all", methods=["POST"])
@login_required
def generate_all():
    emails = Email.query.filter_by(user_id=session["user_id"], smart_replies=None).all()

    if not emails:
        return jsonify({
            "processed": 0,
            "message": "Nothing to process — every email already has smart replies.",
        })

    source_counts = {"llm": 0, "template": 0}
    for email in emails:
        result = generate_smart_replies(email)
        source_counts[result["source"]] += 1

    db.session.commit()

    return jsonify({"processed": len(emails), "source_counts": source_counts})
