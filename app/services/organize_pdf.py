"""Reorder or drop pages of a PDF into a new document.

`pages` is an ordered 1-based list / ranges (e.g. "3,1,2" or "1-2,4").
Pages not listed are omitted. Pure service: no Flask.
"""
import re
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from ..errors import ToolError
from ..helpers import detect_kind, page_count

_TOKEN_RE = re.compile(r"\A\d{1,9}(?:\s*-\s*\d{1,9})?\Z", re.ASCII)


def parse_page_order(spec, total: int) -> list[int]:
    """Parse '3,1-2' into an ordered list of 1-based page numbers."""
    text = str(spec or "").strip()
    if not text:
        raise ToolError(
            "Enter the pages to keep, in order — for example 3,1,2 or 1-2,4.")
    ordered: list[int] = []
    for token in text.split(","):
        token = token.strip()
        if not _TOKEN_RE.match(token):
            shown = token if len(token) <= 40 else token[:40] + "..."
            raise ToolError(
                f"'{shown}' is not a valid page list. Use numbers like 2, "
                f'or ranges like 1-3, separated by commas.')
        if "-" in token:
            a_s, b_s = token.split("-", 1)
            start, end = int(a_s), int(b_s)
            if start < 1 or end < 1:
                raise ToolError("Pages start at 1, not 0.")
            if start > end:
                raise ToolError(
                    f"'{token}' is a reversed range. Write '{end}-{start}' "
                    f"instead.")
            if end > total:
                plural = "page" if total == 1 else "pages"
                raise ToolError(
                    f"Page {end} does not exist: that PDF has {total} "
                    f"{plural}.")
            ordered.extend(range(start, end + 1))
        else:
            page = int(token)
            if page < 1:
                raise ToolError("Pages start at 1, not 0.")
            if page > total:
                plural = "page" if total == 1 else "pages"
                raise ToolError(
                    f"Page {page} does not exist: that PDF has {total} "
                    f"{plural}.")
            ordered.append(page)
    if not ordered:
        raise ToolError("Enter at least one page to keep.")
    return ordered


def run(inputs: list[Path], output_dir: Path, pages: str = "",
        **_options) -> Path:
    """Build a new PDF with pages in the requested order (drops the rest)."""
    inputs = [Path(p) for p in (inputs or [])]
    if len(inputs) != 1:
        raise ToolError("Organize works on one PDF at a time. Please upload "
                        "a single PDF.")
    src = inputs[0]
    if not src.is_file():
        raise ToolError("Your uploaded file is missing or expired. Please "
                        "upload it again.")
    if detect_kind(src) != "pdf":
        raise ToolError("That file doesn't look like a valid PDF.")

    total = page_count(src)
    if total < 1:
        raise ToolError("That PDF does not contain any pages.")

    order = parse_page_order(pages, total)

    try:
        reader = PdfReader(str(src), strict=False)
        writer = PdfWriter()
        for n in order:
            writer.add_page(reader.pages[n - 1])
    except ToolError:
        raise
    except Exception:
        raise ToolError("That PDF could not be reorganized. It may be "
                        "corrupted.")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / "organized.pdf"
    try:
        with open(out, "wb") as fh:
            writer.write(fh)
    except Exception:
        out.unlink(missing_ok=True)
        raise ToolError("The organized PDF could not be written. Please try "
                        "again.")
    return out
