"""Remove annotations (comments, highlights, stamps) from a PDF."""
from pathlib import Path

import pikepdf

from app.errors import ToolError
from app.helpers import detect_kind

_BAD = ("That file doesn't look like a valid PDF, or it is corrupted. "
        "Please try a different file.")


def run(inputs: list[Path], output_dir: Path, **_options) -> Path:
    if len(inputs) != 1:
        raise ToolError("Remove Annotations works on one PDF at a time.")
    src = Path(inputs[0])
    if detect_kind(src) != "pdf":
        raise ToolError("Please upload a PDF file.")
    out = Path(output_dir) / "no-annotations.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)
    removed = 0
    try:
        with pikepdf.open(str(src)) as pdf:
            for page in pdf.pages:
                annots = page.get("/Annots")
                if annots is not None:
                    removed += len(annots)
                    del page["/Annots"]
            pdf.save(str(out))
    except ToolError:
        raise
    except Exception:
        raise ToolError(_BAD)
    if removed == 0:
        # still return a cleaned rewrite — friendly note only if truly empty?
        # Keep silent success: user asked to remove annots; none is fine.
        pass
    return out
