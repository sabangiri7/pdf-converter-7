# TOOL BUILDER CONTRACT — read first

This file is the **only** thing you need to build one PDF tool. The
foundation (job framework, discovery, templates, helpers, error handling) is
already built and **you must not edit shared files**.

## Hard rule: your file set

Building tool `<slug>` (one of: `merge`, `split`, `compress`, `rotate`,
`pdf_to_images`, `images_to_pdf`, `watermark`, `office_to_pdf`, `ocr_pdf`)
means you create **exactly these files** and nothing else:

```
app/services/<slug>.py      the pure PDF logic (no Flask)
app/tools/<slug>.py         thin Flask blueprint (module-level name: bp)
app/templates/tools/<slug>.html   the tool page (uses the shared form macro)
tests/test_<slug>.py        service tests (+ at least one route test)
```

`app/tools/<slug>.json` (the manifest) **already exists — do not touch it**
(and do not touch any other file listed under "builder-owned" below).

## How discovery works

`app/registry.py::discover()` scans `app/tools/*.json` at startup. For each
manifest with a sibling `<slug>.py` it imports the module and registers its
`bp` Blueprint at **`/t/<slug>`**. A module that fails to import is logged
and skipped — the app keeps serving, the card shows "coming soon". So your
blueprint variable MUST be named `bp` and MUST be module-level.

Route convention:

```
GET  /t/<slug>      -> render the tool page (upload form)
POST /t/<slug>      -> run the job, render result page
```

(Define them as `@bp.get("/")` / `@bp.post("/")`; the prefix comes from
registration.) Downloads `/dl/<job_id>/<n>` and `/dl/<job_id>/all.zip` are
**already provided by the foundation** — never write your own.

## Job framework API (`app/jobs.py`)

```python
job_id = create_job()                                # -> uuid4-hex str
files  = save_uploads(job_id, allowed_kinds=("pdf",))  # -> list[JobFile]
ctx    = run_job(job_id, my_service, options_dict, title="Merge PDF")
return render_template("result.html", **ctx)         # done
```

- `create_job() -> str` — makes `instance/uploads/<job_id>/` +
  `instance/outputs/<job_id>/` and a manifest. No args.
- `save_uploads(job_id, req=None, allowed_kinds=("pdf",), field="files")
  -> list[JobFile]` — reads `request.files[field]` (falls back to any file
  field), sniffs **magic bytes** (never the extension), enforces 50 MB/file
  (`ToolError`), 20 files, 200 pages for PDFs, rejects weird display names.
  Each returned `JobFile` has `.path` (internal **uuid-named** `Path` —
  always use this for processing), `.name` (sanitized original, display
  only), `.kind` (`'pdf'|'png'|'jpg'|'tiff'|'webp'|'zip'|'ole'`), `.size`.
  `allowed_kinds` accepts kinds or extensions: `("pdf",)`, `("image",)`,
  `("office",)`, `(".png", ".jpg")`. `office` = zip (docx/xlsx/pptx) or OLE
  (doc/xls/ppt). 413 (request body over total limit) is handled globally.
- `run_job(job_id, service_fn, options: dict, *, title: str) -> dict` —
  calls the service, records outputs, returns the `result.html` context.
  Wraps any unexpected service exception in a friendly `ToolError`.
- `cleanup_job(job_id) -> bool` — optional immediate delete; the hourly
  APScheduler TTL sweep (1 h) is the guaranteed path, so you don't have to
  call it. The manifest is always marked done by `run_job`.
- `ToolError` (`app/errors.py`) — raise with a **user-safe** message; the
  handler renders `templates/error.html` with HTTP 400. Import:
  `from app.errors import ToolError`.

## Service function contract (`app/services/<slug>.py`)

PURE: no Flask, no `request`, no blueprint, no printing. Signature — exactly:

```python
def run(inputs: list[Path], output_dir: Path, **options) -> Path | list[Path]:
    """inputs: saved upload paths (in order). output_dir: write ONLY here.
    Return the output Path(s) you created. Raise ToolError for user errors."""
```

