"""Flatten form fields and strip annotations into static content."""
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from app.errors import ToolError
from app.helpers import detect_kind

_BAD = ("That file doesn't look like a valid PDF, or it is corrupted. "
        "Please try a different file.")


def run(inputs: list[Path], output_dir: Path, **_options) -> Path:
    if len(inputs) != 1:
        raise ToolError("Flatten PDF works on one PDF at a time.")
    src = Path(inputs[0])
    if detect_kind(src) != "pdf":
        raise ToolError("Please upload a PDF file.")
    try:
        reader = PdfReader(str(src), strict=False)
    except Exception:
        raise ToolError(_BAD)
    if reader.is_encrypted:
        raise ToolError("That PDF is password-protected.")
    writer = PdfWriter(clone_from=str(src))
    try:
        try:
            writer.set_need_appearances_writer(False)
        except Exception:
            pass
        for page in writer.pages:
            if "/Annots" in page:
                try:
                    del page["/Annots"]
                except Exception:
                    pass
        try:
            root = writer._root_object
            if "/AcroForm" in root:
                del root["/AcroForm"]
        except Exception:
            pass
    except ToolError:
        raise
    except Exception:
        raise ToolError(_BAD)
    out = Path(output_dir) / "flattened.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as fh:
        writer.write(fh)
    return out
