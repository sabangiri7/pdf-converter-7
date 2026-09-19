"""Generic job framework: create job -> save uploads -> run service ->
download outputs -> cleanup.

Routes stay thin; PDF work lives in pure functions in app/services/.

Storage layout (see CONTRACT.md):
    <instance>/uploads/<job_id>/   saved upload files + job.json manifest
    <instance>/outputs/<job_id>/   files produced by the service function
Both trees are swept hourly (and once at startup) for job dirs whose newest
content is older than JOB_TTL_SECONDS (default 1 hour).
"""
import io
import json
import os
import shutil
import threading
import time
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path

from flask import Blueprint, abort, current_app, request, send_file

from .errors import ToolError
from .helpers import (
    EXT_BY_KIND,
    expand_kinds,
    human_size,
    kind_from_header,
    looks_like_csv,
    looks_like_plain_text,
    page_count,
    safe_display_name,
)

jobs_bp = Blueprint("jobs", __name__)

MANIFEST_NAME = "job.json"

# extension -> kind, so builders may pass either form to save_uploads
KIND_BY_EXT = {
    ".pdf": "pdf", ".png": "png", ".jpg": "jpg", ".jpeg": "jpg",
    ".tif": "tiff", ".tiff": "tiff", ".webp": "webp", ".gif": "gif",
    ".zip": "zip", ".docx": "zip", ".xlsx": "zip", ".pptx": "zip",
    ".doc": "ole", ".xls": "ole", ".ppt": "ole",
    ".csv": "csv",
    ".txt": "text", ".text": "text",
    ".html": "html", ".htm": "html",
    ".md": "markdown", ".markdown": "markdown",
}


@dataclass
class JobFile:
    """One saved upload. `.path` is the INTERNAL uuid-named file — never
    derive anything user-facing from it. `.name` is the sanitized ORIGINAL
    user filename, for display/download only."""
    path: Path
    name: str
    kind: str
    size: int

    def as_dict(self):
        return {"path": str(self.path), "name": self.name,
                "kind": self.kind, "size": self.size}


# ---------------------------------------------------------------------------
# paths / manifest helpers
# ---------------------------------------------------------------------------

def _upload_dir(job_id: str) -> Path:
    return Path(current_app.config["UPLOAD_ROOT"]) / job_id


def _output_dir(job_id: str) -> Path:
    return Path(current_app.config["OUTPUT_ROOT"]) / job_id


def _manifest_path(job_id: str) -> Path:
    return _upload_dir(job_id) / MANIFEST_NAME


