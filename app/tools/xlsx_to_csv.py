"""/t/xlsx_to_csv — convert an Excel .xlsx workbook into a CSV file."""
import json
from pathlib import Path

from flask import Blueprint, render_template

from app.errors import ToolError
from app.jobs import create_job, save_uploads, run_job
from app.services.xlsx_to_csv import run

TOOL = json.loads(Path(__file__).with_suffix(".json").read_text("utf-8"))
bp = Blueprint("xlsx_to_csv", __name__)


@bp.get("/", strict_slashes=False)
def page():
    return render_template("tools/xlsx_to_csv.html", tool=TOOL)


@bp.post("/", strict_slashes=False)
def process():
    job_id = create_job()
    files = save_uploads(job_id, allowed_kinds=("zip",))
    if len(files) > 1:
        raise ToolError("This tool converts one Excel file at a time. "
                        "Please upload a single .xlsx file.")
    # .xlsx is ZIP; reject obvious non-spreadsheet zips via service openpyxl.
    name = (files[0].name or "").lower()
    if name and not name.endswith((".xlsx", ".xlsm")):
        # Soft hint only when extension is clearly wrong; service still validates.
        if name.endswith((".docx", ".pptx", ".zip")):
            raise ToolError("Please upload an Excel .xlsx file (not Word, "
                            "PowerPoint, or a plain ZIP).")
    ctx = run_job(job_id, run, {}, title=TOOL["title"])
    return render_template("result.html", **ctx)
