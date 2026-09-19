"""Extract embedded images from a PDF with PyMuPDF."""
from pathlib import Path

import pymupdf

from app.errors import ToolError
from app.helpers import detect_kind

_BAD = ("That file doesn't look like a valid PDF, or it is corrupted. "
        "Please try a different file.")


def run(inputs: list[Path], output_dir: Path, **_options) -> list[Path]:
    if len(inputs) != 1:
        raise ToolError("Extract Images works on one PDF at a time.")
    src = Path(inputs[0])
    if detect_kind(src) != "pdf":
        raise ToolError("Please upload a PDF file.")
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    try:
        doc = pymupdf.open(str(src))
    except Exception:
        raise ToolError(_BAD)
    try:
        if doc.needs_pass:
            raise ToolError("That PDF is password-protected.")
        seen: set[int] = set()
        n = 0
        for page in doc:
            for img in page.get_images(full=True):
                xref = img[0]
                if xref in seen:
                    continue
                seen.add(xref)
                try:
                    extracted = doc.extract_image(xref)
                except Exception:
                    continue
                if not extracted or not extracted.get("image"):
                    continue
                ext = (extracted.get("ext") or "png").lower()
                if ext == "jpeg":
                    ext = "jpg"
                n += 1
                path = out_dir / f"image-{n}.{ext}"
                path.write_bytes(extracted["image"])
                outputs.append(path)
    finally:
        doc.close()
    if not outputs:
        raise ToolError("No embedded images were found in that PDF.")
    return outputs
