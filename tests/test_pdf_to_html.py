"""Tests for pdf_to_html."""
import io
from pathlib import Path

import pytest

from app.errors import ToolError
from app.services.pdf_to_html import run


def _upload(pdf_path: Path, filename="x.pdf"):
    return {"files": [(io.BytesIO(pdf_path.read_bytes()), filename)]}


def test_service_ok(sample_pdf_2p, tmp_path):
    out = run([sample_pdf_2p], tmp_path)
    assert out.is_file()
    html = out.read_text(encoding="utf-8")
    assert "<html" in html.lower()
    assert "Page 1" in html


def test_service_rejects_bad_input(tmp_path):
    junk = tmp_path / "junk.pdf"
    junk.write_bytes(b"not a pdf")
    with pytest.raises(ToolError):
        run([junk], tmp_path)


def test_get_page(client):
    r = client.get("/t/pdf_to_html")
    assert r.status_code == 200
    assert b"PDF to HTML" in r.data


def test_route_roundtrip(client, sample_pdf_2p):
    r = client.post("/t/pdf_to_html", data=_upload(sample_pdf_2p),
                    content_type="multipart/form-data")
    assert r.status_code == 200
    assert b"/dl/" in r.data
