"""Foundation tests: discovery, job framework, validation, downloads,
helpers. Tool builders should keep this file untouched — each tool gets its
own tests/test_<slug>.py.
"""
import io
import json
import os
import time
import zipfile
from pathlib import Path

import pytest

from app.errors import ToolError
from app.helpers import (
    binary_missing,
    detect_kind,
    human_size,
    page_count,
    safe_display_name,
)
from app import registry
from app import create_app


def _upload(pdf_bytes, filename="doc.pdf"):
    return {"files": [(io.BytesIO(pdf_bytes), filename)]}


# ---------------- discovery ----------------

def test_landing_page_ok(client):
    r = client.get("/")
    assert r.status_code == 200
    body = r.data.decode()
    assert "Merge PDF" in body
    # Essential tools render as cards; remaining tools live under More tools.
    for slug in ("merge", "split", "compress", "ocr_pdf", "watermark"):
        assert f"/t/{slug}" in body
    assert "more-tools" in body
    assert "More tools" in body
    assert "Organize &amp; pages" in body or "Edit &amp; annotate" in body
    assert body.count("tool-card") >= 8
    assert "/t/nup" in body  # non-essential still reachable


def test_all_manifests_load():
    entries = registry.discover()
    slugs = set(entries)
    assert {"merge", "split", "compress", "rotate", "pdf_to_images",
            "images_to_pdf", "watermark", "office_to_pdf",
            "ocr_pdf", "pdf_to_pptx", "csv_to_xlsx",
            "image_convert"} <= slugs
    # every manifest has a working module
    for s in sorted(slugs):
        assert entries[s].available is True, entries[s].error


def test_missing_tool_has_no_route(client):
    # built tool routes; an unknown slug does not
    assert client.get("/t/merge", follow_redirects=True).status_code == 200
    assert client.get("/t/no_such_tool").status_code == 404
    body = client.get("/").data.decode()
    assert "coming soon" not in body


def test_broken_tool_module_is_skipped_not_fatal():
    """A tool .py that raises at import must not crash discovery."""
    ok_py = registry.TOOLS_DIR / "_probe_ok.py"
    ok_json = registry.TOOLS_DIR / "_probe_ok.json"
    bad_py = registry.TOOLS_DIR / "_probe_bad.py"
    bad_json = registry.TOOLS_DIR / "_probe_bad.json"
    try:
        ok_py.write_text("from flask import Blueprint\nbp = Blueprint('_probe_ok', __name__)\n")
        ok_json.write_text(json.dumps({"slug": "_probe_ok", "title": "Probe OK",
                                       "description": "d", "icon": "X"}))
        bad_py.write_text("raise RuntimeError('kaboom at import time')\n")
        bad_json.write_text(json.dumps({"slug": "_probe_bad", "title": "Probe Bad",
                                        "description": "d", "icon": "X"}))
        entries = registry.discover()
        assert entries["_probe_ok"].available is True
        assert entries["_probe_bad"].available is False
        assert "kaboom" in entries["_probe_bad"].error
        app = create_app("testing")   # app still builds with the broken tool
        assert "_probe_bad" not in {s for s, e in app.tool_entries.items()
                                    if e.available}
    finally:
        for p in (ok_py, ok_json, bad_py, bad_json):
            p.unlink(missing_ok=True)


# ---------------- full job round trip over HTTP ----------------
# A tiny blueprint stands in for a real tool (the probe is deleted with this
# test module; production tools live in app/tools/).

def _register_probe(app):
    from flask import Blueprint, request, render_template
    from app.jobs import create_job, save_uploads, run_job
    from app.errors import ToolError as _TE
    bp = Blueprint("probe", __name__, url_prefix="/probe")

    @bp.post("/one")           # single output
    def one():
        jid = create_job()
        save_uploads(jid, allowed_kinds=("pdf",))
        def svc(inputs, output_dir, factor="1"):
            from pathlib import Path as P
            out = P(output_dir) / "out.pdf"
            out.write_bytes(b"".join(p.read_bytes() for p in inputs))
            return out
        ctx = run_job(jid, svc, {"factor": request.form.get("factor", "1")},
                      title="Probe One")
        return render_template("result.html", **ctx)

    @bp.post("/many")          # multiple outputs -> zip
    def many():
        jid = create_job()
        save_uploads(jid, allowed_kinds=("pdf",))
        def svc(inputs, output_dir):
            from pathlib import Path as P
            outs = []
            for i, p in enumerate(inputs, 1):
                o = P(output_dir) / f"part-{i}.pdf"
                o.write_bytes(p.read_bytes())
                outs.append(o)
            return outs
        ctx = run_job(jid, svc, {}, title="Probe Many")
        return render_template("result.html", **ctx)

    @bp.post("/boom")          # service raises -> friendly 400 page
    def boom():
        jid = create_job()
        save_uploads(jid, allowed_kinds=("pdf",))
        def svc(inputs, output_dir):
            raise _TE("service said no")
        ctx = run_job(jid, svc, {}, title="Boom")
        return render_template("result.html", **ctx)

    app.register_blueprint(bp)


