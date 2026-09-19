"""Pure PDF compression service (no Flask).

Two levels:
  basic   -- structural clean-up: garbage collection, stream/object
             deflation, font deflation, page clean.
  extreme -- everything basic does PLUS raster-image recompression:
             oversized images are downscaled with Pillow (longest side
             capped) and re-encoded as lower-quality JPEG, then swapped
             back into the PDF via PyMuPDF's Page.replace_image.

Returns a single output Path. Raises app.errors.ToolError for anything
the user can fix (wrong level, multiple files, unreadable PDF).
"""
import io
from pathlib import Path

from app.errors import ToolError

LEVELS = ("basic", "extreme")

# extreme-mode image policy
MAX_IMAGE_SIDE = 1500      # longest side after downscale (px)
BIG_PIXELS = 800_000       # only bother recompressing images >= this area
JPEG_QUALITY = 45

_BASIC_SAVE_KW = dict(
    garbage=4,
    deflate=True,
    deflate_images=True,
    deflate_fonts=True,
    clean=True,
)


def _validate(level: str) -> str:
    if not isinstance(level, str):
        raise ToolError("Unknown compression level. Choose 'basic' or "
                        "'extreme'.")
    level = level.strip().lower()
    if level not in LEVELS:
        raise ToolError("Unknown compression level. Choose 'basic' or "
                        "'extreme'.")
    return level


def _open(src: Path):
    import pymupdf
    try:
        doc = pymupdf.open(src)
    except Exception:
        raise ToolError("That PDF could not be opened for compression. It "
                        "may be corrupted or password-protected.")
    if doc.needs_pass:
        doc.close()
        raise ToolError("That PDF is password-protected. Please remove the "
                        "password and try again.")
    return doc


def _recompress_images(doc) -> int:
    """Downscale + re-JPEG large raster images. Returns how many were
    replaced. Never raises: any per-image failure is skipped so the basic
    structural compression still happens."""
    replaced = 0
    try:
        from PIL import Image
    except ImportError:
        return 0
    if not any(hasattr(page, "replace_image") for page in doc):
        return 0

    seen: set[int] = set()
    for page in doc:
        try:
            images = page.get_images(full=True)
        except Exception:
            continue
        for img in images:
            xref = img[0]
            if xref in seen:
                continue
            seen.add(xref)
            # Skip images that carry a transparency SMask: extract_image()
            # returns only the base stream, and replace_image() severs the
            # mask link, silently destroying the image's transparency.
            # Structural (basic-level) compression still applies to them.
            if len(img) > 1 and img[1]:
                continue
            try:
                info = doc.extract_image(xref)
                if not info or not info.get("image"):
                    continue
                w, h = int(info.get("width") or 0), int(info.get("height") or 0)
                if w * h < BIG_PIXELS:
                    continue
                im = Image.open(io.BytesIO(info["image"]))
                im.load()
                if im.mode not in ("RGB", "L"):
                    im = im.convert("RGB")
                if max(im.size) > MAX_IMAGE_SIDE:
                    scale = MAX_IMAGE_SIDE / max(im.size)
                    im = im.resize(
                        (max(1, round(im.width * scale)),
                         max(1, round(im.height * scale))),
                        Image.LANCZOS)
                buf = io.BytesIO()
                im.save(buf, format="JPEG", quality=JPEG_QUALITY,
                        optimize=True)
                new_bytes = buf.getvalue()
                # only swap when it actually helps
                if len(new_bytes) >= len(info["image"]):
                    continue
                if hasattr(page, "replace_image"):
                    page.replace_image(xref, stream=new_bytes)
                    replaced += 1
            except Exception:
                continue
    return replaced


def run(inputs: list[Path], output_dir: Path, level: str = "basic",
        **options) -> Path:
    """Compress a single PDF; return the output Path.

    `level` is the only option the route sends; extra option keys from
    `run_job`'s **options are accepted and ignored so a future route-level
    option can never turn into a TypeError.
    """
    level = _validate(level)
    if len(inputs) != 1:
        raise ToolError("Compress PDF works on one file at a time. Please "
                        "upload a single PDF.")
    src = Path(inputs[0])
    outdir = Path(output_dir)
    try:
        outdir.mkdir(parents=True, exist_ok=True)
    except OSError:
        raise ToolError("The output folder could not be prepared for this "
                        "job. Please try again.")

    doc = _open(src)
    try:
        if doc.page_count == 0:
            raise ToolError("That PDF has no pages to compress.")
        if level == "extreme":
            _recompress_images(doc)
        out = outdir / "compressed.pdf"
        doc.save(out, **_BASIC_SAVE_KW)
    finally:
        doc.close()
    if not out.is_file() or out.stat().st_size == 0:
        raise ToolError("Compression failed to produce an output file. "
                        "Please try a different PDF.")
    return out
