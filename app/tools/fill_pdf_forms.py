"""/t/fill_pdf_forms — Fill PDF Forms."""
import json
from pathlib import Path

from flask import Blueprint, render_template, request

from app.jobs import create_job, run_job, save_uploads
from app.services.fill_pdf_forms import run

TOOL = json.loads(Path(__file__).with_suffix(".json").read_text("utf-8"))

bp = Blueprint("fill_pdf_forms", __name__)


@bp.get("/", strict_slashes=False)
def page():
    return render_template("tools/fill_pdf_forms.html", tool=TOOL)


@bp.post("/", strict_slashes=False)
def process():
    job_id = create_job()
    save_uploads(job_id, allowed_kinds=("pdf",))
    options = {"fields": request.form.get("fields", "")}
    ctx = run_job(job_id, run, options, title=TOOL["title"])
    return render_template("result.html", **ctx)
