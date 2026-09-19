"""Pure watermarking service: stamp a text watermark over every page of one
PDF. No Flask — works with plain paths.

Strategy: build a throwaway single-page overlay PDF (reportlab) sized to
match the target page's MediaBox, draw the text with setFillAlpha and a
light gray Helvetica-Bold, then merge it under/over each page with pypdf.
Page sizes can vary inside one document, so overlays are cached per
distinct (width, height) pair.
"""
from __future__ import annotations

import io
import math
import unicodedata
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas as rl_canvas

from app.errors import ToolError

# Option contract (validated both in the route and here, defensively)
ALLOWED_POSITIONS = ("diagonal", "center", "top", "bottom")
MAX_TEXT_CHARS = 200
MIN_OPACITY = 5
MAX_OPACITY = 100
DEFAULT_OPACITY = 20
DEFAULT_POSITION = "diagonal"

_FONT = "Helvetica-Bold"
_GRAY = (0.55, 0.55, 0.55)
_CORRUPT_MSG = ("That file doesn't look like a valid PDF, or it is "
                "corrupted. Please try a different file.")

BAD_OPACITY_MSG = f"Choose a watermark opacity between {MIN_OPACITY} and {MAX_OPACITY}%."
BAD_POSITION_MSG = "Pick a valid watermark position."
EMPTY_TEXT_MSG = "Enter the watermark text."
TOO_LONG_MSG = (f"The watermark text must be {MAX_TEXT_CHARS} characters "
                "or fewer.")
UNSUPPORTED_CHARS_MSG = ("The watermark text uses characters this printer-"
                         "font cannot draw. Please use standard Western "
                         "(Latin-1) letters, digits and punctuation.")


# ---------------------------------------------------------------------------
# option sanitizing (shared by the route and run())
# ---------------------------------------------------------------------------

def clean_text(text) -> str:
    """Strip/collapse whitespace, enforce required + max length.

    The base-14 Helvetica-Bold font can only draw Latin-1 characters; any
    wider code point (CJK, emoji) would silently render as mojibake, and
    leftover control codes (\x00, \x7f — anything str.split() did not
    collapse as whitespace) would render as nothing or as garbage glyphs,
    so we reject both with a friendly message instead.
    """
    collapsed = " ".join(str(text if text is not None else "").split())
    if not collapsed:
        raise ToolError(EMPTY_TEXT_MSG)
    if len(collapsed) > MAX_TEXT_CHARS:
        raise ToolError(TOO_LONG_MSG)
    try:
        collapsed.encode("latin-1")
    except UnicodeEncodeError:
        raise ToolError(UNSUPPORTED_CHARS_MSG)
    if any(unicodedata.category(ch) == "Cc" for ch in collapsed):
        raise ToolError(UNSUPPORTED_CHARS_MSG)
    return collapsed


def clean_opacity(opacity) -> int:
    """Strict int in [MIN_OPACITY, MAX_OPACITY]; junk -> friendly ToolError."""
    try:
        value = int(str(opacity).strip())
    except (TypeError, ValueError):
        raise ToolError(BAD_OPACITY_MSG)
    if not MIN_OPACITY <= value <= MAX_OPACITY:
        raise ToolError(BAD_OPACITY_MSG)
    return value


def clean_position(position) -> str:
    value = str(position or "").strip().lower()
    if value not in ALLOWED_POSITIONS:
        raise ToolError(BAD_POSITION_MSG)
    return value


# ---------------------------------------------------------------------------
# overlay drawing
# ---------------------------------------------------------------------------

def _font_size(width: float, height: float, text: str, position: str) -> float:
    """Pick the largest point size that fits on one line inside the page
    (diagonal text is limited by the 45-degree chord through the centre)."""
    if position == "diagonal":
        available = math.sqrt(2.0) * min(width, height) * 0.85
    else:
        available = width * 0.90
    unit_width = stringWidth(text, _FONT, 100.0) or 1.0
    size = available * 100.0 / unit_width
    return max(6.0, min(72.0, size))


def _overlay_page(width: float, height: float, text: str, position: str,
                  alpha: float):
    """One pypdf PageObject holding the watermark, drawn at (width, height)."""
    size = _font_size(width, height, text, position)
    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=(width, height))
    c.saveState()
    c.setFillAlpha(alpha)
    c.setFillColorRGB(*_GRAY)
    c.setFont(_FONT, size)
    if position == "diagonal":
        c.translate(width / 2.0, height / 2.0)
        c.rotate(45)
        c.drawCentredString(0.0, 0.0, text)
    elif position == "center":
        c.drawCentredString(width / 2.0, (height - size) / 2.0, text)
    elif position == "top":
        c.drawCentredString(width / 2.0, height - size - 28.0, text)
    else:  # bottom
        c.drawCentredString(width / 2.0, 34.0, text)
    c.restoreState()
    c.showPage()
    c.save()
    buf.seek(0)
    return PdfReader(buf).pages[0]


# ---------------------------------------------------------------------------
# service entry point
# ---------------------------------------------------------------------------

def run(inputs: list[Path], output_dir: Path, *, text: str = "",
        opacity: int = DEFAULT_OPACITY,
        position: str = DEFAULT_POSITION) -> Path:
    """Stamp `text` over every page of the single input PDF.

    inputs: one saved upload path. output_dir: write ONLY here.
    Returns the Path of the watermarked PDF. Raises ToolError for user
    errors (bad options, more than one input, corrupt/encrypted PDF).
    """
    text = clean_text(text)
    opacity = clean_opacity(opacity)
    position = clean_position(position)
    alpha = opacity / 100.0

    if len(inputs) != 1:
        raise ToolError("Watermarking works on one PDF at a time. Please "
                        "upload a single file.")
    src = Path(inputs[0])
    try:
        reader = PdfReader(str(src), strict=False)
    except Exception:
        raise ToolError(_CORRUPT_MSG)
    if reader.is_encrypted:
        raise ToolError("That PDF is password-protected. Please remove the "
                        "password and try again.")

    out_path = Path(output_dir) / "watermarked.pdf"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    overlays: dict[tuple[float, float, float, float], object] = {}
    try:
        # clone_from keeps pages assigned to the writer (merge then avoids
        # the pypdf 7 deprecation path of foreign-page mutation). The merge
        # translation aligns the overlay with the page's MediaBox origin —
        # pages whose box does not start at (0, 0) would otherwise get the
        # stamp shifted by that origin offset.
        writer = PdfWriter(clone_from=str(src))
        for page in writer.pages:
            box = page.mediabox
            key = (round(float(box.left), 2), round(float(box.bottom), 2),
                   round(float(box.width), 2), round(float(box.height), 2))
            if key not in overlays:
                overlays[key] = _overlay_page(key[2], key[3], text, position,
                                              alpha)
            page.merge_transformed_page(
                overlays[key], (1.0, 0.0, 0.0, 1.0, key[0], key[1]))
        with open(out_path, "wb") as fh:
            writer.write(fh)
    except ToolError:
        raise
    except Exception:
        raise ToolError(_CORRUPT_MSG)
    return out_path
