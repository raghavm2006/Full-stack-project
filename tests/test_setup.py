"""
Phase 1 verification tests.

Run with: pytest tests/test_setup.py -v

These do NOT require a running MySQL server for the first two tests;
the last two do, since they check real DB connectivity and table creation.
"""

import os

import pytest

os.environ.setdefault("FLASK_ENV", "testing")


@pytest.fixture
def app():
    from dotenv import load_dotenv

    load_dotenv()
    from app import create_app

    application = create_app("testing")
    return application


@pytest.fixture
def client(app):
    return app.test_client()


def test_app_factory_creates_app(app):
    assert app is not None
    assert app.config["TESTING"] is True


def test_landing_page_renders_for_anonymous_visitor(client):
    """
    As of Phase 5, "/" serves the HTML landing page (with a Google sign-in
    button) instead of a bare JSON status blob — see
    app/blueprints/dashboard/routes.py:landing_page.
    """
    response = client.get("/")
    assert response.status_code == 200
    assert b"EmailOrbit" in response.data
    assert b"Continue with Google" in response.data


def test_landing_page_redirects_logged_in_user_to_dashboard(client):
    with client.session_transaction() as sess:
        sess["user_id"] = 1

    response = client.get("/", follow_redirects=False)
    assert response.status_code == 302
    assert "/dashboard" in response.headers["Location"]


def test_health_route_reports_database_status(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.get_json()
    assert "database" in data


def test_models_are_registered(app):
    with app.app_context():
        from app.extensions import db
        from app.models import User, Email, Action, Reminder, UserFeedback

        table_names = set(db.metadata.tables.keys())
        expected = {"users", "emails", "actions", "reminders", "user_feedback"}
        assert expected.issubset(table_names)
