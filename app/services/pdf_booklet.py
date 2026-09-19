"""Impose pages into a simple booklet order (saddle-stitch style)."""
from pathlib import Path

from pypdf import PdfReader, PdfWriter, Transformation

from app.errors import ToolError
from app.helpers import detect_kind

_BAD = ("That file doesn't look like a valid PDF, or it is corrupted. "
        "Please try a different file.")


def run(inputs: list[Path], output_dir: Path, **_options) -> Path:
    if len(inputs) != 1:
        raise ToolError("PDF Booklet works on one PDF at a time.")
    src = Path(inputs[0])
    if detect_kind(src) != "pdf":
        raise ToolError("Please upload a PDF file.")
    try:
        reader = PdfReader(str(src), strict=False)
    except Exception:
        raise ToolError(_BAD)
    if reader.is_encrypted:
        raise ToolError("That PDF is password-protected.")
    pages = list(reader.pages)
    n = len(pages)
    if n < 1:
        raise ToolError("That PDF has no pages.")
    # Pad to multiple of 4
    pad = (4 - (n % 4)) % 4
    box0 = pages[0].mediabox
    w, h = float(box0.width), float(box0.height)
    writer_src = PdfWriter()
    for p in pages:
        writer_src.add_page(p)
    for _ in range(pad):
        writer_src.add_blank_page(width=w, height=h)
    padded = list(writer_src.pages)
    total = len(padded)
    out_writer = PdfWriter()
    # Saddle-stitch: sheets of 4 pages
    for sheet in range(total // 4):
        # Order on sheet: outer-left, outer-right  then  inner...
        # For sheet s (0-based): pages [total-1-2s, 2s, 2s+1, total-2-2s]
        # We put two source pages side-by-side on a landscape sheet.
        left_i = total - 1 - 2 * sheet
        right_i = 2 * sheet
        # First side
        _add_spread(out_writer, padded[left_i], padded[right_i], w, h)
        # Second side
        left_i2 = 2 * sheet + 1
        right_i2 = total - 2 - 2 * sheet
        _add_spread(out_writer, padded[left_i2], padded[right_i2], w, h)
    out = Path(output_dir) / "booklet.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as fh:
        out_writer.write(fh)
    return out


def _add_spread(writer, left_page, right_page, w, h):
    sheet = writer.add_blank_page(width=w * 2, height=h)
    # merge left at origin
    sheet.merge_transformed_page(left_page, Transformation().translate(0, 0))
    sheet.merge_transformed_page(right_page, Transformation().translate(w, 0))
