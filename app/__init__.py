"""
Application factory.

Using create_app() (rather than a bare module-level `app = Flask(...)`)
is what lets tests (Phase 11) spin up isolated app instances with a
TestingConfig, and keeps blueprint registration in one clearly readable
place as more blueprints are added phase by phase.
"""

import os

from flask import Flask

from app.config import config_by_name
from app.extensions import db, migrate
from app.utils.error_handlers import register_error_handlers


def create_app(config_name=None):
    app = Flask(__name__)
    from app.utils.mail_request import MailUploadRequest
    app.request_class = MailUploadRequest

    config_name = config_name or os.environ.get("FLASK_ENV", "development")
    app.config.from_object(config_by_name[config_name])

    db.init_app(app)
    migrate.init_app(app, db)

    register_error_handlers(app)
    register_blueprints(app)
    register_context_processors(app)
    register_template_filters(app)

    return app


def register_context_processors(app):
    @app.context_processor
    def inject_current_user():
        from flask import session

        from app.models import User

        user = None
        if session.get("user_id"):
            user = db.session.get(User, session["user_id"])
        return {"current_user": user}


def register_template_filters(app):
    import json
    from app.utils.email_links import linked_email_body

    app.add_template_filter(linked_email_body, "linked_email_body")

    @app.template_filter("fromjson")
    def fromjson_filter(raw_value):
        """Phase 9: decodes Email.smart_replies (a JSON-encoded list of
        strings) for rendering in email_detail.html. Returns [] for None/
        empty/invalid input rather than raising inside a template."""
        if not raw_value:
            return []
        try:
            return json.loads(raw_value)
        except (ValueError, TypeError):
            return []


def register_blueprints(app):
    # Each phase adds its blueprint import + registration here, and
    # nowhere else.
    from app.blueprints.dashboard.routes import dashboard_bp
    from app.blueprints.auth.routes import auth_bp
    from app.blueprints.gmail.routes import gmail_bp
    from app.blueprints.emails.routes import emails_bp
    from app.blueprints.ml_inference.routes import ml_inference_bp
    from app.blueprints.nlp_features.routes import nlp_features_bp
    from app.blueprints.smart_replies.routes import smart_replies_bp
    from app.blueprints.followup.routes import followup_bp
    from app.blueprints.deduplication.routes import deduplication_bp
    from app.blueprints.commitments.routes import commitments_bp
    from app.blueprints.mail.routes import mail_bp

    app.register_blueprint(dashboard_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(gmail_bp)
    app.register_blueprint(emails_bp)
    app.register_blueprint(ml_inference_bp)
    app.register_blueprint(nlp_features_bp)
    app.register_blueprint(smart_replies_bp)
    app.register_blueprint(followup_bp)
    app.register_blueprint(deduplication_bp)
    app.register_blueprint(commitments_bp)
    app.register_blueprint(mail_bp)
