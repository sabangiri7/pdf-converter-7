"""Security regression tests: CSRF, headers, downloads, redaction, SSRF,
subprocess argv-only, SECRET_KEY policy, concurrent jobs, XSS escaping.
"""
from __future__ import annotations

import io
import subprocess
import threading
from pathlib import Path

import pytest
import pymupdf
from pypdf import PdfReader
from reportlab.pdfgen import canvas

from app import create_app
from app.errors import ToolError
from app.security import assert_secret_key, confined_under, reset_job_semaphore


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def csrf_app(tmp_path):
    app = create_app("testing")
    app.config.update(
        UPLOAD_ROOT=str(tmp_path / "uploads"),
        OUTPUT_ROOT=str(tmp_path / "outputs"),
        WTF_CSRF_ENABLED=True,
        RATELIMIT_ENABLED=False,
    )
    (tmp_path / "uploads").mkdir(parents=True, exist_ok=True)
    (tmp_path / "outputs").mkdir(parents=True, exist_ok=True)
    return app


@pytest.fixture()
def csrf_client(csrf_app):
    return csrf_app.test_client()


def _pdf_with_secret(path: Path, secret: str = "TOPSECRETUNIQUE42") -> Path:
    c = canvas.Canvas(str(path))
    c.drawString(72, 720, f"Visible preamble {secret} trailing words")
    c.showPage()
    c.save()
    return path


# ---------------------------------------------------------------------------
# security headers / cookies
# ---------------------------------------------------------------------------

