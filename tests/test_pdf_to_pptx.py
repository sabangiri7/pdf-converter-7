"""Tests for pdf_to_pptx: pure service + Flask route."""
from pathlib import Path
from zipfile import ZipFile

import pytest

from app.errors import ToolError
from app.services.pdf_to_pptx import clean_options, run

ROOT = Path(__file__).resolve().parent.parent


def test_happy_path_slide_count(sample_pdf_3p, tmp_path):
    out = run([sample_pdf_3p], tmp_path, dpi=96)
    assert out.name == "converted.pptx"
    assert out.is_file()
    # pptx is a zip; [Content_Types].xml must exist
    with ZipFile(out) as zf:
        names = zf.namelist()
    assert "[Content_Types].xml" in names
    slide_parts = [n for n in names if n.startswith("ppt/slides/slide")]
    assert len(slide_parts) == 3


def test_defaults_and_two_pages(sample_pdf_2p, tmp_path):
    out = run([sample_pdf_2p], tmp_path)
    assert out.suffix == ".pptx"
    with ZipFile(out) as zf:
        slides = [n for n in zf.namelist() if n.startswith("ppt/slides/slide")]
    assert len(slides) == 2


def test_requires_single_pdf(sample_pdf_2p, tmp_path):
    with pytest.raises(ToolError):
        run([sample_pdf_2p, sample_pdf_2p], tmp_path)
    with pytest.raises(ToolError):
        run([], tmp_path)


def test_non_pdf_rejected(sample_image_png, tmp_path):
    with pytest.raises(ToolError):
        run([sample_image_png], tmp_path)


@pytest.mark.parametrize("dpi", [71, 301, "abc", None])
def test_invalid_dpi(sample_pdf_2p, tmp_path, dpi):
    with pytest.raises(ToolError):
        run([sample_pdf_2p], tmp_path, dpi=dpi)


def test_clean_options():
    assert clean_options({}) == {"dpi": 150}
    assert clean_options({"dpi": "96"}) == {"dpi": 96}
    with pytest.raises(ToolError):
        clean_options({"dpi": "9999"})


def test_service_pure_no_flask():
    src = (ROOT / "app" / "services" / "pdf_to_pptx.py").read_text("utf-8")
    for token in ("from flask", "import flask", "Blueprint", "save_uploads"):
        assert token not in src


def test_get_page(client):
    r = client.get("/t/pdf_to_pptx/")
    assert r.status_code == 200
    assert b'name="dpi"' in r.data


def test_route_roundtrip(client, sample_pdf_2p):
    r = client.post(
        "/t/pdf_to_pptx/",
        data={"files": [(open(sample_pdf_2p, "rb"), "doc.pdf")],
              "dpi": "96"},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert b"/dl/" in r.data
    assert b".pptx" in r.data


def test_route_rejects_non_pdf(client, sample_image_jpg):
    r = client.post(
        "/t/pdf_to_pptx/",
        data={"files": [(open(sample_image_jpg, "rb"), "x.jpg")]},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert r.status_code == 400
