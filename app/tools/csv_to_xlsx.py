"""/t/csv_to_xlsx — convert a CSV file into an Excel .xlsx workbook."""
import json
from pathlib import Path

from flask import Blueprint, render_template

from app.errors import ToolError
from app.jobs import create_job, save_uploads, run_job
from app.services.csv_to_xlsx import run

TOOL = json.loads(Path(__file__).with_suffix(".json").read_text("utf-8"))
bp = Blueprint("csv_to_xlsx", __name__)


@bp.get("/", strict_slashes=False)
def page():
    return render_template("tools/csv_to_xlsx.html", tool=TOOL)


@bp.post("/", strict_slashes=False)
def process():
    job_id = create_job()
    files = save_uploads(job_id, allowed_kinds=("csv",))
    if len(files) > 1:
        raise ToolError("This tool converts one CSV at a time. Please "
                        "upload a single CSV file.")
    ctx = run_job(job_id, run, {}, title=TOOL["title"])
    return render_template("result.html", **ctx)