def _load_manifest(job_id: str) -> dict:
    try:
        with open(_manifest_path(job_id), "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _save_manifest(job_id: str, data: dict) -> None:
    with open(_manifest_path(job_id), "w", encoding="utf-8") as fh:
        json.dump(data, fh)


def _valid_job_id(job_id) -> bool:
    return (isinstance(job_id, str) and len(job_id) == 32
            and all(c in "0123456789abcdef" for c in job_id))


# ---------------------------------------------------------------------------
# public API used by tool routes
# ---------------------------------------------------------------------------

def create_job() -> str:
    """Create a fresh job: uuid4-hex id + uploads/ and outputs/ dirs.
    Returns the job_id."""
    job_id = uuid.uuid4().hex
    _upload_dir(job_id).mkdir(parents=True, exist_ok=True)
    _output_dir(job_id).mkdir(parents=True, exist_ok=True)
    _save_manifest(job_id, {"job_id": job_id, "inputs": [], "outputs": [],
                            "created": time.time(), "done": False})
    return job_id


def _allowed_kind_set(allowed) -> set[str]:
    kinds: set[str] = set()
    for token in (allowed or ("pdf",)):
        token = str(token).lower().strip()
        if token.startswith("."):
            token = KIND_BY_EXT.get(token, token[1:])
        kinds |= expand_kinds((token,))
    return kinds or {"pdf"}


def save_uploads(job_id: str, req=None, allowed_kinds=("pdf",),
                 field: str = "files", *,
                 allow_encrypted: bool = False) -> list[JobFile]:
    """Validate + persist this request's uploaded files into
    uploads/<job_id>/ under uuid names. `req` defaults to flask `request`.

    `allowed_kinds` accepts kinds ('pdf','png','jpg','tiff','webp','zip',
    'ole','csv','text','html','markdown' or the aliases 'office','image')
    and/or extensions ('.pdf').

    When ``allow_encrypted`` is True, password-protected PDFs are stored
    without a page-count check (used by unlock_pdf).

    Raises ToolError (friendly message) when: no file given, too many files,
    empty file, magic bytes not in allowed_kinds, PDF over MAX_PAGES, PDF
    corrupt/encrypted, or garbage display name. Size is enforced per file
    here and per whole request by MAX_CONTENT_LENGTH (-> 413 handler).
    """
    req = req if req is not None else request
    cfg = current_app.config
    files = [f for f in req.files.getlist(field) if f and f.filename]
    if not files:
        files = [f for f in req.files.values() if f and f.filename]
    if not files:
        raise ToolError("No file was uploaded. Please choose at least one "
                        "file and try again.")
    max_files = int(cfg.get("MAX_FILES", 20))
    if len(files) > max_files:
        raise ToolError(f"Too many files ({len(files)}). The limit is "
                        f"{max_files} per job.")

    kinds_allowed = _allowed_kind_set(allowed_kinds)
    max_bytes = int(cfg["MAX_FILE_MB"]) * 1024 * 1024
    saved: list[JobFile] = []
    updir = _upload_dir(job_id)
    updir.mkdir(parents=True, exist_ok=True)
    for fs in files:
        display = safe_display_name(fs.filename)
        probe = fs.stream.read(16)
        fs.stream.seek(0)
        kind = kind_from_header(probe)
        # Text-like types have no magic bytes: allow when explicitly
        # requested, the display name has a matching extension, and a
        # printable-content sniff passes.
        if kind is None:
            sample = fs.stream.read(65536)
            fs.stream.seek(0)
            name_l = display.lower()
            if "csv" in kinds_allowed and name_l.endswith(".csv") and looks_like_csv(sample):
                kind = "csv"
            elif ("html" in kinds_allowed
                  and name_l.endswith((".html", ".htm"))
                  and looks_like_plain_text(sample)):
                kind = "html"
            elif ("markdown" in kinds_allowed
                  and name_l.endswith((".md", ".markdown"))
                  and looks_like_plain_text(sample)):
                kind = "markdown"
            elif ("text" in kinds_allowed
                  and name_l.endswith((".txt", ".text"))
                  and looks_like_plain_text(sample)):
                kind = "text"
        if kind is None or kind not in kinds_allowed:
            raise ToolError(
                f"'{display}' is not a supported file type for this tool. "
                f"Allowed types: {', '.join(sorted(kinds_allowed))}.")
        internal = updir / f"{uuid.uuid4().hex}{EXT_BY_KIND.get(kind, '.bin')}"
        with open(internal, "wb") as out:
            shutil.copyfileobj(fs.stream, out, 1024 * 1024)
            size = out.tell()
        if size == 0:
            internal.unlink(missing_ok=True)
            raise ToolError(f"'{display}' is empty. Please upload a real file.")
        if size > max_bytes:
            internal.unlink(missing_ok=True)
            raise ToolError(f"'{display}' is larger than the "
                            f"{cfg['MAX_FILE_MB']:g} MB limit.")
        if kind == "pdf":
            pages = page_count(internal, allow_encrypted=allow_encrypted)
            if pages > 0 and pages > int(cfg.get("MAX_PAGES", 200)):
                internal.unlink(missing_ok=True)
                raise ToolError(f"'{display}' has {pages} pages; the limit "
                                f"is {cfg.get('MAX_PAGES', 200)} pages.")
        saved.append(JobFile(path=internal, name=display, kind=kind, size=size))

    manifest = _load_manifest(job_id)
    manifest["inputs"] = [jf.as_dict() for jf in saved]
    _save_manifest(job_id, manifest)
    return saved


def run_job(job_id: str, service_fn, options: dict | None = None, *,
            title: str | None = None) -> dict:
    """Run a PURE service function for this job and return the result-page
    context (pass it straight to render_template("result.html", **ctx)).

    service_fn(inputs: list[Path], output_dir: Path, **options) ->
        Path | list[Path]   (files it created inside output_dir)
    `options` are passed as keyword args when the service signature accepts
    them; a zero-option service may be defined as fn(inputs, output_dir).

    Raises ToolError (rendered on the friendly error page) on any failure.
    The job manifest is always marked done; the TTL sweep deletes the dirs.
    """
    options = dict(options or {})
    manifest = _load_manifest(job_id)
    inputs = [Path(r["path"]) for r in manifest.get("inputs", [])]
    if not inputs or not all(p.exists() for p in inputs):
        raise ToolError("The uploaded files are missing or expired. Please "
                        "upload again.")
    outdir = _output_dir(job_id)
    outdir.mkdir(parents=True, exist_ok=True)
    try:
        produced = _invoke_service(service_fn, inputs, outdir, options)
    except ToolError:
        raise
    except Exception:
        current_app.logger.exception("service failed for job %s", job_id)
        raise ToolError("The tool failed while processing your files. "
                        "Please check the inputs and try again.")
    finally:
        manifest = _load_manifest(job_id)
        manifest["done"] = True
        _save_manifest(job_id, manifest)

    if isinstance(produced, (str, os.PathLike)):
        produced = [produced]
    produced = [Path(p) for p in (produced or [])]
    if not produced or not all(p.is_file() for p in produced):
        raise ToolError("The tool finished but did not produce its output "
                        "files.")

    entries = _finalize_outputs(job_id, manifest, produced)
    return result_context(job_id, entries,
                          title=title or manifest.get("tool_title"))


def _invoke_service(service_fn, inputs, outdir, options):
    import inspect
    try:
        sig = inspect.signature(service_fn)
        has_var_kw = any(p.kind == inspect.Parameter.VAR_KEYWORD
                         for p in sig.parameters.values())
        extra_named = [n for n, p in sig.parameters.items()
                       if p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)
                       and n not in ("inputs", "output_dir")]
    except (TypeError, ValueError):  # builtins etc: assume simplest form
        has_var_kw, extra_named = False, []
    if options or has_var_kw or extra_named:
        return service_fn(inputs, outdir, **options)
    return service_fn(inputs, outdir)


