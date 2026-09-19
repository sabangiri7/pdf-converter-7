"""Render every page of a single PDF into JPG/PNG images with PyMuPDF.

Pure service: no Flask. `run()` receives the saved upload paths and an
output dir, returns the produced image paths in page order
(`page-1.jpg`, `page-2.jpg`, ...).
"""
import io
from pathlib import Path

import pymupdf

from ..errors import ToolError
from ..helpers import detect_kind

FORMATS = ("jpg", "png")
DEFAULT_FORMAT = "jpg"
DEFAULT_DPI = 150
DPI_MIN, DPI_MAX = 72, 400


# ---------------------------------------------------------------------------
# option validation (shared by the route's clean_options and run itself)
# ---------------------------------------------------------------------------

def validate_format(fmt) -> str:
    """'JPG ' -> 'jpg'; anything outside jpg/png -> user-safe ToolError."""
    fmt = str(fmt or "").strip().lower()
    if fmt == "jpeg":
        fmt = "jpg"
    if fmt not in FORMATS:
        raise ToolError("Unknown image format. Please choose JPG or PNG.")
    return fmt


def validate_dpi(dpi) -> int:
    """Whole number in 72-400, else user-safe ToolError."""
    try:
        value = int(dpi)
    except (TypeError, ValueError):
        raise ToolError("Resolution must be a whole number between "
                        f"{DPI_MIN} and {DPI_MAX} dpi.")
    if isinstance(dpi, float) and dpi != value:
        raise ToolError("Resolution must be a whole number between "
                        f"{DPI_MIN} and {DPI_MAX} dpi.")
    if not (DPI_MIN <= value <= DPI_MAX):
        raise ToolError(f"Resolution must be between {DPI_MIN} and "
                        f"{DPI_MAX} dpi.")
    return value


def clean_options(form) -> dict:
    """Validate request.form (anything with .get) -> kwargs for run()."""
    return {
        "format": validate_format(form.get("format", DEFAULT_FORMAT)),
        "dpi": validate_dpi(form.get("dpi", DEFAULT_DPI)),
    }


# ---------------------------------------------------------------------------
# service entry point
# ---------------------------------------------------------------------------

def run(inputs: list[Path], output_dir: Path, *,
        format: str = DEFAULT_FORMAT, dpi: int = DEFAULT_DPI) -> list[Path]:
    """Convert every page of the single uploaded PDF to `format` images at
    `dpi`. Returns the created paths in page order."""
    format = validate_format(format)
    dpi = validate_dpi(dpi)

    inputs = [Path(p) for p in (inputs or [])]
    if len(inputs) != 1:
        raise ToolError("This tool converts one PDF at a time. Please upload "
                        "a single PDF file.")
    src = inputs[0]
    if not src.is_file():
        raise ToolError("Your uploaded file is missing or expired. Please "
                        "upload it again.")
    if detect_kind(src) != "pdf":
        raise ToolError("That file doesn't look like a valid PDF. Please "
                        "upload a PDF file.")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        doc = pymupdf.open(src)
    except Exception:
        doc = None
    if doc is None:
        raise ToolError("That file doesn't look like a valid PDF, or it is "
                        "corrupted. Please try a different file.")
    try:
        try:
            if doc.needs_pass:
                raise ToolError("That PDF is password-protected. Please "
                                "remove the password and try again.")
            # Damaged page trees can make MuPDF raise right here (e.g. an
            # inflated /Count): surface as a clean ToolError, never raw.
            n_pages = doc.page_count
        except ToolError:
            raise
        except Exception:
            raise ToolError("That file doesn't look like a valid PDF, or it "
                            "is corrupted. Please try a different file.")
        if n_pages == 0:
            raise ToolError("That PDF has no pages to convert.")
        outputs: list[Path] = []
        try:
            for i in range(1, n_pages + 1):
                path = output_dir / f"page-{i}.{format}"
                try:
                    # One page at a time: the pixmap is dropped before the
                    # next page, so peak RAM stays near one rendered image.
                    pix = doc[i - 1].get_pixmap(dpi=dpi)
                    _save_pixmap(pix, path, format)
                except ToolError:
                    raise
                except Exception:
                    # A big page at high DPI can trip MuPDF's "Overly large
                    # image" limit (and other render errors): turn them into
                    # a user-safe ToolError, never a raw exception.
                    raise ToolError(
                        f"Page {i} of the PDF is too large or damaged to "
                        f"render at {dpi} dpi. Please try a lower "
                        f"resolution.")
                outputs.append(path)
        except Exception:
            # Never leave a partial image set behind on failure.
            path.unlink(missing_ok=True)
            for p in outputs:
                p.unlink(missing_ok=True)
            raise
        return outputs
    finally:
        doc.close()


def _save_pixmap(pix, path: Path, fmt: str) -> None:
    if fmt == "png":
        pix.save(str(path), output="png")
        return
    try:
        pix.save(str(path), output="jpg", jpg_quality=90)
    except Exception:
        # Some PyMuPDF builds refuse direct jpg saves (or the pixmap has an
        # alpha channel): re-encode through PIL from an in-memory PNG.
        path.unlink(missing_ok=True)
        try:
            from PIL import Image
            Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB") \
                .save(path, "JPEG", quality=90)
        except Exception:
            path.unlink(missing_ok=True)
            raise ToolError("The PDF could not be converted to images. "
                            "Please try again or pick the other format.")
