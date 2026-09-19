"""Convert PDF pages to a simple HTML document."""
from html import escape
from pathlib import Path

import pdfplumber

from app.errors import ToolError
from app.helpers import detect_kind

_BAD = ("That file doesn't look like a valid PDF, or it is corrupted. "
        "Please try a different file.")


def run(inputs: list[Path], output_dir: Path, **_options) -> Path:
    if len(inputs) != 1:
        raise ToolError("PDF to HTML works on one PDF at a time.")
    src = Path(inputs[0])
    if detect_kind(src) != "pdf":
        raise ToolError("Please upload a PDF file.")
    sections: list[str] = []
    try:
        with pdfplumber.open(str(src)) as pdf:
            for i, page in enumerate(pdf.pages, 1):
                text = (page.extract_text() or "").strip()
                if text:
                    body = ("<p>" + "</p><p>".join(
                        escape(ln) for ln in text.splitlines() if ln.strip())
                        + "</p>")
                else:
                    body = "<p><em>[no selectable text]</em></p>"
                sections.append(
                    f'<section class="page" id="page-{i}">'
                    f"<h2>Page {i}</h2>{body}</section>")
    except ToolError:
        raise
    except Exception:
        raise ToolError(_BAD)
    html = (
        "<!DOCTYPE html><html><head><meta charset=\"utf-8\">"
        "<title>PDF export</title>"
        "<style>body{font-family:system-ui,sans-serif;max-width:48rem;"
        "margin:2rem auto;padding:0 1rem;line-height:1.5}"
        "section{margin-bottom:2.5rem;border-bottom:1px solid #ddd;"
        "padding-bottom:1.5rem}</style></head><body>\n"
        + "\n".join(sections) + "\n</body></html>\n"
    )
    out = Path(output_dir) / "export.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out
