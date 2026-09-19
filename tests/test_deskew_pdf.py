"""Tests for deskew_pdf."""
import io
from pathlib import Path

import pytest

from app.errors import ToolError
from app.services.deskew_pdf import run


def _upload(pdf_path: Path, filename="x.pdf"):
    return {"files": [(io.BytesIO(pdf_path.read_bytes()), filename)]}


def test_service_ok(sample_pdf_2p, sample_pdf_3p, tmp_path):
    out = run([sample_pdf_2p], tmp_path)
    assert isinstance(out, Path)
    assert out.is_file()
    assert out.read_bytes().startswith(b"%PDF")


def test_service_rejects_bad_input(tmp_path):
    junk = tmp_path / "junk.pdf"
    junk.write_bytes(b"not a pdf")
    with pytest.raises(ToolError):
        run([junk], tmp_path)


def test_get_page(client):
    r = client.get("/t/deskew_pdf")
    assert r.status_code == 200
    assert 'Deskew PDF'.encode() in r.data


def test_route_roundtrip(client, sample_pdf_2p, sample_pdf_3p):
    r = client.post("/t/deskew_pdf", data=_upload(sample_pdf_2p),
                    content_type="multipart/form-data")
    assert r.status_code == 200
    assert b"/dl/" in r.data
