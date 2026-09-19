"""Tests for the watermark tool: pure service + blueprint routes.

Service tests use temp dirs and the shared sample PDFs (zero Flask).
Route tests exercise the full job flow through the test client.
"""
import io

import pytest
from pypdf import PdfReader

from app.errors import ToolError
from app.helpers import detect_kind
from app.services.watermark import run


def _watermark_text(data: bytes) -> str:
    """Extract text with pypdf (contract requires the stamp be extractable
    from the produced content stream)."""
    reader = PdfReader(io.BytesIO(data))
    return "\n".join(p.extract_text() or "" for p in reader.pages)


def _make_mixed_size_pdf() -> bytes:
    """A 3-page PDF with two distinct page sizes (letter + A4)."""
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(612, 792))
    c.drawString(72, 700, "P1")
    c.showPage()
    c.setPageSize((420, 595))
    c.drawString(50, 500, "P2")
    c.showPage()
    c.setPageSize((612, 792))
    c.drawString(72, 700, "P3")
    c.showPage()
    c.save()
    return buf.getvalue()


# ---------------- service ----------------

def test_run_basic_diagonal(sample_pdf_3p, tmp_path):
    out = run([sample_pdf_3p], tmp_path, text="TOP SECRET",
              opacity=20, position="diagonal")
    assert out.is_file()
    assert out.suffix == ".pdf"
    assert detect_kind(out) == "pdf"
    text = _watermark_text(out.read_bytes())
    assert "TOP SECRET" in text
    # same page count, original content survives
    assert len(PdfReader(out).pages) == 3
    assert "Page 2 of 3" in text
    # the stamp must reach EVERY page, not just the first one found
    import pymupdf
    with pymupdf.open(stream=out.read_bytes(), filetype="pdf") as doc:
        per_page = [len(p.search_for("TOP SECRET")) for p in doc]
    assert per_page == [1, 1, 1]


@pytest.mark.parametrize("position", ["diagonal", "center", "top", "bottom"])
def test_run_all_positions(sample_pdf_2p, tmp_path, position):
    out = run([sample_pdf_2p], tmp_path, text="DRAFT",
              opacity=50, position=position)
    assert len(PdfReader(out).pages) == 2
    text = _watermark_text(out.read_bytes())
    assert text.count("DRAFT") >= 2          # one stamp per page


def test_run_mixed_page_sizes(tmp_path):
    src = tmp_path / "mixed.pdf"
    src.write_bytes(_make_mixed_size_pdf())
    out = run([src], tmp_path, text="OVERLAY TEST", opacity=15,
              position="diagonal")
    reader = PdfReader(out)
    assert len(reader.pages) == 3
    # overlay cached per distinct size; output keeps original page boxes
    assert (float(reader.pages[0].mediabox.width),
            float(reader.pages[1].mediabox.width)) == (612.0, 420.0)
    assert "OVERLAY TEST" in _watermark_text(out.read_bytes())


def test_empty_text_raises(sample_pdf_2p, tmp_path):
    with pytest.raises(ToolError, match="Enter the watermark text."):
        run([sample_pdf_2p], tmp_path, text="   \n ", opacity=20,
            position="center")


def test_oversize_text_raises(sample_pdf_2p, tmp_path):
    with pytest.raises(ToolError):
        run([sample_pdf_2p], tmp_path, text="x" * 201, opacity=20,
            position="center")


@pytest.mark.parametrize("bad", ["", "abc", "0", "4", "101", "150", "-5",
                                 "5.5", None])
def test_invalid_opacity_raises(sample_pdf_2p, tmp_path, bad):
    with pytest.raises(ToolError):
        run([sample_pdf_2p], tmp_path, text="OK", opacity=bad,
            position="center")


def test_invalid_position_raises(sample_pdf_2p, tmp_path):
    with pytest.raises(ToolError):
        run([sample_pdf_2p], tmp_path, text="OK", opacity=20,
            position="middle")


def test_two_inputs_rejected(sample_pdf_2p, sample_pdf_3p, tmp_path):
    with pytest.raises(ToolError):
        run([sample_pdf_2p, sample_pdf_3p], tmp_path, text="OK",
            opacity=20, position="center")


def test_corrupt_pdf_rejected(tmp_path):
    junk = tmp_path / "junk.pdf"
    junk.write_bytes(b"%PDF-1.4 \x00garbagegarbage")
    with pytest.raises(ToolError):
        run([junk], tmp_path, text="OK", opacity=20, position="center")


