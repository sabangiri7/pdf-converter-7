"""Tests for the pdf_to_images tool: pure service + Flask route."""
import io
from pathlib import Path

import pytest
from PIL import Image

from app.errors import ToolError
from app.helpers import detect_kind
from app.services.pdf_to_images import clean_options, run

ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# service: happy paths
# ---------------------------------------------------------------------------

def test_png_happy_path(sample_pdf_3p, tmp_path):
    outs = run([sample_pdf_3p], tmp_path, format="png", dpi=150)
    assert len(outs) == 3
    assert [p.name for p in outs] == ["page-1.png", "page-2.png", "page-3.png"]
    for p in outs:
        assert p.parent == tmp_path
        assert detect_kind(p) == "png"
        with Image.open(p) as im:
            w, h = im.size
        # A4 page (595.28 pt wide) at 150 dpi -> 595.28/72*150 = 1240.2 px
        assert abs(w - 1240) / 1240 < 0.05, w
        assert abs(h - 1754) / 1754 < 0.05, h


def test_jpg_happy_path(sample_pdf_2p, tmp_path):
    outs = run([sample_pdf_2p], tmp_path, format="jpg", dpi=150)
    assert len(outs) == 2
    assert [p.name for p in outs] == ["page-1.jpg", "page-2.jpg"]
    for p in outs:
        assert detect_kind(p) == "jpg"
        with Image.open(io.BytesIO(p.read_bytes())) as im:
            w, h = im.size
            assert im.format == "JPEG"
        assert abs(w - 1240) / 1240 < 0.05, w


def test_low_dpi_dims_scale(sample_pdf_2p, tmp_path):
    outs = run([sample_pdf_2p], tmp_path, format="png", dpi=72)
    with Image.open(outs[0]) as im:
        w = im.width
    # 595.28 pt at 72 dpi = 595 px
    assert abs(w - 595) / 595 < 0.05, w


def test_defaults_are_jpg_150(sample_pdf_2p, tmp_path):
    outs = run([sample_pdf_2p], tmp_path)
    assert [p.suffix for p in outs] == [".jpg", ".jpg"]
    assert detect_kind(outs[0]) == "jpg"


# ---------------------------------------------------------------------------
# service: option validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fmt", ["gif", "webp", "", "bmp"])
def test_invalid_format(sample_pdf_2p, tmp_path, fmt):
    with pytest.raises(ToolError):
        run([sample_pdf_2p], tmp_path, format=fmt, dpi=150)


@pytest.mark.parametrize("dpi", [71, 401, 0, -5, "abc", None, 12.5])
def test_invalid_dpi(sample_pdf_2p, tmp_path, dpi):
    with pytest.raises(ToolError):
        run([sample_pdf_2p], tmp_path, format="jpg", dpi=dpi)


def test_valid_dpi_boundaries(sample_pdf_2p, tmp_path):
    for dpi in (72, 400):
        outs = run([sample_pdf_2p], tmp_path, format="png", dpi=dpi)
        assert len(outs) == 2


# ---------------------------------------------------------------------------
# service: bad inputs
# ---------------------------------------------------------------------------

def test_non_pdf_rejected(sample_image_png, tmp_path):
    with pytest.raises(ToolError):
        run([sample_image_png], tmp_path)


def test_missing_file_rejected(tmp_path):
    with pytest.raises(ToolError):
        run([tmp_path / "ghost.pdf"], tmp_path)


def test_requires_single_pdf(sample_pdf_2p, tmp_path):
    with pytest.raises(ToolError):
        run([sample_pdf_2p, sample_pdf_2p], tmp_path)
    with pytest.raises(ToolError):
        run([], tmp_path)


def test_service_pure_no_flask():
    src = (ROOT / "app" / "services" / "pdf_to_images.py").read_text("utf-8")
    import_lines = [ln for ln in src.splitlines()
                    if ln.strip().startswith(("import ", "from "))]
    assert not any("flask" in ln.lower() for ln in import_lines)
    # no blueprint / job-framework / request usage anywhere in the module
    for token in ("current_app", "Blueprint", "blueprint", "app.jobs",
                  "from flask", "import flask", "save_uploads", "run_job"):
        assert token not in src, token


