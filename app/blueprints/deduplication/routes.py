"""
Phase 10 JSON API:

  POST /duplicates/detect  -> rescan the logged-in user's whole mailbox
                               for exact-content duplicates

This also runs automatically at the end of every Gmail sync (see
gmail/sync_service.py) — this route exists for on-demand rescanning and
so this feature is independently testable (rule #20).
"""

from flask import Blueprint, jsonify, session

from app.blueprints.auth.decorators import login_required
from app.blueprints.deduplication.service import detect_duplicate_emails

deduplication_bp = Blueprint("deduplication", __name__, url_prefix="/duplicates")


@deduplication_bp.route("/detect", methods=["POST"])
@login_required
def detect():
    result = detect_duplicate_emails(session["user_id"])
    return jsonify(result)
