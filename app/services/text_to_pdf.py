"""Create a simple PDF from a plain-text file (reportlab)."""
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from app.errors import ToolError
from app.helpers import detect_kind, looks_like_plain_text

MAX_CHARS = 200_000


def _decode(raw: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ToolError("That text file could not be decoded. Please save it as "
                    "UTF-8 and try again.")


def run(inputs: list[Path], output_dir: Path, **_options) -> Path:
    if len(inputs) != 1:
        raise ToolError("Create PDF from Text works on one text file.")
    src = Path(inputs[0])
    raw = src.read_bytes()
    kind = detect_kind(src)
    suffix_ok = src.suffix.lower() in (".txt", ".text")
    if kind != "text" and not (suffix_ok and looks_like_plain_text(raw[:65536])):
        raise ToolError("Please upload a plain .txt file.")
    text = _decode(raw)
    if not text.strip():
        raise ToolError("That text file is empty.")
    if len(text) > MAX_CHARS:
        raise ToolError(f"Text is too long (max {MAX_CHARS:,} characters).")
    out = Path(output_dir) / "from-text.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    style = styles["BodyText"]
    doc = SimpleDocTemplate(
        str(out), pagesize=A4,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
        topMargin=0.75 * inch, bottomMargin=0.75 * inch)
    story = []
    for para in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        safe = (para.replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;"))
        if not safe.strip():
            story.append(Spacer(1, 8))
        else:
            story.append(Paragraph(safe, style))
            story.append(Spacer(1, 4))
    try:
        doc.build(story)
    except Exception:
        raise ToolError("Could not build the PDF from that text. Please check "
                        "the file and try again.")
    return out