def test_clean_options_form_shaped():
    """The route validates request.form-shaped string values BEFORE run_job."""
    assert clean_options({}) == {"format": "jpg", "dpi": 150}
    assert clean_options({"format": "PNG", "dpi": "96"}) == \
        {"format": "png", "dpi": 96}
    assert clean_options({"format": "jpeg", "dpi": "72"}) == \
        {"format": "jpg", "dpi": 72}
    with pytest.raises(ToolError):
        clean_options({"dpi": "1;rm -rf /"})
    with pytest.raises(ToolError):
        clean_options({"format": "../../etc/passwd"})
    with pytest.raises(ToolError):
        clean_options({"dpi": ""})


def test_corrupt_pdf_bytes_service_raises_toolerror(tmp_path):
    """save_uploads would reject this; called directly the service must
    raise a clean ToolError, never leak a raw exception."""
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"%PDF-1.4 garbage not a real pdf at all\n%%EOF")
    with pytest.raises(ToolError):
        run([bad], tmp_path / "out", format="png", dpi=96)


def _encrypted_copy(sample_pdf, dest):
    """Password-protect a copy of `sample_pdf` (empty owner pw + 'secret')."""
    from pypdf import PdfReader, PdfWriter
    rdr = PdfReader(str(sample_pdf))
    w = PdfWriter()
    for pg in rdr.pages:
        w.add_page(pg)
    w.encrypt("secret")
    buf = io.BytesIO()
    w.write(buf)
    dest.write_bytes(buf.getvalue())
    return dest


def test_encrypted_pdf_service_raises_toolerror(sample_pdf_2p, tmp_path):
    enc = _encrypted_copy(sample_pdf_2p, tmp_path / "enc.pdf")
    with pytest.raises(ToolError):
        run([enc], tmp_path / "o", format="png", dpi=72)


def test_route_rejects_encrypted_pdf(client, sample_pdf_2p, tmp_path):
    """Encrypted uploads get the friendly 400 page (save_uploads' page_count
    check), never a 500."""
    enc = _encrypted_copy(sample_pdf_2p, tmp_path / "enc.pdf")
    r = _post(client, enc)
    assert r.status_code == 400


def test_huge_page_high_dpi_raises_toolerror(tmp_path):
    """A MuPDF 'Overly large image' render failure must surface as a clean
    ToolError and leave no partial files behind."""
    import pymupdf
    doc = pymupdf.open()
    doc.new_page(width=14400, height=14400)  # 200 in square
    big = tmp_path / "big.pdf"
    doc.save(big)
    doc.close()
    out = tmp_path / "o"
    with pytest.raises(ToolError):
        run([big], out, format="png", dpi=400)
    assert not out.exists() or list(out.iterdir()) == []


def test_page_count_corruption_raises_toolerror(sample_pdf_3p, tmp_path):
    """PDF whose page-tree /Count is inflated: pymupdf opens it but raises
    on page_count — must become ToolError, not RuntimeError."""
    raw = sample_pdf_3p.read_bytes().replace(b"/Count 3", b"/Count 999", 1)
    f = tmp_path / "cnt.pdf"
    f.write_bytes(raw)
    with pytest.raises(ToolError):
        run([f], tmp_path / "o", format="png", dpi=72)


def test_midrender_failure_leaves_no_partial_files(monkeypatch,
                                                   sample_pdf_3p, tmp_path):
    """If page 2 fails to render, the already-written page-1.png must be
    removed — the service never returns/leaves a truncated set."""
    import pymupdf
    orig = pymupdf.Page.get_pixmap
    calls = {"n": 0}

    def boom(self, *a, **k):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("simulated render blow-up")
        return orig(self, *a, **k)

    monkeypatch.setattr(pymupdf.Page, "get_pixmap", boom)
    out = tmp_path / "o"
    with pytest.raises(ToolError):
        run([sample_pdf_3p], out, format="png", dpi=72)
    assert not out.exists() or list(out.iterdir()) == []


@pytest.mark.parametrize("dpi", ["1;rm", "999999", "-1", "0;--exec",
                                 "150 --out=/dev/null"])
def test_injection_shaped_dpi_rejected(sample_pdf_2p, tmp_path, dpi):
    with pytest.raises(ToolError):
        run([sample_pdf_2p], tmp_path, format="jpg", dpi=dpi)


@pytest.mark.parametrize("fmt", ["jpg; ls", "../../etc/passwd",
                                 "png\ninject", "$(whoami)"])
def test_injection_shaped_format_rejected(sample_pdf_2p, tmp_path, fmt):
    out = tmp_path / "out"
    with pytest.raises(ToolError):
        run([sample_pdf_2p], out, format=fmt, dpi=96)
    # nothing was written to the output dir
    assert not out.exists() or list(out.iterdir()) == []


