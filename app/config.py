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


class BaseConfig:
    # Upload / validation limits
    MAX_FILE_MB = _mb(os.environ.get("PDF_TOOLS_MAX_FILE_MB", "50"), 50.0)
    MAX_CONTENT_LENGTH = int(MAX_FILE_MB * 1024 * 1024 * 4)  # whole request (multi-file)
    MAX_FILES = int(os.environ.get("PDF_TOOLS_MAX_FILES", "20"))
    MAX_PAGES = int(os.environ.get("PDF_TOOLS_MAX_PAGES", "200"))

    # Job storage (overridden in create_app with instance-path defaults)
    UPLOAD_ROOT = None   # set by create_app -> <instance>/uploads
    OUTPUT_ROOT = None   # set by create_app -> <instance>/outputs

    # Cleanup
    JOB_TTL_SECONDS = int(os.environ.get("PDF_TOOLS_JOB_TTL_SECONDS", "3600"))
    CLEANUP_INTERVAL_SECONDS = int(os.environ.get("PDF_TOOLS_CLEANUP_INTERVAL_SECONDS", "3600"))
    SCHEDULER_ENABLED = True

    SECRET_KEY = os.environ.get("PDF_TOOLS_SECRET_KEY", "dev-secret-change-me")


class DevelopmentConfig(BaseConfig):
    DEBUG = True


class TestingConfig(BaseConfig):
    TESTING = True
    SCHEDULER_ENABLED = False
    DEBUG = False


_CONFIGS = {
    "default": BaseConfig,
    "development": DevelopmentConfig,
    "testing": TestingConfig,
}


def get_config(config_name=None):
    name = config_name or os.environ.get("PDF_TOOLS_CONFIG", "default")
    return _CONFIGS.get(name, BaseConfig)
