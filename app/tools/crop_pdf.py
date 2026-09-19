"""/t/crop_pdf — Crop PDF."""
import json
from pathlib import Path

from flask import Blueprint, render_template, request

from app.jobs import create_job, run_job, save_uploads
from app.services.crop_pdf import run

TOOL = json.loads(Path(__file__).with_suffix(".json").read_text("utf-8"))

bp = Blueprint("crop_pdf", __name__)


@bp.get("/", strict_slashes=False)
def page():
    return render_template("tools/crop_pdf.html", tool=TOOL)


@bp.post("/", strict_slashes=False)
def process():
    job_id = create_job()
    save_uploads(job_id, allowed_kinds=("pdf",))
    options = {"left": request.form.get("left", "0"), "right": request.form.get("right", "0"), "top": request.form.get("top", "0"), "bottom": request.form.get("bottom", "0")}
    ctx = run_job(job_id, run, options, title=TOOL["title"])
    return render_template("result.html", **ctx)
