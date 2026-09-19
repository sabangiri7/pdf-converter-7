"""Extract selectable text from a PDF into a .txt file."""
from pathlib import Path

import pdfplumber

from app.errors import ToolError
from app.helpers import detect_kind

_BAD = ("That file doesn't look like a valid PDF, or it is corrupted. "
        "Please try a different file.")


def run(inputs: list[Path], output_dir: Path, **_options) -> Path:
    if len(inputs) != 1:
        raise ToolError("PDF to Text works on one PDF at a time.")
    src = Path(inputs[0])
    if detect_kind(src) != "pdf":
        raise ToolError("Please upload a PDF file.")
    parts: list[str] = []
    try:
        with pdfplumber.open(str(src)) as pdf:
            for i, page in enumerate(pdf.pages, 1):
                text = (page.extract_text() or "").strip()
                parts.append(f"--- Page {i} ---")
                parts.append(text if text else "[no selectable text]")
                parts.append("")
    except ToolError:
        raise
    except Exception:
        raise ToolError(_BAD)
    has_text = any(
        p and not p.startswith("---") and p != "[no selectable text]"
        for p in parts
    )
    if not has_text:
        raise ToolError("No selectable text was found in that PDF. If it is "
                        "a scan, run OCR first.")
    out = Path(output_dir) / "extracted.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(parts).rstrip() + "\n", encoding="utf-8")
    return out
