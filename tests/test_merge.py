"""Tests for the merge tool: pure service + HTTP route round trips."""
import io

import pytest
from pypdf import PdfReader

from app.errors import ToolError
from app.services.merge import run


# ---------------- service ----------------

def test_merge_two_pdfs_page_counts_add_up(sample_pdf_3p, sample_pdf_2p,
                                           tmp_path):
    out = run([sample_pdf_3p, sample_pdf_2p], tmp_path)
    assert out == tmp_path / "merged.pdf"
    assert out.is_file()
    reader = PdfReader(out)
    assert len(reader.pages) == 5


def test_merge_preserves_upload_order(sample_pdf_3p, sample_pdf_2p, tmp_path):
    out = run([sample_pdf_2p, sample_pdf_3p], tmp_path)
    texts = [p.extract_text() or "" for p in PdfReader(out).pages]
    assert len(texts) == 5
    assert "Page 1 of 2" in texts[0]
    assert "Page 2 of 2" in texts[1]
    assert "Page 1 of 3" in texts[2]
    assert "Page 3 of 3" in texts[4]


def test_merge_three_inputs(tmp_path, sample_pdf_3p, sample_pdf_2p):
    out = run([sample_pdf_2p, sample_pdf_3p, sample_pdf_2p], tmp_path)
    assert len(PdfReader(out).pages) == 7


def test_merge_requires_two_inputs(sample_pdf_3p, tmp_path):
    with pytest.raises(ToolError):
        run([sample_pdf_3p], tmp_path)
    with pytest.raises(ToolError):
        run([], tmp_path)


def test_merge_error_message_is_user_safe(sample_pdf_3p, tmp_path):
    with pytest.raises(ToolError) as excinfo:
        run([sample_pdf_3p], tmp_path)
    assert str(excinfo.value.message) == "Please upload at least two PDF files."


def test_corrupt_pdf_raises_user_safe_error(tmp_path, sample_pdf_3p):
    bad = tmp_path / "junk.pdf"
    bad.write_bytes(b"%PDF-1.4 \x00totally not a pdf structure")
    with pytest.raises(ToolError) as excinfo:
        run([bad, sample_pdf_3p], tmp_path)
    msg = str(excinfo.value.message)
    assert "corrupted" in msg.lower() or "read" in msg.lower()
    # user-safe: no filesystem paths, internals or tracebacks leak out
    assert str(tmp_path) not in msg and "Traceback" not in msg
    assert "PdfReader" not in msg and "pypdf" not in msg.lower()


def test_encrypted_pdf_raises_tool_error(tmp_path, sample_pdf_2p,
                                         sample_pdf_3p):
    from pypdf import PdfWriter
    enc = tmp_path / "locked.pdf"
    w = PdfWriter()
    w.append(sample_pdf_2p)
    w.encrypt("secret")
    with open(enc, "wb") as fh:
        w.write(fh)
    with pytest.raises(ToolError) as excinfo:
        run([enc, sample_pdf_3p], tmp_path)
    assert str(tmp_path) not in str(excinfo.value.message)


def test_missing_input_raises_tool_error(sample_pdf_3p, tmp_path):
    with pytest.raises(ToolError) as excinfo:
        run([tmp_path / "nope.pdf", sample_pdf_3p], tmp_path)
    msg = str(excinfo.value.message)
    assert "missing" in msg.lower() and str(tmp_path) not in msg


def test_same_file_twice_merges_six_pages(sample_pdf_3p, tmp_path):
    out = run([sample_pdf_3p, sample_pdf_3p], tmp_path)
    assert len(PdfReader(out).pages) == 6


# ---------------- routes ----------------

def _merge_data(*paths_names):
    return {"files": [(io.BytesIO(p.read_bytes()), n)
                      for p, n in paths_names]}


def test_get_page_renders_form(client):
    r = client.get("/t/merge", follow_redirects=True)
    assert r.status_code == 200  # via 308 -> /t/merge/
    assert b"Merge PDF" in r.data
    assert b'name="files"' in r.data
    assert b"multiple" in r.data


def test_merge_roundtrip_returns_result_page(client, sample_pdf_3p,
                                             sample_pdf_2p):
    r = client.post("/t/merge",
                    data=_merge_data((sample_pdf_3p, "a.pdf"),
                                     (sample_pdf_2p, "b.pdf")),
                    content_type="multipart/form-data",
                    follow_redirects=True)
    assert r.status_code == 200
    assert b"/dl/" in r.data
    assert b"a.pdf" in r.data  # single output inherits first input's stem


def test_merge_canonical_url_no_redirect(client, sample_pdf_3p,
                                         sample_pdf_2p):
    # /t/merge (no trailing slash) is the form action / landing-card URL;
    # it must handle the POST directly, not 308-redirect and re-upload.
    r = client.post("/t/merge",
                    data=_merge_data((sample_pdf_3p, "a.pdf"),
                                     (sample_pdf_2p, "b.pdf")),
                    content_type="multipart/form-data")
    assert r.status_code == 200
    assert r.headers.get("Location") is None
    assert b"/dl/" in r.data


def test_merge_roundtrip_download_is_valid_pdf(client, sample_pdf_3p,
                                               sample_pdf_2p):
    r = client.post("/t/merge/",
                    data=_merge_data((sample_pdf_3p, "a.pdf"),
                                     (sample_pdf_2p, "b.pdf")),
                    content_type="multipart/form-data")
    assert r.status_code == 200
    html = r.data.decode()
    url = "/dl/" + html.split('href="/dl/')[1].split('"')[0]
    d = client.get(url)
    assert d.status_code == 200
    assert d.data.startswith(b"%PDF")
    assert len(PdfReader(io.BytesIO(d.data)).pages) == 5


def test_single_pdf_rejected_with_friendly_400(client, sample_pdf_3p):
    r = client.post("/t/merge/", data=_merge_data((sample_pdf_3p, "only.pdf")),
                    content_type="multipart/form-data")
    assert r.status_code == 400
    assert b"at least two PDF" in r.data


def test_non_pdf_input_rejected(client, sample_pdf_3p, sample_image_png):
    r = client.post("/t/merge/",
                    data=_merge_data((sample_pdf_3p, "a.pdf"),
                                     (sample_image_png, "pic.png")),
                    content_type="multipart/form-data")
    assert r.status_code == 400
    assert b"not a supported file type" in r.data
