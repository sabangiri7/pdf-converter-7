"""Tests for pdf_to_docx."""
import io
from pathlib import Path

import pytest
from docx import Document

from app.errors import ToolError
from app.services.pdf_to_docx import run

ROOT = Path(__file__).resolve().parent.parent


def test_happy_path(sample_pdf_3p, tmp_path):
    out = run([sample_pdf_3p], tmp_path / "out")
    assert out.suffix == ".docx"
    doc = Document(str(out))
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "Page 1 of 3" in text
    assert "Page 3 of 3" in text


def test_rejects_image_only_pdf(tmp_path, sample_image_jpg):
    import img2pdf
    scanned = tmp_path / "scan.pdf"
    scanned.write_bytes(img2pdf.convert(str(sample_image_jpg)))
    with pytest.raises(ToolError) as ei:
        run([scanned], tmp_path / "o")
    assert "OCR" in str(ei.value) or "selectable" in str(ei.value).lower()


def test_requires_single(sample_pdf_3p, sample_pdf_2p, tmp_path):
    with pytest.raises(ToolError):
        run([sample_pdf_3p, sample_pdf_2p], tmp_path)


def test_service_pure_no_flask():
    src = (ROOT / "app" / "services" / "pdf_to_docx.py").read_text("utf-8")
    for token in ("from flask", "import flask", "Blueprint"):
        assert token not in src


def test_get_page(client):
    r = client.get("/t/pdf_to_docx/")
    assert r.status_code == 200
    assert b"Word" in r.data or b"PDF" in r.data


def test_route_roundtrip(client, sample_pdf_3p):
    r = client.post(
        "/t/pdf_to_docx/",
        data={"files": [(io.BytesIO(sample_pdf_3p.read_bytes()), "a.pdf")]},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert b"/dl/" in r.data
