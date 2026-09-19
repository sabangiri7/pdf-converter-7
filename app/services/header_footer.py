"""Add header and/or footer text to every page of a PDF."""
import io
import unicodedata
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas as rl_canvas

from app.errors import ToolError
from app.helpers import detect_kind

MAX_CHARS = 120
_BAD = ("That file doesn't look like a valid PDF, or it is corrupted. "
        "Please try a different file.")


def clean_line(value, *, label: str) -> str:
    text = " ".join(str(value if value is not None else "").split())
    if len(text) > MAX_CHARS:
        raise ToolError(f"{label} must be {MAX_CHARS} characters or fewer.")
    if text:
        try:
            text.encode("latin-1")
        except UnicodeEncodeError:
            raise ToolError(
                f"{label} uses characters that cannot be drawn with the "
                "built-in font. Use standard Latin letters.")
        if any(unicodedata.category(ch) == "Cc" for ch in text):
            raise ToolError(f"{label} contains invalid control characters.")
    return text


def _overlay(width, height, header: str, footer: str):
    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=(width, height))
    c.setFont("Helvetica", 9)
    c.setFillGray(0.3)
    if header:
        c.drawCentredString(width / 2, height - 28, header)
    if footer:
        c.drawCentredString(width / 2, 24, footer)
    c.showPage()
    c.save()
    buf.seek(0)
    return PdfReader(buf).pages[0]


def run(inputs: list[Path], output_dir: Path, *,
        header: str = "", footer: str = "", **_options) -> Path:
    header = clean_line(header, label="Header")
    footer = clean_line(footer, label="Footer")
    if not header and not footer:
        raise ToolError("Enter a header, a footer, or both.")
    if len(inputs) != 1:
        raise ToolError("Header & Footer works on one PDF at a time.")
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
    writer = PdfWriter(clone_from=str(src))
    cache: dict = {}
    try:
        for page in writer.pages:
            box = page.mediabox
            key = (round(float(box.width), 2), round(float(box.height), 2),
                   round(float(box.left), 2), round(float(box.bottom), 2))
            if key not in cache:
                cache[key] = _overlay(key[0], key[1], header, footer)
            page.merge_transformed_page(
                cache[key], (1, 0, 0, 1, key[2], key[3]))
    except ToolError:
        raise
    except Exception:
        raise ToolError(_BAD)
    out = Path(output_dir) / "header-footer.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as fh:
        writer.write(fh)
    return out
