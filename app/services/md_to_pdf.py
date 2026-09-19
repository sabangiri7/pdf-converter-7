"""Convert a Markdown file to a simple PDF."""
from pathlib import Path

import markdown as md_lib
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from app.errors import ToolError
from app.helpers import detect_kind, looks_like_plain_text
from app.services.html_to_pdf import html_to_text

MAX_CHARS = 200_000


def run(inputs: list[Path], output_dir: Path, **_options) -> Path:
    if len(inputs) != 1:
        raise ToolError("Markdown to PDF works on one Markdown file.")
    src = Path(inputs[0])
    raw_b = src.read_bytes()
    kind = detect_kind(src)
    suffix_ok = src.suffix.lower() in (".md", ".markdown")
    if kind not in ("markdown", "text") and not (
            suffix_ok and looks_like_plain_text(raw_b[:65536])):
        raise ToolError("Please upload a .md Markdown file.")
    try:
        raw = raw_b.decode("utf-8-sig")
    except UnicodeDecodeError:
        raw = raw_b.decode("latin-1")
    if not raw.strip():
        raise ToolError("That Markdown file is empty.")
    if len(raw) > MAX_CHARS:
        raise ToolError(f"Markdown is too long (max {MAX_CHARS:,} characters).")
    try:
        html = md_lib.markdown(raw, extensions=["extra", "sane_lists"])
    except Exception:
        html = md_lib.markdown(raw)
    text = html_to_text(html)
    out = Path(output_dir) / "from-markdown.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    style = styles["BodyText"]
    doc = SimpleDocTemplate(
        str(out), pagesize=A4,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
        topMargin=0.75 * inch, bottomMargin=0.75 * inch)
    story = []
    for para in text.replace("\r\n", "\n").split("\n"):
        safe = (para.replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;"))
        if not safe.strip():
            story.append(Spacer(1, 6))
        else:
            story.append(Paragraph(safe, style))
            story.append(Spacer(1, 4))
    try:
        doc.build(story)
    except Exception:
        raise ToolError("Could not build the PDF from that Markdown.")
    return out
