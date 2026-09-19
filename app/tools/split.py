# app/tools/split.py
"""Split PDF tool blueprint: thin route layer over the pure service."""
import json
from pathlib import Path

from flask import Blueprint, render_template, request

from app.errors import ToolError
from app.jobs import create_job, run_job, save_uploads
from app.services.split import MODES, run

TOOL = json.loads(Path(__file__).with_suffix(".json").read_text("utf-8"))
bp = Blueprint("split", __name__)


# strict_slashes=False so the canonical /t/split URL (used by the form
# action and the landing card) matches directly instead of 308-redirecting.
@bp.get("/", strict_slashes=False)
def page():
    return render_template("tools/split.html", tool=TOOL)


@bp.post("/", strict_slashes=False)
def process():
    job_id = create_job()
    files = save_uploads(job_id, allowed_kinds=("pdf",))
    if len(files) != 1:
        # The manifest declares multiple=false; enforce it server-side too
        # (the client file input is not a security boundary).
        raise ToolError("Split works on one PDF at a time. Please upload "
                        "exactly one PDF.")

    mode = (request.form.get("mode") or "extract").strip().lower()
    if mode not in MODES:
        raise ToolError("Choose a valid split option.")
    ranges = (request.form.get("ranges") or "").strip()
    page_no = (request.form.get("page") or "").strip()
    chunk_size = (request.form.get("chunk_size") or "").strip()

    options = {
        "mode": mode,
        "ranges": ranges,
        "page": page_no,
        "chunk_size": chunk_size,
    }
    ctx = run_job(job_id, run, options, title=TOOL["title"])
    return render_template("result.html", **ctx)
