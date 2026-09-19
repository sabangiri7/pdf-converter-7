"""/t/page_numbers — Add Page Numbers."""
import json
from pathlib import Path

from flask import Blueprint, render_template, request

from app.jobs import create_job, run_job, save_uploads
from app.services.page_numbers import run

TOOL = json.loads(Path(__file__).with_suffix(".json").read_text("utf-8"))

bp = Blueprint("page_numbers", __name__)


@bp.get("/", strict_slashes=False)
def page():
    return render_template("tools/page_numbers.html", tool=TOOL)


@bp.post("/", strict_slashes=False)
def process():
    job_id = create_job()
    save_uploads(job_id, allowed_kinds=("pdf",))
    options = {"position": request.form.get("position", "bottom-center"), "start": request.form.get("start", "1"), "format": request.form.get("format", "n")}
    ctx = run_job(job_id, run, options, title=TOOL["title"])
    return render_template("result.html", **ctx)
