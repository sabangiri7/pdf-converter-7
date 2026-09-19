"""Best-effort color mode conversion by re-rendering pages."""
from pathlib import Path

import pymupdf

from app.errors import ToolError
from app.helpers import detect_kind

MODES = ("grayscale", "rgb", "cmyk")
_BAD = ("That file doesn't look like a valid PDF, or it is corrupted. "
        "Please try a different file.")


def clean_mode(value) -> str:
    v = str(value or "grayscale").strip().lower()
    if v not in MODES:
        raise ToolError("Choose grayscale, RGB, or CMYK.")
    return v


def run(inputs: list[Path], output_dir: Path, *, mode: str = "grayscale",
        dpi: int = 150, **_options) -> Path:
    mode = clean_mode(mode)
    try:
        dpi = int(str(dpi).strip())
    except (TypeError, ValueError):
        raise ToolError("DPI must be a whole number between 72 and 300.")
    if not 72 <= dpi <= 300:
        raise ToolError("DPI must be a whole number between 72 and 300.")
    if len(inputs) != 1:
        raise ToolError("PDF Color Converter works on one PDF at a time.")
    src = Path(inputs[0])
    if detect_kind(src) != "pdf":
        raise ToolError("Please upload a PDF file.")
    cs = {"grayscale": pymupdf.csGRAY, "rgb": pymupdf.csRGB,
          "cmyk": pymupdf.csCMYK}[mode]
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
            try:
                pix = page.get_pixmap(matrix=mat, colorspace=cs, alpha=False)
            except Exception:
                # CMYK may fail on some builds — fall back to RGB then convert
                if mode == "cmyk":
                    raise ToolError(
                        "CMYK conversion is not supported for this PDF on "
                        "this server. Try grayscale or RGB instead.")
                raise ToolError(_BAD)
            rect = page.rect
            new_page = out_doc.new_page(width=rect.width, height=rect.height)
            new_page.insert_image(rect, pixmap=pix)
    except ToolError:
        raise
    except Exception:
        raise ToolError(_BAD)
    finally:
        src_doc.close()
    out = Path(output_dir) / f"{mode}.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        out_doc.save(str(out), garbage=4, deflate=True)
    finally:
        out_doc.close()
    return out