def _finalize_outputs(job_id: str, manifest: dict,
                      produced: list[Path]) -> list[dict]:
    """Record produced files in the manifest; return display entries."""
    first_in = (manifest.get("inputs") or [{}])[0].get("name") or "output"
    stem = os.path.splitext(os.path.basename(first_in))[0] or "output"
    entries = []
    for i, p in enumerate(produced):
        if len(produced) == 1:
            # name the single output after the first INPUT's display name
            display = safe_display_name(f"{stem}{p.suffix.lower() or '.pdf'}")
        else:
            display = safe_display_name(p.name)
        entries.append({"index": i, "path": str(p), "display_name": display,
                        "size": p.stat().st_size,
                        "size_h": human_size(p.stat().st_size)})
    manifest = _load_manifest(job_id)
    manifest["outputs"] = [{"index": e["index"], "name": e["display_name"],
                            "path": e["path"], "size": e["size"]}
                           for e in entries]
    _save_manifest(job_id, manifest)
    return entries


def result_context(job_id: str, entries: list[dict],
                   title: str | None = None) -> dict:
    """Template context for result.html, built from finalized entries."""
    return {
        "job_id": job_id,
        "tool_title": title or "Done",
        "outputs": [{
            "index": e["index"],
            "display_name": e["display_name"],
            "size_h": e["size_h"],
            "url": f"/dl/{job_id}/{e['index']}",
        } for e in entries],
        "zip_url": f"/dl/{job_id}/all.zip" if len(entries) > 1 else None,
        "single": len(entries) == 1,
    }


# ---------------------------------------------------------------------------
# cleanup
# ---------------------------------------------------------------------------

def cleanup_job(job_id: str) -> bool:
    """Delete a job's upload + output dirs immediately (optional explicit
    cleanup hook; the TTL sweep is the guaranteed path). Safe to double-call."""
    if not _valid_job_id(job_id):
        return False
    removed = False
    for d in (_upload_dir(job_id), _output_dir(job_id)):
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)
            removed = True
    return removed


def _last_activity(job_dir: Path) -> float:
    """Newest mtime of the dir itself and everything under it (Windows dir
    mtimes don't advance when file contents change)."""
    newest = job_dir.stat().st_mtime
    for dirpath, _dirnames, filenames in os.walk(job_dir):
        for fn in filenames:
            try:
                newest = max(newest, os.path.getmtime(
                    os.path.join(dirpath, fn)))
            except OSError:
                continue
    return newest


