"""Pure service: rotate pages of a single PDF by 90, 180 or 270 degrees.

No Flask imports anywhere (CONTRACT.md purity rule). Raise ToolError for
anything the user can fix; unexpected failures are wrapped into a friendly
400 page by app.jobs.run_job.
"""
import re
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from app.errors import ToolError

VALID_ANGLES = (90, 180, 270)

_BAD_ANGLE = "Choose a rotation angle of 90, 180 or 270 degrees."
_BAD_PAGES = ('Page selection must be page numbers or ranges like "1,3-4" '
              "(the first page is 1).")
_BAD_PDF = ("That file doesn't look like a valid PDF, or it is corrupted. "
            "Please try a different file.")
_VERIFY_FAIL = ("The rotation did not apply correctly. Please try again "
                "with a different file.")

# ASCII digits only: str.isdigit() also matches "²"/"٣", which then crash int()
_UINT = re.compile(r"[0-9]+")
_DIGIT_CHUNK_MAX = 9  # page counts above this are out of range anyway and
#                      # keep int() far below CPython's 4300-digit limit.


def parse_angle(value) -> int:
    """Accept 90 | 180 | 270 as int or string. Anything else -> ToolError."""
    try:
        angle = int(str(value).strip())
    except (TypeError, ValueError):
        raise ToolError(_BAD_ANGLE)
    if angle not in VALID_ANGLES:
        raise ToolError(_BAD_ANGLE)
    return angle


def _page_number(text: str) -> int:
    """ASCII-digit string -> int; absurdly long numbers clamp above any page
    count so the caller's range check reports them as out of range instead
    of tripping CPython's integer-string-conversion limit."""
    if len(text) > _DIGIT_CHUNK_MAX:
        return 10 ** _DIGIT_CHUNK_MAX
    return int(text)


def _rotation_of(page) -> int:
    """Page's current /Rotate as an int in [0, 360). A non-numeric /Rotate
    (possible in a broken PDF) becomes a friendly ToolError, never a raw
    ValueError."""
    try:
        return int(page.rotation) % 360
    except (TypeError, ValueError):
        raise ToolError(_BAD_PDF)


def parse_pages(spec, n_pages: int) -> set[int]:
    """'1,3-4' -> {0, 2, 3} (0-based indices). None/empty -> every page.

    Raises ToolError on malformed syntax or out-of-range numbers.
    """
    if spec is None:
        return set(range(n_pages))
    text = str(spec).strip()
    if not text:
        return set(range(n_pages))
    selected: set[int] = set()
    for chunk in text.split(","):
        chunk = chunk.strip()
        m = re.fullmatch(r"([0-9]+)\s*-\s*([0-9]+)", chunk)
        if m:
            start, end = _page_number(m.group(1)), _page_number(m.group(2))
        elif _UINT.fullmatch(chunk):
            start = end = _page_number(chunk)
        else:
            raise ToolError(_BAD_PAGES)
        if start > end or start < 1 or end > n_pages:
            raise ToolError(
                f"Page selection is out of range: this PDF has {n_pages} "
                f"page{'s' if n_pages != 1 else ''}.")
        selected.update(range(start - 1, end))
    return selected


def run(inputs: list[Path], output_dir: Path, angle=90,
        pages: str = "") -> Path:
    """Rotate the selected pages of one PDF and write a single output.

    inputs: exactly one saved PDF path (order irrelevant). output_dir: write
    ONLY here. angle: 90|180|270 (int or string). pages: "" = all pages, or
    a 1-based comma/range list like "1,3-4". Returns the output Path;
    re-opens the written file and verifies the /Rotate values stuck.
    """
    if len(inputs) != 1:
        raise ToolError("Rotate works on one PDF at a time. Please upload a "
                        "single file.")
    src = Path(inputs[0])
    angle = parse_angle(angle)

    try:
        reader = PdfReader(str(src), strict=False)
        if reader.is_encrypted:
            raise ToolError("That PDF is password-protected. Please remove "
                            "the password and try again.")
        source_pages = list(reader.pages)
    except ToolError:
        raise
    except Exception:
        raise ToolError(_BAD_PDF)

    n = len(source_pages)
    if n == 0:
        raise ToolError("That PDF has no pages to rotate.")
    selected = parse_pages(pages, n)

    # snapshot original rotations BEFORE mutating anything; verify against
    # these later (a page may already carry its own /Rotate value).
    source_rot = [_rotation_of(p) for p in source_pages]

    writer = PdfWriter()
    for i, page in enumerate(source_pages):
        if i in selected:
            page.rotate(angle)
        writer.add_page(page)

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "rotated.pdf"
    with open(out_path, "wb") as fh:
        writer.write(fh)

    # verify rotation stuck: re-open and check each page's /Rotate value
    check = PdfReader(str(out_path), strict=False)
    expected = [((source_rot[i] + angle) % 360) if i in selected
                else source_rot[i] for i in range(n)]
    got = [_rotation_of(p) for p in check.pages]
    if len(got) != n or any((g - e) % 360 for g, e in zip(got, expected)):
        raise ToolError(_VERIFY_FAIL)
    return out_path
