"""Tests for the compress tool: pure service + Flask blueprint round trip."""
import io
from pathlib import Path

import pytest

from app.errors import ToolError
from app.services.compress import run


# ---------------------------------------------------------------------------
# service (pure — no Flask context needed)
# ---------------------------------------------------------------------------

def _assert_ok_pdf(out, expected_pages):
    import pymupdf
    assert out.is_file()
    assert out.stat().st_size > 0
    doc = pymupdf.open(out)
    try:
        assert doc.page_count == expected_pages
        assert doc.load_page(0).get_text().strip() != ""
    finally:
        doc.close()
    # independent validation: parse the output back with pypdf too
    from pypdf import PdfReader
    reader = PdfReader(str(out), strict=False)
    assert len(reader.pages) == expected_pages
    assert reader.pages[0].extract_text().strip() != ""


@pytest.mark.parametrize("level", ["basic", "extreme"])
def test_service_levels(tmp_path, sample_pdf_3p, level):
    out = run([sample_pdf_3p], tmp_path, level=level)
    assert isinstance(out, Path)
    _assert_ok_pdf(out, 3)


@pytest.mark.parametrize("level", ["basic", "extreme"])
def test_service_two_page(tmp_path, sample_pdf_2p, level):
    out = run([sample_pdf_2p], tmp_path, level=level)
    _assert_ok_pdf(out, 2)


def test_service_default_level_is_basic(tmp_path, sample_pdf_3p):
    out = run([sample_pdf_3p], tmp_path)          # no level kwarg
    _assert_ok_pdf(out, 3)


def test_service_level_case_insensitive(tmp_path, sample_pdf_2p):
    out = run([sample_pdf_2p], tmp_path, level="Extreme")
    _assert_ok_pdf(out, 2)


@pytest.mark.parametrize("bad", ["nope", "", "high", "Basic!", "extrem",
                                 "1;rm", "-1", "999999", "0;--exec",
                                 "__import__('os')"])
def test_service_invalid_level_raises(tmp_path, sample_pdf_3p, bad):
    with pytest.raises(ToolError):
        run([sample_pdf_3p], tmp_path, level=bad)


def test_service_invalid_level_nonstring(tmp_path, sample_pdf_3p):
    with pytest.raises(ToolError):
        run([sample_pdf_3p], tmp_path, level=3)


def test_service_requires_single_input(tmp_path, sample_pdf_3p, sample_pdf_2p):
    with pytest.raises(ToolError):
        run([sample_pdf_3p, sample_pdf_2p], tmp_path, level="basic")


def test_service_corrupt_pdf(tmp_path):
    junk = tmp_path / "junk.pdf"
    junk.write_bytes(b"%PDF-1.4 \x00garbagegarbagegarbage")
    outdir = tmp_path / "out"
    with pytest.raises(ToolError):
        run([junk], outdir, level="basic")


def test_service_encrypted_pdf(tmp_path, sample_pdf_2p):
    """A password-protected PDF must raise a friendly ToolError, not crash."""
    from pypdf import PdfReader, PdfWriter
    enc = tmp_path / "enc.pdf"
    w = PdfWriter()
    w.append(PdfReader(str(sample_pdf_2p)))
    w.encrypt("hunter2")
    with open(enc, "wb") as fh:
        w.write(fh)
    with pytest.raises(ToolError):
        run([enc], tmp_path / "out", level="basic")


def test_service_missing_input_pdf(tmp_path):
    """A path that does not exist must raise ToolError, not FileNotFoundError."""
    with pytest.raises(ToolError):
        run([tmp_path / "does-not-exist.pdf"], tmp_path / "out")


