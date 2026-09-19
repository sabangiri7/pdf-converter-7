"""Merge PDF tool route: renders the upload page and runs the merge job."""
import json
from pathlib import Path

from flask import Blueprint, render_template

from app.errors import ToolError
from app.jobs import create_job, save_uploads, run_job
from app.services.merge import run

TOOL = json.loads(Path(__file__).with_suffix(".json").read_text("utf-8"))

bp = Blueprint("merge", __name__)


# strict_slashes=False so the canonical /t/merge URL (used by the form
# action and the landing-page card) matches directly instead of
# 308-redirecting to /t/merge/ — a POST redirect would force the browser to
# re-upload the whole multipart body.
@bp.get("/", strict_slashes=False)
def page():
    return render_template("tools/merge.html", tool=TOOL)


@bp.post("/", strict_slashes=False)
def process():
    job_id = create_job()
    files = save_uploads(job_id, allowed_kinds=("pdf",))
    if len(files) < 2:
        raise ToolError("Please upload at least two PDF files.")
    ctx = run_job(job_id, run, {}, title=TOOL["title"])
    return render_template("result.html", **ctx)
