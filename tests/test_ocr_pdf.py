"""Tests for the ocr_pdf tool: pure service + blueprint routes.

Tesseract is NOT installed on the dev box, so the real-OCR test skips; every
other test fakes the environment (monkeypatched shutil.which / subprocess.run)
and exercises the actual service and route code paths.
"""
import io
import subprocess
import sys
from pathlib import Path

import pytest

import app.helpers as helpers
from app.errors import ToolError
from app.services.ocr_pdf import (
    ALREADY_TEXT_MESSAGE,
    LANGUAGES,
    MISSING_DEPENDENCY_MESSAGE,
    TAGGED_PDF_MESSAGE,
    run,
)

MINI_PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"


def _fake_which(found):
    """Factory: replacement for shutil.which returning a fake path or None."""
    return lambda name: (r"C:\fake\tesseract.exe" if found else None)


def _recording_fake_run(store, rc=0, writes=True, stderr=b""):
    """Replacement for subprocess.run that records every invocation."""
    def fake_run(cmd, **kwargs):
        store.append((cmd, kwargs))
        if writes:
            Path(cmd[-1]).write_bytes(MINI_PDF)
        return subprocess.CompletedProcess(cmd, rc, b"", stderr)
    return fake_run


# ---------------------------------------------------------------------------
# service-level tests
# ---------------------------------------------------------------------------

def test_missing_binary(monkeypatch, sample_pdf_3p, tmp_path):
    """Per CONTRACT.md: missing tesseract must become a friendly ToolError,
    checked FIRST — before any subprocess work."""
    monkeypatch.setattr("app.helpers.shutil.which", _fake_which(False))
    calls = []
    monkeypatch.setattr("app.services.ocr_pdf.subprocess.run",
                        _recording_fake_run(calls))
    with pytest.raises(ToolError) as ei:
        run([sample_pdf_3p], tmp_path, language="eng")
    msg = str(ei.value)
    assert "Tesseract" in msg and "not installed" in msg
    assert not calls                      # binary check ran BEFORE subprocess
    assert not (tmp_path / "ocr.pdf").exists()


def test_invalid_language(monkeypatch, sample_pdf_3p, tmp_path):
    # binary "present", so the ToolError can only come from validation
    monkeypatch.setattr("app.helpers.shutil.which", _fake_which(True))
    calls = []
    monkeypatch.setattr("app.services.ocr_pdf.subprocess.run",
                        _recording_fake_run(calls))
    with pytest.raises(ToolError):
        run([sample_pdf_3p], tmp_path, language="klingon")
    assert not calls
    assert not (tmp_path / "ocr.pdf").exists()


@pytest.mark.parametrize("evil", [
    "eng; rm -rf /", "eng && calc.exe", "$(whoami)", "--exec=x", "-x",
    "eng\x00deu", "999999", "1;rm", "['eng']", 12345,
])
def test_injection_shaped_language_rejected_without_subprocess(
        monkeypatch, sample_pdf_3p, tmp_path, evil):
    """Option-injection-shaped values must never reach an argv or a shell —
    the whitelist check runs first and no subprocess is spawned."""
    monkeypatch.setattr("app.helpers.shutil.which", _fake_which(True))
    calls = []
    monkeypatch.setattr("app.services.ocr_pdf.subprocess.run",
                        _recording_fake_run(calls))
    with pytest.raises(ToolError):
        run([sample_pdf_3p], tmp_path, language=evil)
    assert not calls


def test_service_never_uses_shell(monkeypatch, sample_pdf_3p, tmp_path):
    """OCR runs as an argv list with shell=False (the default), never a
    shell string."""
    monkeypatch.setattr("app.helpers.shutil.which", _fake_which(True))
    calls = []
    monkeypatch.setattr("app.services.ocr_pdf.subprocess.run",
                        _recording_fake_run(calls))
    run([sample_pdf_3p], tmp_path, language="eng")
    cmd, kwargs = calls[0]
    assert isinstance(cmd, list)
    assert not kwargs.get("shell", False)
    assert all(isinstance(a, str) for a in cmd)
    assert ";" not in "".join(cmd) and "|" not in "".join(cmd)


