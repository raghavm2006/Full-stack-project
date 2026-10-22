"""
Phase 2 verification tests.

Run with: pytest tests/test_auth.py -v

These test the OAuth *plumbing* (flow construction, token encryption,
session guarding) without making real calls to Google — that part is
verified manually via the browser (see README "Phase 2: manual test").
"""

import os

import pytest

os.environ.setdefault("FLASK_ENV", "testing")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("ENCRYPTION_KEY", "kx6Qv6VU6m2yjcVQ2rC0j0y3Q1sV2v9b2b5h1z2m4kA=")


@pytest.fixture
def app():
    from app import create_app

    application = create_app("testing")
    return application


@pytest.fixture
def client(app):
    return app.test_client()


def test_me_requires_login(client):
    response = client.get("/auth/me")
    assert response.status_code == 401


def test_login_without_google_credentials_returns_clear_error(app, client, monkeypatch):
    monkeypatch.setitem(app.config, "GOOGLE_CLIENT_ID", None)
    monkeypatch.setitem(app.config, "GOOGLE_CLIENT_SECRET", None)
    monkeypatch.setitem(app.config, "GOOGLE_REDIRECT_URI", None)

    response = client.get("/auth/login")
    assert response.status_code == 500
    assert "GOOGLE_CLIENT_ID" in response.get_json()["error"]


def test_login_redirects_to_google_when_configured(app, client, monkeypatch):
    monkeypatch.setitem(app.config, "GOOGLE_CLIENT_ID", "fake-client-id")
    monkeypatch.setitem(app.config, "GOOGLE_CLIENT_SECRET", "fake-client-secret")
    monkeypatch.setitem(
        app.config, "GOOGLE_REDIRECT_URI", "http://localhost:5000/auth/callback"
    )

    response = client.get("/auth/login")
    assert response.status_code == 302
    assert "accounts.google.com" in response.headers["Location"]

    with client.session_transaction() as sess:
        assert "oauth_state" in sess


def test_callback_rejects_mismatched_state(client):
    with client.session_transaction() as sess:
        sess["oauth_state"] = "expected-state"

    response = client.get("/auth/callback?state=wrong-state&code=abc123")
    assert response.status_code == 400
    assert "state" in response.get_json()["error"].lower()


def test_callback_rejects_missing_code(client):
    with client.session_transaction() as sess:
        sess["oauth_state"] = "expected-state"

    response = client.get("/auth/callback?state=expected-state")
    assert response.status_code == 400


def test_token_encryption_roundtrip(app):
    from app.utils.crypto import decrypt_token, encrypt_token

    with app.app_context():
        original = "super-secret-access-token"
        encrypted = encrypt_token(original)
        assert encrypted != original
        assert decrypt_token(encrypted) == original


def test_login_scopes_are_minimal():
    """Rule #16: Phase 2 must not request Gmail scopes yet."""
    from app.config import Config

    scopes = Config.GOOGLE_LOGIN_SCOPES
    assert all("gmail" not in scope for scope in scopes)
    assert "openid" in scopes


@pytest.mark.parametrize("scope_case", ["login", "incremental", "sending", "drafts", "missing", "unexpected"])
def test_token_exchange_validates_incremental_scopes(app, monkeypatch, scope_case):
    import json
    from requests import Response, Request
    from app.blueprints.auth.oauth import build_flow

    app.config.update(GOOGLE_CLIENT_ID="fake", GOOGLE_CLIENT_SECRET="fake",
                      GOOGLE_REDIRECT_URI="https://example.com/auth/callback")
    with app.app_context():
        flow = build_flow(state="expected")
        scopes = list(app.config["GOOGLE_LOGIN_SCOPES"])
        if scope_case == "incremental":
            scopes += app.config["GOOGLE_GMAIL_SCOPES"]
        elif scope_case == "sending":
            scopes += app.config["GOOGLE_GMAIL_SCOPES"] + app.config["GOOGLE_SEND_SCOPES"]
        elif scope_case == "drafts":
            scopes += app.config["GOOGLE_GMAIL_SCOPES"] + app.config["GOOGLE_DRAFT_SCOPES"]
        elif scope_case == "missing":
            scopes.remove("openid")
        elif scope_case == "unexpected":
            scopes.append("https://www.googleapis.com/auth/drive")
        response = Response()
        response.status_code = 200
        response.request = Request("POST", "https://oauth2.googleapis.com/token").prepare()
        response._content = json.dumps({"access_token": "fake-token", "token_type": "Bearer",
                                        "expires_in": 3600, "scope": " ".join(scopes)}).encode()
        monkeypatch.setattr(flow.oauth2session, "request", lambda *args, **kwargs: response)
        exchange = lambda: flow.fetch_token(authorization_response=
            "https://example.com/auth/callback?state=expected&code=fake")
        if scope_case in {"missing", "unexpected"}:
            with pytest.raises(ValueError, match="permissions"):
                exchange()
        else:
            exchange()
            assert set(flow.credentials.granted_scopes) == set(scopes)
