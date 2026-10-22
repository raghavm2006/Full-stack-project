"""
Pytest loads conftest.py before collecting any test module in this
directory, which is exactly why the environment variables live here:
app/config.py reads os.environ at CLASS-BODY level (import time), and
`import app` gets triggered as soon as any test module does something
like `from app.blueprints.emails.parser import ...`. If that happened
before TEST_DATABASE_URI were set, Config would already have baked in
the MySQL URI and every test would try (and fail) to hit a real MySQL
server. Setting everything here guarantees it happens first.
"""

import os

os.environ.setdefault("FLASK_ENV", "testing")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("ENCRYPTION_KEY", "kx6Qv6VU6m2yjcVQ2rC0j0y3Q1sV2v9b2b5h1z2m4kA=")
os.environ.setdefault("TEST_DATABASE_URI", "sqlite:///:memory:")
