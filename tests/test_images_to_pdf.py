"""Tests for the images_to_pdf tool: pure service + blueprint routes."""
import io
from pathlib import Path

import pytest
from PIL import Image
from pypdf import PdfReader

from app.errors import ToolError
from app.services.images_to_pdf import run, validate_options


def _write_img(dirpath: Path, name: str, mode="RGB", size=(800, 600),
               color=(180, 40, 40), fmt=None) -> Path:
    dirpath.mkdir(parents=True, exist_ok=True)
    p = dirpath / name
    Image.new(mode, size, color).save(p, format=fmt)
    return p


# ---------------------------------------------------------------------------
# service
# ---------------------------------------------------------------------------

def test_single_jpg_one_page(sample_image_jpg, tmp_path):
    out = run([sample_image_jpg], tmp_path)
    assert isinstance(out, Path) and out.is_file()
    assert out.read_bytes()[:4] == b"%PDF"
    r = PdfReader(out)
    assert len(r.pages) == 1
    # fit mode: page sized to the image at a sane DPI (samples carry no DPI
    # info -> img2pdf's 96 dpi default -> 600x450 pt) and aspect ratio kept
    box = r.pages[0].mediabox
    assert float(box.width) > 0 and float(box.height) > 0
    implied_dpi = 800 / (float(box.width) / 72)
    assert 50 <= implied_dpi <= 600
    assert abs(float(box.width) / float(box.height) - 800 / 600) < 0.05


def test_three_images_in_order_give_three_pages(sample_images, tmp_path):
    imgs = list(sample_images[:3])           # jpg, jpg, jpg in upload order
    out = run(imgs, tmp_path)
    r = PdfReader(out)
    assert len(r.pages) == 3


def test_mixed_png_and_jpg_accepted(sample_image_jpg, sample_image_png,
                                   tmp_path):
    """The 'image' kind alias must let png and jpg through together."""
    out = run([sample_image_jpg, sample_image_png], tmp_path)
    assert len(PdfReader(out).pages) == 2


def test_cmyk_jpeg_accepted(tmp_path):
    """CMYK jpeg (scanners/PS exports) must produce a page, either via
    img2pdf's native embed or the Pillow RGB fallback — never an error."""
    p = _write_img(tmp_path / "in", "cmyk.jpg", mode="CMYK",
                   color=(0, 100, 100, 10))
    out = run([p], tmp_path / "o")
    assert len(PdfReader(out).pages) == 1
    # and through the A4 canvas path too
    out_a4 = run([p], tmp_path / "o-a4", page_size="a4", margin="small")
    assert len(PdfReader(out_a4).pages) == 1


def test_page_order_preserved_by_dimensions(tmp_path):
    """Different-sized images must land on different-sized pages in input
    order (fit mode sizes each page to its image)."""
    a = _write_img(tmp_path / "in", "a.jpg", size=(800, 600))
    b = _write_img(tmp_path / "in", "b.jpg", size=(400, 900))
    out = run([a, b], tmp_path / "o")
    pages = PdfReader(out).pages
    assert len(pages) == 2
    ar = [float(p.mediabox.width) / float(p.mediabox.height) for p in pages]
    assert abs(ar[0] - 800 / 600) < 0.05
    assert abs(ar[1] - 400 / 900) < 0.05


def test_alpha_png_and_webp_fallback(tmp_path):
    """Alpha PNG / webp / tiff inputs must produce pages. (img2pdf 0.6.3
    embeds RGBA png via an /SMask and plain webp/tiff natively, so these may
    take the lossless path; the genuine Pillow fallback is proven by
    test_pillow_fallback_actually_used below.)"""
    png = _write_img(tmp_path / "in", "a.png", mode="RGBA",
                     color=(0, 120, 0, 128))
    webp = _write_img(tmp_path / "in", "b.webp", fmt="WEBP")
    tif = _write_img(tmp_path / "in", "c.tif", fmt="TIFF")
    out = run([png, webp, tif], tmp_path / "o")
    assert len(PdfReader(out).pages) == 3


def test_pillow_fallback_actually_used(tmp_path):
    """Inputs img2pdf genuinely refuses (RGBA webp, 16-bit tiff) must come
    out via the Pillow RGB-PNG fallback, not an error — and the fallback must
    really be exercised (payload re-encoded, not the raw bytes)."""
    from app.services.images_to_pdf import _fit_payload
    rgba_webp = tmp_path / "in" / "a.webp"
    rgba_webp.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (120, 90), (10, 200, 10, 160)).save(
        rgba_webp, format="WEBP", lossless=True)
    raw = rgba_webp.read_bytes()
    payload = _fit_payload(rgba_webp)
    assert payload != raw                      # Pillow conversion happened
    assert payload[:8] == b"\x89PNG\r\n\x1a\n"  # came back as RGB PNG
    tif16 = tmp_path / "in" / "b.tif"
    Image.new("I;16", (64, 64)).save(tif16, format="TIFF")
    assert _fit_payload(tif16) != tif16.read_bytes()
    out = run([rgba_webp, tif16], tmp_path / "o")
    assert len(PdfReader(out).pages) == 2


