"""Best-effort deskew: detect page skew via text direction and re-render."""
import math
from pathlib import Path

import pymupdf

from app.errors import ToolError
from app.helpers import detect_kind

_BAD = ("That file doesn't look like a valid PDF, or it is corrupted. "
        "Please try a different file.")


def _estimate_skew(page) -> float:
    try:
        d = page.get_text("dict")
    except Exception:
        return 0.0
    angles: list[float] = []
    for block in d.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            dir_ = line.get("dir")
            if not dir_ or len(dir_) < 2:
                continue
            dx, dy = float(dir_[0]), float(dir_[1])
            if abs(dx) < 1e-6 and abs(dy) < 1e-6:
                continue
            ang = math.degrees(math.atan2(dy, dx))
            if ang > 45:
                ang -= 90
            elif ang < -45:
                ang += 90
            if abs(ang) < 15:
                angles.append(ang)
    if not angles:
        return 0.0
    angles.sort()
    return angles[len(angles) // 2]


def run(inputs: list[Path], output_dir: Path, **_options) -> Path:
    if len(inputs) != 1:
        raise ToolError("Deskew PDF works on one PDF at a time.")
    src = Path(inputs[0])
    if detect_kind(src) != "pdf":
        raise ToolError("Please upload a PDF file.")
    try:
        doc = pymupdf.open(str(src))
    except Exception:
        raise ToolError(_BAD)
    out = Path(output_dir) / "deskewed.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)
    out_doc = pymupdf.open()
    try:
        if doc.needs_pass:
            raise ToolError("That PDF is password-protected.")
        if doc.page_count < 1:
            raise ToolError("That PDF has no pages.")
        for i in range(doc.page_count):
            page = doc[i]
            skew = _estimate_skew(page)
            mat = pymupdf.Matrix(2, 2)
            if abs(skew) >= 0.3:
                mat = mat.prerotate(-skew)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            rect = page.rect
            np = out_doc.new_page(width=rect.width, height=rect.height)
            np.insert_image(rect, pixmap=pix)
        out_doc.save(str(out), garbage=4, deflate=True)
    except ToolError:
        raise
    except Exception:
        raise ToolError(_BAD)
    finally:
        out_doc.close()
        doc.close()
    return out
