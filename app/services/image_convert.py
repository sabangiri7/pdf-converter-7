"""Convert images among JPG, PNG, WEBP, and TIFF with Pillow.

Pure service: no Flask. Accepts one or more image uploads; returns one
converted file per input.
"""
from pathlib import Path

from PIL import Image

from ..errors import ToolError
from ..helpers import detect_kind

FORMATS = ("jpg", "png", "webp", "tiff")
DEFAULT_FORMAT = "png"
_KIND_TO_PIL = {
    "jpg": "JPEG",
    "png": "PNG",
    "webp": "WEBP",
    "tiff": "TIFF",
}
_EXT = {
    "jpg": ".jpg",
    "png": ".png",
    "webp": ".webp",
    "tiff": ".tif",
}


def validate_format(fmt) -> str:
    fmt = str(fmt or "").strip().lower()
    if fmt == "jpeg":
        fmt = "jpg"
    if fmt in ("tif", "tiff"):
        fmt = "tiff"
    if fmt not in FORMATS:
        raise ToolError("Unknown image format. Please choose JPG, PNG, "
                        "WEBP or TIFF.")
    return fmt


def clean_options(form) -> dict:
    return {"format": validate_format(form.get("format", DEFAULT_FORMAT))}


def run(inputs: list[Path], output_dir: Path, *,
        format: str = DEFAULT_FORMAT) -> list[Path]:
    """Convert every uploaded image to `format`. Returns output paths."""
    format = validate_format(format)
    inputs = [Path(p) for p in (inputs or [])]
    if not inputs:
        raise ToolError("Please upload at least one image.")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    pil_fmt = _KIND_TO_PIL[format]
    ext = _EXT[format]

    try:
        for i, src in enumerate(inputs, start=1):
            if not src.is_file():
                raise ToolError("Your uploaded file is missing or expired. "
                                "Please upload it again.")
            kind = detect_kind(src)
            if kind not in ("png", "jpg", "tiff", "webp"):
                raise ToolError("One of the uploaded files is not a supported "
                                "image. Please upload JPG, PNG, TIFF or WEBP.")
            try:
                with Image.open(src) as im:
                    im.load()
                    out_im = _prepare_for_format(im, format)
                    name = f"image-{i}{ext}" if len(inputs) > 1 else f"converted{ext}"
                    dest = output_dir / name
                    save_kw = {}
                    if format == "jpg":
                        save_kw["quality"] = 90
                        save_kw["optimize"] = True
                    elif format == "webp":
                        save_kw["quality"] = 90
                    out_im.save(dest, pil_fmt, **save_kw)
            except ToolError:
                raise
            except Exception:
                raise ToolError("One of the uploaded files could not be read "
                                "as an image. Please try a different file.")
            outputs.append(dest)
    except Exception:
        for p in outputs:
            p.unlink(missing_ok=True)
        raise
    return outputs


def _prepare_for_format(im: Image.Image, fmt: str) -> Image.Image:
    """Convert mode so the target format can save cleanly."""
    if fmt == "jpg":
        if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
            rgba = im.convert("RGBA")
            bg = Image.new("RGB", rgba.size, (255, 255, 255))
            bg.paste(rgba, mask=rgba.split()[-1])
            return bg
        return im.convert("RGB")
    if fmt == "tiff":
        if im.mode == "P":
            return im.convert("RGBA") if "transparency" in im.info else im.convert("RGB")
        return im
    # png / webp keep alpha when present
    if im.mode == "P":
        return im.convert("RGBA") if "transparency" in im.info else im.convert("RGB")
    return im
