"""Export each PDF page as an SVG via PyMuPDF."""
from pathlib import Path

import pymupdf

from app.errors import ToolError
from app.helpers import detect_kind

_BAD = ("That file doesn't look like a valid PDF, or it is corrupted. "
        "Please try a different file.")


def run(inputs: list[Path], output_dir: Path, **_options) -> list[Path]:
    if len(inputs) != 1:
        raise ToolError("PDF to SVG works on one PDF at a time.")
    src = Path(inputs[0])
    if detect_kind(src) != "pdf":
        raise ToolError("Please upload a PDF file.")
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    try:
        doc = pymupdf.open(str(src))
    except Exception:
        raise ToolError(_BAD)
    try:
        if doc.needs_pass:
            raise ToolError("That PDF is password-protected. Please remove "
                            "the password and try again.")
        if doc.page_count < 1:
            raise ToolError("That PDF has no pages.")
        for i in range(doc.page_count):
            try:
                svg = doc[i].get_svg_image()
            except Exception:
                raise ToolError(
                    "This PDF could not be converted to SVG. Try a simpler "
                    "document, or export pages as images instead.")
            path = out_dir / f"page-{i + 1}.svg"
            path.write_text(svg, encoding="utf-8")
            outputs.append(path)
    finally:
        doc.close()
    return outputs