def test_output_pages_match_input_page_count(sample_pdf_3p, tmp_path):
    """Core spec: one image per page, in order, exact count from pypdf."""
    from pypdf import PdfReader
    n = len(PdfReader(str(sample_pdf_3p)).pages)
    outs = run([sample_pdf_3p], tmp_path, format="png", dpi=72)
    assert len(outs) == n
    assert [p.name for p in outs] == [f"page-{i}.png" for i in range(1, n + 1)]


def test_rendered_pages_contain_text(sample_pdf_3p, tmp_path):
    """Pages render the sample's 'Page i of 3' text: output is non-blank."""
    outs = run([sample_pdf_3p], tmp_path, format="png", dpi=150)
    for p in outs:
        with Image.open(p) as im:
            lo, _hi = im.convert("L").getextrema()
        assert lo < 128, f"{p.name} is a blank render"


def test_rotated_page_uses_mediabox_rotation(sample_pdf_2p, tmp_path):
    """A /Rotate 90 page must render swapped (landscape), like viewers do."""
    import io as _io
    from pypdf import PdfReader, PdfWriter
    rdr = PdfReader(str(sample_pdf_2p))
    w = PdfWriter()
    for pg in rdr.pages:
        w.add_page(pg)
    w.pages[0].rotate(90)
    buf = _io.BytesIO()
    w.write(buf)
    rot = tmp_path / "rot.pdf"
    rot.write_bytes(buf.getvalue())
    outs = run([rot], tmp_path / "o", format="png", dpi=96)
    with Image.open(outs[0]) as im:
        w0, h0 = im.size
    with Image.open(outs[1]) as im:
        w1, h1 = im.size
    assert (w0 > h0) != (w1 > h1), "rotation ignored: both pages same shape"


# ---------------------------------------------------------------------------
# routes
# ---------------------------------------------------------------------------

def test_get_page(client):
    r = client.get("/t/pdf_to_images/")
    assert r.status_code == 200
    assert b'name="format"' in r.data
    assert b'name="dpi"' in r.data
    assert b"/t/pdf_to_images" in r.data


def _post(client, sample_pdf, fmt="jpg", dpi="150"):
    # trailing slash: the non-slash URL 308-redirects and the werkzeug test
    # client cannot replay an already-consumed multipart stream.
    return client.post(
        "/t/pdf_to_images/",
        data={"files": [(open(sample_pdf, "rb"), "doc.pdf")],
              "format": fmt, "dpi": dpi},
        content_type="multipart/form-data",
        follow_redirects=True,
    )


def test_route_roundtrip_jpg(client, sample_pdf_3p):
    r = _post(client, sample_pdf_3p, fmt="jpg")
    assert r.status_code == 200
    assert b"/dl/" in r.data
    assert b"page-1.jpg" in r.data
    assert b"all.zip" in r.data  # 3 outputs -> zip offered


def test_route_roundtrip_png(client, sample_pdf_2p):
    r = _post(client, sample_pdf_2p, fmt="png", dpi="96")
    assert r.status_code == 200
    assert b"/dl/" in r.data
    assert b"page-2.png" in r.data


def test_route_downloads_work(client, app, sample_pdf_2p):
    r = _post(client, sample_pdf_2p, fmt="png")
    assert r.status_code == 200
    # find first /dl/ link and fetch it
    html = r.data.decode("utf-8")
    start = html.index("/dl/")
    href = html[start:start + 60].split('"')[0]
    d = client.get(href)
    assert d.status_code == 200
    assert detect_kind_from_bytes(d.data[:16]) == "png"


def detect_kind_from_bytes(header: bytes) -> str | None:
    from app.helpers import kind_from_header
    return kind_from_header(header)


def test_route_invalid_format_400(client, sample_pdf_2p):
    r = _post(client, sample_pdf_2p, fmt="gif")
    assert r.status_code == 400
    assert b"format" in r.data.lower()


def test_route_invalid_dpi_400(client, sample_pdf_2p):
    r = _post(client, sample_pdf_2p, dpi="9999")
    assert r.status_code == 400


def test_route_rejects_non_pdf(client, sample_image_jpg):
    r = client.post(
        "/t/pdf_to_images/",
        data={"files": [(open(sample_image_jpg, "rb"), "x.jpg")]},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert r.status_code == 400
