"""
Thin wrapper around the Gmail API: credential loading/refresh, and the two
calls the sync flow needs (list message ids, fetch a full message). No
parsing of the message body happens here — that's Phase 4's job. This
module only knows how to talk to Gmail, nothing about our data model.
"""

from datetime import timezone

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.utils.crypto import decrypt_token, encrypt_token
from app.extensions import db


class GmailNotConnectedError(Exception):
    """Raised when a user hasn't completed the Gmail OAuth consent yet."""


def get_credentials_for_user(user, client_id, client_secret) -> Credentials:
    """
    Rebuilds a google-auth Credentials object from a user's stored,
    encrypted tokens, refreshing the access token (and persisting the new
    one) if it has expired.
    """
    if not user.gmail_scope_granted or not user.oauth_refresh_token_encrypted:
        raise GmailNotConnectedError(
            "User has not granted Gmail access yet. Call /gmail/connect first."
        )

    expiry = user.oauth_token_expiry
    if expiry is not None and expiry.tzinfo is not None:
        expiry = expiry.astimezone(timezone.utc).replace(tzinfo=None)
    credentials = Credentials(
        token=decrypt_token(user.oauth_token_encrypted),
        refresh_token=decrypt_token(user.oauth_refresh_token_encrypted),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        expiry=expiry,
    )

    if expiry is None or not credentials.valid:
        credentials.refresh(Request())
        # Persist the refreshed access token so we don't have to refresh
        # again on every request within its lifetime.
        user.oauth_token_encrypted = encrypt_token(credentials.token)
        if credentials.expiry:
            user.oauth_token_expiry = credentials.expiry
        db.session.commit()

    return credentials


def build_gmail_service(credentials):
    return build("gmail", "v1", credentials=credentials, cache_discovery=False)


def list_message_ids(service, max_results=25, page_token=None, query=None):
    """Returns (list_of_message_ids, next_page_token_or_None)."""
    try:
        response = (
            service.users()
            .messages()
            .list(
                userId="me",
                maxResults=max_results,
                pageToken=page_token,
                q=query,
            )
            .execute()
        )
    except HttpError as exc:
        raise RuntimeError(f"Gmail API list request failed: {exc}") from exc

    messages = response.get("messages", [])
    return [m["id"] for m in messages], response.get("nextPageToken")


def get_full_message(service, message_id):
    """Returns the full Gmail message resource (headers + MIME payload)."""
    try:
        return (
            service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )
    except HttpError as exc:
        raise RuntimeError(f"Gmail API get request failed for {message_id}: {exc}") from exc
