# PDF Tools

Local Flask app for PDF and file conversion: merge, split, compress, convert, OCR, and more. Upload in the browser, download the result. Jobs expire after one hour.

## Quick start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run.py
```

Open http://127.0.0.1:5000

## Optional system tools

Needed only for some features (friendly error if missing):

| Binary | Used by |
|---|---|
| LibreOffice (`soffice`) | Office → PDF |
| Tesseract | OCR PDF |
| Ghostscript | OCR (sometimes) |

Details: [SYSTEM_DEPENDENCIES.md](SYSTEM_DEPENDENCIES.md)

## Config

| Variable | Default | Meaning |
|---|---|---|
| `PDF_TOOLS_HOST` | `127.0.0.1` | Bind address |
| `PDF_TOOLS_PORT` | `5000` | Port |
| `PDF_TOOLS_DEBUG` | `1` | Debug (`1`/`0`) |
| `PDF_TOOLS_SECRET_KEY` | (dev) | Change for any shared deploy |
| `PDF_TOOLS_MAX_FILE_MB` | `50` | Max size per file |

## Tests

```powershell
python scripts/generate_samples.py
pytest
```

## Layout

```
app/           # Flask app, tools, services, templates
run.py         # Entry point
samples/       # Test fixtures
tests/
```

Tool builder notes: [CONTRACT.md](CONTRACT.md)