def test_security_headers_present(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("X-Frame-Options") == "DENY"
    assert "strict-origin" in (r.headers.get("Referrer-Policy") or "")
    csp = r.headers.get("Content-Security-Policy") or ""
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp


def test_healthz_ok(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.get_json()["status"] == "ok"


# ---------------------------------------------------------------------------
# CSRF
# ---------------------------------------------------------------------------

def test_csrf_rejects_bare_post(csrf_client, sample_pdf_2p):
    data = {"files": [(io.BytesIO(sample_pdf_2p.read_bytes()), "a.pdf")],
            "find": "Page"}
    r = csrf_client.post("/t/redact_pdf", data=data,
                         content_type="multipart/form-data")
    assert r.status_code == 400
    assert b"security token" in r.data.lower() or b"CSRF" in r.data


def test_csrf_accepts_token(csrf_client, sample_pdf_2p):
    page = csrf_client.get("/t/redact_pdf")
    assert page.status_code == 200
    html = page.data.decode()
    assert 'name="csrf_token"' in html
    # Pull token from hidden input
    token = html.split('name="csrf_token"')[1].split('value="')[1].split('"')[0]
    data = {
        "csrf_token": token,
        "files": [(io.BytesIO(sample_pdf_2p.read_bytes()), "a.pdf")],
        "find": "Page",
    }
    r = csrf_client.post("/t/redact_pdf", data=data,
                         content_type="multipart/form-data")
    assert r.status_code == 200
    assert b"/dl/" in r.data


# ---------------------------------------------------------------------------
# download authorization / path confinement
# ---------------------------------------------------------------------------

def test_download_rejects_non_hex_job_id(client):
    assert client.get("/dl/../etc/passwd/0").status_code == 404
    assert client.get("/dl/not-a-uuid/0").status_code == 404
    assert client.get("/dl/" + ("a" * 31) + "/0").status_code == 404


def test_download_rejects_path_escape(app, tmp_path):
    """Poisoned manifest path outside OUTPUT_ROOT must 404."""
    from app.jobs import create_job, _save_manifest, _load_manifest, _output_dir

    with app.app_context():
        jid = create_job()
        secret = tmp_path / "outside-secret.txt"
        secret.write_text("should-not-leak")
        # Place a decoy inside the job dir AND point manifest at outside file
        decoy = _output_dir(jid) / "ok.pdf"
        decoy.write_bytes(b"%PDF-1.4 decoy")
        man = _load_manifest(jid)
        man["outputs"] = [{
            "index": 0,
            "name": "ok.pdf",
            "path": str(secret),  # absolute escape
            "size": secret.stat().st_size,
        }]
        man["done"] = True
        _save_manifest(jid, man)

    client = app.test_client()
    r = client.get(f"/dl/{jid}/0")
    assert r.status_code == 404
    assert b"should-not-leak" not in r.data


def test_confined_under_blocks_traversal(tmp_path):
    root = tmp_path / "out"
    root.mkdir()
    good = root / "a.pdf"
    good.write_bytes(b"%PDF")
    assert confined_under(root, good) == good.resolve()
    outside = tmp_path / "x.pdf"
    outside.write_bytes(b"%PDF")
    with pytest.raises(Exception):  # werkzeug abort -> HTTPException
        confined_under(root, outside)


# ---------------------------------------------------------------------------
# XSS: filenames / errors autoescaped
# ---------------------------------------------------------------------------

def test_error_message_escaped(client, sample_pdf_2p):
    # ToolError echoes find-preview; Jinja must escape HTML metacharacters.
    r = client.post(
        "/t/redact_pdf",
        data={"files": [(io.BytesIO(sample_pdf_2p.read_bytes()), "a.pdf")],
              "find": '<script>alert(1)</script>'},
        content_type="multipart/form-data")
    assert r.status_code == 400
    body = r.data.decode()
    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;" in body


def test_display_name_escaped_in_result(client):
    with client.application.test_request_context("/"):
        from flask import render_template
        html = render_template(
            "result.html",
            job_id="a" * 32,
            tool_title='</h1><script>alert(1)</script>',
            outputs=[{
                "index": 0,
                "display_name": '"><img src=x>',
                "size_h": "1 KB",
                "url": "/dl/" + ("a" * 32) + "/0",
            }],
            zip_url=None,
            single=True,
        )
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
    assert "<img src=x>" not in html
    assert "&lt;img" in html or "&quot;" in html


# ---------------------------------------------------------------------------
# SECRET_KEY policy
# ---------------------------------------------------------------------------

def test_secret_key_refuses_weak_in_production(monkeypatch, tmp_path):
    monkeypatch.setenv("PDF_TOOLS_CONFIG", "production")
    monkeypatch.delenv("PUBLIC_DEPLOY", raising=False)
    app = create_app("testing")  # bypass factory assert via testing first
    app.config["TESTING"] = False
    app.config["DEBUG"] = False
    app.config["SECRET_KEY"] = "dev-secret-change-me"
    monkeypatch.setenv("PDF_TOOLS_CONFIG", "production")
    with pytest.raises(RuntimeError, match="PDF_TOOLS_SECRET_KEY"):
        assert_secret_key(app)


def test_secret_key_allows_dev_weak(monkeypatch):
    monkeypatch.setenv("PDF_TOOLS_CONFIG", "development")
    monkeypatch.delenv("PUBLIC_DEPLOY", raising=False)
    app = create_app("testing")
    app.config["TESTING"] = False
    app.config["DEBUG"] = True
    app.config["SECRET_KEY"] = "dev-secret-change-me"
    monkeypatch.setenv("PDF_TOOLS_CONFIG", "development")
    assert_secret_key(app)  # must not raise


# ---------------------------------------------------------------------------
# concurrent job semaphore
# ---------------------------------------------------------------------------

def test_concurrent_job_limit(app, sample_pdf_2p, monkeypatch):
    from app.jobs import create_job, save_uploads, run_job
    from werkzeug.datastructures import FileStorage, MultiDict

    reset_job_semaphore()
    app.config["MAX_CONCURRENT_JOBS"] = 1
    reset_job_semaphore()

    started = threading.Event()
    release = threading.Event()
    errors: list = []

    def slow_svc(inputs, output_dir):
        started.set()
        release.wait(timeout=5)
        out = Path(output_dir) / "out.pdf"
        out.write_bytes(inputs[0].read_bytes())
        return out

    class FakeReq:
        def __init__(self, data):
            self.files = MultiDict([("files", FileStorage(
                stream=io.BytesIO(data), filename="a.pdf"))])

    with app.app_context():
        j1 = create_job()
        save_uploads(j1, FakeReq(sample_pdf_2p.read_bytes()))
        j2 = create_job()
        save_uploads(j2, FakeReq(sample_pdf_2p.read_bytes()))

    def run1():
        with app.app_context():
            try:
                run_job(j1, slow_svc, {}, title="one")
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

    t = threading.Thread(target=run1)
    t.start()
    assert started.wait(timeout=5)
    with app.app_context():
        with pytest.raises(ToolError, match="busy"):
            run_job(j2, slow_svc, {}, title="two")
    release.set()
    t.join(timeout=5)
    assert not errors
    reset_job_semaphore()


# ---------------------------------------------------------------------------
# redaction permanence
# ---------------------------------------------------------------------------

def test_redaction_removes_text_from_content_stream(tmp_path):
    from app.services.redact_pdf import run

    secret = "TOPSECRETUNIQUE42"
    src = _pdf_with_secret(tmp_path / "in.pdf", secret)
    # Confirm present before
    before = pymupdf.open(str(src))
    assert secret in before[0].get_text()
    before.close()

    out = run([src], tmp_path / "out", find=secret)
    after = pymupdf.open(str(out))
    text = after[0].get_text()
    after.close()
    assert secret not in text

    # Also check raw bytes / pypdf extraction
    raw = out.read_bytes()
    assert secret.encode() not in raw
    reader = PdfReader(str(out))
    extracted = "".join((p.extract_text() or "") for p in reader.pages)
    assert secret not in extracted


# ---------------------------------------------------------------------------
# SSRF: html_to_pdf never fetches
# ---------------------------------------------------------------------------

def test_html_to_pdf_no_network(tmp_path, monkeypatch):
    from app.services import html_to_pdf as mod

    html = tmp_path / "x.html"
    html.write_text(
        "<html><body><p>Hello</p>"
        '<img src="http://127.0.0.1:9/steal">'
        '<script src="https://evil.example/x.js"></script>'
        "</body></html>",
        encoding="utf-8")

    def boom(*_a, **_k):
        raise AssertionError("network must not be used")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    monkeypatch.setattr("urllib.request.urlretrieve", boom)
    try:
        import urllib3
        monkeypatch.setattr(urllib3.PoolManager, "request", boom)
    except ImportError:
        pass

    out = mod.run([html], tmp_path / "out")
    assert out.is_file() and out.read_bytes().startswith(b"%PDF")


# ---------------------------------------------------------------------------
# subprocess: argv only, no shell
# ---------------------------------------------------------------------------

def test_office_and_ocr_subprocess_argv_only():
    src_office = Path("app/services/office_to_pdf.py").read_text(encoding="utf-8")
    src_ocr = Path("app/services/ocr_pdf.py").read_text(encoding="utf-8")
    assert "shell=True" not in src_office
    assert "shell=True" not in src_ocr
    assert "subprocess.run" in src_office
    assert "subprocess.run" in src_ocr


def test_office_subprocess_uses_list_argv(monkeypatch, tmp_path):
    from app.services import office_to_pdf as mod

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        assert isinstance(cmd, list)
        assert kwargs.get("shell") in (None, False)
        out = Path(cmd[cmd.index("--outdir") + 1]) / (Path(cmd[-1]).stem + ".pdf")
        out.write_bytes(b"%PDF-1.4 fake")
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    monkeypatch.setattr(mod.helpers, "binary_path",
                        lambda n: "/usr/bin/soffice" if n == "soffice" else None)
    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    src = tmp_path / "doc.docx"
    src.write_bytes(b"PK\x03\x04" + b"\x00" * 40)
    out = mod.run([src], tmp_path / "out")
    assert out.is_file()
    assert calls and isinstance(calls[0][0], list)


# ---------------------------------------------------------------------------
# Pillow pixel cap applied
# ---------------------------------------------------------------------------

def test_pillow_max_pixels_configured(app):
    from PIL import Image
    assert Image.MAX_IMAGE_PIXELS == app.config["MAX_IMAGE_PIXELS"]
