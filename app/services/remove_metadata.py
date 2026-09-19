"""Strip document metadata from a PDF."""
from pathlib import Path

import pikepdf

from app.errors import ToolError
from app.helpers import detect_kind

_BAD = ("That file doesn't look like a valid PDF, or it is corrupted. "
        "Please try a different file.")


def run(inputs: list[Path], output_dir: Path, **_options) -> Path:
    if len(inputs) != 1:
        raise ToolError("Remove Metadata works on one PDF at a time.")
    src = Path(inputs[0])
    if detect_kind(src) != "pdf":
        raise ToolError("Please upload a PDF file.")
    out = Path(output_dir) / "no-metadata.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        with pikepdf.open(str(src)) as pdf:
            try:
                with pdf.open_metadata() as meta:
                    for key in list(meta.keys()):
                        try:
                            del meta[key]
                        except Exception:
                            pass
            except Exception:
                pass
            # Clear Info dict keys individually (clear() can fail on some docs)
            try:
                info = pdf.docinfo
                for key in list(info.keys()):
                    try:
                        del info[key]
                    except Exception:
                        pass
            except Exception:
                pass
            try:
                if "/Metadata" in pdf.Root:
                    del pdf.Root["/Metadata"]
            except Exception:
                pass
            pdf.save(str(out))
    except ToolError:
        raise
    except Exception:
        raise ToolError(_BAD)
    return out
