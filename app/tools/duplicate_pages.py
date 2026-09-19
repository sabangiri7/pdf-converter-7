"""/t/duplicate_pages — Duplicate Pages."""
import json
from pathlib import Path

from flask import Blueprint, render_template, request

from app.jobs import create_job, run_job, save_uploads
from app.services.duplicate_pages import run

TOOL = json.loads(Path(__file__).with_suffix(".json").read_text("utf-8"))

bp = Blueprint("duplicate_pages", __name__)


@bp.get("/", strict_slashes=False)
def page():
    return render_template("tools/duplicate_pages.html", tool=TOOL)


@bp.post("/", strict_slashes=False)
def process():
    job_id = create_job()
    save_uploads(job_id, allowed_kinds=("pdf",))
    options = {"pages": request.form.get("pages", ""), "copies": request.form.get("copies", "1")}
    ctx = run_job(job_id, run, options, title=TOOL["title"])
    return render_template("result.html", **ctx)
