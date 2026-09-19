"""Tests for image_convert: pure service + Flask route."""
from pathlib import Path

import pytest
from PIL import Image

from app.errors import ToolError
from app.helpers import detect_kind
from app.services.image_convert import clean_options, run

ROOT = Path(__file__).resolve().parent.parent


def test_png_to_jpg(sample_image_png, tmp_path):
    outs = run([sample_image_png], tmp_path, format="jpg")
    assert len(outs) == 1
    assert detect_kind(outs[0]) == "jpg"
    with Image.open(outs[0]) as im:
        assert im.format == "JPEG"
        assert im.mode == "RGB"


def test_jpg_to_webp(sample_image_jpg, tmp_path):
    outs = run([sample_image_jpg], tmp_path, format="webp")
    assert detect_kind(outs[0]) == "webp"


def test_jpg_to_tiff(sample_image_jpg, tmp_path):
    outs = run([sample_image_jpg], tmp_path, format="tiff")
    assert detect_kind(outs[0]) == "tiff"


def test_multiple_images(sample_images, tmp_path):
    # use first two of mixed samples
    outs = run(sample_images[:2], tmp_path, format="png")
    assert len(outs) == 2
    assert all(detect_kind(p) == "png" for p in outs)


def test_invalid_format(sample_image_png, tmp_path):
    with pytest.raises(ToolError):
        run([sample_image_png], tmp_path, format="gif")


def test_clean_options():
    assert clean_options({}) == {"format": "png"}
    assert clean_options({"format": "JPEG"}) == {"format": "jpg"}
    with pytest.raises(ToolError):
        clean_options({"format": "bmp"})


def test_rejects_pdf(sample_pdf_2p, tmp_path):
    with pytest.raises(ToolError):
        run([sample_pdf_2p], tmp_path, format="png")


def test_service_pure_no_flask():
    src = (ROOT / "app" / "services" / "image_convert.py").read_text("utf-8")
    for token in ("from flask", "import flask", "Blueprint"):
        assert token not in src


def test_get_page(client):
    r = client.get("/t/image_convert/")
    assert r.status_code == 200
    assert b'name="format"' in r.data


def test_route_roundtrip(client, sample_image_png):
    r = client.post(
        "/t/image_convert/",
        data={"files": [(open(sample_image_png, "rb"), "pic.png")],
              "format": "jpg"},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert b"/dl/" in r.data
    assert b".jpg" in r.data


def test_route_rejects_pdf(client, sample_pdf_2p):
    r = client.post(
        "/t/image_convert/",
        data={"files": [(open(sample_pdf_2p, "rb"), "x.pdf")],
              "format": "png"},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert r.status_code == 400