def _encrypted_copy(src: Path, dst: Path) -> None:
    """Write a password-protected copy of a sample PDF (encrypted path tests)."""
    from pypdf import PdfReader, PdfWriter
    writer = PdfWriter()
    writer.append(PdfReader(str(src)))
    writer.encrypt("hunter2")
    with open(dst, "wb") as fh:
        writer.write(fh)


def _assert_clean_corrupt_error(calls, out_dir):
    """Common assertions for corrupt-input rejection: no engine spawned,
    no partial output left behind in the output dir."""
    assert not calls
    assert not any(out_dir.iterdir())


def test_corrupt_pdf_is_rejected_before_subprocess(monkeypatch, tmp_path):
    """%PDF magic bytes + garbage body: the service fails clean (ToolError),
    never a 500-style crash, never spawns the engine."""
    monkeypatch.setattr("app.helpers.shutil.which", _fake_which(True))
    calls = []
    monkeypatch.setattr("app.services.ocr_pdf.subprocess.run",
                        _recording_fake_run(calls))
    out_dir = tmp_path / "o"
    out_dir.mkdir()
    bad = out_dir.parent / "corrupt.pdf"   # upload lives OUTSIDE output_dir
    bad.write_bytes(b"%PDF-1.4 garbagegarbage")
    with pytest.raises(ToolError) as ei:
        run([bad], out_dir, language="eng")
    msg = str(ei.value)
    assert "PDF" in msg and str(tmp_path) not in msg   # user-safe wording
    _assert_clean_corrupt_error(calls, out_dir)


def test_encrypted_pdf_is_rejected_before_subprocess(monkeypatch,
                                                     sample_pdf_3p, tmp_path):
    """Password-protected PDF: friendly ToolError from the early page_count
    check — never the engine, never a 500."""
    monkeypatch.setattr("app.helpers.shutil.which", _fake_which(True))
    calls = []
    monkeypatch.setattr("app.services.ocr_pdf.subprocess.run",
                        _recording_fake_run(calls))
    enc = tmp_path / "enc.pdf"
    _encrypted_copy(sample_pdf_3p, enc)
    out_dir = tmp_path / "o"
    out_dir.mkdir()
    with pytest.raises(ToolError) as ei:
        run([enc], out_dir, language="eng")
    assert "password" in str(ei.value).lower()
    _assert_clean_corrupt_error(calls, out_dir)


def test_language_none_falls_back_to_default(monkeypatch, sample_pdf_3p, tmp_path):
    monkeypatch.setattr("app.helpers.shutil.which", _fake_which(True))
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        Path(cmd[-1]).write_bytes(MINI_PDF)
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    monkeypatch.setattr("app.services.ocr_pdf.subprocess.run", fake_run)
    run([sample_pdf_3p], tmp_path, language=None)  # defensive: treated as eng
    assert "--language" in seen["cmd"]
    assert seen["cmd"][seen["cmd"].index("--language") + 1] == "eng"


def test_success_returns_ocr_pdf_in_output_dir(monkeypatch, sample_pdf_3p,
                                               tmp_path):
    monkeypatch.setattr("app.helpers.shutil.which", _fake_which(True))
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    calls = {}

    def fake_run(cmd, **kwargs):
        calls["cmd"] = cmd
        calls["timeout"] = kwargs.get("timeout")
        Path(cmd[-1]).write_bytes(MINI_PDF)
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    monkeypatch.setattr("app.services.ocr_pdf.subprocess.run", fake_run)
    result = run([sample_pdf_3p], out_dir, language="deu")
    assert isinstance(result, Path)
    assert result == out_dir / "ocr.pdf" and result.is_file()
    cmd = calls["cmd"]
    assert cmd[0] == sys.executable and cmd[1] == "-m"
    assert cmd[2] == "ocrmypdf"
    assert cmd[cmd.index("--language") + 1] == "deu"
    assert cmd[-2] == str(sample_pdf_3p) and cmd[-1] == str(result)
    assert calls["timeout"] == 300