def test_empty_and_truncated_pdf_rejected(sample_pdf_3p, tmp_path):
    empty = tmp_path / "empty.pdf"
    empty.write_bytes(b"")
    with pytest.raises(ToolError):
        run([empty], tmp_path, text="OK")
    trunc = tmp_path / "trunc.pdf"
    blob = sample_pdf_3p.read_bytes()
    trunc.write_bytes(blob[: len(blob) // 2])
    with pytest.raises(ToolError):
        run([trunc], tmp_path, text="OK")


def test_output_dir_created_if_missing(sample_pdf_2p, tmp_path):
    """Service is directly callable (purity contract): it must create its
    output dir instead of failing with a bare FileNotFoundError."""
    out = run([sample_pdf_2p], tmp_path / "deep" / "nested", text="DEEP")
    assert out.is_file()
    assert detect_kind(out) == "pdf"


def test_latin1_text_stamps_verbatim(sample_pdf_2p, tmp_path):
    out = run([sample_pdf_2p], tmp_path, text="café résumé", opacity=20,
              position="center")
    assert "café résumé" in _watermark_text(out.read_bytes())


def test_non_latin1_text_rejected_not_mojibake(sample_pdf_2p, tmp_path):
    """Base-14 Helvetica cannot draw Cyrillic; silently stamping 'IIIIII'
    would be a wrong output, so a friendly ToolError is required."""
    with pytest.raises(ToolError, match="characters"):
        run([sample_pdf_2p], tmp_path, text="Привет", opacity=20,
            position="center")


def test_control_chars_rejected_not_blank_stamp(sample_pdf_2p, tmp_path):
    """\\x00 and DEL survive str.split() and are latin-1 encodable;
    reportlab would draw them as nothing/garbage, so reject them. (NEL
    \\x85 is fine: split() already collapses it to a space.)"""
    for bad in ("A\x00B", "ok\x7f", "A\x0bB\x1a"):
        with pytest.raises(ToolError, match="characters"):
            run([sample_pdf_2p], tmp_path, text=bad, opacity=20,
                position="center")


def test_offset_mediabox_page_stays_centred(tmp_path):
    """A page whose MediaBox origin is not (0,0) must still get the stamp
    centred on the visible area (merge with a translate, not a raw
    merge_page that ignores the box origin)."""
    import pymupdf
    from pypdf import PdfWriter
    from pypdf.generic import ArrayObject, FloatObject, NameObject
    from reportlab.pdfgen import canvas

    src = tmp_path / "offset.pdf"
    c = canvas.Canvas(str(src), pagesize=(612, 792))
    c.drawString(72, 700, "OFFSET")
    c.showPage()
    c.save()
    w = PdfWriter(clone_from=str(src))
    box = ArrayObject([FloatObject(v) for v in (36, 36, 648, 828)])
    w.pages[0][NameObject("/MediaBox")] = box
    with open(src, "wb") as fh:
        w.write(fh)

    out = run([src], tmp_path / "out", text="XMARKX", opacity=30,
              position="center")
    with pymupdf.open(str(out)) as doc:
        page = doc[0]
        hits = page.search_for("XMARKX")
        assert hits, "stamp vanished on offset-origin page"
        r = hits[0]
        cx = (r.x0 + r.x1) / 2.0
        cy = (r.y0 + r.y1) / 2.0
    # pymupdf normalises the visible area to (0,0,612,792): a correctly
    # placed centre stamp lands on the middle of that box (baseline-centered
    # text means the bbox centre can sit up to ~1/4 of the font height low)
    assert abs(cx - 306.0) < 6, cx
    assert abs(cy - 396.0) < 20, cy


def test_defaults_via_kwargs(sample_pdf_2p, tmp_path):
    """opacity/position default when omitted."""
    out = run([sample_pdf_2p], tmp_path, text="DEFAULTS")
    assert "DEFAULTS" in _watermark_text(out.read_bytes())


# ---------------- routes ----------------

def _post(client, sample_pdf, url="/t/watermark/", **form):
    data = {"files": [(io.BytesIO(sample_pdf.read_bytes()), "doc.pdf")]}
    data.update(form)
    return client.post(url, data=data, content_type="multipart/form-data")


def test_get_page(client):
    r = client.get("/t/watermark/")
    assert r.status_code == 200
    assert b"Watermark PDF" in r.data
    assert b'name="text"' in r.data
    assert b"diagonal" in r.data


def test_get_page_no_trailing_slash_also_ok(client):
    """strict_slashes=False: landing links point at /t/watermark without a
    trailing slash, so both forms must serve."""
    assert client.get("/t/watermark").status_code == 200
    assert client.get("/t/watermark/").status_code == 200


def test_route_roundtrip(client, sample_pdf_3p):
    r = _post(client, sample_pdf_3p, text="CONFIDENTIAL", opacity=30,
              position="diagonal")
    assert r.status_code == 200
    assert b"/dl/" in r.data
    # download the produced file and check it really carries the stamp
    html = r.data.decode()
    url = "/dl/" + html.split('href="/dl/')[1].split('"')[0].removeprefix("/dl/")
    d = client.get(url)
    assert d.status_code == 200
    assert d.data.startswith(b"%PDF")
    assert len(PdfReader(io.BytesIO(d.data)).pages) == 3
    import pymupdf
    with pymupdf.open(stream=d.data, filetype="pdf") as doc:
        per_page = [len(p.search_for("CONFIDENTIAL")) for p in doc]
    assert per_page == [1, 1, 1]          # every page watermarked


def test_route_post_without_trailing_slash(client, sample_pdf_2p):
    """The form action is exactly '/t/watermark' (no slash) — the browser
    POST must be processed, not 308-redirected (redirects can drop the
    multipart body)."""
    r = _post(client, sample_pdf_2p, url="/t/watermark", text="NOSLASH",
              opacity=40, position="top")
    assert r.status_code == 200
    assert b"/dl/" in r.data


def test_route_defaults_when_options_omitted(client, sample_pdf_2p):
    r = _post(client, sample_pdf_2p, text="JUST TEXT")
    assert r.status_code == 200
    assert b"/dl/" in r.data


def test_route_empty_text(client, sample_pdf_2p):
    r = _post(client, sample_pdf_2p, text="   ")
    assert r.status_code == 400
    assert b"Enter the watermark text." in r.data


def test_route_junk_opacity(client, sample_pdf_2p):
    r = _post(client, sample_pdf_2p, text="X", opacity="150")
    assert r.status_code == 400
    assert b"opacity" in r.data.lower()
