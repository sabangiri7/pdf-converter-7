"""/t/remove_metadata — Remove Metadata."""
import json
from pathlib import Path

from flask import Blueprint, render_template

from app.jobs import create_job, run_job, save_uploads
from app.services.remove_metadata import run

TOOL = json.loads(Path(__file__).with_suffix(".json").read_text("utf-8"))

bp = Blueprint("remove_metadata", __name__)


@bp.get("/", strict_slashes=False)
def page():
    return render_template("tools/remove_metadata.html", tool=TOOL)


@bp.post("/", strict_slashes=False)
def process():
    job_id = create_job()
    save_uploads(job_id, allowed_kinds=("pdf",))
    options = {}
    ctx = run_job(job_id, run, options, title=TOOL["title"])
    return render_template("result.html", **ctx)
