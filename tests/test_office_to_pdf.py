"""Tests for the office_to_pdf tool: pure service + Flask routes.

LibreOffice is NOT installed on the dev box, so:
- the missing-binary path is covered by monkeypatching
  ``app.helpers.shutil.which`` (per CONTRACT.md),
- a fake-binary round trip (monkeypatched which + subprocess.run) exercises
  the full 200 / /dl/ route flow,
- the real conversion test skips itself unless soffice/libreoffice exist.
"""
import io
import subprocess
import types
import zipfile
from pathlib import Path

import pytest

import app.helpers as helpers
from app.errors import ToolError
from app.services.office_to_pdf import run

# ---------------------------------------------------------------------------
# builders
# ---------------------------------------------------------------------------

_DOCX_CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/'
    'content-types">'
    '<Default Extension="rels" ContentType="application/'
    'vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" ContentType="application/'
    'vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    '</Types>')

_DOCX_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
    'relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/'
    'officeDocument/2006/relationships/officeDocument" '
    'Target="word/document.xml"/></Relationships>')

_DOCX_DOCUMENT = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<w:document xmlns:w="http://schemas.openxmlformats.org/'
    'wordprocessingml/2006/main"><w:body><w:p><w:r>'
    '<w:t>Hello PDF</w:t></w:r></w:p></w:body></w:document>')


