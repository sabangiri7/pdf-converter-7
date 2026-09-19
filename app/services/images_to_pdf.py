"""Pure service: combine images into one PDF.

No Flask here. Inputs are saved upload paths (in order); the output is a
single PDF written into `output_dir`.

Strategy (see tool spec):
  * prefer img2pdf, which embeds JPEG/PNG/TIFF losslessly;
  * img2pdf raises on alpha-PNG / webp / some tiff / CMYK jpeg, so each
    image is probed individually and, on failure, converted through Pillow
    to an RGB PNG in memory and re-probed;
  * "a4" mode scales/pastes every image centred onto a white A4 canvas at
    150 DPI (with the requested margin baked in as whitespace), and the
    composite is handed to img2pdf with its DPI recorded so the PDF page
    comes out at true A4 size (595 x 842 pt).
"""
import io
from pathlib import Path

import img2pdf
from PIL import Image, ImageOps

from app.errors import ToolError

PAGE_SIZES = ("fit", "a4")
MARGINS = ("none", "small", "big")

# margin name -> whitespace in pixels on the 150-DPI A4 canvas
_MARGIN_PX = {"none": 0, "small": 50, "big": 120}

DPI = 150
# A4 is 210 x 297 mm
A4_PX = (round(210 / 25.4 * DPI), round(297 / 25.4 * DPI))  # 1240 x 1754

_BAD_IMAGE_MSG = ("One of the uploaded files could not be read as an image. "
                  "Please upload valid JPG, PNG, TIFF or WebP files.")


def validate_options(page_size, margin) -> dict:
    """Sanitize raw option values -> options dict. Raises ToolError with a
    user-safe message on junk. Unknown-but-empty values fall back to the
    defaults ('fit' / 'none')."""
    ps = str(page_size or "fit").strip().lower()
    mg = str(margin or "none").strip().lower()
    if ps not in PAGE_SIZES:
        raise ToolError("Please choose a valid page size: either fit the "
                        "pages to the images or use A4.")
    if mg not in MARGINS:
        raise ToolError("Please choose a valid margin: none, small or big.")
    return {"page_size": ps, "margin": mg}


# ---------------------------------------------------------------------------
# payloads
# ---------------------------------------------------------------------------

def _convertible(payload) -> bool:
    """True if img2pdf can embed this payload on its own."""
    try:
        img2pdf.convert([payload])
        return True
    except Exception:
        return False


def _rgb_png_bytes(im: Image.Image, dpi=None) -> bytes:
    buf = io.BytesIO()
    im.convert("RGB").save(buf, format="PNG",
                           **({"dpi": (dpi, dpi)} if dpi else {}))
    return buf.getvalue()


def _fit_payload(path: Path) -> bytes:
    """Bytes for `path` that img2pdf will accept: the original file when
    possible (lossless), a Pillow RGB-PNG conversion otherwise."""
    try:
        raw = path.read_bytes()
    except OSError:
        raise ToolError(_BAD_IMAGE_MSG)
    if _convertible(raw):
        return raw
    # fall back through Pillow (alpha PNG, webp, odd tiff, CMYK jpeg, ...)
    try:
        im = Image.open(io.BytesIO(raw))
        im.load()
        # bake the EXIF display orientation into the pixels (the re-encoded
        # PNG carries no EXIF, so img2pdf can no longer express it as /Rotate)
        im = ImageOps.exif_transpose(im)
    except Exception:
        raise ToolError(_BAD_IMAGE_MSG)
    dpi = (im.info.get("dpi") or (0, 0))[0] or None
    payload = _rgb_png_bytes(im, dpi=dpi)
    if not _convertible(payload):
        raise ToolError(_BAD_IMAGE_MSG)
    return payload


def _a4_payload(path: Path, margin: str) -> bytes:
    """Composite the image centred on a white A4 canvas (150 DPI) with the
    given margin, as RGB PNG bytes carrying the DPI so img2pdf emits a
    true-size A4 page."""
    try:
        im = Image.open(path)
        im.load()
        # respect EXIF display orientation: an unrotated landscape jpeg with
        # Orientation=6 must land portrait-centred on the A4 canvas
        im = ImageOps.exif_transpose(im)
    except Exception:
        raise ToolError(_BAD_IMAGE_MSG)
    if im.mode != "RGB":
        im = im.convert("RGB")
    m = _MARGIN_PX[margin]
    cw, ch = max(A4_PX[0] - 2 * m, 1), max(A4_PX[1] - 2 * m, 1)
    im.thumbnail((cw, ch), Image.LANCZOS)
    canvas = Image.new("RGB", A4_PX, "white")
    canvas.paste(im, ((A4_PX[0] - im.width) // 2, (A4_PX[1] - im.height) // 2))
    return _rgb_png_bytes(canvas, dpi=DPI)


# ---------------------------------------------------------------------------
# service entry point
# ---------------------------------------------------------------------------

def run(inputs: list[Path], output_dir: Path,
        page_size: str = "fit", margin: str = "none") -> Path:
    """Combine `inputs` (image paths, upload order) into one PDF in
    `output_dir`. Returns the output Path. Raises ToolError on bad options
    or unreadable images."""
    opts = validate_options(page_size, margin)
    page_size, margin = opts["page_size"], opts["margin"]
    paths = [Path(p) for p in (inputs or [])]
    if not paths:
        raise ToolError("Please upload at least one image.")

    if page_size == "a4":
        payloads = [_a4_payload(p, margin) for p in paths]
    else:
        payloads = [_fit_payload(p) for p in paths]

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / "images.pdf"
    try:
        with open(out, "wb") as fh:
            img2pdf.convert(payloads, outputstream=fh)
    except Exception:
        out.unlink(missing_ok=True)
        raise ToolError("The images could not be combined into a PDF. "
                        "Please check the files and try again.")
    return out
