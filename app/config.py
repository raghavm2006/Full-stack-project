"""
Application configuration, loaded entirely from environment variables.

Rule: no secrets or credentials are ever hardcoded here. All real values
live in a local .env file (which is gitignored) and are loaded via
python-dotenv in run.py before this module is imported.
"""

import os
from sqlalchemy.engine import URL

# Project root (parent of app/) — used to locate models_store/ regardless
# of the process's current working directory.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY")
    if not SECRET_KEY:
        raise RuntimeError(
            "SECRET_KEY is not set. Copy .env.example to .env and fill it in."
        )

    DB_HOST = os.environ.get("DB_HOST", "localhost")
    DB_PORT = os.environ.get("DB_PORT", "3306")
    DB_NAME = os.environ.get("DB_NAME", "emailorbit")
    DB_USER = os.environ.get("DB_USER")
    DB_PASSWORD = os.environ.get("DB_PASSWORD")

    # TEST_DATABASE_URI is an escape hatch used ONLY by the automated test
    # suite (see tests/test_gmail_sync.py) so sync logic can be verified
    # against a throwaway SQLite DB instead of requiring a live MySQL
    # server. The real app always uses the MySQL URI below.
    _test_db_uri = os.environ.get("TEST_DATABASE_URI")
    if _test_db_uri:
        SQLALCHEMY_DATABASE_URI = _test_db_uri
    else:
        if not DB_USER or not DB_PASSWORD:
            raise RuntimeError(
                "DB_USER / DB_PASSWORD are not set. Check your .env file."
            )
        SQLALCHEMY_DATABASE_URI = URL.create(
            "mysql+pymysql", username=DB_USER, password=DB_PASSWORD,
            host=DB_HOST, port=int(DB_PORT), database=DB_NAME,
        )

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Google OAuth (Phase 2). Not validated here (unlike DB creds) because
    # unit tests that don't touch the auth blueprint shouldn't need them —
    # oauth.py raises a clear error itself if a flow is actually built
    # without these set.
    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
    GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI")

    # Rule #16: request the minimum OAuth scopes needed for each phase.
    # Phase 2 only needs to identify the user (login) — no Gmail access yet.
    # Phase 3 adds the Gmail scope via incremental authorization, not by
    # widening this list.
    GOOGLE_LOGIN_SCOPES = [
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
    ]

    # Phase 3: requested separately, via incremental authorization, only
    # once a user chooses to connect Gmail — read-only is the minimum
    # scope that lets us list/fetch messages. Widen only if a later phase
    # (e.g. Phase 9 sending smart replies) genuinely needs write access.
    GOOGLE_GMAIL_SCOPES = [
        "https://www.googleapis.com/auth/gmail.readonly",
    ]
    GOOGLE_SEND_SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
    GOOGLE_DRAFT_SCOPES = ["https://www.googleapis.com/auth/gmail.compose"]

    # Fernet key for encrypting OAuth tokens at rest (app/utils/crypto.py).
    ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY")

    # Phase 7: where app/blueprints/ml_inference looks for the .joblib
    # artifacts Phase 6's training scripts produce. Rule #15 — the app
    # only ever loads pre-trained models from here; it never trains.
    MODELS_DIR = os.environ.get("MODELS_DIR", os.path.join(BASE_DIR, "models_store"))

    # Phase 9: smart replies call the Anthropic API when a key is present.
    # Deliberately optional — app/blueprints/smart_replies falls back to
    # deterministic templates whenever this is unset, invalid, or the API
    # call fails for any reason (rate limit, network, etc.), so smart
    # replies work with zero configuration and get better once a key is
    # added. Never hardcode a real key here — set it in your local .env.
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
    SMART_REPLY_MODEL = os.environ.get("SMART_REPLY_MODEL", "claude-3-5-haiku-latest")


class DevelopmentConfig(Config):
    DEBUG = True


class TestingConfig(Config):
    TESTING = True
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
