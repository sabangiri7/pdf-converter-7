"""Tests for text_to_pdf."""
import io
from pathlib import Path

import pytest
from pypdf import PdfReader

from app.errors import ToolError
from app.services.text_to_pdf import run


def _upload(pdf_path: Path, filename="x.pdf"):
    return {"files": [(io.BytesIO(pdf_path.read_bytes()), filename)]}


def test_service_ok(sample_pdf_2p, sample_pdf_3p, tmp_path):
    txt = tmp_path / "sample.txt"
    txt.write_text("Hello from text.\nLine two.", encoding="utf-8")
    out = run([txt], tmp_path)
    assert out.is_file() and out.read_bytes().startswith(b"%PDF")


def test_service_rejects_bad_input(tmp_path):
    junk = tmp_path / "junk.txt"
    junk.write_bytes(b"\x00\x01\x02\xffbinary")
    with pytest.raises(ToolError):
        run([junk], tmp_path)


def test_get_page(client):
    r = client.get("/t/text_to_pdf")
    assert r.status_code == 200
    assert 'Create PDF from Text'.encode() in r.data


def test_route_roundtrip(client, sample_pdf_2p, sample_pdf_3p):
    data = {"files": [(io.BytesIO(b"Hello PDF\n"), "note.txt")]}
    r = client.post("/t/text_to_pdf", data=data, content_type="multipart/form-data")
    assert r.status_code == 200 and b"/dl/" in r.data
