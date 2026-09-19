"""Convert CSV spreadsheets to Excel (.xlsx) with openpyxl.

Pure service: no Flask. Accepts one .csv upload; returns one .xlsx.
"""
import csv
from pathlib import Path

from openpyxl import Workbook

from ..errors import ToolError
from ..helpers import detect_kind

# Keep worksheets within Excel's practical cell limit.
_MAX_ROWS = 100_000
_MAX_COLS = 256


def _decode_text(raw: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ToolError("That CSV could not be read as text. Please save it as "
                    "UTF-8 and try again.")


def _sniff_dialect(sample: str):
    try:
        return csv.Sniffer().sniff(sample[:8192], delimiters=",;\t|")
    except csv.Error:
        return csv.excel


def run(inputs: list[Path], output_dir: Path, **_options) -> Path:
    """Parse the single CSV upload into an .xlsx workbook."""
    inputs = [Path(p) for p in (inputs or [])]
    if len(inputs) != 1:
        raise ToolError("This tool converts one CSV at a time. Please upload "
                        "a single CSV file.")
    src = inputs[0]
    if not src.is_file():
        raise ToolError("Your uploaded file is missing or expired. Please "
                        "upload it again.")
    if detect_kind(src) != "csv":
        raise ToolError("That file doesn't look like a CSV spreadsheet. "
                        "Please upload a .csv file.")

    try:
        raw = src.read_bytes()
    except OSError:
        raise ToolError("Your uploaded file is missing or expired. Please "
                        "upload it again.")
    if not raw.strip():
        raise ToolError("That CSV is empty. Please upload a file with data.")

    text = _decode_text(raw)
    dialect = _sniff_dialect(text)
    try:
        rows = list(csv.reader(text.splitlines(), dialect))
    except csv.Error:
        raise ToolError("That CSV could not be parsed. Please check the "
                        "delimiter and try again.")

    # Drop completely blank trailing rows.
    while rows and not any(cell.strip() for cell in rows[-1]):
        rows.pop()
    if not rows:
        raise ToolError("That CSV is empty. Please upload a file with data.")
    if len(rows) > _MAX_ROWS:
        raise ToolError(f"That CSV has too many rows (limit {_MAX_ROWS:,}).")
    width = max(len(r) for r in rows)
    if width > _MAX_COLS:
        raise ToolError(f"That CSV has too many columns (limit {_MAX_COLS}).")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / "converted.xlsx"

    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    for r_idx, row in enumerate(rows, start=1):
        for c_idx, value in enumerate(row, start=1):
            ws.cell(row=r_idx, column=c_idx, value=value)
    try:
        wb.save(out)
    except Exception:
        out.unlink(missing_ok=True)
        raise ToolError("The Excel file could not be written. Please try again.")
    return out