def test_exit_code_6_already_has_text(monkeypatch, sample_pdf_3p, tmp_path):
    """ocrmypdf ExitCode 6 = already_done_ocr (input has selectable text)."""
    monkeypatch.setattr("app.helpers.shutil.which", _fake_which(True))

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 6, b"", b"prior text noise")

    monkeypatch.setattr("app.services.ocr_pdf.subprocess.run", fake_run)
    with pytest.raises(ToolError) as ei:
        run([sample_pdf_3p], tmp_path, language="eng")
    assert str(ei.value) == ALREADY_TEXT_MESSAGE
    assert not (tmp_path / "ocr.pdf").exists()


def test_exit_code_2_tagged_pdf(monkeypatch, sample_pdf_3p, tmp_path):
    """ocrmypdf ExitCode 2 + TaggedPDFError = born-digital office PDF."""
    monkeypatch.setattr("app.helpers.shutil.which", _fake_which(True))
    stderr = (b"TaggedPDFError: This PDF is marked as a Tagged PDF. This "
              b"often indicates that the PDF was generated from an office "
              b"document and does not need OCR.\n")

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 2, b"", stderr)

    monkeypatch.setattr("app.services.ocr_pdf.subprocess.run", fake_run)
    with pytest.raises(ToolError) as ei:
        run([sample_pdf_3p], tmp_path, language="eng")
    assert str(ei.value) == TAGGED_PDF_MESSAGE
    assert "corrupted" not in str(ei.value).lower()
    assert not (tmp_path / "ocr.pdf").exists()


def test_exit_code_3_missing_dependency(monkeypatch, sample_pdf_3p, tmp_path):
    """ocrmypdf ExitCode 3 = missing_dependency (e.g. no language pack), NOT
    selectable text — the friendly message must not blame the user's file."""
    monkeypatch.setattr("app.helpers.shutil.which", _fake_which(True))

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 3, b"", b"missing dependency")

    monkeypatch.setattr("app.services.ocr_pdf.subprocess.run", fake_run)
    with pytest.raises(ToolError) as ei:
        run([sample_pdf_3p], tmp_path, language="eng")
    assert str(ei.value) == MISSING_DEPENDENCY_MESSAGE
    assert "selectable text" not in str(ei.value)
    assert not (tmp_path / "ocr.pdf").exists()


def test_timeout_is_friendly(monkeypatch, sample_pdf_3p, tmp_path):
    monkeypatch.setattr("app.helpers.shutil.which", _fake_which(True))

    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 300))

    monkeypatch.setattr("app.services.ocr_pdf.subprocess.run", fake_run)
    with pytest.raises(ToolError) as ei:
        run([sample_pdf_3p], tmp_path, language="eng")
    assert "5 minutes" in str(ei.value)
    assert not (tmp_path / "ocr.pdf").exists()


def test_generic_failure_is_user_safe(monkeypatch, sample_pdf_3p, tmp_path):
    monkeypatch.setattr("app.helpers.shutil.which", _fake_which(True))

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(
            cmd, 1, b"", b"C:\\secret\\path\\traceback explode")

    monkeypatch.setattr("app.services.ocr_pdf.subprocess.run", fake_run)
    with pytest.raises(ToolError) as ei:
        run([sample_pdf_3p], tmp_path, language="eng")
    msg = str(ei.value)
    assert "traceback" not in msg.lower() and "secret" not in msg
    assert msg  # a real user-safe message, not empty
    assert not (tmp_path / "ocr.pdf").exists()


def test_success_but_no_output_file_is_error(monkeypatch, sample_pdf_3p,
                                             tmp_path):
    monkeypatch.setattr("app.helpers.shutil.which", _fake_which(True))

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, b"", b"")  # writes nothing

    monkeypatch.setattr("app.services.ocr_pdf.subprocess.run", fake_run)
    with pytest.raises(ToolError):
        run([sample_pdf_3p], tmp_path, language="eng")


