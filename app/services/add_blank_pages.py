"""Insert blank pages into a PDF."""
import re
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from app.errors import ToolError
from app.helpers import detect_kind

_BAD = ("That file doesn't look like a valid PDF, or it is corrupted. "
        "Please try a different file.")


def clean_count(value) -> int:
    try:
        n = int(str(value).strip())
    except (TypeError, ValueError):
        raise ToolError("Enter how many blank pages to add (1–50).")
    if not 1 <= n <= 50:
        raise ToolError("Enter how many blank pages to add (1–50).")
    return n


def clean_at(value, total: int) -> int:
    """1-based insert-before position; total+1 = append."""
    raw = str(value if value is not None else "").strip().lower()
    if raw in ("", "end", "append"):
        return total + 1
    if not re.fullmatch(r"\d{1,9}", raw, re.ASCII):
        raise ToolError("Insert position must be a page number, or 'end'.")
    n = int(raw)
    if not 1 <= n <= total + 1:
        raise ToolError(f"Insert position must be between 1 and {total + 1}.")
    return n


def run(inputs: list[Path], output_dir: Path, *,
        count: int = 1, at: str = "end", **_options) -> Path:
    if len(inputs) != 1:
        raise ToolError("Add Blank Pages works on one PDF at a time.")
    src = Path(inputs[0])
    if detect_kind(src) != "pdf":
        raise ToolError("Please upload a PDF file.")
    count = clean_count(count)
    try:
        reader = PdfReader(str(src), strict=False)
    except Exception:
        raise ToolError(_BAD)
    if reader.is_encrypted:
        raise ToolError("That PDF is password-protected.")
    pages = list(reader.pages)
    total = len(pages)
    if total < 1:
        raise ToolError("That PDF has no pages.")
    pos = clean_at(at, total)
    box = pages[0].mediabox
    w, h = float(box.width), float(box.height)
    writer = PdfWriter()
    insert_at = pos - 1
    for i, page in enumerate(pages):
        if i == insert_at:
            for _ in range(count):
                writer.add_blank_page(width=w, height=h)
        writer.add_page(page)
    if insert_at >= total:
        for _ in range(count):
            writer.add_blank_page(width=w, height=h)
    out = Path(output_dir) / "blank-pages.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as fh:
        writer.write(fh)
    return out
