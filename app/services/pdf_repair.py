"""Rewrite a PDF with pikepdf to repair common structural issues."""
from pathlib import Path

import pikepdf

from app.errors import ToolError
from app.helpers import detect_kind

_BAD = ("That PDF could not be repaired. It may be too damaged or "
        "password-protected.")


def run(inputs: list[Path], output_dir: Path, **_options) -> Path:
    if len(inputs) != 1:
        raise ToolError("PDF Repair works on one PDF at a time.")
    src = Path(inputs[0])
    if detect_kind(src) != "pdf":
        raise ToolError("Please upload a PDF file.")
    out = Path(output_dir) / "repaired.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        with pikepdf.open(str(src), suppress_warnings=False) as pdf:
            pdf.save(str(out), linearize=True)
    except ToolError:
        raise
    except Exception:
        raise ToolError(_BAD)
    return out
