"""Redact matching text occurrences in a PDF (PyMuPDF search + redaction)."""
from pathlib import Path

import pymupdf

from app.errors import ToolError
from app.helpers import detect_kind

MAX_FIND = 200
_BAD = ("That file doesn't look like a valid PDF, or it is corrupted. "
        "Please try a different file.")


def clean_find(value) -> str:
    text = str(value if value is not None else "").strip()
    if not text:
        raise ToolError("Enter the text to redact.")
    if len(text) > MAX_FIND:
        raise ToolError(f"Search text must be {MAX_FIND} characters or fewer.")
    return text


def run(inputs: list[Path], output_dir: Path, *, find: str = "",
        **_options) -> Path:
    find = clean_find(find)
    if len(inputs) != 1:
        raise ToolError("Redact PDF works on one PDF at a time.")
    src = Path(inputs[0])
    if detect_kind(src) != "pdf":
        raise ToolError("Please upload a PDF file.")
    try:
        doc = pymupdf.open(str(src))
    except Exception:
        raise ToolError(_BAD)
    out = Path(output_dir) / "redacted.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)
    hits = 0
    try:
        if doc.needs_pass:
            raise ToolError("That PDF is password-protected.")
        for page in doc:
            rects = page.search_for(find)
            for rect in rects:
                page.add_redact_annot(rect, fill=(0, 0, 0))
                hits += 1
            if rects:
                page.apply_redactions()
        if hits == 0:
            raise ToolError(
                f'No occurrences of "{find[:60]}" were found to redact.')
        doc.save(str(out), garbage=4, deflate=True)
    except ToolError:
        raise
    except Exception:
        raise ToolError(_BAD)
    finally:
        doc.close()
    return out
