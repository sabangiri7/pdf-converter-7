"""Tests for protect_pdf and unlock_pdf."""
import io
from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter

from app.errors import ToolError
from app.helpers import page_count
from app.services import protect_pdf, unlock_pdf

ROOT = Path(__file__).resolve().parent.parent


def test_protect_then_unlock(sample_pdf_3p, tmp_path):
    protected = protect_pdf.run([sample_pdf_3p], tmp_path / "p",
                                password="secret")
    assert protected.is_file()
    assert PdfReader(str(protected)).is_encrypted

    unlocked = unlock_pdf.run([protected], tmp_path / "u", password="secret")
    assert unlocked.is_file()
    reader = PdfReader(str(unlocked))
    assert not reader.is_encrypted
    assert len(reader.pages) == 3
    assert page_count(unlocked) == 3


def test_protect_requires_password(sample_pdf_3p, tmp_path):
    with pytest.raises(ToolError):
        protect_pdf.run([sample_pdf_3p], tmp_path, password="")


def test_unlock_wrong_password(sample_pdf_3p, tmp_path):
    protected = protect_pdf.run([sample_pdf_3p], tmp_path / "p",
                                password="secret")
    with pytest.raises(ToolError) as ei:
        unlock_pdf.run([protected], tmp_path / "u", password="nope")
    assert "password" in str(ei.value).lower()


def test_unlock_rejects_unencrypted(sample_pdf_3p, tmp_path):
    with pytest.raises(ToolError) as ei:
        unlock_pdf.run([sample_pdf_3p], tmp_path, password="x")
    assert "not password-protected" in str(ei.value).lower()


def test_protect_rejects_already_encrypted(sample_pdf_3p, tmp_path):
    protected = protect_pdf.run([sample_pdf_3p], tmp_path / "p",
                                password="secret")
    with pytest.raises(ToolError):
        protect_pdf.run([protected], tmp_path / "p2", password="other")


def test_services_pure():
    for name in ("protect_pdf", "unlock_pdf"):
        src = (ROOT / "app" / "services" / f"{name}.py").read_text("utf-8")
        for token in ("from flask", "import flask", "Blueprint"):
            assert token not in src


def test_protect_get_page(client):
    assert client.get("/t/protect_pdf/").status_code == 200


def test_unlock_get_page(client):
    assert client.get("/t/unlock_pdf/").status_code == 200


def test_protect_route_roundtrip(client, sample_pdf_3p):
    r = client.post(
        "/t/protect_pdf/",
        data={"files": [(io.BytesIO(sample_pdf_3p.read_bytes()), "a.pdf")],
              "password": "hunter2"},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert b"/dl/" in r.data


def test_unlock_route_roundtrip(client, sample_pdf_3p, tmp_path):
    # Build an encrypted PDF for upload.
    enc = tmp_path / "enc.pdf"
    w = PdfWriter()
    w.append(str(sample_pdf_3p))
    w.encrypt("hunter2")
    with open(enc, "wb") as fh:
        w.write(fh)
    r = client.post(
        "/t/unlock_pdf/",
        data={"files": [(open(enc, "rb"), "locked.pdf")],
              "password": "hunter2"},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert b"/dl/" in r.data
