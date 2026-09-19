"""/t/organize_pdf — reorder or drop pages of a PDF."""
import json
from pathlib import Path

from flask import Blueprint, render_template, request

from app.errors import ToolError
from app.jobs import create_job, save_uploads, run_job
from app.services.organize_pdf import run

TOOL = json.loads(Path(__file__).with_suffix(".json").read_text("utf-8"))
bp = Blueprint("organize_pdf", __name__)


@bp.get("/", strict_slashes=False)
def page():
    return render_template("tools/organize_pdf.html", tool=TOOL)


@bp.post("/", strict_slashes=False)
def process():
    job_id = create_job()
    files = save_uploads(job_id, allowed_kinds=("pdf",))
    if len(files) > 1:
        raise ToolError("Organize works on one PDF at a time. Please upload "
                        "a single PDF.")
    pages = (request.form.get("pages") or "").strip()
    ctx = run_job(job_id, run, {"pages": pages}, title=TOOL["title"])
    return render_template("result.html", **ctx)
