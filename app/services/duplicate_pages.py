"""Duplicate selected pages of a PDF (copies appended at the end)."""
import re
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from app.errors import ToolError
from app.helpers import detect_kind

_BAD = ("That file doesn't look like a valid PDF, or it is corrupted. "
        "Please try a different file.")
_TOKEN = re.compile(r"\A\d{1,9}(?:\s*-\s*\d{1,9})?\Z", re.ASCII)


def parse_pages(spec, total: int) -> list[int]:
    text = str(spec or "").strip()
    if not text:
        raise ToolError('Enter pages to duplicate, e.g. "1,3" or "2-4".')
    out: list[int] = []
    for token in text.split(","):
        token = token.strip()
        if not _TOKEN.match(token):
            raise ToolError('Page list must look like "1,3" or "2-4".')
        if "-" in token:
            a, b = token.split("-", 1)
            start, end = int(a), int(b)
            if start > end or start < 1 or end > total:
                raise ToolError(
                    f"Page selection is out of range (this PDF has "
                    f"{total} pages).")
            out.extend(range(start, end + 1))
        else:
            p = int(token)
            if not 1 <= p <= total:
                raise ToolError(
                    f"Page selection is out of range (this PDF has "
                    f"{total} pages).")
            out.append(p)
    return out


def clean_copies(value) -> int:
    try:
        n = int(str(value).strip())
    except (TypeError, ValueError):
        raise ToolError("Copies must be a whole number between 1 and 20.")
    if not 1 <= n <= 20:
        raise ToolError("Copies must be a whole number between 1 and 20.")
    return n


def run(inputs: list[Path], output_dir: Path, *,
        pages: str = "", copies: int = 1, **_options) -> Path:
    if len(inputs) != 1:
        raise ToolError("Duplicate Pages works on one PDF at a time.")
    src = Path(inputs[0])
    if detect_kind(src) != "pdf":
        raise ToolError("Please upload a PDF file.")
    copies = clean_copies(copies)
    try:
        reader = PdfReader(str(src), strict=False)
    except Exception:
        raise ToolError(_BAD)
    if reader.is_encrypted:
        raise ToolError("That PDF is password-protected.")
    total = len(reader.pages)
    if total < 1:
        raise ToolError("That PDF has no pages.")
    selected = parse_pages(pages, total)
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    for _ in range(copies):
        for n in selected:
            writer.add_page(reader.pages[n - 1])
    out = Path(output_dir) / "duplicated.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as fh:
        writer.write(fh)
    return out
