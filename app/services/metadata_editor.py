"""Edit common PDF document metadata fields."""
from pathlib import Path

import pikepdf

from app.errors import ToolError
from app.helpers import detect_kind

MAX_FIELD = 200
_BAD = ("That file doesn't look like a valid PDF, or it is corrupted. "
        "Please try a different file.")


def clean_field(value, *, label: str) -> str:
    text = str(value if value is not None else "").strip()
    if len(text) > MAX_FIELD:
        raise ToolError(f"{label} must be {MAX_FIELD} characters or fewer.")
    return text


def run(inputs: list[Path], output_dir: Path, *,
        title: str = "",
        author: str = "",
        subject: str = "",
        keywords: str = "",
        **_options) -> Path:
    fields = {
        "/Title": clean_field(title, label="Title"),
        "/Author": clean_field(author, label="Author"),
        "/Subject": clean_field(subject, label="Subject"),
        "/Keywords": clean_field(keywords, label="Keywords"),
    }
    if len(inputs) != 1:
        raise ToolError("PDF Metadata Editor works on one PDF at a time.")
    src = Path(inputs[0])
    if detect_kind(src) != "pdf":
        raise ToolError("Please upload a PDF file.")
    out = Path(output_dir) / "metadata.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        with pikepdf.open(str(src)) as pdf:
            for key, val in fields.items():
                if val:
                    pdf.docinfo[key] = val
                elif key in pdf.docinfo:
                    try:
                        del pdf.docinfo[key]
                    except Exception:
                        pass
            pdf.save(str(out))
    except ToolError:
        raise
    except Exception:
        raise ToolError(_BAD)
    return out
