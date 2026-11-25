"""LedgerIQ - Smart Expense and Financial Advisor (application factory)."""
import os
from datetime import timedelta

from flask import Flask, jsonify, request, send_from_directory, session
from werkzeug.middleware.proxy_fix import ProxyFix

from .db import close_db, get_db, init_db
from .utils import ApiError

CSRF_EXEMPT = {"/api/auth/login", "/api/auth/register"}


def create_app(config=None):
    app = Flask(__name__, static_folder="static", static_url_path="/static")
    production = os.environ.get("APP_ENV") == "production"
    secret = os.environ.get("SECRET_KEY")
    if production and not secret:
        raise RuntimeError("SECRET_KEY must be set when APP_ENV=production")
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    app.config.update(
        SECRET_KEY=secret or "dev-only-secret-change-me",
        DATABASE_URL=os.environ.get("DATABASE_URL") or "sqlite:///" + os.path.join(base, "instance", "ledgeriq.db"),
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=production or os.environ.get("COOKIE_SECURE") == "1",
        PERMANENT_SESSION_LIFETIME=timedelta(days=7), MAX_CONTENT_LENGTH=1024 * 1024,
    )
    if config:
        app.config.update(config)
    if os.environ.get("TRUST_PROXY") == "1":
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    init_db(app)
    app.teardown_appcontext(close_db)

    from . import auth, finance, insights
    for m in (auth, finance, insights):
        app.register_blueprint(m.bp)

    @app.before_request
    def csrf_protect():
        if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.path.startswith("/api/") \
                and request.path not in CSRF_EXEMPT:
            token = session.get("csrf")
            if not token or request.headers.get("X-CSRF-Token") != token:
                raise ApiError("Security token missing or invalid. Please refresh the page.", 403)

    @app.errorhandler(ApiError)
    def handle_api_error(e):
        return jsonify({"error": e.message, "field": e.field}), e.status

    @app.errorhandler(404)
    def not_found(_e):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Not found"}), 404
        return send_from_directory(app.static_folder, "index.html")

    @app.errorhandler(405)
    def bad_method(_e):
        return jsonify({"error": "Method not allowed"}), 405

    @app.errorhandler(413)
    def too_big(_e):
        return jsonify({"error": "Request too large"}), 413

    @app.errorhandler(Exception)
    def unexpected(e):
        from werkzeug.exceptions import HTTPException
        if isinstance(e, HTTPException):
            return e
        app.logger.exception("Unhandled error")
        return jsonify({"error": "Something went wrong on our side. Please try again."}), 500

    @app.after_request
    def security_headers(resp):
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "same-origin"
        if request.path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-store"
        if app.config["SESSION_COOKIE_SECURE"]:
            resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return resp

    @app.get("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    @app.get("/api/health")
    def health():
        get_db().one("SELECT 1 AS ok")
        return jsonify({"status": "ok"})

    return app
