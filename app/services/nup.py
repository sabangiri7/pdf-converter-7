"""N-up: place multiple PDF pages onto each output sheet."""
from pathlib import Path

from pypdf import PdfReader, PdfWriter, Transformation

from app.errors import ToolError
from app.helpers import detect_kind

LAYOUTS = {
    "2": (1, 2),  # cols, rows — 2-up side by side
    "4": (2, 2),
    "6": (2, 3),
    "9": (3, 3),
}
_BAD = ("That file doesn't look like a valid PDF, or it is corrupted. "
        "Please try a different file.")


def clean_n(value) -> str:
    v = str(value or "2").strip()
    if v not in LAYOUTS:
        raise ToolError("Choose 2, 4, 6, or 9 pages per sheet.")
    return v


def run(inputs: list[Path], output_dir: Path, *, n: str = "2",
        **_options) -> Path:
    n = clean_n(n)
    cols, rows = LAYOUTS[n]
    per_sheet = cols * rows
    if len(inputs) != 1:
        raise ToolError("PDF N-up works on one PDF at a time.")
    src = Path(inputs[0])
    if detect_kind(src) != "pdf":
        raise ToolError("Please upload a PDF file.")
    try:
        reader = PdfReader(str(src), strict=False)
    except Exception:
        raise ToolError(_BAD)
    if reader.is_encrypted:
        raise ToolError("That PDF is password-protected.")
    pages = list(reader.pages)
    if not pages:
        raise ToolError("That PDF has no pages.")
    box = pages[0].mediabox
    pw, ph = float(box.width), float(box.height)
    sheet_w, sheet_h = pw * cols, ph * rows
    writer = PdfWriter()
    for i in range(0, len(pages), per_sheet):
        chunk = pages[i:i + per_sheet]
        sheet = writer.add_blank_page(width=sheet_w, height=sheet_h)
        for j, page in enumerate(chunk):
            col = j % cols
            row = rows - 1 - (j // cols)  # top-to-bottom
            tx = col * pw
            ty = row * ph
            sheet.merge_transformed_page(
                page, Transformation().translate(tx, ty))
    out = Path(output_dir) / f"nup-{n}.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as fh:
        writer.write(fh)
    return out
