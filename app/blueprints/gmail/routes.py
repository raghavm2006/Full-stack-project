"""
Phase 3: Gmail connection (incremental OAuth) and manual sync trigger.

  GET  /gmail/connect  -> redirect to Google, requesting gmail.readonly
                          ON TOP OF the Phase 2 login scopes (incremental
                          authorization; requires being logged in already)
  GET  /gmail/callback -> Google redirects back here; store the new
                          token/refresh token, mark gmail_scope_granted
  POST /gmail/sync     -> fetch recent messages and store new ones
"""

from flask import Blueprint, current_app, flash, jsonify, redirect, request, session, url_for

from app.blueprints.auth.decorators import login_required
from app.blueprints.auth.oauth import build_flow, fetch_google_user_info, update_mail_permissions
from app.blueprints.gmail.gmail_client import (
    GmailNotConnectedError,
    build_gmail_service,
    get_credentials_for_user,
)
from app.blueprints.gmail.sync_service import sync_user_emails
from app.extensions import db
from app.models import User, OutgoingMessage
from app.utils.crypto import encrypt_token

gmail_bp = Blueprint("gmail", __name__, url_prefix="/gmail")


def _gmail_redirect_uri():
    # Share the registered login callback; auth.callback dispatches by state.
    configured = current_app.config.get("GOOGLE_REDIRECT_URI")
    if not configured:
        raise RuntimeError("GOOGLE_REDIRECT_URI is not set. Check your .env file.")
    return configured


@gmail_bp.route("/connect")
@login_required
def connect():
    scopes = current_app.config["GOOGLE_LOGIN_SCOPES"] + current_app.config["GOOGLE_GMAIL_SCOPES"]
    mode = request.args.get("mode", "read")
    if mode not in {"read", "send", "drafts"}:
        return jsonify({"error": "Invalid Gmail permission mode"}), 400
    if mode == "send":
        scopes += current_app.config["GOOGLE_SEND_SCOPES"]
    elif mode == "drafts":
        scopes += current_app.config["GOOGLE_DRAFT_SCOPES"]

    try:
        flow = build_flow(scopes=scopes, redirect_uri=_gmail_redirect_uri())
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 500

    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    session["gmail_oauth_state"] = state
    session["gmail_oauth_mode"] = mode
    session.pop("mail_return_id", None)
    if request.args.get("outgoing"):
        item_id = request.args.get("outgoing", type=int)
        message = OutgoingMessage.query.filter_by(id=item_id, user_id=session["user_id"]).first()
        if message:
            session["mail_return_id"] = message.id
    return redirect(authorization_url)


@gmail_bp.route("/callback")
@login_required
def callback():
    error = request.args.get("error")
    if error:
        return jsonify({"error": f"Google OAuth error: {error}"}), 400

    expected_state = session.get("gmail_oauth_state")
    returned_state = request.args.get("state")
    if not expected_state or expected_state != returned_state:
        return jsonify({"error": "Invalid OAuth state (possible CSRF)"}), 400

    if not request.args.get("code"):
        return jsonify({"error": "Missing authorization code"}), 400

    user = db.session.get(User, session["user_id"])
    if user is None:
        return jsonify({"error": "User no longer exists"}), 401

    try:
        scopes = current_app.config["GOOGLE_LOGIN_SCOPES"] + current_app.config["GOOGLE_GMAIL_SCOPES"]
        mode = session.get("gmail_oauth_mode", "read")
        if mode == "send":
            scopes += current_app.config["GOOGLE_SEND_SCOPES"]
        elif mode == "drafts":
            scopes += current_app.config["GOOGLE_DRAFT_SCOPES"]
        flow = build_flow(scopes=scopes, state=expected_state, redirect_uri=_gmail_redirect_uri())
        flow.fetch_token(authorization_response=request.url)
        credentials = flow.credentials
        user_info = fetch_google_user_info(credentials)
    except Exception as exc:  # noqa: BLE001
        current_app.logger.exception("Gmail connect callback failed")
        return jsonify({"error": "Gmail connection failed", "details": str(exc)}), 400

    # Rule #17: never let one user's mail get linked to another user's
    # account — the Google account granting Gmail access must be the same
    # one the person is logged in as.
    if user_info.get("sub") != user.google_id:
        return jsonify({
            "error": "The Google account you authorized does not match your "
                     "logged-in account. Please connect Gmail using the same "
                     "account you signed in with."
        }), 400

    user.oauth_token_encrypted = encrypt_token(credentials.token)
    if credentials.refresh_token:
        user.oauth_refresh_token_encrypted = encrypt_token(credentials.refresh_token)
    if credentials.expiry:
        user.oauth_token_expiry = credentials.expiry
    user.gmail_scope_granted = True
    update_mail_permissions(user, credentials)
    db.session.commit()

    session.pop("gmail_oauth_state", None)
    session.pop("gmail_oauth_mode", None)
    flash("Gmail connected successfully.", "success")
    item_id = session.pop("mail_return_id", None)
    if mode in {"send", "drafts"} and item_id and OutgoingMessage.query.filter_by(id=item_id, user_id=user.id).first():
        return redirect(url_for("mail.preview", item_id=item_id))
    return redirect(url_for("mail.compose") if mode in {"send", "drafts"} else url_for("dashboard.dashboard_page"))


@gmail_bp.route("/sync", methods=["POST"])
@login_required
def sync():
    max_results = request.args.get("max_results", default=25, type=int)
    if max_results < 1 or max_results > 100:
        return jsonify({"error": "max_results must be between 1 and 100"}), 400

    user = db.session.get(User, session["user_id"])
    if user is None:
        return jsonify({"error": "User no longer exists"}), 401

    try:
        credentials = get_credentials_for_user(
            user,
            current_app.config["GOOGLE_CLIENT_ID"],
            current_app.config["GOOGLE_CLIENT_SECRET"],
        )
    except GmailNotConnectedError as exc:
        return jsonify({"error": str(exc)}), 400

    service = build_gmail_service(credentials)

    try:
        result = sync_user_emails(user, service, max_results=max_results,
                                  page_token=request.args.get("page_token") or None)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502

    return jsonify(result)
