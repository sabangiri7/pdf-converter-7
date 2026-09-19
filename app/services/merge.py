"""Merge service: combine two or more PDFs into one document.

Pure module — no Flask, no request context. `run()` receives the saved
upload paths (in upload order) and a directory to write into; it returns the
path of the single merged PDF it created.
"""
from pathlib import Path

from pypdf import PdfWriter

from app.errors import ToolError


def run(inputs: list[Path], output_dir: Path) -> Path:
    """Append every input PDF, in order, into output_dir/merged.pdf.

    Raises ToolError (user-safe message) when fewer than two PDFs were
    given, an input file is missing, or a PDF cannot be read (corrupt or
    encrypted).
    """
    if len(inputs) < 2:
        raise ToolError("Please upload at least two PDF files.")

    writer = PdfWriter()
    for path in inputs:
        p = Path(path)
        if not p.is_file():
            raise ToolError("One of the uploaded files is missing or "
                            "expired. Please upload again.")
        try:
            writer.append(p)
        except Exception:
            raise ToolError("One of the PDFs could not be read. It may be "
                            "corrupted or password-protected — please check "
                            "your files and try again.")

    out = Path(output_dir) / "merged.pdf"
    try:
        with open(out, "wb") as fh:
            writer.write(fh)
    except OSError:
        raise ToolError("The merged document could not be written. "
                        "Please try again.")
    except Exception:
        # pypdf resolves page objects lazily while writing, so a corrupt or
        # encrypted input can fail here rather than at append() time.
        raise ToolError("One of the PDFs could not be read. It may be "
                        "corrupted or password-protected — please check "
                        "your files and try again.")
    return out