def test_service_extreme_with_images(tmp_path):
    """Build a PDF containing large raster images so the extreme path
    actually exercises the Pillow recompression branch — and assert the
    spec's core effect (the file gets smaller)."""
    import pymupdf
    from PIL import Image

    im = Image.new("RGB", (2000, 1600))
    px = im.load()
    for y in range(1600):          # noisy pixels so q95 JPEG stays large
        for x in range(2000):
            px[x, y] = ((x * 7 + y * 13) % 256, (x * 3 ^ y) % 256,
                        (x + y * 5) % 256)
    jpg = tmp_path / "big.jpg"
    im.save(jpg, format="JPEG", quality=95)

    src = tmp_path / "img.pdf"
    doc = pymupdf.open()
    for _ in range(2):
        page = doc.new_page()
        page.insert_image(page.rect, filename=str(jpg))
        page.insert_text((72, 72), "image heavy page")
    doc.save(src)
    doc.close()

    outdir = tmp_path / "out"
    out = run([src], outdir, level="extreme")
    _assert_ok_pdf(out, 2)
    # core spec effect on an image-heavy file: extreme must shrink it
    assert out.stat().st_size < src.stat().st_size

    # the recompressed image is downscaled to the MAX_IMAGE_SIDE cap
    doc = pymupdf.open(out)
    try:
        imgs = doc.load_page(0).get_images(full=True)
        assert imgs
        assert max(imgs[0][2], imgs[0][3]) <= 1500
    finally:
        doc.close()

    # basic must also succeed on the same input (no crash on images)
    out_b = run([src], tmp_path / "out_b", level="basic")
    _assert_ok_pdf(out_b, 2)


def test_service_extreme_preserves_transparency(tmp_path):
    """Regression: an image with an SMask must NOT be swapped (replace_image
    severs the mask link); extreme keeps the transparency intact."""
    import pymupdf
    from PIL import Image

    im = Image.new("RGBA", (2000, 1600))
    px = im.load()
    for y in range(1600):
        for x in range(2000):
            a = 128 if (x + y) % 2 else 255
            px[x, y] = ((x * 11) % 256, (y * 5) % 256, (x ^ y) % 256, a)
    png = tmp_path / "t.png"
    im.save(png, compress_level=0)
    src = tmp_path / "t.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_image(page.rect, filename=str(png))
    page.insert_text((50, 50), "transparent")
    doc.save(src)
    doc.close()

    out = run([src], tmp_path / "out", level="extreme")
    _assert_ok_pdf(out, 1)
    doc = pymupdf.open(out)
    try:
        imgs = doc.load_page(0).get_images(full=True)
        assert imgs and imgs[0][1] != 0, "SMask was lost"
        assert max(imgs[0][2], imgs[0][3]) == 2000, "masked image was altered"
    finally:
        doc.close()
    # rendered pixels before vs after must be identical
    def _render(p):
        d = pymupdf.open(p)
        pm = d.load_page(0).get_pixmap(dpi=36)
        b = bytes(pm.samples)
        d.close()
        return b
    assert _render(src) == _render(out)


@pytest.mark.parametrize("samp, pages", [("sample_pdf_2p", 2),
                                         ("sample_pdf_3p", 3)])
def test_service_basic_reduces_size(tmp_path, request, samp, pages):
    """Core spec effect on the plain samples too: output < input bytes."""
    src = request.getfixturevalue(samp)
    out = run([src], tmp_path, level="basic")
    _assert_ok_pdf(out, pages)
    assert out.stat().st_size < src.stat().st_size


def test_service_zero_page_pdf(tmp_path):
    """A 0-page PDF must produce a friendly ToolError, not a raw crash."""
    from pypdf import PdfWriter
    src = tmp_path / "zero.pdf"
    with open(src, "wb") as fh:
        PdfWriter().write(fh)
    with pytest.raises(ToolError):
        run([src], tmp_path / "out", level="basic")


def test_service_extreme_vector_only_pdf(tmp_path, sample_pdf_2p):
    """A text-only PDF has no rasters; extreme must skip gracefully."""
    out = run([sample_pdf_2p], tmp_path, level="extreme")
    _assert_ok_pdf(out, 2)