`run_job` introspects the signature: if your service takes no extra keyword
args you may write `def run(inputs, output_dir)`. Return `Path` for one
output (auto-named after the input's display name on download), or
`list[Path]` for many (result page then offers a zip). Multiple outputs →
give them distinct names like `page-1.png`.

Purity test: your service must work in a plain `pytest` run with temp dirs,
zero Flask imports.

## Helpers (`app/helpers.py`)

```python
detect_kind(path) -> 'pdf'|'png'|'jpg'|'tiff'|'webp'|'zip'|'ole'|None
page_count(path) -> int                    # ToolError if corrupt/encrypted
binary_missing(name) -> bool               # e.g. binary_missing("soffice")
require_binary(name, friendly=None) -> str # path, or friendly ToolError
safe_display_name(name) -> str             # sanitized for download header
human_size(n_bytes) -> "1.5 MB"
```

For tools needing external binaries (`office_to_pdf` → `soffice`;
`ocr_pdf` → `tesseract`/`ocrmypdf`): call `require_binary(...)` at the start
of the service so a missing binary becomes a friendly 400 page, never a 500.
Tests MUST cover the missing-binary path:

```python
def test_missing_binary(monkeypatch):
    monkeypatch.setattr("app.helpers.shutil.which", lambda name: None)
    with pytest.raises(ToolError):
        run([sample_pdf_3p], tmp_path)
```

(PDF→images uses PyMuPDF — no binary needed. Do not use pdf2image.)

## Tool page template (exact pattern)

`app/templates/tools/<slug>.html` — all tool pages must look identical:

```jinja
{% extends "base.html" %}
{% from "_form.html" import upload_form %}
{% block title %}{{ tool.title }} — PDF Tools{% endblock %}
{% block content %}
<section class="tool-page">
  <h1>{{ tool.title }}</h1>
  <p class="tool-lede">{{ tool.description }}</p>
  {% call upload_form(action='/t/<slug>', accept=tool.accept,
                      multiple=tool.multiple, submit_label='Merge PDF') %}
    {# your options, plain HTML inputs with real names, e.g.: #}
    <label>Angle
      <select name="angle"><option value="90">90°</option></select>
    </label>
  {% endcall %}
</section>
{% endblock %}
```

`upload_form` already provides: `<input type="file" name="files">` inside a
`.dropzone` (drag-drop + file list wired by `app/static/js/upload.js`),
spinner-on-submit, and the limits note. Options are read in the POST route
via `request.form.get("angle")` etc. — validate/sanitize there, then pass to
`run_job` in the options dict.

The route passes the manifest to the template. Canonical GET:

```python
@bp.get("/")
def page():
    return render_template("tools/<slug>.html", tool=TOOL)  # see below
```

## Manifest fields (`app/tools/<slug>.json`, already created)

```json
{"slug": "merge", "title": "Merge PDF", "description": "...",
 "icon": "🗂", "accept": ".pdf", "multiple": true}
```

`accept`/`multiple` drive the file input; `title`/`description`/`icon` the
landing card. Discovery only routes slugs whose `.py` exists. If a manifest
is missing, discovery warns and the page 404s (log line explains).

## Blueprint skeleton (copy, rename, fill options)

```python
# app/tools/<slug>.py
import json
from pathlib import Path
from flask import Blueprint, render_template, request
from app.jobs import create_job, save_uploads, run_job
from app.services.<slug> import run

TOOL = json.loads(Path(__file__).with_suffix(".json").read_text("utf-8"))
bp = Blueprint("<slug>", __name__)

@bp.get("/")
def page():
    return render_template(f"tools/<slug>.html", tool=TOOL)

@bp.post("/")
def process():
    job_id = create_job()
    save_uploads(job_id, allowed_kinds=("pdf",))      # per-tool kinds
    options = {"angle": request.form.get("angle", "90")}
    ctx = run_job(job_id, run, options, title=TOOL["title"])
    return render_template("result.html", **ctx)
```

## Tests

`tests/conftest.py` gives you (session-scoped, absolute `pathlib.Path`s;
samples live in `samples/`, regenerate with
`python scripts/generate_samples.py`):

- `sample_pdf_3p` → `samples/sample_3p.pdf` (3 pages, "Page i of 3")
- `sample_pdf_2p` → `samples/sample_2p.pdf` (2 pages)
- `sample_images` → list of the 3 jpg + 3 png (800×600 solid) samples
- `sample_image_jpg`, `sample_image_png` → first of each
- `app`, `client` → testing-config Flask app (scheduler off, job dirs in a
  per-test tmp dir)

Route test pattern (uploads use the file field name `files`):

```python
def test_rotate_roundtrip(client):
    r = client.post("/t/rotate",
                    data={"files": [(open(sample_pdf_2p, "rb"), "x.pdf")],
                          "angle": "90"},
                    content_type="multipart/form-data")
    assert r.status_code == 200
    assert b"/dl/" in r.data
```

## File storage (documented decision)

Job files live under the **instance folder**:
`instance/uploads/<job_id>/` and `instance/outputs/<job_id>/` (gitignored,
created at first startup). Internal file names are uuid-based; original
user names are kept only in the job manifest for display/download.
Cleanup: APScheduler `BackgroundScheduler` sweeps idle job dirs older than
1 h, hourly (plus one sweep at boot); `SCHEDULER_ENABLED=False` in tests.

## Environment limits (dev box = Windows, no binaries)

LibreOffice / Tesseract / poppler / ghostscript are NOT installed on the dev
machine. Your tests must pass here: cover missing-binary handling via
monkeypatching `shutil.which` (see above), and skip actual conversion
results with `pytest.skipif(app.helpers.binary_missing("soffice"), ...)`.

## Builder-owned-files list template (put in your PR/task notes)

```
app/services/<slug>.py
app/tools/<slug>.py
app/templates/tools/<slug>.html
tests/test_<slug>.py
```

Anything else you touched is a contract violation.
