"""Centralized error handlers (rule #11: proper error handling)."""

from flask import jsonify


def register_error_handlers(app):
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({"error": "Resource not found"}), 404

    @app.errorhandler(400)
    def bad_request(error):
        return jsonify({"error": "Bad request", "details": str(error)}), 400

    @app.errorhandler(500)
    def internal_error(error):
        app.logger.exception("Unhandled server error")
        return jsonify({"error": "Internal server error"}), 500
