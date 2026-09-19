"""/t/protect_pdf — add a password to a PDF."""
import json
from pathlib import Path

from flask import Blueprint, render_template, request

from app.errors import ToolError
from app.jobs import create_job, save_uploads, run_job
from app.services.protect_pdf import run

TOOL = json.loads(Path(__file__).with_suffix(".json").read_text("utf-8"))
bp = Blueprint("protect_pdf", __name__)


@bp.get("/", strict_slashes=False)
def page():
    return render_template("tools/protect_pdf.html", tool=TOOL)


@bp.post("/", strict_slashes=False)
def process():
    job_id = create_job()
    files = save_uploads(job_id, allowed_kinds=("pdf",))
    if len(files) > 1:
        raise ToolError("Protect works on one PDF at a time. Please upload "
                        "a single PDF.")
    password = request.form.get("password") or ""
    ctx = run_job(job_id, run, {"password": password}, title=TOOL["title"])
    return render_template("result.html", **ctx)