@pytest.fixture()
def probe_client(app):
    _register_probe(app)
    return app.test_client()


def test_roundtrip_single_output_and_download(probe_client, sample_pdf_3p):
    r = probe_client.post("/probe/one", data=_upload(sample_pdf_3p.read_bytes(),
                                                     "my report.pdf"),
                          content_type="multipart/form-data")
    assert r.status_code == 200
    html = r.data.decode()
    assert "my report.pdf" in html          # display name preserved
    url = "/dl/" + html.split('href="/dl/')[1].split('"')[0].removeprefix("/dl/")
    d = probe_client.get(url)
    assert d.status_code == 200
    cd = d.headers["Content-Disposition"]
    assert "attachment" in cd and "my report" in cd
    assert d.data.startswith(b"%PDF")
    # uuid-only internal names: nothing user-named was written to disk
    assert not any("my report" in p for p in os.listdir(
        probe_client.application.config["UPLOAD_ROOT"]))


def test_roundtrip_multi_output_zip(probe_client, sample_pdf_3p, sample_pdf_2p):
    data = {"files": [(io.BytesIO(sample_pdf_3p.read_bytes()), "a.pdf"),
                      (io.BytesIO(sample_pdf_2p.read_bytes()), "b.pdf")]}
    r = probe_client.post("/probe/many", data=data,
                          content_type="multipart/form-data")
    assert r.status_code == 200
    html = r.data.decode()
    assert "all.zip" in html
    import re
    zip_url = re.search(r'href="(/dl/[0-9a-f]+/all\.zip)"', html).group(1)
    z = probe_client.get(zip_url)
    assert z.status_code == 200
    assert z.mimetype == "application/zip"
    names = sorted(zipfile.ZipFile(io.BytesIO(z.data)).namelist())
    assert names == ["part-1.pdf", "part-2.pdf"]


def test_service_toolerror_friendly_page(probe_client, sample_pdf_3p):
    r = probe_client.post("/probe/boom", data=_upload(sample_pdf_3p.read_bytes()),
                          content_type="multipart/form-data")
    assert r.status_code == 400
    assert b"service said no" in r.data


def test_rejects_fake_pdf(probe_client):
    r = probe_client.post("/probe/one", data=_upload(b"not a pdf at all", "evil.pdf"),
                          content_type="multipart/form-data")
    assert r.status_code == 400
    assert b"not a supported file type" in r.data


def test_rejects_corrupt_pdf(probe_client):
    r = probe_client.post("/probe/one",
                          data=_upload(b"%PDF-1.4 \x00garbagegarbage", "bad.pdf"),
                          content_type="multipart/form-data")
    assert r.status_code == 400
    assert b"valid PDF" in r.data


def test_no_file_rejected(probe_client):
    r = probe_client.post("/probe/one", data={},
                          content_type="multipart/form-data")
    assert r.status_code == 400
    assert b"No file was uploaded" in r.data


def test_path_traversal_filename_is_inert(probe_client, sample_pdf_3p):
    r = probe_client.post("/probe/one",
                          data=_upload(sample_pdf_3p.read_bytes(),
                                       "../../etc/shadow.pdf"),
                          content_type="multipart/form-data")
    assert r.status_code == 200  # stored under uuid name; traversal ignored
    assert not Path(probe_client.application.config["UPLOAD_ROOT"]).joinpath(
        "..", "..", "etc").exists()


def test_download_unknown_404(client):
    assert client.get("/dl/deadbeefdeadbeefdeadbeefdeadbeef/0").status_code == 404
    assert client.get("/dl/nope/all.zip").status_code == 404


# ---------------- helpers ----------------

def test_detect_kind(sample_pdf_3p, sample_images):
    assert detect_kind(sample_pdf_3p) == "pdf"
    assert {detect_kind(p) for p in sample_images} == {"jpg", "png"}


def _tmp_bytes(data: bytes, suffix: str) -> Path:
    import tempfile
    fd, p = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
    return Path(p)


