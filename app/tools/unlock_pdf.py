"""/t/unlock_pdf — remove password protection from a PDF."""
import json
from pathlib import Path

from flask import Blueprint, render_template, request

from app.errors import ToolError
from app.jobs import create_job, save_uploads, run_job
from app.services.unlock_pdf import run

TOOL = json.loads(Path(__file__).with_suffix(".json").read_text("utf-8"))
bp = Blueprint("unlock_pdf", __name__)


@bp.get("/", strict_slashes=False)
def page():
    return render_template("tools/unlock_pdf.html", tool=TOOL)


@bp.post("/", strict_slashes=False)
def process():
    job_id = create_job()
    files = save_uploads(job_id, allowed_kinds=("pdf",), allow_encrypted=True)
    if len(files) > 1:
        raise ToolError("Unlock works on one PDF at a time. Please upload "
                        "a single PDF.")
    password = request.form.get("password") or ""
    ctx = run_job(job_id, run, {"password": password}, title=TOOL["title"])
    return render_template("result.html", **ctx)
