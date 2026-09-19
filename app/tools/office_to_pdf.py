"""Thin blueprint for the office_to_pdf tool.

All real work lives in the pure service (app/services/office_to_pdf.py);
this module just wires uploads -> job -> result page. Downloads are served
by the foundation's /dl/... routes.
"""
import json
from pathlib import Path

from flask import Blueprint, render_template

from app.jobs import create_job, save_uploads, run_job
from app.services.office_to_pdf import run

TOOL = json.loads(Path(__file__).with_suffix(".json").read_text("utf-8"))

bp = Blueprint("office_to_pdf", __name__)


# strict_slashes=False so the canonical /t/office_to_pdf URLs (the landing
# card links and the form action in the template) match directly with 200/400
# instead of 308-redirecting to the trailing-slash form.
@bp.get("/", strict_slashes=False)
def page():
    return render_template("tools/office_to_pdf.html", tool=TOOL)


@bp.post("/", strict_slashes=False)
def process():
    job_id = create_job()
    save_uploads(job_id, allowed_kinds=("office",))
    # No user-configurable options for this conversion; the service takes
    # **options, so passing an empty dict is correct and future-proof.
    options = {}
    ctx = run_job(job_id, run, options, title=TOOL["title"])
    return render_template("result.html", **ctx)
