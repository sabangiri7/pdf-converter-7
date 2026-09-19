"""Watermark tool route: thin glue between the job framework and the pure
service in app/services/watermark.py."""
import json
from pathlib import Path

from flask import Blueprint, render_template, request

from app.jobs import create_job, run_job, save_uploads
from app.services.watermark import (
    DEFAULT_OPACITY,
    DEFAULT_POSITION,
    clean_opacity,
    clean_position,
    clean_text,
    run,
)

TOOL = json.loads(Path(__file__).with_suffix(".json").read_text("utf-8"))

bp = Blueprint("watermark", __name__)


# strict_slashes=False: discovery links cards to /t/watermark (no trailing
# slash) while the blueprint root rule is "/"; this serves both directly
# instead of a 308 redirect that would drop nothing for GET but complicate
# simple POST clients.
@bp.get("/", strict_slashes=False)
def page():
    return render_template("tools/watermark.html", tool=TOOL)


@bp.post("/", strict_slashes=False)
def process():
    job_id = create_job()
    save_uploads(job_id, allowed_kinds=("pdf",))
    # sanitize options up front so bad input fails before any PDF work;
    # blank opacity/position fall back to the defaults, junk raises
    options = {
        "text": clean_text(request.form.get("text", "")),
        "opacity": clean_opacity(request.form.get("opacity")
                                 or DEFAULT_OPACITY),
        "position": clean_position(request.form.get("position")
                                   or DEFAULT_POSITION),
    }
    ctx = run_job(job_id, run, options, title=TOOL["title"])
    return render_template("result.html", **ctx)
