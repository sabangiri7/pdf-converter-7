"""Application configuration.

Storage layout decision (documented in CONTRACT.md / README.md):
job-scoped folders live under the Flask *instance* folder:

    <repo>/instance/uploads/<job_id>/
    <repo>/instance/outputs/<job_id>/

They are created at startup and gitignored.
"""
import os


def _mb(value: str, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


class BaseConfig:
    # Upload / validation limits
    MAX_FILE_MB = _mb(os.environ.get("PDF_TOOLS_MAX_FILE_MB", "50"), 50.0)
    MAX_CONTENT_LENGTH = int(MAX_FILE_MB * 1024 * 1024 * 4)  # whole request
    MAX_FILES = int(os.environ.get("PDF_TOOLS_MAX_FILES", "20"))
    MAX_PAGES = int(os.environ.get("PDF_TOOLS_MAX_PAGES", "200"))
    MAX_IMAGE_PIXELS = int(os.environ.get(
        "PDF_TOOLS_MAX_IMAGE_PIXELS", "40000000"))
    MAX_CONCURRENT_JOBS = int(os.environ.get(
        "PDF_TOOLS_MAX_CONCURRENT_JOBS", "2"))

    # Job storage (overridden in create_app with instance-path defaults)
    UPLOAD_ROOT = None   # set by create_app -> <instance>/uploads
    OUTPUT_ROOT = None   # set by create_app -> <instance>/outputs

    # Cleanup
    JOB_TTL_SECONDS = int(os.environ.get("PDF_TOOLS_JOB_TTL_SECONDS", "3600"))
    CLEANUP_INTERVAL_SECONDS = int(os.environ.get(
        "PDF_TOOLS_CLEANUP_INTERVAL_SECONDS", "3600"))
    SCHEDULER_ENABLED = True

    SECRET_KEY = os.environ.get("PDF_TOOLS_SECRET_KEY", "dev-secret-change-me")

    # Cookies / CSRF (Flask-WTF)
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 3600
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _bool(os.environ.get("PDF_TOOLS_COOKIE_SECURE"),
                                  False)
    REMEMBER_COOKIE_HTTPONLY = True

    # Rate limiting (Flask-Limiter). Disabled when RATELIMIT_ENABLED is false.
    RATELIMIT_ENABLED = _bool(os.environ.get("PDF_TOOLS_RATELIMIT", "true"),
                              True)
    RATELIMIT_STORAGE_URI = os.environ.get(
        "PDF_TOOLS_RATELIMIT_STORAGE", "memory://")
    RATELIMIT_DEFAULT = os.environ.get(
        "PDF_TOOLS_RATELIMIT_DEFAULT", "120 per hour;30 per minute")
    RATELIMIT_POST = os.environ.get(
        "PDF_TOOLS_RATELIMIT_POST", "20 per minute;60 per hour")

    # Public internet posture (also see PUBLIC_DEPLOY env)
    PUBLIC_DEPLOY = _bool(os.environ.get("PUBLIC_DEPLOY"), False)


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    # Local-only: CSRF on, but weak SECRET_KEY allowed by assert_secret_key
    SESSION_COOKIE_SECURE = False


class TestingConfig(BaseConfig):
    TESTING = True
    SCHEDULER_ENABLED = False
    DEBUG = False
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False
    SECRET_KEY = "testing-secret-key-not-for-production-use!!"  # noqa: S105
    MAX_CONCURRENT_JOBS = 8


class ProductionConfig(BaseConfig):
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    # Prefer an explicitly generated key; create_app refuses weak defaults.


_CONFIGS = {
    "default": ProductionConfig,  # Docker / gunicorn: production posture
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(config_name=None):
    name = config_name or os.environ.get("PDF_TOOLS_CONFIG", "default")
    return _CONFIGS.get(name, ProductionConfig)