def make_docx_bytes() -> bytes:
    """A minimal but structurally valid .docx (OOXML package). Its PK\\x03\\x04
    magic bytes make the foundation's zip-kind detection classify it as an
    office file; the content is irrelevant on the missing-binary path."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _DOCX_CONTENT_TYPES)
        zf.writestr("_rels/.rels", _DOCX_RELS)
        zf.writestr("word/document.xml", _DOCX_DOCUMENT)
    return buf.getvalue()


def write_docx(dir_: Path, name: str = "fake.docx") -> Path:
    p = dir_ / name
    p.write_bytes(make_docx_bytes())
    return p


def fake_soffice_success(monkeypatch, calls: list):
    """Pretend soffice exists AND that it produces <input-stem>.pdf."""
    monkeypatch.setattr("app.helpers.shutil.which",
                        lambda name: "/fake/bin/soffice")

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        assert isinstance(cmd, list), "must never use shell=True"
        assert "--headless" in cmd and "--convert-to" in cmd
        outdir = Path(cmd[cmd.index("--outdir") + 1])
        src = Path(cmd[-1])
        (outdir / f"{src.stem}.pdf").write_bytes(b"%PDF-1.4 fake pdf\n")
        return types.SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr("app.services.office_to_pdf.subprocess.run", fake_run)


# ---------------------------------------------------------------------------
# service: missing binary (the required CONTRACT pattern)
# ---------------------------------------------------------------------------

def test_missing_binary(monkeypatch, tmp_path):
    monkeypatch.setattr("app.helpers.shutil.which", lambda name: None)
    docx = write_docx(tmp_path)
    with pytest.raises(ToolError):
        run([docx], tmp_path / "out")


def test_missing_binary_message_is_user_safe(monkeypatch, tmp_path):
    monkeypatch.setattr("app.helpers.shutil.which", lambda name: None)
    docx = write_docx(tmp_path)
    with pytest.raises(ToolError) as ei:
        run([docx], tmp_path / "out")
    msg = str(ei.value)
    assert "soffice" in msg            # names the program
    assert str(tmp_path) not in msg    # leaks no paths


def test_falls_back_to_libreoffice_when_no_soffice(monkeypatch, tmp_path):
    """soffice missing but libreoffice present -> no ToolError; the binary
    actually invoked is libreoffice."""
    monkeypatch.setattr("app.helpers.shutil.which",
                        lambda name: None if name == "soffice"
                        else "/fake/bin/libreoffice")
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        outdir = Path(cmd[cmd.index("--outdir") + 1])
        src = Path(cmd[-1])
        (outdir / f"{src.stem}.pdf").write_bytes(b"%PDF-1.4 fake pdf\n")
        return types.SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr("app.services.office_to_pdf.subprocess.run", fake_run)
    docx = write_docx(tmp_path)
    out = run([docx], tmp_path / "out")
    assert calls and calls[0][0] == "/fake/bin/libreoffice"
    assert out.is_file() and out.read_bytes().startswith(b"%PDF")


# ---------------------------------------------------------------------------
# service: success / failure shapes with a faked conversion
# ---------------------------------------------------------------------------

def test_service_single_input_returns_path(monkeypatch, tmp_path):
    calls: list = []
    fake_soffice_success(monkeypatch, calls)
    docx = write_docx(tmp_path)
    outdir = tmp_path / "out"
    out = run([docx], outdir)
    assert isinstance(out, Path)
    assert out.parent == outdir and out.is_file()
    assert out.name == f"{docx.stem}.pdf"
    assert len(calls) == 1
    cmd = calls[0]
    assert cmd[0] == "/fake/bin/soffice"
    assert cmd[cmd.index("--convert-to") + 1] == "pdf"
    assert cmd[-1] == str(docx)         # list args, no shell


def test_service_multiple_inputs_returns_list(monkeypatch, tmp_path):
    calls: list = []
    fake_soffice_success(monkeypatch, calls)
    a = write_docx(tmp_path, "a.docx")
    b = write_docx(tmp_path, "b.xlsx")
    outdir = tmp_path / "out"
    outs = run([a, b], outdir)
    assert isinstance(outs, list) and len(outs) == 2
    assert all(p.is_file() for p in outs)
    assert outs[0] != outs[1]              # distinct names for many outputs
    assert len(calls) == 2                 # one conversion per input


def test_service_nonzero_returncode_raises(monkeypatch, tmp_path):
    monkeypatch.setattr("app.helpers.shutil.which",
                        lambda name: "/fake/bin/soffice")
    monkeypatch.setattr(
        "app.services.office_to_pdf.subprocess.run",
        lambda cmd, **kw: types.SimpleNamespace(returncode=81, stdout=b"",
                                                stderr=b"boom"))
    with pytest.raises(ToolError):
        run([write_docx(tmp_path)], tmp_path / "out")


def test_service_timeout_raises_toolerror(monkeypatch, tmp_path):
    monkeypatch.setattr("app.helpers.shutil.which",
                        lambda name: "/fake/bin/soffice")

    def slow(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, 120)

    monkeypatch.setattr("app.services.office_to_pdf.subprocess.run", slow)
    with pytest.raises(ToolError):
        run([write_docx(tmp_path)], tmp_path / "out")


def test_service_zero_byte_output_raises(monkeypatch, tmp_path):
    """returncode 0 but an EMPTY pdf on disk -> ToolError, not a 0-byte download."""
    monkeypatch.setattr("app.helpers.shutil.which",
                        lambda name: "/fake/bin/soffice")

    def empty_output(cmd, **kw):
        outdir = Path(cmd[cmd.index("--outdir") + 1])
        src = Path(cmd[-1])
        (outdir / f"{src.stem}.pdf").write_bytes(b"")
        return types.SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr("app.services.office_to_pdf.subprocess.run", empty_output)
    with pytest.raises(ToolError):
        run([write_docx(tmp_path)], tmp_path / "out")


def test_service_spawn_failure_raises_clean_toolerror(monkeypatch, tmp_path):
    """Binary vanished between which() and exec (OSError at spawn) -> friendly
    ToolError whose message leaks no OS error text."""
    monkeypatch.setattr("app.helpers.shutil.which",
                        lambda name: "/fake/bin/soffice")

    def spawn_fail(cmd, **kw):
        raise OSError(2, "The system cannot find the file specified")

    monkeypatch.setattr("app.services.office_to_pdf.subprocess.run", spawn_fail)
    with pytest.raises(ToolError) as ei:
        run([write_docx(tmp_path)], tmp_path / "out")
    msg = str(ei.value)
    assert "system cannot find" not in msg.lower()   # no raw OS text leaks


def test_missing_binary_errors_before_any_subprocess(monkeypatch, tmp_path):
    """The gate must come from binary RESOLUTION, not from catching a failed
    spawn: subprocess.run must never even be reached."""
    monkeypatch.setattr("app.helpers.shutil.which", lambda name: None)

    def _never(cmd, **kwargs):
        raise AssertionError("subprocess.run must not be spawned when the "
                             "binary is missing")

    monkeypatch.setattr("app.services.office_to_pdf.subprocess.run", _never)
    with pytest.raises(ToolError):
        run([write_docx(tmp_path)], tmp_path / "out")


def test_service_corrupt_input_no_raw_exception(monkeypatch, tmp_path):
    """Called directly with %PDF garbage named .docx (skipping save_uploads),
    a soffice failure must surface as a user-safe ToolError, never a crash,
    and raw stderr must not leak into the message."""
    monkeypatch.setattr("app.helpers.shutil.which",
                        lambda name: "/fake/bin/soffice")
    corrupt = tmp_path / "corrupt.docx"
    corrupt.write_bytes(b"%PDF-1.4 garbagegarbagegarbage")

    def rc1(cmd, **kw):
        return types.SimpleNamespace(returncode=1, stdout=b"",
                                     stderr=b"Error: source file could not be loaded")

    monkeypatch.setattr("app.services.office_to_pdf.subprocess.run", rc1)
    with pytest.raises(ToolError) as ei:
        run([corrupt], tmp_path / "out")
    assert "could not be loaded" not in str(ei.value)


@pytest.mark.parametrize("opts", [
    {"angle": "1;rm -rf /"},
    {"pages": "0;--exec"},
    {"lang": "-1"},
    {"limit": "999999 | sh"},
    {"format": "$(whoami)"},
    {"outdir": ".."},
])
def test_service_ignores_injection_shaped_options(monkeypatch, tmp_path, opts):
    """Options are not part of this tool's contract; whatever a caller passes
    must be ignored, never interpolated into the command line, and the spawn
    must stay shell=False with a fixed argv."""
    calls: list = []
    kwargs_seen: list = []

    monkeypatch.setattr("app.helpers.shutil.which",
                        lambda name: "/fake/bin/soffice")

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        kwargs_seen.append(dict(kwargs))
        outdir = Path(cmd[cmd.index("--outdir") + 1])
        src = Path(cmd[-1])
        (outdir / f"{src.stem}.pdf").write_bytes(b"%PDF-1.4 fake pdf\n")
        return types.SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr("app.services.office_to_pdf.subprocess.run", fake_run)
    docx = write_docx(tmp_path)
    outdir = tmp_path / "out"
    run([docx], outdir, **opts)
    cmd = [str(c) for c in calls[0]]
    # (a) the argv must be EXACTLY the fixed conversion command (plus the
    #     mandatory -env:UserInstallation profile URI): option values are
    #     ignored entirely (paths excluded from the substring scan because
    #     temp-dir names can accidentally contain e.g. "-1")
    fixed = [tok for tok in cmd if not tok.startswith("-env:UserInstallation")]
    assert fixed == ["/fake/bin/soffice", "--headless", "--convert-to", "pdf",
                     "--outdir", str(outdir), str(docx)]
    fixed_flags = fixed[:4]
    for value in opts.values():
        assert not any(value in tok for tok in fixed_flags), \
            f"injected option value leaked: {value!r}"
    assert not any(kw.get("shell") for kw in kwargs_seen)


def _profile_dir_from_argv(argv):
    """Extract the -env:UserInstallation profile dir as a Path."""
    import urllib.request
    env_arg = next((t for t in argv if str(t).startswith(
        "-env:UserInstallation=")), None)
    assert env_arg, "soffice argv must pin a dedicated profile"
    uri = env_arg.split("=", 1)[1]
    assert uri.startswith("file://"), uri
    return Path(urllib.request.url2pathname(uri[len("file://"):]))


def test_service_uses_dedicated_profile_and_cleans_up(monkeypatch, tmp_path):
    """Parallel soffice runs need a dedicated -env:UserInstallation profile
    per invocation; the profile dir must be OUTSIDE the job trees and must
    not be left behind as junk."""
    monkeypatch.setattr("app.helpers.shutil.which",
                        lambda name: "/fake/bin/soffice")
    profiles = []

    def fake_run(c, **kw):
        p = _profile_dir_from_argv(c)
        assert p.is_dir(), "profile dir must exist while soffice runs"
        outdir = Path(c[c.index("--outdir") + 1])
        assert outdir not in p.parents and p != outdir, \
            "profile must not live inside the job output dir"
        src = Path(c[-1])
        (outdir / f"{src.stem}.pdf").write_bytes(b"%PDF-1.4 fake pdf\n")
        profiles.append(p)
        return types.SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr("app.services.office_to_pdf.subprocess.run", fake_run)
    outdir = tmp_path / "out"
    a = write_docx(tmp_path, "a.docx")
    b = write_docx(tmp_path, "b.docx")
    run([a, b], outdir)
    assert len(profiles) == 2
    assert profiles[0] == profiles[1]      # one profile reused per run()
    for p in profiles:                     # removed after run() returns
        assert not p.exists()
    # a second run() gets a FRESH, different profile
    c = write_docx(tmp_path, "c.docx")
    run([c], outdir)
    assert len(profiles) == 3
    assert profiles[2] != profiles[0]
    assert not profiles[2].exists()


def test_service_profile_cleaned_up_on_failure(monkeypatch, tmp_path):
    """A failed conversion must still remove the temp profile dir."""
    monkeypatch.setattr("app.helpers.shutil.which",
                        lambda name: "/fake/bin/soffice")
    captured = {}

    def fail_run(c, **kw):
        captured["p"] = _profile_dir_from_argv(c)
        return types.SimpleNamespace(returncode=1, stdout=b"", stderr=b"")

    monkeypatch.setattr("app.services.office_to_pdf.subprocess.run", fail_run)
    with pytest.raises(ToolError):
        run([write_docx(tmp_path)], tmp_path / "out")
    assert "p" in captured and not captured["p"].exists()


def test_service_output_lands_valid_pdf_kind(monkeypatch, tmp_path):
    """Independently sniff the produced file's magic bytes (not just trust the
    fake): output must be detect_kind == 'pdf'."""
    fake_soffice_success(monkeypatch, [])
    out = run([write_docx(tmp_path)], tmp_path / "out")
    assert helpers.detect_kind(out) == "pdf"
    assert out.read_bytes().startswith(b"%PDF")


def test_service_no_output_file_raises(monkeypatch, tmp_path):
    """returncode 0 but no PDF written (soffice crashed quietly) -> ToolError,
    never a returned path to a missing file."""
    monkeypatch.setattr("app.helpers.shutil.which",
                        lambda name: "/fake/bin/soffice")
    monkeypatch.setattr(
        "app.services.office_to_pdf.subprocess.run",
        lambda cmd, **kw: types.SimpleNamespace(returncode=0, stdout=b"",
                                                stderr=b""))
    with pytest.raises(ToolError):
        run([write_docx(tmp_path)], tmp_path / "out")


def test_service_uses_only_given_output_dir(monkeypatch, tmp_path):
    calls: list = []
    fake_soffice_success(monkeypatch, calls)
    outdir = tmp_path / "job-out"
    run([write_docx(tmp_path)], outdir)
    assert Path(calls[0][calls[0].index("--outdir") + 1]) == outdir


def test_service_pure_no_flask_import():
    src = Path("app/services/office_to_pdf.py").read_text(encoding="utf-8")
    lowered = src.lower()
    assert "import flask" not in lowered
    assert "from flask" not in lowered
    assert "request" not in lowered.replace("subprocess", "")


# ---------------------------------------------------------------------------
# real conversion — must SKIP on this box (no LibreOffice installed)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    helpers.binary_missing("soffice") and helpers.binary_missing("libreoffice"),
    reason="LibreOffice (soffice/libreoffice) not installed on this machine")
def test_real_conversion_to_pdf(tmp_path):
    docx = write_docx(tmp_path)
    outdir = tmp_path / "out"
    out = run([docx], outdir)
    assert out.is_file()
    assert out.read_bytes().startswith(b"%PDF")
    assert helpers.detect_kind(out) == "pdf"


# ---------------------------------------------------------------------------
# routes
# ---------------------------------------------------------------------------
# Routes are defined as "/" under url_prefix /t/office_to_pdf with
# strict_slashes=False, so both the canonical /t/office_to_pdf (the landing
# card + form action URL) and the trailing-slash form answer directly.

def test_get_page_renders(client):
    # both URL forms answer directly (strict_slashes=False): the landing card
    # and the form action use the canonical bare /t/office_to_pdf
    for url in ("/t/office_to_pdf", "/t/office_to_pdf/"):
        r = client.get(url)
        assert r.status_code == 200
        assert b"Office to PDF" in r.data
        assert b'action="/t/office_to_pdf"' in r.data
        assert b'name="files"' in r.data
        assert b".docx" in r.data      # accept list from the manifest
        assert b"multiple" in r.data   # multiple:true from the manifest


def test_route_missing_binary_friendly_400(client, monkeypatch):
    monkeypatch.setattr("app.helpers.shutil.which", lambda name: None)
    r = client.post("/t/office_to_pdf",
                    data={"files": [(io.BytesIO(make_docx_bytes()),
                                     "report.docx")]},
                    content_type="multipart/form-data")
    assert r.status_code == 400
    assert b"not installed" in r.data   # friendly binary-missing text


def test_route_rejects_non_office_file(client):
    r = client.post("/t/office_to_pdf",
                    data={"files": [(io.BytesIO(b"%PDF-1.4 junk"), "x.pdf")]},
                    content_type="multipart/form-data")
    assert r.status_code == 400
    assert b"not a supported file type" in r.data


def test_route_no_file_rejected(client):
    r = client.post("/t/office_to_pdf", data={},
                    content_type="multipart/form-data")
    assert r.status_code == 400
    assert b"No file was uploaded" in r.data


def test_route_roundtrip_success(client, monkeypatch):
    """Full job flow with the conversion faked: 200 + a working /dl/ link."""
    calls: list = []
    fake_soffice_success(monkeypatch, calls)
    r = client.post("/t/office_to_pdf",
                    data={"files": [(io.BytesIO(make_docx_bytes()),
                                     "report.docx")]},
                    content_type="multipart/form-data")
    assert r.status_code == 200
    assert b"/dl/" in r.data
    assert b"report.pdf" in r.data     # single output renamed after the input
    assert calls                        # soffice actually invoked once
    import re
    url = re.search(r'href="(/dl/[0-9a-f]+/0)"', r.data.decode()).group(1)
    d = client.get(url)
    assert d.status_code == 200
    assert d.data.startswith(b"%PDF")  # downloaded bytes really are the pdf


def test_route_roundtrip_multiple_outputs_zip(client, monkeypatch):
    calls: list = []
    fake_soffice_success(monkeypatch, calls)
    r = client.post("/t/office_to_pdf",
                    data={"files": [(io.BytesIO(make_docx_bytes()), "a.docx"),
                                    (io.BytesIO(make_docx_bytes()), "b.pptx")]},
                    content_type="multipart/form-data")
    assert r.status_code == 200
    assert b"/dl/" in r.data
    assert b"all.zip" in r.data         # >1 output -> zip on result page
    assert len(calls) == 2
