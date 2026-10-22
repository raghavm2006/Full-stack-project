"""
Phase 2: Google OAuth login/logout.

Flow:
  GET /auth/login    -> redirect the browser to Google's consent screen
  GET /auth/callback -> Google redirects back here with a code; we exchange
                        it for tokens, fetch the user's profile, upsert a
                        User row, store tokens encrypted, start a session
  GET /auth/logout   -> clear the session
  GET /auth/me       -> current logged-in user (login_required demo route)

Only the minimum login scopes (openid/email/profile) are requested here —
no Gmail scope yet (rule #16). Phase 3 will request the Gmail scope
incrementally, reusing this same flow machinery.
"""

from datetime import timezone

from flask import Blueprint, current_app, flash, jsonify, redirect, request, session, url_for

from app.blueprints.auth.decorators import login_required
from app.blueprints.auth.oauth import build_flow, fetch_google_user_info, update_mail_permissions
from app.extensions import db
from app.models import User
from app.utils.crypto import encrypt_token

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/login")
def login():
    try:
        flow = build_flow()
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 500

    authorization_url, state = flow.authorization_url(
        access_type="offline",       # request a refresh token
        include_granted_scopes="true",
        prompt="consent",
    )
    session["oauth_state"] = state
    return redirect(authorization_url)


@auth_bp.route("/callback")
def callback():
    gmail_state = session.get("gmail_oauth_state")
    if gmail_state and request.args.get("state") == gmail_state:
        # Gmail shares the registered callback but retains its own state,
        # login requirement, and Google account identity check.
        from app.blueprints.gmail.routes import callback as gmail_callback
        return gmail_callback()

    error = request.args.get("error")
    if error:
        return jsonify({"error": f"Google OAuth error: {error}"}), 400

    expected_state = session.get("oauth_state")
    returned_state = request.args.get("state")
    if not expected_state or expected_state != returned_state:
        return jsonify({"error": "Invalid OAuth state (possible CSRF)"}), 400

    if not request.args.get("code"):
        return jsonify({"error": "Missing authorization code"}), 400

    try:
        flow = build_flow(state=expected_state)
        flow.fetch_token(authorization_response=request.url)
        credentials = flow.credentials
        user_info = fetch_google_user_info(credentials)
    except Exception as exc:  # noqa: BLE001
        current_app.logger.exception("OAuth callback failed")
        return jsonify({"error": "Authentication failed", "details": str(exc)}), 400

    google_id = user_info.get("sub")
    email = user_info.get("email")
    if not google_id or not email:
        return jsonify({"error": "Google did not return a user id/email"}), 400

    user = User.query.filter_by(google_id=google_id).first()
    if user is None:
        user = User(google_id=google_id, email=email)
        db.session.add(user)

    user.email = email
    user.name = user_info.get("name")
    user.profile_picture_url = user_info.get("picture")

    user.oauth_token_encrypted = encrypt_token(credentials.token)
    update_mail_permissions(user, credentials)
    if credentials.refresh_token:
        # Google only sends a refresh token on the FIRST consent; keep the
        # existing one on subsequent logins instead of overwriting with None.
        user.oauth_refresh_token_encrypted = encrypt_token(credentials.refresh_token)
    if credentials.expiry:
        user.oauth_token_expiry = credentials.expiry.replace(tzinfo=timezone.utc)

    db.session.commit()

    session.pop("oauth_state", None)
    session["user_id"] = user.id

    flash(f"Signed in as {user.email}.", "success")
    return redirect(url_for("dashboard.dashboard_page"))


@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("dashboard.landing_page"))


@auth_bp.route("/me")
@login_required
def me():
    user = db.session.get(User, session["user_id"])
    if user is None:
        session.clear()
        return jsonify({"error": "User no longer exists"}), 401

    return jsonify({
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "profile_picture_url": user.profile_picture_url,
        "last_synced_at": user.last_synced_at.isoformat() if user.last_synced_at else None,
    })
