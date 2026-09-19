"""Compare two PDFs: page counts + per-page text diff report."""
from pathlib import Path

import pdfplumber
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from app.errors import ToolError
from app.helpers import detect_kind

_BAD = ("One of the files doesn't look like a valid PDF, or it is "
        "corrupted. Please try different files.")


def _page_texts(path: Path) -> list[str]:
    texts: list[str] = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            texts.append((page.extract_text() or "").strip())
    return texts


def run(inputs: list[Path], output_dir: Path, **_options) -> Path:
    inputs = [Path(p) for p in (inputs or [])]
    if len(inputs) != 2:
        raise ToolError("PDF Compare needs exactly two PDF files.")
    for p in inputs:
        if detect_kind(p) != "pdf":
            raise ToolError("Please upload two PDF files.")
    try:
        a_texts = _page_texts(inputs[0])
        b_texts = _page_texts(inputs[1])
    except Exception:
        raise ToolError(_BAD)
    lines: list[str] = []
    lines.append(f"File A pages: {len(a_texts)}")
    lines.append(f"File B pages: {len(b_texts)}")
    if len(a_texts) != len(b_texts):
        lines.append("Page counts differ.")
    n = max(len(a_texts), len(b_texts))
    diffs = 0
    for i in range(n):
        a = a_texts[i] if i < len(a_texts) else "[missing page]"
        b = b_texts[i] if i < len(b_texts) else "[missing page]"
        if a == b:
            lines.append(f"Page {i + 1}: identical text")
        else:
            diffs += 1
            lines.append(f"Page {i + 1}: DIFFER")
            a_show = (a[:240] + "…") if len(a) > 240 else a
            b_show = (b[:240] + "…") if len(b) > 240 else b
            lines.append(f"  A: {a_show or '[empty]'}")
            lines.append(f"  B: {b_show or '[empty]'}")
    lines.append(f"Summary: {diffs} page(s) differ.")
    out = Path(output_dir) / "compare-report.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    style = styles["BodyText"]
    doc = SimpleDocTemplate(
        str(out), pagesize=A4,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
        topMargin=0.75 * inch, bottomMargin=0.75 * inch)
    story = [Paragraph("<b>PDF Compare Report</b>", styles["Heading1"]),
             Spacer(1, 12)]
    for ln in lines:
        safe = (ln.replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;"))
        story.append(Paragraph(safe, style))
        story.append(Spacer(1, 4))
    try:
        doc.build(story)
    except Exception:
        raise ToolError("The comparison report could not be written.")
    return out
