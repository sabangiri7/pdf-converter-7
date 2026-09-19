# PDF Tools

Local Flask web app for PDF and file conversion: merge, split, compress, rotate, convert (images / Office / CSV / Markdown / HTML), OCR, protect/unlock, organize pages, redact, N-up, booklet, and more.

Upload in the browser → pick options → download. Job files are deleted automatically after about one hour.

**Repo:** [github.com/sabangiri7/pdf-converter-7](https://github.com/sabangiri7/pdf-converter-7)

---

## Features (overview)

| Area | Examples |
|---|---|
| Organize | Merge, split, organize (live page preview), reverse, blank/duplicate pages, rotate, N-up, booklet, crop |
| Edit | Watermark, page numbers, header/footer, redact, sign (visual), fill forms, flatten, remove annotations |
| Secure / info | Protect, unlock, metadata editor, remove metadata, compare, repair |
| Convert from PDF | Images, PPTX, DOCX, Excel, text, HTML, SVG, extract images, OCR |
| Create / convert to PDF | Images→PDF, Office→PDF, text/HTML/Markdown→PDF, compress, grayscale, color convert, deskew |
| Other | Image format convert, CSV↔Excel |

The home page shows **essential tools as cards**; everything else is under **More tools**.

Health check: `GET /healthz`

---

## Requirements

- **Python 3.12+** (3.14 works on Windows; Docker image uses 3.12)
- **pip** + a virtualenv
- Optional system binaries (only for some tools — app shows a friendly error if missing):

| Binary | Used by |
|---|---|
| LibreOffice (`soffice`) | Office → PDF |
| Tesseract | OCR PDF |
| Ghostscript (`gs` / `gswin64c`) | OCR (sometimes) |

Full OS notes: [SYSTEM_DEPENDENCIES.md](SYSTEM_DEPENDENCIES.md)

---

## Quick start (any OS)

```bash
git clone https://github.com/sabangiri7/pdf-converter-7.git
cd pdf-converter-7
```

Then follow your platform below, or jump to [Docker](#docker).

---

## Windows

### 1. Install Python

Install Python 3.12+ from [python.org](https://www.python.org/downloads/) and check **“Add python.exe to PATH”**.

```powershell
python --version
```

### 2. Create venv and install deps

```powershell
cd D:\path\to\pdf-converter-7
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If PowerShell blocks activation:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### 3. (Optional) LibreOffice / Tesseract / Ghostscript

Install and add to **User PATH**, then open a **new** terminal:

| Tool | Install |
|---|---|
| LibreOffice | [libreoffice.org](https://www.libreoffice.org) → add `C:\Program Files\LibreOffice\program` to PATH |
| Tesseract | [UB-Mannheim build](https://github.com/UB-Mannheim/tesseract/wiki) |
| Ghostscript | [ghostscript.com](https://ghostscript.com/releases/gsdnld.html) → add `...\gs\gsX.XX\bin` (`gswin64c`) to PATH |

Verify:

```powershell
soffice --version
tesseract --version
gswin64c --version
```

### 4. Run

```powershell
python run.py
```

Open **http://127.0.0.1:5000**

Stop with `Ctrl+C`.

### 5. Tests (optional)

```powershell
python scripts/generate_samples.py
pytest
```

---

## Linux (Ubuntu / Debian)

### 1. System packages

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip \
  libreoffice tesseract-ocr tesseract-ocr-eng ghostscript
```

### 2. App setup

```bash
cd /path/to/pdf-converter-7
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Run (dev)

```bash
python run.py
# or: flask --app run:app run --debug --host 127.0.0.1 --port 5000
```

### 4. Run (production-style with gunicorn)

```bash
pip install gunicorn
export PDF_TOOLS_SECRET_KEY="$(openssl rand -hex 32)"
export PDF_TOOLS_DEBUG=0
export PDF_TOOLS_HOST=0.0.0.0
gunicorn -b 0.0.0.0:5000 -w 2 --timeout 300 "run:app"
```

---

## macOS

### 1. Homebrew + Python

```bash
brew install python@3.12
# Optional tools:
brew install --cask libreoffice
brew install tesseract tesseract-lang ghostscript
```

### 2. App setup

```bash
cd /path/to/pdf-converter-7
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
python run.py
```

Open **http://127.0.0.1:5000**

---

## Docker

Includes LibreOffice, Tesseract (English), and Ghostscript. No host Python install required.

### Build & run (Docker only)

```bash
docker build -t pdf-tools .
docker run --rm -p 5000:5000 \
  -e PDF_TOOLS_SECRET_KEY="$(openssl rand -hex 32)" \
  pdf-tools
```

Windows PowerShell (secret):

```powershell
docker build -t pdf-tools .
docker run --rm -p 5000:5000 `
  -e PDF_TOOLS_SECRET_KEY="change-me-to-a-long-random-string" `
  pdf-tools
```

Open **http://127.0.0.1:5000**

### Docker Compose (recommended)

```bash
cp .env.example .env
# edit PDF_TOOLS_SECRET_KEY in .env

docker compose up --build
```

- App: http://127.0.0.1:5000  
- Job data persisted in the `pdf_tools_data` volume under `/app/instance`

Stop:

```bash
docker compose down
```

### Docker notes

- First build can take several minutes (LibreOffice is large).
- OCR / Office conversion can take longer than a normal HTTP request; the image uses gunicorn `--timeout 300`.
- Put Cloudflare (or another reverse proxy) in front of the container/VPS if you need a public domain — this is a full server app, not a Cloudflare Worker.

---

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `PDF_TOOLS_HOST` | `127.0.0.1` (Docker: `0.0.0.0`) | Bind address |
| `PDF_TOOLS_PORT` | `5000` | Port |
| `PDF_TOOLS_DEBUG` | `1` locally / `0` in Docker | Flask debug |
| `PDF_TOOLS_CONFIG` | `development` / `default` in Docker | Config profile |
| `PDF_TOOLS_SECRET_KEY` | weak dev default | **Change for any shared/public deploy** |
| `PDF_TOOLS_MAX_FILE_MB` | `50` | Max size per uploaded file |
| `PDF_TOOLS_MAX_FILES` | `20` | Max files per request |
| `PDF_TOOLS_MAX_PAGES` | `200` | Max PDF pages |
| `PDF_TOOLS_JOB_TTL_SECONDS` | `3600` | How long uploads/outputs are kept |

Example (Linux/macOS):

```bash
export PDF_TOOLS_PORT=8080
export PDF_TOOLS_SECRET_KEY="your-long-secret"
python run.py
```

Windows PowerShell:

```powershell
$env:PDF_TOOLS_PORT = "8080"
$env:PDF_TOOLS_SECRET_KEY = "your-long-secret"
python run.py
```

See also `.env.example` for Compose.

---

## Project layout

```
app/
  tools/          # Blueprints + manifests → /t/<slug>
  services/       # Pure conversion logic (no Flask)
  templates/      # UI
  static/         # CSS / JS
  jobs.py         # Upload, download, TTL cleanup
  catalog.py      # Home page essentials / categories
run.py            # Entry point
Dockerfile
docker-compose.yml
samples/          # Test fixtures
scripts/          # generate_samples.py
tests/
instance/         # Runtime uploads/outputs (gitignored)
```

Adding a tool: [CONTRACT.md](CONTRACT.md)

---

## Troubleshooting

| Symptom | What to try |
|---|---|
| “LibreOffice / Tesseract not installed” | Install binary, fix PATH, **restart** the app |
| Port already in use | `PDF_TOOLS_PORT=8080` or stop the other process |
| Docker build fails on wheels | Ensure Docker can reach PyPI; image targets Python 3.12 |
| OCR / Office times out | Increase gunicorn `--timeout`; use smaller files |
| Blank home page after update | Hard refresh; ensure Flask reloaded / container restarted |
| Push / clone auth errors | Use HTTPS + GitHub login or SSH keys |

---

## License / use

Intended for local or self-hosted use. Do not expose publicly without a strong `PDF_TOOLS_SECRET_KEY`, HTTPS, and appropriate upload limits.
