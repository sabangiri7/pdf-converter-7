"""Stamp a simple text (or image) signature on the last page of a PDF.

This is a visual stamp only — not a cryptographic / PKI digital signature.
"""
import io
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as rl_canvas

from app.errors import ToolError
from app.helpers import detect_kind

MAX_NAME = 80
_BAD = ("That file doesn't look like a valid PDF, or it is corrupted. "
        "Please try a different file.")


def clean_name(value) -> str:
    text = " ".join(str(value if value is not None else "").split())
    if not text:
        raise ToolError("Enter the signer name (e.g. Jane Doe).")
    if len(text) > MAX_NAME:
        raise ToolError(f"Signer name must be {MAX_NAME} characters or fewer.")
    try:
        text.encode("latin-1")
    except UnicodeEncodeError:
        raise ToolError("Signer name must use standard Latin characters.")
    return text


def _stamp_overlay(width, height, name: str, image_path: Path | None):
    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=(width, height))
    x = width - 200
    y = 60
    if image_path is not None:
        try:
            c.drawImage(ImageReader(str(image_path)), x, y, width=140,
                        height=50, mask="auto", preserveAspectRatio=True,
                        anchor="c")
            y = 40
        except Exception:
            raise ToolError("That signature image could not be used. Please "
                            "upload a PNG or JPG.")
    c.setFont("Helvetica-Oblique", 12)
    c.setFillGray(0.15)
    c.drawRightString(width - 36, y, f"Signed by {name}")
    c.showPage()
    c.save()
    buf.seek(0)
    return PdfReader(buf).pages[0]


def run(inputs: list[Path], output_dir: Path, *, name: str = "",
        **_options) -> Path:
    name = clean_name(name)
    inputs = [Path(p) for p in (inputs or [])]
    pdfs = [p for p in inputs if detect_kind(p) == "pdf"]
    images = [p for p in inputs if detect_kind(p) in ("png", "jpg", "webp")]
    if len(pdfs) != 1:
        raise ToolError("Sign PDF needs exactly one PDF "
                        "(and optionally one signature image).")
    if len(images) > 1:
        raise ToolError("Upload at most one signature image.")
    src = pdfs[0]
    image_path = images[0] if images else None
    try:
        reader = PdfReader(str(src), strict=False)
    except Exception:
        raise ToolError(_BAD)
    if reader.is_encrypted:
        raise ToolError("That PDF is password-protected.")
    if len(reader.pages) < 1:
        raise ToolError("That PDF has no pages.")
    writer = PdfWriter(clone_from=str(src))
    page = writer.pages[-1]
    box = page.mediabox
    w, h = float(box.width), float(box.height)
    left, bottom = float(box.left), float(box.bottom)
    try:
        ov = _stamp_overlay(w, h, name, image_path)
        page.merge_transformed_page(ov, (1, 0, 0, 1, left, bottom))
    except ToolError:
        raise
    except Exception:
        raise ToolError(_BAD)
    out = Path(output_dir) / "signed.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as fh:
        writer.write(fh)
    return out
