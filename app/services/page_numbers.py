"""Stamp page numbers on every page of a PDF."""
import io
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas as rl_canvas

from app.errors import ToolError
from app.helpers import detect_kind

POSITIONS = ("bottom-center", "bottom-right", "bottom-left",
             "top-center", "top-right", "top-left")
DEFAULT_POSITION = "bottom-center"
DEFAULT_START = 1
_BAD = ("That file doesn't look like a valid PDF, or it is corrupted. "
        "Please try a different file.")


def clean_position(value) -> str:
    v = str(value or DEFAULT_POSITION).strip().lower()
    if v not in POSITIONS:
        raise ToolError("Pick a valid page-number position.")
    return v


def clean_start(value) -> int:
    try:
        n = int(str(value).strip())
    except (TypeError, ValueError):
        raise ToolError("Starting number must be a whole number between "
                        "1 and 9999.")
    if not 1 <= n <= 9999:
        raise ToolError("Starting number must be a whole number between "
                        "1 and 9999.")
    return n


def clean_format(value) -> str:
    fmt = str(value or "n").strip().lower()
    if fmt not in ("n", "n_of_n", "page_n"):
        raise ToolError("Choose a page-number format.")
    return fmt


def _overlay(width, height, text, position):
    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=(width, height))
    c.setFont("Helvetica", 10)
    c.setFillGray(0.25)
    margin = 28
    y = height - margin if "top" in position else margin
    if "left" in position:
        c.drawString(margin, y, text)
    elif "right" in position:
        c.drawRightString(width - margin, y, text)
    else:
        c.drawCentredString(width / 2, y, text)
    c.showPage()
    c.save()
    buf.seek(0)
    return PdfReader(buf).pages[0]


def run(inputs: list[Path], output_dir: Path, *,
        position: str = DEFAULT_POSITION,
        start: int = DEFAULT_START,
        format: str = "n", **_options) -> Path:
    position = clean_position(position)
    start = clean_start(start)
    fmt = clean_format(format)
    if len(inputs) != 1:
        raise ToolError("Add Page Numbers works on one PDF at a time.")
    src = Path(inputs[0])
    if detect_kind(src) != "pdf":
        raise ToolError("Please upload a PDF file.")
    try:
        reader = PdfReader(str(src), strict=False)
    except Exception:
        raise ToolError(_BAD)
    if reader.is_encrypted:
        raise ToolError("That PDF is password-protected.")
    n = len(reader.pages)
    if n < 1:
        raise ToolError("That PDF has no pages.")
    writer = PdfWriter(clone_from=str(src))
    try:
        for i, page in enumerate(writer.pages):
            num = start + i
            if fmt == "n_of_n":
                label = f"{num} / {start + n - 1}"
            elif fmt == "page_n":
                label = f"Page {num}"
            else:
                label = str(num)
            box = page.mediabox
            w, h = float(box.width), float(box.height)
            left, bottom = float(box.left), float(box.bottom)
            ov = _overlay(w, h, label, position)
            page.merge_transformed_page(ov, (1, 0, 0, 1, left, bottom))
    except ToolError:
        raise
    except Exception:
        raise ToolError(_BAD)
    out = Path(output_dir) / "page-numbers.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as fh:
        writer.write(fh)
    return out