def test_requires_exactly_one_pdf(monkeypatch, sample_pdf_3p, tmp_path):
    monkeypatch.setattr("app.helpers.shutil.which", _fake_which(True))
    with pytest.raises(ToolError):
        run([], tmp_path, language="eng")
    with pytest.raises(ToolError):
        run([sample_pdf_3p, sample_pdf_3p], tmp_path, language="eng")
    junk = tmp_path / "notpdf.pdf"
    junk.write_bytes(b"definitely not a pdf")
    with pytest.raises(ToolError):
        run([junk], tmp_path, language="eng")


@pytest.mark.skipif(helpers.binary_missing("tesseract"),
                    reason="tesseract not installed on this machine")
def test_real_ocr(sample_pdf_3p, tmp_path):
    """End-to-end OCR of a genuinely scanned PDF. Skipped on the dev box
    (no Tesseract installed) per CONTRACT.md."""
    img = sorted((Path(__file__).resolve().parent.parent / "samples")
                 .glob("sample_*.jpg"))[0]
    import img2pdf
    scanned = tmp_path / "scanned.pdf"
    scanned.write_bytes(img2pdf.convert(str(img)))
    out_dir = tmp_path / "o"
    out_dir.mkdir()
    out = run([scanned], out_dir, language="eng")
    assert out.is_file() and out.read_bytes().startswith(b"%PDF")


# ---------------------------------------------------------------------------
# route tests
# ---------------------------------------------------------------------------

def test_get_page_renders(client):
    r = client.get("/t/ocr_pdf/")
    assert r.status_code == 200
    assert b"OCR PDF" in r.data
    assert b'name="language"' in r.data
    for lang in LANGUAGES:
        assert lang.encode() in r.data


def test_route_missing_binary_returns_400(client, sample_pdf_3p, monkeypatch):
    monkeypatch.setattr("app.helpers.shutil.which", _fake_which(False))
    r = client.post("/t/ocr_pdf/",
                    data={"files": [(io.BytesIO(sample_pdf_3p.read_bytes()),
                                     "scan.pdf")],
                          "language": "eng"},
                    content_type="multipart/form-data")
    assert r.status_code == 400
    assert b"Tesseract" in r.data and b"not installed" in r.data


def test_route_bad_language_rejected_400(client, sample_pdf_3p):
    r = client.post("/t/ocr_pdf/",
                    data={"files": [(io.BytesIO(sample_pdf_3p.read_bytes()),
                                     "scan.pdf")],
                          "language": "latin"},
                    content_type="multipart/form-data")
    assert r.status_code == 400
    assert b"language" in r.data.lower()


def test_route_rejects_non_pdf(client):
    r = client.post("/t/ocr_pdf/",
                    data={"files": [(io.BytesIO(b"not a pdf"), "x.pdf")]},
                    content_type="multipart/form-data")
    assert r.status_code == 400
    assert b"not a supported file type" in r.data


def test_route_roundtrip_ok(client, sample_pdf_3p, monkeypatch):
    """Full upload -> job -> result page roundtrip with tesseract + the
    ocrmypdf subprocess faked (not installed on this dev box)."""
    monkeypatch.setattr("app.helpers.shutil.which", _fake_which(True))

    def fake_run(cmd, **kwargs):
        Path(cmd[-1]).write_bytes(MINI_PDF)
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    monkeypatch.setattr("app.services.ocr_pdf.subprocess.run", fake_run)
    r = client.post("/t/ocr_pdf/",
                    data={"files": [(io.BytesIO(sample_pdf_3p.read_bytes()),
                                     "scan.pdf")],
                          "language": "fra"},
                    content_type="multipart/form-data")
    assert r.status_code == 200
    assert b"/dl/" in r.data
    assert b"scan.pdf" in r.data