def test_service_extreme_not_larger_than_input(tmp_path, sample_pdf_3p):
    """The strongest level must never grow the file (<= keeps it non-flaky)."""
    out = run([sample_pdf_3p], tmp_path, level="extreme")
    assert out.stat().st_size <= sample_pdf_3p.stat().st_size


def test_service_tiny_pdf_does_not_balloon(tmp_path):
    """An already-compressed tiny PDF must succeed and not grow."""
    import pymupdf
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "tiny")
    src = tmp_path / "tiny.pdf"
    doc.save(src, garbage=4, deflate=True, clean=True)
    doc.close()
    outdir = tmp_path / "out"
    out = run([src], outdir, level="extreme")
    _assert_ok_pdf(out, 1)
    assert out.stat().st_size <= src.stat().st_size


def test_service_writes_only_inside_output_dir(tmp_path, sample_pdf_2p):
    """Output dir contains exactly the returned file; no stray temps."""
    outdir = tmp_path / "out"
    out = run([sample_pdf_2p], outdir, level="extreme")
    assert out.parent == outdir
    assert sorted(p.name for p in outdir.iterdir()) == [out.name]
    # nothing else was written anywhere under tmp_path
    strays = {p for p in tmp_path.rglob("*") if p.is_file()
              and not str(p).startswith(str(outdir))}
    assert strays == set()


# ---------------------------------------------------------------------------
# routes
# ---------------------------------------------------------------------------

def _pdf_part(path, name="doc.pdf"):
    return [(io.BytesIO(path.read_bytes()), name)]


def test_get_page(client):
    # /t/compress canonicalises to /t/compress/ (Flask trailing-slash 308),
    # exactly like a browser hitting the form action would be redirected.
    r = client.get("/t/compress", follow_redirects=True)
    assert r.status_code == 200
    assert b"Compress PDF" in r.data
    assert b'name="level"' in r.data


@pytest.mark.parametrize("level", ["basic", "extreme"])
def test_compress_roundtrip(client, sample_pdf_3p, level):
    r = client.post("/t/compress",
                    data={"files": _pdf_part(sample_pdf_3p), "level": level},
                    content_type="multipart/form-data",
                    follow_redirects=True)
    assert r.status_code == 200
    assert b"/dl/" in r.data


def test_compress_roundtrip_default_level(client, sample_pdf_2p):
    r = client.post("/t/compress",
                    data={"files": _pdf_part(sample_pdf_2p, "x.pdf")},
                    content_type="multipart/form-data",
                    follow_redirects=True)
    assert r.status_code == 200
    assert b"/dl/" in r.data


def test_compress_route_invalid_level(client, sample_pdf_3p):
    r = client.post("/t/compress/",
                    data={"files": _pdf_part(sample_pdf_3p, "x.pdf"),
                          "level": "ultra"},
                    content_type="multipart/form-data")
    assert r.status_code == 400
    assert b"compression level" in r.data


def test_compress_route_no_file(client):
    r = client.post("/t/compress/", data={},
                    content_type="multipart/form-data")
    assert r.status_code == 400


def test_compress_route_rejects_non_pdf(client, sample_image_png):
    r = client.post("/t/compress/",
                    data={"files": [(io.BytesIO(sample_image_png.read_bytes()),
                                     "p.png")]},
                    content_type="multipart/form-data")
    assert r.status_code == 400


def test_compress_download_serves_pdf(client, sample_pdf_3p):
    import re
    r = client.post("/t/compress",
                    data={"files": _pdf_part(sample_pdf_3p, "rep.pdf"),
                          "level": "basic"},
                    content_type="multipart/form-data",
                    follow_redirects=True)
    assert r.status_code == 200
    url = re.search(r'href="(/dl/[0-9a-f]+/0)"', r.data.decode()).group(1)
    d = client.get(url)
    assert d.status_code == 200
    assert d.data.startswith(b"%PDF")
