"""Remove nearly-blank pages from a PDF."""
from pathlib import Path

import pymupdf
from pypdf import PdfReader, PdfWriter

from app.errors import ToolError
from app.helpers import detect_kind

_BAD = ("That file doesn't look like a valid PDF, or it is corrupted. "
        "Please try a different file.")


def _is_blank(page) -> bool:
    text = (page.get_text("text") or "").strip()
    if len(text) > 20:
        return False
    try:
        pix = page.get_pixmap(matrix=pymupdf.Matrix(0.25, 0.25), alpha=False)
        samples = pix.samples
        if not samples:
            return True
        whiteish = 0
        total = len(samples) // 3
        for i in range(0, len(samples), 3):
            if (samples[i] > 245 and samples[i + 1] > 245
                    and samples[i + 2] > 245):
                whiteish += 1
        return (whiteish / max(total, 1)) >= 0.995
    except Exception:
        return len(text) == 0


def run(inputs: list[Path], output_dir: Path, **_options) -> Path:
    if len(inputs) != 1:
        raise ToolError("Remove Blank Pages works on one PDF at a time.")
    src = Path(inputs[0])
    if detect_kind(src) != "pdf":
        raise ToolError("Please upload a PDF file.")
    try:
        doc = pymupdf.open(str(src))
    except Exception:
        raise ToolError(_BAD)
    keep: list[int] = []
    try:
        if doc.needs_pass:
            raise ToolError("That PDF is password-protected.")
        if doc.page_count < 1:
            raise ToolError("That PDF has no pages.")
        for i in range(doc.page_count):
            if not _is_blank(doc[i]):
                keep.append(i)
    finally:
        doc.close()
    if not keep:
        raise ToolError(
            "Every page looked blank — nothing would remain. "
            "No changes were made.")
    try:
        reader = PdfReader(str(src), strict=False)
    except Exception:
        raise ToolError(_BAD)
    if len(keep) == len(reader.pages):
        raise ToolError("No blank pages were found to remove.")
    writer = PdfWriter()
    for i in keep:
        writer.add_page(reader.pages[i])
    out = Path(output_dir) / "no-blanks.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as fh:
        writer.write(fh)
    return out
