"""
Shared Flask extension instances.

Kept in their own module (rather than inside app/__init__.py) so that
blueprint and model modules can import `db` without triggering a circular
import with the application factory.
"""

from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

db = SQLAlchemy()
migrate = Migrate()
