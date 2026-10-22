"""
Google OAuth 2.0 flow construction and user-info retrieval.

Client ID/secret come from environment variables (Config), never from a
downloaded credentials.json committed to the repo — google-auth-oauthlib
supports building a Flow from an in-memory client config dict, which is
what we use here instead of Flow.from_client_secrets_file().
"""

import requests
from flask import current_app
from google_auth_oauthlib.flow import Flow

GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


def build_flow(scopes=None, state=None, redirect_uri=None) -> Flow:
    """Builds a Flow using this phase's minimum required scopes by default."""
    client_id = current_app.config.get("GOOGLE_CLIENT_ID")
    client_secret = current_app.config.get("GOOGLE_CLIENT_SECRET")
    redirect_uri = redirect_uri or current_app.config.get("GOOGLE_REDIRECT_URI")

    if not all([client_id, client_secret, redirect_uri]):
        raise RuntimeError(
            "GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / GOOGLE_REDIRECT_URI "
            "are not set. Check your .env file."
        )

    client_config = {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri],
        }
    }

    flow = Flow.from_client_config(
        client_config,
        scopes=scopes or current_app.config["GOOGLE_LOGIN_SCOPES"],
        state=state,
    )
    flow.redirect_uri = redirect_uri
    required_scopes = set(scopes or current_app.config["GOOGLE_LOGIN_SCOPES"])
    allowed_scopes = (required_scopes | set(current_app.config["GOOGLE_GMAIL_SCOPES"])
                      | set(current_app.config["GOOGLE_SEND_SCOPES"])
                      | set(current_app.config["GOOGLE_DRAFT_SCOPES"]))

    def accept_incremental_scopes(response):
        # Google can return previously granted Gmail scopes on later logins.
        # Validate the token response, rather than trusting the callback query
        # or disabling OAuthlib's scope checks process-wide.
        token = response.json()
        if "error" in token or "scope" not in token:
            return response
        returned = token["scope"]
        if not isinstance(returned, str):
            raise ValueError("Google returned invalid OAuth scopes")
        granted = set(returned.split())
        if not required_scopes <= granted or not granted <= allowed_scopes:
            raise ValueError("Google returned missing or unexpected OAuth permissions")
        flow.oauth2session.scope = returned.split()
        return response

    flow.oauth2session.register_compliance_hook("access_token_response", accept_incremental_scopes)
    return flow


def update_mail_permissions(user, credentials):
    granted = getattr(credentials, "granted_scopes", None) or getattr(credentials, "scopes", None)
    if isinstance(granted, (list, tuple, set)) and all(isinstance(s, str) for s in granted):
        user.gmail_send_granted = any(s in granted for s in current_app.config["GOOGLE_SEND_SCOPES"] + current_app.config["GOOGLE_DRAFT_SCOPES"])
        user.gmail_drafts_granted = all(s in granted for s in current_app.config["GOOGLE_DRAFT_SCOPES"])


def fetch_google_user_info(credentials) -> dict:
    """
    Returns {"sub", "email", "name", "picture"} for the authenticated user.

    Uses the userinfo endpoint directly (rather than decoding the ID token)
    so this works the same way regardless of which scopes were granted.
    """
    response = requests.get(
        GOOGLE_USERINFO_URL,
        headers={"Authorization": f"Bearer {credentials.token}"},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()
