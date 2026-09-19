"""Tests for the rotate tool: pure service + blueprint round trips."""
import io
from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, NumberObject, TextStringObject

from app.errors import ToolError
from app.services.rotate import run


def _rotations(path) -> list[int]:
    reader = PdfReader(str(path))
    return [int(p.rotation or 0) % 360 for p in reader.pages]


# ---------------- service ----------------

def test_service_rotates_all_pages_90(sample_pdf_3p, tmp_path):
    out = run([sample_pdf_3p], tmp_path, angle=90, pages="")
    assert isinstance(out, Path)
    assert out.is_file()
    assert out.read_bytes().startswith(b"%PDF")
    assert _rotations(out) == [90, 90, 90]


def test_service_rotates_only_selected_page(sample_pdf_3p, tmp_path):
    out = run([sample_pdf_3p], tmp_path, angle=90, pages="2")
    assert _rotations(out) == [0, 90, 0]
    # page count preserved, page 1 untouched
    assert len(PdfReader(str(out)).pages) == 3


def test_service_pages_range_and_list(sample_pdf_3p, tmp_path):
    out = run([sample_pdf_3p], tmp_path, angle=180, pages="1,3")
    assert _rotations(out) == [180, 0, 180]
    out = run([sample_pdf_3p], tmp_path, angle=270, pages="1-2")
    assert _rotations(out) == [270, 270, 0]


def test_service_accepts_angle_as_string(sample_pdf_2p, tmp_path):
    out = run([sample_pdf_2p], tmp_path, angle="270", pages=None)
    assert _rotations(out) == [270, 270]


@pytest.mark.parametrize("bad", [45, 0, 360, "45", "abc", None, -90, 90.5])
def test_service_bad_angle_raises_toolerror(sample_pdf_2p, tmp_path, bad):
    with pytest.raises(ToolError):
        run([sample_pdf_2p], tmp_path, angle=bad)


@pytest.mark.parametrize("bad", ["abc", "0", "99", "3-1", "1,", "1;2", "-2"])
def test_service_bad_pages_raises_toolerror(sample_pdf_3p, tmp_path, bad):
    with pytest.raises(ToolError):
        run([sample_pdf_3p], tmp_path, angle=90, pages=bad)


def test_service_rejects_multiple_inputs(sample_pdf_2p, sample_pdf_3p, tmp_path):
    with pytest.raises(ToolError):
        run([sample_pdf_2p, sample_pdf_3p], tmp_path, angle=90)


def test_service_rejects_not_a_pdf(tmp_path):
    junk = tmp_path / "junk.pdf"
    junk.write_bytes(b"not a pdf at all")
    with pytest.raises(ToolError):
        run([junk], tmp_path, angle=90)


def _with_rotations(sample_pdf: Path, dst: Path, rotations: list[int]) -> Path:
    """Copy the sample PDF forcing per-page /Rotate values."""
    reader = PdfReader(str(sample_pdf))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    for page, rot in zip(writer.pages, rotations):
        if rot:
            page[NameObject("/Rotate")] = NumberObject(rot)
    with open(dst, "wb") as fh:
        writer.write(fh)
    return dst


def test_service_wraps_pre_existing_rotation(sample_pdf_3p, tmp_path):
    """Spec: final /Rotate == (original + angle) % 360, not just `angle`."""
    src = _with_rotations(sample_pdf_3p, tmp_path / "pre.pdf", [90, 270, 0])
    assert _rotations(src) == [90, 270, 0]
    out = run([src], tmp_path, angle=90, pages="")
    assert _rotations(out) == [180, 0, 90]          # 270+90 wraps past 360


def test_service_portrait_page_metadata_only(sample_pdf_3p, tmp_path):
    """A non-square (portrait) page must gain the /Rotate value WITHOUT the
    MediaBox geometry being rewritten — 90° rotation is metadata in PDF."""
    src_box = PdfReader(str(sample_pdf_3p)).pages[0].mediabox
    assert src_box.height > src_box.width           # sample really portrait
    out = run([sample_pdf_3p], tmp_path, angle=90)
    page = PdfReader(str(out)).pages[0]
    assert int(page.rotation) == 90
    assert page.mediabox == src_box


def test_service_bogus_rotate_value_is_toolerror(sample_pdf_3p, tmp_path):
    """A corrupt /Rotate (non-numeric) must be a friendly ToolError, never a
    raw ValueError escaping the service."""
    src = tmp_path / "badrot.pdf"
    reader = PdfReader(str(sample_pdf_3p))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.pages[1][NameObject("/Rotate")] = TextStringObject("abc")
    with open(src, "wb") as fh:
        writer.write(fh)
    with pytest.raises(ToolError):
        run([src], tmp_path, angle=90)


