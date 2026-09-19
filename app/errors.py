"""Shared error types + Flask error handlers."""
from flask import render_template
from flask_wtf.csrf import CSRFError
from werkzeug.exceptions import HTTPException


class ToolError(Exception):
    """Raise from services or routes for a *user-safe* friendly error.

    The message is shown to the end user on templates/error.html, so it must
    never contain paths, tracebacks or library internals.
    """

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def register_error_handlers(app):
    @app.errorhandler(ToolError)
    def on_tool_error(exc):
        return render_template("error.html", message=exc.message), 400

    @app.errorhandler(CSRFError)
    def on_csrf_error(exc):
        return render_template(
            "error.html",
            message="This form expired or was missing a security token. "
                    "Please reload the page and try again.",
        ), 400

    @app.errorhandler(404)
    def on_not_found(exc):
        return render_template(
            "error.html",
            message="That page or file does not exist. It may have expired "
                    "(files are deleted after 1 hour).",
        ), 404

    @app.errorhandler(413)
    def on_too_large(exc):
        limit = app.config.get("MAX_FILE_MB", 50)
        return render_template(
            "error.html",
            message=f"That upload is too large. The limit is {limit:g} MB per file "
                    f"(and a limited total per request). Try splitting the file or "
                    f"compressing it first.",
        ), 413

    @app.errorhandler(429)
    def on_rate_limited(exc):
        return render_template(
            "error.html",
            message="Too many requests from this address. Please wait a minute "
                    "and try again.",
        ), 429

    @app.errorhandler(Exception)
    def on_internal_error(exc):
        if isinstance(exc, HTTPException):
            return exc  # let 405 etc. keep their normal handling
        app.logger.exception("Unhandled error")
        return render_template(
            "error.html",
            message="Something went wrong on our side while handling that request. "
                    "Please try again.",
        ), 500

