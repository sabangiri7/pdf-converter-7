"""Rotate PDF pages tool blueprint (thin; all work is in the service)."""
import json
from pathlib import Path

from flask import Blueprint, render_template, request

from app.errors import ToolError
from app.helpers import page_count
from app.jobs import create_job, run_job, save_uploads
from app.services.rotate import parse_angle, parse_pages, run

TOOL = json.loads(Path(__file__).with_suffix(".json").read_text("utf-8"))

bp = Blueprint("rotate", __name__)


# strict_slashes=False so the canonical /t/rotate URL (used by the form
# action and the contract's route tests) matches directly instead of
# 308-redirecting to /t/rotate/.
@bp.get("/", strict_slashes=False)
def page():
    return render_template("tools/rotate.html", tool=TOOL)


@bp.post("/", strict_slashes=False)
def process():
    job_id = create_job()
    files = save_uploads(job_id, allowed_kinds=("pdf",))
    if len(files) != 1:
        raise ToolError("Rotate PDF works on one file at a time. Please "
                        "upload a single PDF.")
    # Validate/sanitize options BEFORE run_job (service re-checks them).
    angle = parse_angle(request.form.get("angle") or "90")
    pages = (request.form.get("pages") or "").strip()
    if pages:
        parse_pages(pages, page_count(files[0].path))
    options = {"angle": str(angle), "pages": pages}
    ctx = run_job(job_id, run, options, title=TOOL["title"])
    return render_template("result.html", **ctx)
