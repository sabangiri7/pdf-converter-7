"""Fill AcroForm text fields on a PDF from name=value lines."""
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from app.errors import ToolError
from app.helpers import detect_kind

MAX_LINES = 200
MAX_VALUE = 500
_BAD = ("That file doesn't look like a valid PDF, or it is corrupted. "
        "Please try a different file.")


def parse_fields(raw) -> dict[str, str]:
    text = str(raw if raw is not None else "")
    lines = [ln.strip() for ln in text.replace("\r\n", "\n").split("\n")
             if ln.strip()]
    if not lines:
        raise ToolError(
            "Enter form fields as one name=value pair per line.")
    if len(lines) > MAX_LINES:
        raise ToolError(f"Too many field lines (max {MAX_LINES}).")
    out: dict[str, str] = {}
    for ln in lines:
        if "=" not in ln:
            raise ToolError(
                f'Each line must be name=value (problem with "{ln[:40]}").')
        key, val = ln.split("=", 1)
        key, val = key.strip(), val.strip()
        if not key:
            raise ToolError("Field names cannot be empty.")
        if len(val) > MAX_VALUE:
            raise ToolError(f'Value for "{key}" is too long.')
        out[key] = val
    return out


def run(inputs: list[Path], output_dir: Path, *, fields: str = "",
        **_options) -> Path:
    values = parse_fields(fields)
    if len(inputs) != 1:
        raise ToolError("Fill PDF Forms works on one PDF at a time.")
    src = Path(inputs[0])
    if detect_kind(src) != "pdf":
        raise ToolError("Please upload a PDF file.")
    try:
        reader = PdfReader(str(src), strict=False)
    except Exception:
        raise ToolError(_BAD)
    if reader.is_encrypted:
        raise ToolError("That PDF is password-protected.")
    existing = reader.get_fields() or {}
    if not existing:
        raise ToolError(
            "That PDF has no fillable form fields (AcroForm). "
            "Only interactive PDF forms can be filled.")
    # Match case-insensitively where helpful
    lower_map = {k.lower(): k for k in existing}
    mapped: dict[str, str] = {}
    missing = []
    for k, v in values.items():
        if k in existing:
            mapped[k] = v
        elif k.lower() in lower_map:
            mapped[lower_map[k.lower()]] = v
        else:
            missing.append(k)
    if missing:
        raise ToolError(
            "Unknown form field(s): " + ", ".join(missing[:8])
            + ". Check the field names in the PDF.")
    writer = PdfWriter(clone_from=str(src))
    try:
        writer.set_need_appearances_writer(True)
        for page in writer.pages:
            writer.update_page_form_field_values(page, mapped)
    except ToolError:
        raise
    except Exception:
        raise ToolError(
            "The form fields could not be filled. The PDF form may use "
            "unsupported field types.")
    out = Path(output_dir) / "filled.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as fh:
        writer.write(fh)
    return out
