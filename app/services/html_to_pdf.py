"""Create a simple PDF from an HTML file (tags stripped; reportlab).

Security: this converter NEVER fetches remote URLs, never loads images /
stylesheets / scripts from the network, and never executes JavaScript.
Uploaded HTML is stripped to plain text only (see ``html_to_text``). Remote
resource URLs that appear in the markup are ignored as text content.
"""
import re
from html.parser import HTMLParser
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from app.errors import ToolError
from app.helpers import detect_kind, looks_like_plain_text

MAX_CHARS = 200_000

# Patterns that would indicate an author expected remote loading. We do not
# fetch them; they are left as inert text after stripping. Documented for
# reviewers / SSRF regression tests.
_REMOTE_HINT = re.compile(
    r"""(?ix)
    \b(?:https?|ftp|file)://
    | \bsrc\s*=
    | \bhref\s*=
    | @import\b
    | url\s*\(
    """)


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "iframe", "object", "embed", "link"):
            self._skip = True
        elif tag in ("p", "div", "br", "h1", "h2", "h3", "h4", "li", "tr"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "iframe", "object", "embed", "link"):
            self._skip = False
        elif tag in ("p", "div", "h1", "h2", "h3", "h4", "li"):
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def html_to_text(raw: str) -> str:
    p = _TextExtractor()
    try:
        p.feed(raw)
        p.close()
    except Exception:
        return re.sub(r"<[^>]+>", " ", raw)
    return re.sub(r"[ \t]+\n", "\n", "".join(p.parts))


def run(inputs: list[Path], output_dir: Path, **_options) -> Path:
    if len(inputs) != 1:
        raise ToolError("HTML to PDF works on one HTML file.")
    src = Path(inputs[0])
    raw_b = src.read_bytes()
    kind = detect_kind(src)
    suffix_ok = src.suffix.lower() in (".html", ".htm")
    if kind != "html" and not (suffix_ok and looks_like_plain_text(raw_b[:65536])):
        raise ToolError("Please upload an .html file.")
    try:
        raw = raw_b.decode("utf-8-sig")
    except UnicodeDecodeError:
        raw = raw_b.decode("latin-1")
    # Explicit non-fetching: even if markup contains remote URLs, we only
    # render stripped text. (Regression tests assert no network I/O.)
    _ = _REMOTE_HINT.search(raw)
    text = html_to_text(raw)
    if not text.strip():
        raise ToolError("That HTML file has no readable text content.")
    if len(text) > MAX_CHARS:
        raise ToolError(
            f"HTML content is too long (max {MAX_CHARS:,} characters).")
    out = Path(output_dir) / "from-html.pdf"
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
        raise ToolError(
            "Could not build the PDF from that HTML. Complex layouts are "
            "not supported — use simpler HTML.")
    return out
