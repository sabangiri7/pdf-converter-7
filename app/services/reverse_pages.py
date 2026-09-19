"""Reverse the page order of a PDF."""
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from app.errors import ToolError
from app.helpers import detect_kind

_BAD = ("That file doesn't look like a valid PDF, or it is corrupted. "
        "Please try a different file.")


def run(inputs: list[Path], output_dir: Path, **_options) -> Path:
    if len(inputs) != 1:
        raise ToolError("Reverse Page Order works on one PDF at a time.")
    src = Path(inputs[0])
    if detect_kind(src) != "pdf":
        raise ToolError("Please upload a PDF file.")
    try:
        reader = PdfReader(str(src), strict=False)
    except Exception:
        raise ToolError(_BAD)
    if reader.is_encrypted:
        raise ToolError("That PDF is password-protected.")
    if len(reader.pages) < 1:
        raise ToolError("That PDF has no pages.")
    writer = PdfWriter()
    for page in reversed(list(reader.pages)):
        writer.add_page(page)
    out = Path(output_dir) / "reversed.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as fh:
        writer.write(fh)
    return out
