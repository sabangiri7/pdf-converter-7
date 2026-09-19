"""Tests for redact_pdf."""
import io
from pathlib import Path

import pytest
from pypdf import PdfReader

from app.errors import ToolError
from app.services.redact_pdf import run


def _upload(pdf_path: Path, filename="x.pdf"):
    return {"files": [(io.BytesIO(pdf_path.read_bytes()), filename)]}


def test_service_ok(sample_pdf_2p, sample_pdf_3p, tmp_path):
    out = run([sample_pdf_2p], tmp_path, find="Page")
    assert out.is_file() and out.read_bytes().startswith(b"%PDF")
    # Redacted token must not remain extractable.
    text = "".join((p.extract_text() or "") for p in PdfReader(str(out)).pages)
    # sample PDFs contain "Page"; after redaction it should be gone
    assert "Page" not in text


def test_service_rejects_bad_input(tmp_path):
    junk = tmp_path / "junk.pdf"
    junk.write_bytes(b"not a pdf")
    with pytest.raises(ToolError):
        run([junk], tmp_path, find="x")


def test_get_page(client):
    r = client.get("/t/redact_pdf")
    assert r.status_code == 200
    assert b"Redact PDF" in r.data


def test_route_roundtrip(client, sample_pdf_2p, sample_pdf_3p):
    r = client.post("/t/redact_pdf",
                    data={**_upload(sample_pdf_2p), "find": "Page"},
                    content_type="multipart/form-data")
    assert r.status_code == 200 and b"/dl/" in r.data
