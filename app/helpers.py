"""Shared, framework-level helpers. No Flask imports needed here (safe for
pure service code to import if it wants)."""
import os
import re
import shutil
import unicodedata
from pathlib import Path

from .errors import ToolError

# ---------------------------------------------------------------------------
# Magic-byte detection
# ---------------------------------------------------------------------------

# kind -> canonical internal extension
EXT_BY_KIND = {
    "pdf": ".pdf",
    "png": ".png",
    "jpg": ".jpg",
    "tiff": ".tif",
    "webp": ".webp",
    "zip": ".zip",   # docx/xlsx/pptx (and plain zips)
    "ole": ".doc",   # legacy doc/xls/ppt (and other OLE compound files)
    "csv": ".csv",   # text; sniffed, not magic-byte based
    "text": ".txt",
    "html": ".html",
    "markdown": ".md",
}

# Aliases tools may pass to save_uploads(allowed_kinds=...)
KIND_ALIASES = {
    "office": {"zip", "ole"},
    "image": {"png", "jpg", "tiff", "webp"},
}

_PNG = b"\x89PNG\r\n\x1a\n"
_JPEG = b"\xff\xd8\xff"
_TIFF_LE = b"II\x2a\x00"
_TIFF_BE = b"MM\x00\x2a"
_OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_RIFF = b"RIFF"
_WEBP = b"WEBP"
_ZIP = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")


def kind_from_header(header: bytes) -> str | None:
    """Classify the first ~16 bytes of a file. Returns a kind string or None."""
    if header.startswith(b"%PDF"):
        return "pdf"
    if header.startswith(_PNG):
        return "png"
    if header.startswith(_JPEG):
        return "jpg"
    if header.startswith(_TIFF_LE) or header.startswith(_TIFF_BE):
        return "tiff"
    if header.startswith(_OLE):
        return "ole"
    if len(header) >= 12 and header[:4] == _RIFF and header[8:12] == _WEBP:
        return "webp"
    if header.startswith(_ZIP):
        return "zip"
    return None


def looks_like_plain_text(data: bytes) -> bool:
    """True if `data` looks like printable UTF-8/latin-1 text (no NUL)."""
    if not data or b"\x00" in data:
        return False
    if kind_from_header(data[:16]) is not None:
        return False
    ctrl = sum(1 for b in data if b < 0x20 and b not in (0x09, 0x0A, 0x0D))
    if ctrl > max(2, len(data) // 100):
        return False
    try:
        data.decode("utf-8-sig")
        return True
    except UnicodeDecodeError:
        try:
            data.decode("latin-1")
            return True
        except UnicodeDecodeError:
            return False


def looks_like_csv(data: bytes) -> bool:
    """True if `data` is a plausible UTF-8 CSV sample (no magic type).

    Allowlist: printable text, no NUL bytes, at least one comma (or
    semicolon/tab) delimiter on the first non-empty line, and either a
    newline or a short single-line row. Rejects known binary headers.
    """
    if not looks_like_plain_text(data):
        return False
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = data.decode("latin-1")
        except UnicodeDecodeError:
            return False
    # Strip BOM leftovers / normalize newlines for line scan.
    lines = [ln for ln in text.replace("\r\n", "\n").replace("\r", "\n")
             .split("\n") if ln.strip()]
    if not lines:
        return False
    first = lines[0]
    delim = "," if "," in first else (";" if ";" in first else
                                      ("\t" if "\t" in first else None))
    if delim is None:
        return False
    # Single-line CSV must still look like a row (2+ fields).
    if len(lines) == 1 and first.count(delim) < 1:
        return False
    return True


def detect_kind(path: str | os.PathLike) -> str | None:
    """Sniff a file -> 'pdf'|'png'|'jpg'|'tiff'|'webp'|'zip'|'ole'|'csv'|
    'text'|'html'|'markdown'|None. Binary types use magic bytes; text
    kinds use extension + printable-content sniff."""
    try:
        path = Path(path)
        with open(path, "rb") as fh:
            header = fh.read(16)
            kind = kind_from_header(header)
            if kind is not None:
                return kind
            fh.seek(0)
            sample = fh.read(65536)
            if looks_like_csv(sample):
                return "csv"
            name = path.name.lower()
            if not looks_like_plain_text(sample):
                return None
            if name.endswith((".html", ".htm")):
                return "html"
            if name.endswith((".md", ".markdown")):
                return "markdown"
            if name.endswith((".txt", ".text")):
                return "text"
            return None
    except OSError:
        return None


# ---------------------------------------------------------------------------
# Sizes / names / pages
# ---------------------------------------------------------------------------

def human_size(num_bytes: float) -> str:
    """1536 -> '1.5 KB'."""
    if num_bytes is None:
        return "?"
    n = float(num_bytes)
    if n < 1024:
        return f"{int(n)} B"
    for unit in ("KB", "MB", "GB", "TB"):
        n /= 1024.0
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}".replace(".0 ", " ")
    return f"{n:.1f} TB"


