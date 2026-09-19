"""/t/metadata_editor — PDF Metadata Editor."""
import json
from pathlib import Path

from flask import Blueprint, render_template, request

from app.jobs import create_job, run_job, save_uploads
from app.services.metadata_editor import run

TOOL = json.loads(Path(__file__).with_suffix(".json").read_text("utf-8"))

bp = Blueprint("metadata_editor", __name__)


@bp.get("/", strict_slashes=False)
def page():
    return render_template("tools/metadata_editor.html", tool=TOOL)


@bp.post("/", strict_slashes=False)
def process():
    job_id = create_job()
    save_uploads(job_id, allowed_kinds=("pdf",))
    options = {"title": request.form.get("title", ""), "author": request.form.get("author", ""), "subject": request.form.get("subject", ""), "keywords": request.form.get("keywords", "")}
    ctx = run_job(job_id, run, options, title=TOOL["title"])
    return render_template("result.html", **ctx)
