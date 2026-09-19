"""Tests for organize_pdf."""
import io
from pathlib import Path

import pytest
from pypdf import PdfReader

from app.errors import ToolError
from app.helpers import page_count
from app.services.organize_pdf import parse_page_order, run

ROOT = Path(__file__).resolve().parent.parent


def test_parse_order():
    assert parse_page_order("3,1,2", 3) == [3, 1, 2]
    assert parse_page_order("1-2,3", 3) == [1, 2, 3]


def test_parse_rejects_bad(sample_pdf_3p):
    with pytest.raises(ToolError):
        parse_page_order("", 3)
    with pytest.raises(ToolError):
        parse_page_order("9", 3)
    with pytest.raises(ToolError):
        parse_page_order("3-1", 3)


def test_reorder_and_drop(sample_pdf_3p, tmp_path):
    out = run([sample_pdf_3p], tmp_path / "o", pages="3,1")
    assert page_count(out) == 2
    texts = [p.extract_text().splitlines()[0]
             for p in PdfReader(str(out)).pages]
    assert texts == ["Page 3 of 3", "Page 1 of 3"]


def test_service_pure():
    src = (ROOT / "app" / "services" / "organize_pdf.py").read_text("utf-8")
    for token in ("from flask", "import flask", "Blueprint"):
        assert token not in src


def test_get_page(client):
    r = client.get("/t/organize_pdf/")
    assert r.status_code == 200
    assert b"Organize" in r.data
    assert b"organize-pages" in r.data
    assert b"organize_pdf.js" in r.data
    assert b"pdf.min.js" in r.data
    assert b'name="pages"' in r.data


def test_route_roundtrip(client, sample_pdf_3p):
    r = client.post(
        "/t/organize_pdf/",
        data={"files": [(io.BytesIO(sample_pdf_3p.read_bytes()), "a.pdf")],
              "pages": "2,1"},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert b"/dl/" in r.data


def test_route_accepts_full_reorder(client, sample_pdf_3p):
    r = client.post(
        "/t/organize_pdf/",
        data={"files": [(io.BytesIO(sample_pdf_3p.read_bytes()), "a.pdf")],
              "pages": "3,1,2"},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert b"/dl/" in r.data
