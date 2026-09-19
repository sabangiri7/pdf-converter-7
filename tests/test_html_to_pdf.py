"""Tests for html_to_pdf."""
import io
from pathlib import Path

import pytest

from app.errors import ToolError
from app.services.html_to_pdf import run


def _upload(pdf_path: Path, filename="x.pdf"):
    return {"files": [(io.BytesIO(pdf_path.read_bytes()), filename)]}


def test_service_ok(sample_pdf_2p, sample_pdf_3p, tmp_path):
    html = tmp_path / "s.html"
    html.write_text("<html><body><h1>Hi</h1><p>There</p></body></html>", encoding="utf-8")
    out = run([html], tmp_path)
    assert out.is_file() and out.read_bytes().startswith(b"%PDF")


def test_service_rejects_bad_input(tmp_path):
    junk = tmp_path / "junk.pdf"
    junk.write_bytes(b"not a pdf")
    with pytest.raises(ToolError):
        run([junk], tmp_path)


def test_get_page(client):
    r = client.get("/t/html_to_pdf")
    assert r.status_code == 200
    assert 'HTML to PDF'.encode() in r.data


def test_route_roundtrip(client, sample_pdf_2p, sample_pdf_3p):
    data = {"files": [(io.BytesIO(b"<html><body><p>Hi</p></body></html>"), "x.html")]}
    r = client.post("/t/html_to_pdf", data=data, content_type="multipart/form-data")
    assert r.status_code == 200 and b"/dl/" in r.data
