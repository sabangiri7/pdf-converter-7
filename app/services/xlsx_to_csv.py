"""Convert Excel (.xlsx) workbooks to CSV with openpyxl.

Pure service: no Flask. First worksheet only → UTF-8 CSV with BOM.
"""
import csv
from io import BytesIO
from pathlib import Path

from openpyxl import load_workbook

from ..errors import ToolError
from ..helpers import detect_kind

_MAX_ROWS = 100_000
_MAX_COLS = 256


def run(inputs: list[Path], output_dir: Path, **_options) -> Path:
    """Export the first sheet of one .xlsx upload to CSV."""
    inputs = [Path(p) for p in (inputs or [])]
    if len(inputs) != 1:
        raise ToolError("This tool converts one Excel file at a time. "
                        "Please upload a single .xlsx file.")
    src = inputs[0]
    if not src.is_file():
        raise ToolError("Your uploaded file is missing or expired. Please "
                        "upload it again.")
    if detect_kind(src) != "zip":
        raise ToolError("That file doesn't look like an Excel .xlsx workbook. "
                        "Please upload a .xlsx file (not the old .xls format).")

    try:
        # Uploads are stored with a .zip suffix (OOXML is a ZIP). openpyxl
        # rejects that extension, so load from bytes instead of the path.
        wb = load_workbook(BytesIO(src.read_bytes()), read_only=True,
                           data_only=True)
    except Exception:
        raise ToolError("That Excel file could not be opened. Please make "
                        "sure it is a valid .xlsx workbook.")

    try:
        ws = wb.active
        if ws is None:
            raise ToolError("That workbook has no sheets to export.")

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        out = output_dir / "converted.csv"

        row_count = 0
        with open(out, "w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.writer(fh)
            for row in ws.iter_rows(values_only=True):
                row_count += 1
                if row_count > _MAX_ROWS:
                    out.unlink(missing_ok=True)
                    raise ToolError(
                        f"That sheet has too many rows (limit {_MAX_ROWS:,}).")
                cells = list(row)
                if len(cells) > _MAX_COLS:
                    out.unlink(missing_ok=True)
                    raise ToolError(
                        f"That sheet has too many columns (limit {_MAX_COLS}).")
                writer.writerow(["" if c is None else str(c) for c in cells])
        if row_count == 0:
            out.unlink(missing_ok=True)
            raise ToolError("That worksheet is empty. Please upload a file "
                            "with data.")
        return out
    finally:
        wb.close()
