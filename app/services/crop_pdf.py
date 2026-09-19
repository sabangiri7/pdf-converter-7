"""Crop every page of a PDF by margins (points)."""
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from app.errors import ToolError
from app.helpers import detect_kind

_BAD = ("That file doesn't look like a valid PDF, or it is corrupted. "
        "Please try a different file.")


def clean_margin(value, *, label: str) -> float:
    try:
        n = float(str(value).strip())
    except (TypeError, ValueError):
        raise ToolError(f"{label} must be a number of points (e.g. 36).")
    if n < 0 or n > 500:
        raise ToolError(f"{label} must be between 0 and 500 points.")
    return n


def run(inputs: list[Path], output_dir: Path, *,
        left: float = 0, right: float = 0,
        top: float = 0, bottom: float = 0, **_options) -> Path:
    left = clean_margin(left, label="Left margin")
    right = clean_margin(right, label="Right margin")
    top = clean_margin(top, label="Top margin")
    bottom = clean_margin(bottom, label="Bottom margin")
    if left == right == top == bottom == 0:
        raise ToolError("Enter at least one crop margin greater than 0.")
    if len(inputs) != 1:
        raise ToolError("Crop PDF works on one PDF at a time.")
    src = Path(inputs[0])
    if detect_kind(src) != "pdf":
        raise ToolError("Please upload a PDF file.")
    try:
        reader = PdfReader(str(src), strict=False)
    except Exception:
        raise ToolError(_BAD)
    if reader.is_encrypted:
        raise ToolError("That PDF is password-protected.")
    writer = PdfWriter()
    try:
        for page in reader.pages:
            box = page.mediabox
            new_left = float(box.left) + left
            new_bottom = float(box.bottom) + bottom
            new_right = float(box.right) - right
            new_top = float(box.top) - top
            if new_right - new_left < 36 or new_top - new_bottom < 36:
                raise ToolError(
                    "Crop margins are too large for one or more pages. "
                    "Reduce the margins and try again.")
            page.mediabox.lower_left = (new_left, new_bottom)
            page.mediabox.upper_right = (new_right, new_top)
            page.cropbox.lower_left = (new_left, new_bottom)
            page.cropbox.upper_right = (new_right, new_top)
            writer.add_page(page)
    except ToolError:
        raise
    except Exception:
        raise ToolError(_BAD)
    out = Path(output_dir) / "cropped.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as fh:
        writer.write(fh)
    return out