def test_a4_respects_exif_orientation(tmp_path):
    """A landscape-sampled jpeg with EXIF Orientation=6 displays as portrait;
    on the A4 canvas its centred content must be taller than wide."""
    import pymupdf
    jp = tmp_path / "in" / "rot.jpg"
    jp.parent.mkdir(parents=True, exist_ok=True)
    im = Image.new("RGB", (400, 200), (200, 0, 0))
    ex = Image.Exif()
    ex[0x0112] = 6                       # 90 deg CW -> display portrait
    im.save(jp, format="JPEG", exif=ex)
    out = run([jp], tmp_path / "o", page_size="a4")

    def red_bbox(pdf_path):
        doc = pymupdf.open(pdf_path)
        pix = doc[0].get_pixmap(dpi=36)
        minx = miny = 10 ** 9
        maxx = maxy = -1
        for y in range(pix.height):
            for x in range(pix.width):
                o = (y * pix.width + x) * pix.n
                if (pix.samples[o] > 150 and pix.samples[o + 1] < 100
                        and pix.samples[o + 2] < 100):
                    minx, maxx = min(minx, x), max(maxx, x)
                    miny, maxy = min(miny, y), max(maxy, y)
        doc.close()
        return maxx - minx, maxy - miny

    w, h = red_bbox(out)
    assert h > w > 0, f"EXIF-rotated image landed {w}x{h} (want portrait)"


def test_a4_margin_shrinks_content(tmp_path):
    """The margin option must actually leave white border: the rendered
    content for 'big' is smaller and inset from the page edge."""
    import pymupdf
    img = _write_img(tmp_path / "in", "sq.jpg", size=(1100, 1100),
                     color=(200, 0, 0))

    def content_box(pdf_path):
        doc = pymupdf.open(pdf_path)
        pix = doc[0].get_pixmap(dpi=36)
        minx = miny = 10 ** 9
        maxx = maxy = -1
        for y in range(pix.height):
            for x in range(pix.width):
                o = (y * pix.width + x) * pix.n
                if (pix.samples[o] > 150 and pix.samples[o + 1] < 100
                        and pix.samples[o + 2] < 100):
                    minx, maxx = min(minx, x), max(maxx, x)
                    miny, maxy = min(miny, y), max(maxy, y)
        doc.close()
        return minx, miny, maxx - minx, maxy - miny

    n_x, n_y, n_w, n_h = content_box(
        run([img], tmp_path / "o-n", page_size="a4", margin="none"))
    b_x, b_y, b_w, b_h = content_box(
        run([img], tmp_path / "o-b", page_size="a4", margin="big"))
    assert n_w > b_w and n_h > b_h          # big margin = smaller content
    assert b_x > n_x and b_y > n_y          # and inset further from the edge
    assert n_x >= 10                        # even 'none' keeps a hairline,
    assert n_w > 200                        # but content dominates the page


def test_a4_margin_happy_paths(tmp_path):
    img = _write_img(tmp_path / "in", "a.jpg")
    for margin in ("none", "small", "big"):
        out = run([img], tmp_path / f"o-{margin}",
                  page_size="a4", margin=margin)
        pages = PdfReader(out).pages
        assert len(pages) == 1
        box = pages[0].mediabox
        # A4 is portrait: 595 x 842 pt
        assert abs(float(box.width) - 595.3) < 2.0
        assert abs(float(box.height) - 841.9) < 2.0


def test_invalid_option_raises_toolerror(sample_image_jpg, tmp_path):
    with pytest.raises(ToolError):
        run([sample_image_jpg], tmp_path, page_size="legal-size")
    with pytest.raises(ToolError):
        run([sample_image_jpg], tmp_path, margin="huge")
    with pytest.raises(ToolError):
        validate_options("fit", "lots")


def test_empty_inputs_and_bad_file_raise(tmp_path):
    with pytest.raises(ToolError):
        run([], tmp_path)
    fake = tmp_path / "not-an-image.png"
    fake.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 40)  # png header, junk
    with pytest.raises(ToolError):
        run([fake], tmp_path)
    zero = tmp_path / "zero.jpg"                          # 0-byte (should be
    zero.write_bytes(b"")                                 # caught upstream too)
    with pytest.raises(ToolError):
        run([zero], tmp_path)
    with pytest.raises(ToolError):                        # missing path
        run([tmp_path / "nope.jpg"], tmp_path)
    with pytest.raises(ToolError):                        # a directory
        run([tmp_path], tmp_path)


# ---------------------------------------------------------------------------
# routes
# ---------------------------------------------------------------------------

def test_get_page_renders(client, sample_images):
    r = client.get("/t/images_to_pdf/")
    assert r.status_code == 200
    assert b"JPG to PDF" in r.data
    assert b'name="page_size"' in r.data
    assert b'name="margin"' in r.data


def _files_payload(paths):
    return {"files": [(io.BytesIO(p.read_bytes()), p.name) for p in paths]}


def test_post_roundtrip_fit(client, sample_images):
    r = client.post("/t/images_to_pdf/",
                    data=_files_payload(sample_images[:3]),
                    content_type="multipart/form-data")
    assert r.status_code == 200
    assert b"/dl/" in r.data


def test_post_roundtrip_a4_big(client, sample_image_png):
    r = client.post("/t/images_to_pdf/",
                    data={**_files_payload([sample_image_png]),
                          "page_size": "a4", "margin": "big"},
                    content_type="multipart/form-data")
    assert r.status_code == 200
    assert b"/dl/" in r.data


def test_post_invalid_option_is_400(client, sample_image_jpg):
    r = client.post("/t/images_to_pdf/",
                    data={**_files_payload([sample_image_jpg]),
                          "page_size": "tabloid"},
                    content_type="multipart/form-data")
    assert r.status_code == 400
    assert b"page size" in r.data.lower()


def test_post_rejects_pdf_upload(client, sample_pdf_3p):
    r = client.post("/t/images_to_pdf/",
                    data=_files_payload([sample_pdf_3p]),
                    content_type="multipart/form-data")
    assert r.status_code == 400
    assert b"not a supported file type" in r.data
