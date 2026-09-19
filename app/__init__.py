"""Flask app factory for the PDF tools app."""
import atexit
import logging
from pathlib import Path

from flask import Flask, render_template

from .catalog import group_tools
from .config import get_config
from .errors import register_error_handlers
from .jobs import jobs_bp, start_scheduler
from .registry import discover


def create_app(config_name=None):
    """Create and configure the Flask app.

    - loads config (env PDF_TOOLS_CONFIG or explicit name)
    - ensures <instance>/uploads and <instance>/outputs exist
    - registry.discover() imports app/tools/*.py (manifest-matched) and
      registers each blueprint at /t/<slug>; a broken tool module is logged
      and skipped, never fatal
    - starts the APScheduler TTL cleanup job (guarded, idempotent)
    - registers error handlers + the landing page route
    """
    root = Path(__file__).resolve().parent.parent
    app = Flask(__name__, instance_path=str(root / "instance"))
    app.config.from_object(get_config(config_name))

    app.config["UPLOAD_ROOT"] = str(Path(app.instance_path) / "uploads")
    app.config["OUTPUT_ROOT"] = str(Path(app.instance_path) / "outputs")
    Path(app.config["UPLOAD_ROOT"]).mkdir(parents=True, exist_ok=True)
    Path(app.config["OUTPUT_ROOT"]).mkdir(parents=True, exist_ok=True)

    # discover + register tool blueprints ---------------------------------
    app.tool_entries = discover()
    for slug, entry in app.tool_entries.items():
        if entry.available:
            try:
                app.register_blueprint(entry.bp, url_prefix=f"/t/{slug}")
                app.logger.info("registered tool '%s' at /t/%s", slug, slug)
            except Exception:
                app.logger.exception(
                    "tool '%s' blueprint failed to register — skipping", slug)
                entry.bp = None
                entry.error = "blueprint registration failed"
        else:
            app.logger.warning("tool '%s' is not available: %s", slug,
                               entry.error or "module missing (coming soon)")

    # shared download blueprint --------------------------------------------
    app.register_blueprint(jobs_bp)

    # error handlers ---------------------------------------------------------
    register_error_handlers(app)

    # landing page -----------------------------------------------------------
    @app.get("/")
    def index():
        grouped = group_tools(app.tool_entries)
        return render_template(
            "index.html",
            essentials=grouped["essentials"],
            more_categories=grouped["more"],
        )

    @app.get("/healthz")
    def healthz():
        n_ok = sum(1 for e in app.tool_entries.values() if e.available)
        return {"status": "ok", "tools": len(app.tool_entries),
                "available": n_ok}

    # background cleanup -------------------------------------------------------
    if app.config.get("SCHEDULER_ENABLED", True):
        start_scheduler(app)
        atexit.register(shutdown_scheduler)

    return app


def shutdown_scheduler():
    from . import jobs as jobs_mod
    sched = getattr(jobs_mod, "_scheduler", None)
    if sched is not None:
        try:
            sched.shutdown(wait=False)
        except Exception:
            pass
        jobs_mod._scheduler = None


logging.getLogger("apscheduler").setLevel(logging.WARNING)
