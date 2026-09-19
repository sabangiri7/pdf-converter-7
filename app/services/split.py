"""Pure split service: extract pages, split every page, odd/even, from/to,
or fixed-size chunks. No Flask imports.

`parse_page_ranges` is the strict, user-facing page-spec parser ("1-3,5")
and is unit-tested directly. All validation errors are ToolErrors with
user-safe messages.
"""
import re
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from ..errors import ToolError
from ..helpers import page_count

# a single token is "N" or "N-M"; ASCII digits only (no signs, junk).
# Optional whitespace around the hyphen ("1 - 2") is tolerated for
# consistency with "1 , 3", but "1 2" (space instead of a hyphen) stays
# malformed. re.ASCII keeps Python's \d from matching non-ASCII digits
# (e.g. Arabic-Indic or full-width), and the 9-digit cap keeps int()
# inside CPython's 4300-digit conversion limit so a huge spec cannot
# raise a raw ValueError instead of a ToolError.
_TOKEN_RE = re.compile(r"\A\d{1,9}(?:\s*-\s*\d{1,9})?\Z", re.ASCII)

MODES = ("extract", "all", "odd", "even", "from", "to", "chunks")


def parse_page_ranges(spec, total):
    """Parse a page spec like "1-3,5" into 1-based inclusive (start, end)
    pairs, in the order given. Blank/empty spec -> [(1, total)] (all pages).

    Raises ToolError (friendly, user-safe) on: a malformed token, page 0,
    a reversed range like "5-2", or any page beyond `total`.
    """
    spec = str(spec or "").strip()
    if not spec:
        return [(1, total)]
    ranges = []
    for token in spec.split(","):
        token = token.strip()
        if not _TOKEN_RE.match(token):
            shown = token if len(token) <= 40 else token[:40] + "..."
            raise ToolError(
                f"'{shown}' is not a valid page range. Use whole numbers "
                f'like 2, or ranges like 1-5, separated by commas (e.g. '
                f'"1-3,5").')
        if "-" in token:
            start_s, end_s = token.split("-", 1)
            start, end = int(start_s), int(end_s)
            if start < 1 or end < 1:
                raise ToolError(
                    f"'{token}' is not a valid page range: pages start "
                    f"at 1, not 0.")
            if start > end:
                raise ToolError(
                    f"'{token}' is a reversed range. Write "
                    f"'{end}-{start}' instead.")
            if end > total:
                raise ToolError(_too_big_message(end, total))
        else:
            page = int(token)
            if page < 1:
                raise ToolError(
                    f"'{token}' is not a valid page range: pages start "
                    f"at 1, not 0.")
            if page > total:
                raise ToolError(_too_big_message(page, total))
            start, end = page, page
        ranges.append((start, end))
    return ranges


def _too_big_message(page, total):
    plural = "page" if total == 1 else "pages"
    return (f"Page {page} does not exist: that PDF has {total} {plural}.")


def _parse_positive_int(value, *, field_label: str) -> int:
    """Parse a required positive whole number from a form/option value."""
    raw = str(value if value is not None else "").strip()
    if not raw or not re.fullmatch(r"\d{1,9}", raw, re.ASCII):
        raise ToolError(
            f"Enter a whole number for {field_label} (for example 2).")
    n = int(raw)
    if n < 1:
        raise ToolError(
            f"{field_label.capitalize()} must be at least 1.")
    return n


def run(inputs: list[Path], output_dir: Path, mode="extract",
        ranges="", page="", chunk_size="", **options) -> "Path | list[Path]":
    """Split one PDF.

    Modes:
      extract — one PDF with the selected page ranges (empty = all pages)
      all     — one 1-page PDF per page (page-1.pdf, ...)
      odd     — one PDF with only odd pages (1, 3, 5, ...)
      even    — one PDF with only even pages (2, 4, 6, ...)
      from    — one PDF from ``page`` through the end
      to      — one PDF from page 1 through ``page``
      chunks  — several PDFs, each with ``chunk_size`` pages
    """
    inputs = [Path(p) for p in inputs]
    if len(inputs) != 1:
        raise ToolError("Split works on one PDF at a time. Please upload "
                        "exactly one PDF.")
    mode = str(mode or "extract").strip().lower()
    if mode not in MODES:
        raise ToolError("Choose a valid split option.")

    src = inputs[0]
    total = page_count(src)  # friendly ToolError if corrupt / encrypted
    if total < 1:
        raise ToolError("That PDF does not contain any pages.")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        reader = PdfReader(str(src), strict=False)
    except Exception:
        raise ToolError("That file doesn't look like a valid PDF, or it is "
                        "corrupted. Please try a different file.")

    if mode == "all":
        outputs = []
        for i in range(total):
            out = output_dir / f"page-{i + 1}.pdf"
            _write_pages(reader.pages[i:i + 1], out)
            outputs.append(out)
        return outputs

    if mode == "chunks":
        size = _parse_positive_int(chunk_size, field_label="pages per file")
        if size > total:
            raise ToolError(
                f"Pages per file ({size}) is larger than this PDF "
                f"({total} pages). Choose a smaller number.")
        outputs = []
        part = 1
        for start0 in range(0, total, size):
            end0 = min(start0 + size, total)
            out = output_dir / f"part-{part}.pdf"
            _write_pages(reader.pages[start0:end0], out)
            outputs.append(out)
            part += 1
        return outputs

    if mode == "odd":
        selected = list(range(1, total + 1, 2))
        if not selected:
            raise ToolError("That PDF has no odd-numbered pages to extract.")
        out = output_dir / "odd-pages.pdf"
        _write_pages([reader.pages[n - 1] for n in selected], out)
        return out

    if mode == "even":
        selected = list(range(2, total + 1, 2))
        if not selected:
            raise ToolError(
                "That PDF has only one page, so there are no even pages "
                "to extract.")
        out = output_dir / "even-pages.pdf"
        _write_pages([reader.pages[n - 1] for n in selected], out)
        return out

    if mode in ("from", "to"):
        n = _parse_positive_int(page, field_label="page number")
        if n > total:
            raise ToolError(_too_big_message(n, total))
        if mode == "from":
            selected = list(range(n, total + 1))
            out = output_dir / "from-page.pdf"
        else:
            selected = list(range(1, n + 1))
            out = output_dir / "to-page.pdf"
        _write_pages([reader.pages[i - 1] for i in selected], out)
        return out

    # extract
    selected = [page_no
                for start, end in parse_page_ranges(ranges, total)
                for page_no in range(start, end + 1)]
    out = output_dir / "split.pdf"
    _write_pages([reader.pages[n - 1] for n in selected], out)
    return out


def _write_pages(pages, dest):
    writer = PdfWriter()
    for page in pages:
        writer.add_page(page)
    with open(dest, "wb") as fh:
        writer.write(fh)
