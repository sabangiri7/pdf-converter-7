"""Tests for duplicate_pages."""
import io
from pathlib import Path

import pytest
from pypdf import PdfReader

from app.errors import ToolError
from app.services.duplicate_pages import run


def _upload(pdf_path: Path, filename="x.pdf"):
    return {"files": [(io.BytesIO(pdf_path.read_bytes()), filename)]}


def test_service_ok(sample_pdf_2p, sample_pdf_3p, tmp_path):
    out = run([sample_pdf_2p], tmp_path, pages="1", copies=1)
    assert len(PdfReader(str(out)).pages) == 3


def test_service_rejects_bad_input(tmp_path):
    junk = tmp_path / "junk.pdf"
    junk.write_bytes(b"not a pdf")
    with pytest.raises(ToolError):
        run([junk], tmp_path, pages="1")


def test_get_page(client):
    r = client.get("/t/duplicate_pages")
    assert r.status_code == 200
    assert 'Duplicate Pages'.encode() in r.data


def test_route_roundtrip(client, sample_pdf_2p, sample_pdf_3p):
    r = client.post("/t/duplicate_pages",
                    data={**_upload(sample_pdf_2p), "pages": "1", "copies": "1"},
                    content_type="multipart/form-data")
    assert r.status_code == 200 and b"/dl/" in r.data
