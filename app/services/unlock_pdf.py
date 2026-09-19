"""Remove password protection from a PDF (pypdf). Pure service: no Flask."""
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from ..errors import ToolError
from ..helpers import detect_kind

_MAX_PASSWORD_LEN = 128
_MAX_PAGES = 200


def run(inputs: list[Path], output_dir: Path, password: str = "",
        **_options) -> Path:
    """Decrypt one PDF with the given password and write an unlocked copy."""
    inputs = [Path(p) for p in (inputs or [])]
    if len(inputs) != 1:
        raise ToolError("Unlock works on one PDF at a time. Please upload "
                        "a single PDF.")
    src = inputs[0]
    if not src.is_file():
        raise ToolError("Your uploaded file is missing or expired. Please "
                        "upload it again.")
    if detect_kind(src) != "pdf":
        raise ToolError("That file doesn't look like a valid PDF.")

    pwd = str(password or "")
    if not pwd:
        raise ToolError("Enter the PDF password to unlock it.")
    if len(pwd) > _MAX_PASSWORD_LEN:
        raise ToolError(f"Password is too long (max {_MAX_PASSWORD_LEN} "
                        "characters).")
    if any(ord(c) < 32 for c in pwd):
        raise ToolError("Password must not contain control characters.")

    try:
        reader = PdfReader(str(src), strict=False)
    except Exception:
        raise ToolError("That file doesn't look like a valid PDF, or it is "
                        "corrupted.")

    if not getattr(reader, "is_encrypted", False):
        raise ToolError("That PDF is not password-protected — nothing to "
                        "unlock.")

    try:
        ok = reader.decrypt(pwd)
    except Exception:
        raise ToolError("That password could not be applied. Please check "
                        "it and try again.")
    # pypdf returns 0 on failure, non-zero on success (PasswordType enum / int)
    if not ok:
        raise ToolError("Incorrect password. Please try again.")

    try:
        n_pages = len(reader.pages)
    except Exception:
        raise ToolError("Incorrect password. Please try again.")
    if n_pages < 1:
        raise ToolError("That PDF does not contain any pages.")
    if n_pages > _MAX_PAGES:
        raise ToolError(f"That PDF has too many pages (limit {_MAX_PAGES}).")

    writer = PdfWriter()
    try:
        writer.append(reader)
    except Exception:
        raise ToolError("The PDF could not be unlocked. It may use an "
                        "unsupported encryption scheme.")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / "unlocked.pdf"
    try:
        with open(out, "wb") as fh:
            writer.write(fh)
    except Exception:
        out.unlink(missing_ok=True)
        raise ToolError("The unlocked PDF could not be written. Please try "
                        "again.")
    return out