def test_detect_kind_zip_ole_webp_tiff():
    assert detect_kind(_tmp_bytes(b"PK\x03\x04" + b"\x00" * 30, ".zip")) == "zip"
    assert detect_kind(_tmp_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 8,
                                  ".doc")) == "ole"
    assert detect_kind(_tmp_bytes(b"RIFF\x00\x00\x00\x00WEBPVP8 ", ".webp")) == "webp"
    assert detect_kind(_tmp_bytes(b"II\x2a\x00" + b"\x00" * 8, ".tif")) == "tiff"
    assert detect_kind(_tmp_bytes(b"hello world", ".bin")) is None


def test_human_size():
    assert human_size(500) == "500 B"
    assert human_size(1536) == "1.5 KB"
    assert human_size(50 * 1024 * 1024) == "50 MB"


def test_page_count(sample_pdf_3p, sample_pdf_2p, tmp_path):
    assert page_count(sample_pdf_3p) == 3
    assert page_count(sample_pdf_2p) == 2
    bad = tmp_path / "junk.pdf"
    bad.write_bytes(b"%PDF-1.1 not really a pdf")
    with pytest.raises(ToolError):
        page_count(bad)


def test_page_count_limit_validation(probe_client, sample_pdf_3p, monkeypatch):
    monkeypatch.setitem(probe_client.application.config, "MAX_PAGES", 2)
    r = probe_client.post("/probe/one", data=_upload(sample_pdf_3p.read_bytes()),
                          content_type="multipart/form-data")
    assert r.status_code == 400
    assert b"pages" in r.data


def test_safe_display_name():
    assert safe_display_name("../../etc/passwd") == "passwd"
    assert safe_display_name("C:\\temp\\a b.pdf") == "a b.pdf"
    # reserved chars are stripped; * and ? also terminate the name (Windows
    # globbing weirdness is cut off entirely rather than smuggled through)
    assert safe_display_name('weird<>:"/\\|?*name.pdf') == "name.pdf"
    assert safe_display_name("ok [final].pdf") == "ok [final].pdf"
    assert safe_display_name("ok.pdf") == "ok.pdf"
    # Long titles must keep a real extension (Office -> PDF downloads).
    long = ("Seceon aiSIEM vs CrowdStrike Falcon Next-Gen SIEM (LogScale)  "
            "Next-Gen SIEM, Threat Intelligence and Pricing Comparison.pdf")
    fixed = safe_display_name(long)
    assert fixed.endswith(".pdf")
    assert len(fixed) <= 120
    with pytest.raises(ToolError):
        safe_display_name("...")
    with pytest.raises(ToolError):
        safe_display_name(None)


def test_binary_missing(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda n: None)
    assert binary_missing("soffice") is True
    monkeypatch.setattr("shutil.which", lambda n: "/usr/bin/soffice")
    assert binary_missing("soffice") is False


# ---------------- jobs framework ----------------

def test_create_and_cleanup_job(app):
    from app.jobs import create_job, cleanup_job, _upload_dir, _output_dir
    with app.app_context():
        jid = create_job()
        assert _upload_dir(jid).is_dir() and _output_dir(jid).is_dir()
        assert cleanup_job(jid) is True
        assert not _upload_dir(jid).exists() and not _output_dir(jid).exists()
        assert cleanup_job(jid) is False          # idempotent
        assert cleanup_job("not-a-job-id") is False


def test_save_uploads_kind_filter(app, sample_image_png):
    from app.jobs import create_job, save_uploads
    from werkzeug.datastructures import FileStorage, MultiDict

    class FakeReq:
        def __init__(self, fs):
            self.files = MultiDict([("files", fs)])

    with app.app_context():
        jid = create_job()
        png = FakeReq(FileStorage(stream=io.BytesIO(sample_image_png.read_bytes()),
                                  filename="pic.png"))
        with pytest.raises(ToolError):          # only PDF allowed
            save_uploads(jid, png, allowed_kinds=("pdf",))
        out = save_uploads(jid, png, allowed_kinds=(".png",))
        assert out[0].kind == "png"
        # office alias: zip-header (docx-like) accepted as 'office'
        z = FakeReq(FileStorage(stream=io.BytesIO(b"PK\x03\x04" + b"\x00" * 60),
                                filename="deck.pptx"))
        out2 = save_uploads(jid, z, allowed_kinds=("office",))
        assert out2[0].kind == "zip"


def test_sweep_expired(app):
    from app.jobs import create_job, sweep_expired, _upload_dir
    with app.app_context():
        old = create_job()
        f = _upload_dir(old) / "stamp"
        f.write_text("x")
        past = time.time() - 7200
        for p in (_upload_dir(old) / "job.json", f, _upload_dir(old)):
            os.utime(p, (past, past))
        fresh = create_job()
        n = sweep_expired(ttl=3600)
        assert n >= 1
        assert not _upload_dir(old).exists()
        assert _upload_dir(fresh).exists()
