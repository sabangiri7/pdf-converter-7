"""/t/pdf_to_pptx — convert a PDF into a PowerPoint deck (one slide/page)."""
import json
from pathlib import Path

from flask import Blueprint, render_template, request

from app.errors import ToolError
from app.jobs import create_job, save_uploads, run_job
from app.services.pdf_to_pptx import clean_options, run

TOOL = json.loads(Path(__file__).with_suffix(".json").read_text("utf-8"))
bp = Blueprint("pdf_to_pptx", __name__)


@bp.get("/", strict_slashes=False)
def page():
    return render_template("tools/pdf_to_pptx.html", tool=TOOL)


@bp.post("/", strict_slashes=False)
def process():
    job_id = create_job()
    files = save_uploads(job_id, allowed_kinds=("pdf",))
    options = clean_options(request.form)
    if len(files) > 1:
        raise ToolError("This tool converts one PDF at a time. Please "
                        "upload a single PDF file.")
    ctx = run_job(job_id, run, options, title=TOOL["title"])
    return render_template("result.html", **ctx)