def sweep_expired(roots: list[str] | None = None,
                  ttl: float | None = None) -> int:
    """Delete every job dir idle longer than `ttl` seconds; return count.
    With no args, uses the current app config when in an app context, else
    the state captured at scheduler start (the scheduler thread runs without
    one)."""
    if roots is None:
        try:
            roots = [current_app.config["UPLOAD_ROOT"],
                     current_app.config["OUTPUT_ROOT"]]
        except RuntimeError:
            with _cleanup_state_lock:
                roots = list(_cleanup_state["roots"])
    if ttl is None:
        try:
            ttl = current_app.config["JOB_TTL_SECONDS"]
        except RuntimeError:
            with _cleanup_state_lock:
                ttl = _cleanup_state["ttl"]
    removed = 0
    for root in roots:
        root = Path(root)
        if not root.is_dir():
            continue
        for child in root.iterdir():
            if not child.is_dir() or not _valid_job_id(child.name):
                continue
            try:
                if time.time() - _last_activity(child) > ttl:
                    shutil.rmtree(child, ignore_errors=True)
                    removed += 1
            except OSError:
                continue
    return removed


_scheduler = None
_scheduler_lock = threading.Lock()
_cleanup_state_lock = threading.Lock()
_cleanup_state = {"roots": [], "ttl": 3600}


def start_scheduler(app) -> None:
    """Start the singleton BackgroundScheduler cleanup job (hourly interval
    plus one sweep at boot). Idempotent across double-init in tests."""
    global _scheduler
    from apscheduler.schedulers.background import BackgroundScheduler
    with _scheduler_lock:
        with _cleanup_state_lock:
            _cleanup_state["roots"] = [app.config["UPLOAD_ROOT"],
                                       app.config["OUTPUT_ROOT"]]
            _cleanup_state["ttl"] = app.config["JOB_TTL_SECONDS"]
        if _scheduler is None:
            _scheduler = BackgroundScheduler(daemon=True)
            _scheduler.add_job(
                sweep_expired, "interval",
                seconds=int(app.config["CLEANUP_INTERVAL_SECONDS"]),
                id="pdf-tools-cleanup", replace_existing=True,
                max_instances=1, coalesce=True)
            try:
                _scheduler.start()
            except Exception:
                app.logger.exception("scheduler failed to start")
                _scheduler = None
        # one sweep at boot (covers files left by a previous crash)
        try:
            sweep_expired(list(_cleanup_state["roots"]),
                          _cleanup_state["ttl"])
        except Exception:
            app.logger.exception("boot sweep failed")


# ---------------------------------------------------------------------------
# download routes (registered by create_app; tools never touch these)
# ---------------------------------------------------------------------------

def _output_entry(job_id: str, index: int) -> dict:
    manifest = _load_manifest(job_id)
    for e in manifest.get("outputs", []):
        if e["index"] == index:
            return e
    abort(404)


@jobs_bp.get("/dl/<job_id>/<int:index>")
def download_one(job_id: str, index: int):
    """Serve one output file. Content-Disposition = sanitized original stem
    + uuid suffix; never the raw user name."""
    if not _valid_job_id(job_id):
        abort(404)
    entry = _output_entry(job_id, index)
    path = Path(entry["path"])
    if not path.is_file():
        abort(404)
    stem, ext = os.path.splitext(entry["name"])
    download_name = f"{stem[:80]}-{job_id[:8]}{ext.lower()}"
    return send_file(path, as_attachment=True, download_name=download_name,
                     conditional=True)


@jobs_bp.get("/dl/<job_id>/all.zip")
def download_all(job_id: str):
    """Multiple outputs -> one zip built on the fly (in memory) and served."""
    if not _valid_job_id(job_id):
        abort(404)
    manifest = _load_manifest(job_id)
    outs = manifest.get("outputs", [])
    paths = [Path(e["path"]) for e in outs]
    if not paths or not all(p.is_file() for p in paths):
        abort(404)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        seen: dict[str, int] = {}
        for e, p in zip(outs, paths):
            name = safe_display_name(e["name"])
            if name in seen:  # dedupe display-name collisions inside zip
                seen[name] += 1
                stem, ext = os.path.splitext(name)
                name = f"{stem}-{seen[name]}{ext}"
            else:
                seen[name] = 0
            zf.write(p, arcname=name)
    buf.seek(0)
    return send_file(buf, as_attachment=True, mimetype="application/zip",
                     download_name=f"pdf-tools-{job_id[:8]}.zip")