_BAD_NAME_CHARS = re.compile(r"[\x00-\x1f\x7f<>:\"/\\|?*]")


def safe_display_name(name: str | None) -> str:
    """Sanitize a user-supplied filename for DISPLAY/DOWNLOAD only.
    Never used as an internal path. Raises ToolError on total garbage.

    Truncation keeps a short extension (e.g. ``.pdf``) so a long Office
    title does not chop the type suffix off the download name.
    """
    if not name:
        raise ToolError("Uploaded file is missing a filename.")
    name = unicodedata.normalize("NFKC", str(name))
    name = os.path.basename(name.replace("\\", "/"))
    name = _BAD_NAME_CHARS.sub("", name).strip(" .")
    if not name:
        raise ToolError("That filename is not allowed. Please rename the file.")
    stem, ext = os.path.splitext(name)
    # Only treat a short, dotted suffix as an extension worth preserving.
    if not (ext and 1 < len(ext) <= 10 and ext.startswith(".")
            and ext[1:].isalnum()):
        stem, ext = name, ""
    max_stem = 120 - len(ext)
    if max_stem < 1:
        return name[:120]
    stem = stem[:max_stem].rstrip(" .") or "file"
    return stem + ext


def expand_kinds(allowed_kinds) -> set[str]:
    """('pdf',) -> {'pdf'};  ('office',) -> {'zip','ole'}."""
    out: set[str] = set()
    for k in allowed_kinds or ("pdf",):
        out |= KIND_ALIASES.get(k, {k})
    return out


def page_count(path: str | os.PathLike, *, allow_encrypted: bool = False) -> int:
    """Number of pages in a PDF. Raises ToolError for corrupt / encrypted /
    unreadable files. When ``allow_encrypted`` is True, encrypted PDFs are
    accepted and return 0 pages (caller decrypts later) instead of erroring.
    """
    try:
        from pypdf import PdfReader
    except ImportError:  # pragma: no cover
        raise ToolError("PDF processing library is not available on this server.")
    try:
        reader = PdfReader(os.fspath(path), strict=False)
        if getattr(reader, "is_encrypted", False):
            if allow_encrypted:
                return 0
            raise ToolError("That PDF is password-protected. Please remove the "
                            "password and try again.")
        return len(reader.pages)
    except ToolError:
        raise
    except Exception:
        raise ToolError("That file doesn't look like a valid PDF, or it is "
                        "corrupted. Please try a different file.")


# ---------------------------------------------------------------------------
# External binaries
# ---------------------------------------------------------------------------

def binary_path(name: str) -> str | None:
    """Absolute path of a system binary (soffice, tesseract, ...) or None."""
    return shutil.which(name)


def binary_missing(name: str) -> bool:
    """True if the system binary is NOT on PATH."""
    return shutil.which(name) is None


def require_binary(name: str, friendly: str | None = None) -> str:
    """Return the binary path or raise a user-safe ToolError."""
    p = shutil.which(name)
    if not p:
        raise ToolError(friendly or (
            f"The {name} program is not installed on this server, so this "
            f"feature cannot run right now. See SYSTEM_DEPENDENCIES.md for "
            f"install instructions."))
    return p
