# app/tools/compress.py
import json
from pathlib import Path

from flask import Blueprint, render_template, request

from app.errors import ToolError
from app.jobs import create_job, run_job, save_uploads
from app.services.compress import run

TOOL = json.loads(Path(__file__).with_suffix(".json").read_text("utf-8"))
bp = Blueprint("compress", __name__)

LEVELS = {"basic", "extreme"}


@bp.get("/", strict_slashes=False)
def page():
    return render_template("tools/compress.html", tool=TOOL)


@bp.post("/", strict_slashes=False)
def process():
    job_id = create_job()
    files = save_uploads(job_id, allowed_kinds=("pdf",))
    if len(files) != 1:
        raise ToolError("Compress PDF works on one file at a time. Please "
                        "upload a single PDF.")
    level = (request.form.get("level") or "basic").strip().lower()
    if level not in LEVELS:
        raise ToolError("Unknown compression level. Choose 'basic' or "
                        "'extreme'.")
    options = {"level": level}
    ctx = run_job(job_id, run, options, title=TOOL["title"])
    return render_template("result.html", **ctx)
