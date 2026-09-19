"""Add password protection to a PDF (pypdf). Pure service: no Flask."""
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from ..errors import ToolError
from ..helpers import detect_kind, page_count

_MAX_PASSWORD_LEN = 128


def run(inputs: list[Path], output_dir: Path, password: str = "",
        **_options) -> Path:
    """Encrypt one PDF with the given user password."""
    inputs = [Path(p) for p in (inputs or [])]
    if len(inputs) != 1:
        raise ToolError("Protect works on one PDF at a time. Please upload "
                        "a single PDF.")
    src = inputs[0]
    if not src.is_file():
        raise ToolError("Your uploaded file is missing or expired. Please "
                        "upload it again.")
    if detect_kind(src) != "pdf":
        raise ToolError("That file doesn't look like a valid PDF.")

    pwd = str(password or "")
    if not pwd:
        raise ToolError("Enter a password to protect the PDF.")
    if len(pwd) > _MAX_PASSWORD_LEN:
        raise ToolError(f"Password is too long (max {_MAX_PASSWORD_LEN} "
                        "characters).")
    # Reject control characters that can break download / forms.
    if any(ord(c) < 32 for c in pwd):
        raise ToolError("Password must not contain control characters.")

    total = page_count(src)
    if total < 1:
        raise ToolError("That PDF does not contain any pages.")

    try:
        reader = PdfReader(str(src), strict=False)
        if getattr(reader, "is_encrypted", False):
            raise ToolError("That PDF is already password-protected. Unlock "
                            "it first if you want to set a new password.")
        writer = PdfWriter()
        writer.append(reader)
        writer.encrypt(pwd)
    except ToolError:
        raise
    except Exception:
        raise ToolError("That PDF could not be protected. It may be "
                        "corrupted.")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / "protected.pdf"
    try:
        with open(out, "wb") as fh:
            writer.write(fh)
    except Exception:
        out.unlink(missing_ok=True)
        raise ToolError("The protected PDF could not be written. Please try "
                        "again.")
    return out