@pytest.mark.parametrize("pages", [
    "²",            # superscript-two: str.isdigit() True, int() crashes
    "٢",            # Arabic-Indic digit
    "9" * 5000,          # past CPython's 4300-digit int() conversion limit
    "1;rm -rf /",        # option-injection shape: never executed, always 400
    "1-0", "1,,2", "1.5", "--exec",
])
def test_service_nasty_pages_values_raise_toolerror(sample_pdf_3p, tmp_path,
                                                    pages):
    with pytest.raises(ToolError):
        run([sample_pdf_3p], tmp_path, angle=90, pages=pages)


@pytest.mark.parametrize("angle", ["90;rm", "1e2", "0", "360", 90.0, [], None])
def test_service_nasty_angle_values_raise_toolerror(sample_pdf_2p, tmp_path,
                                                    angle):
    with pytest.raises(ToolError):
        run([sample_pdf_2p], tmp_path, angle=angle)


def test_service_corrupt_pdf_with_valid_magic(tmp_path):
    """%PDF magic bytes but garbage body (what save_uploads would have let
    through as 'pdf'): the service must ToolError, not raise a 500-style
    library exception."""
    bad = tmp_path / "badmagic.pdf"
    bad.write_bytes(b"%PDF-1.4 \x00garbagegarbagegarbage")
    with pytest.raises(ToolError):
        run([bad], tmp_path, angle=90)


# ---------------- routes ----------------

def _upload(pdf_path: Path, filename="x.pdf"):
    return {"files": [(io.BytesIO(pdf_path.read_bytes()), filename)]}


def test_get_page_renders_form(client):
    r = client.get("/t/rotate")
    assert r.status_code == 200
    assert b"Rotate PDF" in r.data
    assert b'name="angle"' in r.data
    assert b'name="pages"' in r.data
    assert b'action="/t/rotate"' in r.data


def test_route_roundtrip(client, sample_pdf_2p):
    r = client.post("/t/rotate",
                    data={**_upload(sample_pdf_2p), "angle": "90"},
                    content_type="multipart/form-data")
    assert r.status_code == 200
    assert b"/dl/" in r.data


def test_route_roundtrip_with_pages(client, sample_pdf_3p):
    r = client.post("/t/rotate",
                    data={**_upload(sample_pdf_3p, "doc.pdf"),
                          "angle": "180", "pages": "1-2"},
                    content_type="multipart/form-data")
    assert r.status_code == 200
    assert b"/dl/" in r.data


def test_route_downloaded_output_is_actually_rotated(client, sample_pdf_3p):
    """End-to-end: the bytes served from /dl/... must carry the rotated
    /Rotate values, not just a 200 page."""
    r = client.post("/t/rotate",
                    data={**_upload(sample_pdf_3p, "doc.pdf"),
                          "angle": "270", "pages": "2-3"},
                    content_type="multipart/form-data")
    assert r.status_code == 200
    html = r.data.decode()
    assert "/dl/" in html
    url = "/dl/" + html.split('href="/dl/')[1].split('"')[0]
    d = client.get(url)
    assert d.status_code == 200
    assert d.data.startswith(b"%PDF")
    out = _dl_tmp()
    out.write_bytes(d.data)
    assert _rotations(out) == [0, 270, 270]


def _dl_tmp() -> Path:
    import tempfile
    return Path(tempfile.mkdtemp()) / "dl.pdf"


def test_route_rejects_two_files(client, sample_pdf_2p, sample_pdf_3p):
    r = client.post("/t/rotate",
                    data={"files": [(io.BytesIO(sample_pdf_2p.read_bytes()),
                                     "a.pdf"),
                                    (io.BytesIO(sample_pdf_3p.read_bytes()),
                                     "b.pdf")],
                          "angle": "90"},
                    content_type="multipart/form-data")
    assert r.status_code == 400
    assert b"single" in r.data


def test_route_bad_angle_gives_400(client, sample_pdf_2p):
    r = client.post("/t/rotate",
                    data={**_upload(sample_pdf_2p), "angle": "45"},
                    content_type="multipart/form-data")
    assert r.status_code == 400
    assert b"90, 180 or 270" in r.data


def test_route_bad_pages_gives_400(client, sample_pdf_2p):
    r = client.post("/t/rotate",
                    data={**_upload(sample_pdf_2p), "angle": "90",
                          "pages": "7"},
                    content_type="multipart/form-data")
    assert r.status_code == 400
    assert b"out of range" in r.data


def test_route_no_file_gives_400(client):
    r = client.post("/t/rotate", data={"angle": "90"},
                    content_type="multipart/form-data")
    assert r.status_code == 400


def test_route_non_pdf_gives_400(client, sample_image_png):
    r = client.post("/t/rotate",
                    data={"files": [(io.BytesIO(sample_image_png.read_bytes()),
                                     "pic.png")], "angle": "90"},
                    content_type="multipart/form-data")
    assert r.status_code == 400
