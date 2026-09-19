# app/tools/images_to_pdf.py
import json
from pathlib import Path

from flask import Blueprint, render_template, request

from app.jobs import create_job, run_job, save_uploads
from app.services.images_to_pdf import run, validate_options

TOOL = json.loads(Path(__file__).with_suffix(".json").read_text("utf-8"))
bp = Blueprint("images_to_pdf", __name__)


@bp.get("/", strict_slashes=False)
def page():
    return render_template("tools/images_to_pdf.html", tool=TOOL)


@bp.post("/", strict_slashes=False)
def process():
    job_id = create_job()
    save_uploads(job_id, allowed_kinds=("image",))
    options = validate_options(request.form.get("page_size", "fit"),
                               request.form.get("margin", "none"))
    ctx = run_job(job_id, run, options, title=TOOL["title"])
    return render_template("result.html", **ctx)
