"""
Phase 10 JSON API:

  POST /followups/detect  -> rescan the logged-in user's whole mailbox
                              and refresh every email's needs_follow_up
                              flag

This also runs automatically at the end of every Gmail sync (see
gmail/sync_service.py) — this route exists for on-demand rechecking
(e.g. if enough time has passed that something newly counts as stale)
and so this feature is independently testable (rule #20).
"""

from flask import Blueprint, jsonify, session

from app.blueprints.auth.decorators import login_required
from app.blueprints.followup.service import detect_pending_follow_ups

followup_bp = Blueprint("followup", __name__, url_prefix="/followups")


@followup_bp.route("/detect", methods=["POST"])
@login_required
def detect():
    result = detect_pending_follow_ups(session["user_id"])
    return jsonify(result)
