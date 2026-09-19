"""App-wide security helpers: headers, path confinement, Pillow limits,
SECRET_KEY policy, concurrent-job gate.
"""
from __future__ import annotations

import os
import threading
from pathlib import Path

from flask import abort, request

# Placeholder / documented-weak keys — never acceptable outside local/test.
_WEAK_SECRET_KEYS = frozenset({
    "",
    "dev-secret-change-me",
    "change-me-in-production",
    "change-me-to-a-long-random-string",
    "secret",
    "changeme",
})

_DEFAULT_MAX_IMAGE_PIXELS = 40_000_000  # ~ Pillow default; explicit for bombs

_job_semaphore: threading.BoundedSemaphore | None = None
_job_sem_lock = threading.Lock()
_job_sem_slots: int | None = None


def public_deploy_enabled() -> bool:
    return os.environ.get("PUBLIC_DEPLOY", "false").strip().lower() in (
        "1", "true", "yes", "on")


def assert_secret_key(app) -> None:
    """Refuse to start with a weak SECRET_KEY outside testing / local debug.

    Local ``PDF_TOOLS_CONFIG=development`` with DEBUG may keep the weak
    default. Docker / production / PUBLIC_DEPLOY=true must set a strong key.
    """
    if app.config.get("TESTING"):
        return
    key = str(app.config.get("SECRET_KEY") or "")
    weak = key in _WEAK_SECRET_KEYS or len(key) < 32
    debug = bool(app.config.get("DEBUG"))
    public = public_deploy_enabled()
    cfg_name = (os.environ.get("PDF_TOOLS_CONFIG") or "").strip().lower()
    productionish = public or cfg_name in ("default", "production") or (
        not debug and cfg_name not in ("development", "testing"))
    if weak and (productionish or public):
        raise RuntimeError(
            "Refusing to start: set PDF_TOOLS_SECRET_KEY to a strong random "
            "value (at least 32 characters). Weak/default keys are only "
            "allowed for local development (PDF_TOOLS_CONFIG=development). "
            "See README.md / SECURITY.md.")


def apply_pillow_limits(app) -> None:
    """Cap Pillow decompression to mitigate image bombs."""
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover
        return
    max_px = int(app.config.get("MAX_IMAGE_PIXELS", _DEFAULT_MAX_IMAGE_PIXELS))
    Image.MAX_IMAGE_PIXELS = max_px


def get_job_semaphore(app) -> threading.BoundedSemaphore:
    """Process-local semaphore limiting concurrent service runs."""
    global _job_semaphore, _job_sem_slots
    slots = int(app.config.get("MAX_CONCURRENT_JOBS", 2))
    with _job_sem_lock:
        if _job_semaphore is None or _job_sem_slots != slots:
            _job_semaphore = threading.BoundedSemaphore(slots)
            _job_sem_slots = slots
        return _job_semaphore


def reset_job_semaphore() -> None:
    """Test helper: drop the process-local semaphore."""
    global _job_semaphore, _job_sem_slots
    with _job_sem_lock:
        _job_semaphore = None
        _job_sem_slots = None


def confined_under(root: Path, candidate: Path) -> Path:
    """Resolve ``candidate`` and abort(404) unless it is a file under ``root``.

    Prevents path-traversal / absolute-path escapes via a poisoned job
    manifest. Symlinks that escape ``root`` are also rejected.
    """
    try:
        root_r = root.resolve(strict=False)
        cand_r = candidate.resolve(strict=False)
    except OSError:
        abort(404)
    try:
        cand_r.relative_to(root_r)
    except ValueError:
        abort(404)
    if not cand_r.is_file():
        abort(404)
    return cand_r


def install_security_headers(app) -> None:
    """Attach baseline security headers on every response."""

    @app.after_request
    def _security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault(
            "Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy",
            "geolocation=(), microphone=(), camera=(), payment=()")
        # Allow self + pdf.js CDN used by organize_pdf preview only.
        csp = app.config.get("CONTENT_SECURITY_POLICY") or (
            "default-src 'self'; "
            "script-src 'self' https://cdnjs.cloudflare.com; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )
        response.headers.setdefault("Content-Security-Policy", csp)
        if (app.config.get("SESSION_COOKIE_SECURE")
                or public_deploy_enabled()
                or request.is_secure):
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains")
        return response
