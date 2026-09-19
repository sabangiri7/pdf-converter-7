# System (non-Python) dependencies

The app is pure-Python **except** for a few tools that shell out to external
binaries. Everything else (pypdf, pikepdf, PyMuPDF, img2pdf, reportlab,
Pillow) ships as wheels — no system packages needed.

| Binary | Needed by | Notes |
|---|---|---|
| **LibreOffice** (`soffice`) | Office → PDF (`office_to_pdf`) | headless conversion of .doc/.docx/.xls/.xlsx/.ppt/.pptx |
| **Tesseract** (`tesseract`) | OCR PDF (`ocr_pdf`) | `ocrmypdf` drives it; needs `tesseract` on PATH |
| **Ghostscript** (`gs`) | OCR PDF (sometimes) | used by ocrmypdf for PDF re-writing |
| **poppler** (`pdftoppm`) | *not required* | PDF → images uses **PyMuPDF** instead; pdf2image has been removed from requirements.txt |
| **qpdf** | *not required* | pikepdf vendors its own copy |

All tools must **detect missing binaries and show a friendly error**, never a
500 page. Use `app.helpers.binary_missing("soffice")` / `require_binary(...)`
which raise `ToolError`. Their tests must cover the missing-binary path
(monkeypatch `shutil.which`).

## Ubuntu / Debian

```bash
# soffice headless; tesseract OCR engine (+ language packs); gs backend
sudo apt-get install -y libreoffice tesseract-ocr tesseract-ocr-eng ghostscript
```

## macOS (Homebrew)

```bash
brew install --cask libreoffice
brew install tesseract tesseract-lang ghostscript
# not required here but if you want pdf2image: brew install poppler
```

Verify:

```bash
soffice --version
tesseract --version
gs --version
```

## Windows (dev box)

Neither LibreOffice, Tesseract nor Ghostscript are preinstalled here, so
`office_to_pdf` and `ocr_pdf` will show their friendly "not installed" error
until you:

- LibreOffice: download and install from <https://www.libreoffice.org>, then
  add the program directory (e.g. `C:\Program Files\LibreOffice\program`) to
  `PATH` so `soffice.exe` resolves.
- Tesseract: install the UB-Mannheim build
  (<https://github.com/UB-Mannheim/tesseract/wiki>) and add it to `PATH`.
- Ghostscript: install from <https://ghostscript.com/releases/gsdnld.html>
  and add `gswin64c` to `PATH`.

After installing, restart the Flask process so it inherits the new `PATH`.

## Docker

The project `Dockerfile` already installs LibreOffice, Tesseract (eng), and
Ghostscript. Prefer `docker compose up --build` for a full stack without
host installs. See the main [README.md](README.md#docker).
