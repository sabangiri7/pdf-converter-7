"""Convert every page of a PDF to grayscale."""
from pathlib import Path

import pymupdf

from app.errors import ToolError
from app.helpers import detect_kind

_BAD = ("That file doesn't look like a valid PDF, or it is corrupted. "
        "Please try a different file.")


def run(inputs: list[Path], output_dir: Path, *, dpi: int = 150,
        **_options) -> Path:
    try:
        dpi = int(str(dpi).strip())
    except (TypeError, ValueError):
        raise ToolError("DPI must be a whole number between 72 and 300.")
    if not 72 <= dpi <= 300:
        raise ToolError("DPI must be a whole number between 72 and 300.")
    if len(inputs) != 1:
        raise ToolError("Grayscale PDF works on one PDF at a time.")
    src = Path(inputs[0])
    if detect_kind(src) != "pdf":
        raise ToolError("Please upload a PDF file.")
    try:
        src_doc = pymupdf.open(str(src))
    except Exception:
        raise ToolError(_BAD)
    out_doc = pymupdf.open()
    try:
        if src_doc.needs_pass:
            raise ToolError("That PDF is password-protected.")
        if src_doc.page_count < 1:
            raise ToolError("That PDF has no pages.")
        mat = pymupdf.Matrix(dpi / 72.0, dpi / 72.0)
        for i in range(src_doc.page_count):
            page = src_doc[i]
            pix = page.get_pixmap(matrix=mat, colorspace=pymupdf.csGRAY,
                                  alpha=False)
            rect = page.rect
            new_page = out_doc.new_page(width=rect.width, height=rect.height)
            new_page.insert_image(rect, pixmap=pix)
    except ToolError:
        raise
    except Exception:
        raise ToolError(_BAD)
    finally:
        src_doc.close()
    out = Path(output_dir) / "grayscale.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        out_doc.save(str(out), garbage=4, deflate=True)
    finally:
        out_doc.close()
    return out
