"""OCR PDF tool blueprint (thin: upload -> validate options -> job)."""
import json
from pathlib import Path

from flask import Blueprint, render_template, request

from app.errors import ToolError
from app.jobs import create_job, run_job, save_uploads
from app.services.ocr_pdf import DEFAULT_LANGUAGE, LANGUAGES, run

TOOL = json.loads(Path(__file__).with_suffix(".json").read_text("utf-8"))
bp = Blueprint("ocr_pdf", __name__)


@bp.get("/", strict_slashes=False)
def page():
    return render_template("tools/ocr_pdf.html", tool=TOOL)


@bp.post("/", strict_slashes=False)
def process():
    job_id = create_job()
    files = save_uploads(job_id, allowed_kinds=("pdf",))
    if len(files) > 1:
        raise ToolError("OCR works on one PDF at a time. Please upload a "
                        "single file.")

    language = (request.form.get("language") or DEFAULT_LANGUAGE).strip().lower()
    if language not in LANGUAGES:
        raise ToolError("Choose a supported OCR language: "
                        + ", ".join(LANGUAGES) + ".")
    options = {"language": language}

    ctx = run_job(job_id, run, options, title=TOOL["title"])
    return render_template("result.html", **ctx)
