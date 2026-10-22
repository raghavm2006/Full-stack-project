"""
Phase 8 JSON API — mirrors Phase 7's ml_inference/routes.py pattern:

  POST /nlp/process/<email_id>  -> (re)run summarization/action-item/
                                     deadline extraction for one email
  POST /nlp/process-all         -> backfill every email that doesn't
                                     have a summary yet (e.g. emails
                                     synced before Phase 8 existed)

New emails get these fields set automatically during Gmail sync from
Phase 8 onward (see gmail/sync_service.py) — these routes exist for
backfilling and on-demand reprocessing, and so this feature is
independently testable (rule #20) without a fresh Gmail sync.
"""

from flask import Blueprint, jsonify, session

from app.blueprints.auth.decorators import login_required
from app.blueprints.emails.serializers import to_detail_dict
from app.blueprints.nlp_features.service import process_email_nlp
from app.extensions import db
from app.models import Email

nlp_features_bp = Blueprint("nlp_features", __name__, url_prefix="/nlp")


@nlp_features_bp.route("/process/<int:email_id>", methods=["POST"])
@login_required
def process_one(email_id):
    email = Email.query.filter_by(id=email_id, user_id=session["user_id"]).first()
    if email is None:
        return jsonify({"error": "Email not found"}), 404

    result = process_email_nlp(email)
    db.session.commit()

    return jsonify({"result": result, "email": to_detail_dict(email)})


@nlp_features_bp.route("/process-all", methods=["POST"])
@login_required
def process_all():
    emails = Email.query.filter_by(user_id=session["user_id"], summary=None).all()

    if not emails:
        return jsonify({
            "processed": 0,
            "message": "Nothing to process — every email already has a summary.",
        })

    total_actions = 0
    total_deadlines = 0
    for email in emails:
        result = process_email_nlp(email)
        total_actions += result["actions_found"]
        total_deadlines += result["deadlines_found"]

    db.session.commit()

    return jsonify({
        "processed": len(emails),
        "actions_found": total_actions,
        "deadlines_found": total_deadlines,
    })
