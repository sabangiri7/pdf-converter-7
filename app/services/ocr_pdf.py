"""Pure OCR service: make a scanned PDF searchable with ocrmypdf + Tesseract.

No Flask imports (CONTRACT.md service rules). Order of operations matters:
``require_binary("tesseract", ...)`` runs FIRST so a missing dependency is
always a friendly ToolError (HTTP 400), never a 500 — this is what the
monkeypatched missing-binary tests exercise. OCR itself shells out to
``python -m ocrmypdf`` (module invocation avoids PATH issues for the
``ocrmypdf`` console script).

Exit-code mapping (ocrmypdf.exceptions.ExitCode, verified against the
pinned 17.11.0): 6 ``already_done_ocr`` means the input already contains
selectable/OCR text; 3 ``missing_dependency`` means the server is missing an
OCR component (a language pack, Ghostscript, ...); 2 ``input_file`` with a
TaggedPDFError means a born-digital/office PDF that does not need OCR.
Those become friendly messages; any other non-zero exit becomes a generic,
user-safe failure (raw stderr is logged server-side only, never shown).
"""
import logging
import subprocess
import sys
from pathlib import Path

from app.errors import ToolError
from app.helpers import detect_kind, page_count, require_binary

log = logging.getLogger(__name__)

# ISO 639-2/T codes accepted as the `language` option (route validates too;
# the service stays defensive).
LANGUAGES = ("eng", "deu", "fra", "spa", "ita", "por", "nld")
DEFAULT_LANGUAGE = "eng"

_OCR_TIMEOUT_SECONDS = 300

# ocrmypdf.exceptions.ExitCode (verified against the pinned ocrmypdf 17.11.0):
#   2 = input_file          -> bad/unsupported input (incl. TaggedPDFError)
#   3 = missing_dependency  -> a required component is absent on the server
#                               (e.g. the Tesseract language pack)
#   6 = already_done_ocr    -> the input already contains selectable/OCR text
EXIT_CODE_INPUT_FILE = 2
EXIT_CODE_MISSING_DEPENDENCY = 3
EXIT_CODE_ALREADY_OCRD = 6

ALREADY_TEXT_MESSAGE = ("This PDF already contains selectable text — nothing "
                        "needs to be OCR'd.")

TAGGED_PDF_MESSAGE = (
    "This PDF is a Tagged (born-digital) document — usually from Word, "
    "Excel or similar — and already has a text layer. OCR is only for "
    "scanned image PDFs. Try a scan, or use the file as-is.")

MISSING_DEPENDENCY_MESSAGE = (
    "The OCR engine is missing a required component on this server — "
    "usually the Tesseract language pack for the selected language. See "
    "SYSTEM_DEPENDENCIES.md for install instructions.")

_MISSING_TESSERESS_MESSAGE = (
    "The Tesseract OCR engine is not installed on this server, so OCR "
    "cannot run right now. See SYSTEM_DEPENDENCIES.md for install "
    "instructions.")

_FAILED_MESSAGE = ("The OCR engine could not process this PDF. It may be "
                   "corrupted, encrypted or use a layout we cannot read. "
                   "Please try a different file.")

_TIMED_OUT_MESSAGE = ("OCR took longer than 5 minutes. The PDF may be very "
                      "large or complex — please try a smaller file.")


def _stderr_text(proc) -> str:
    raw = bytes(getattr(proc, "stderr", b"") or b"")
    return raw.decode("utf-8", errors="replace")


def _is_tagged_pdf_error(proc) -> bool:
    """True when ocrmypdf rejected a Tagged / born-digital PDF."""
    if getattr(proc, "returncode", None) != EXIT_CODE_INPUT_FILE:
        return False
    err = _stderr_text(proc).lower()
    return "tagged" in err


def run(inputs: list[Path], output_dir: Path,
        language: str = DEFAULT_LANGUAGE, **options) -> Path:
    """OCR one scanned PDF.

    inputs: [Path] — exactly one saved upload (the manifest sets
        multiple=false, but the service re-checks defensively).
    output_dir: write ONLY here. Returns the produced ``ocr.pdf`` Path.
    language: ISO code from LANGUAGES. Extra options are accepted and
        ignored (contract canonical signature).
    """
    # 1. external binary check FIRST (friendly error on dev boxes)
    require_binary("tesseract", _MISSING_TESSERESS_MESSAGE)

    # 2. defensive option / input validation
    if not inputs:
        raise ToolError("No PDF was uploaded for OCR.")
    if len(inputs) > 1:
        raise ToolError("OCR works on one PDF at a time. Please upload a "
                        "single file.")
    src = Path(inputs[0])
    if not src.is_file():
        raise ToolError("Your uploaded file is missing. Please upload it "
                        "again.")
    if detect_kind(src) != "pdf":
        raise ToolError("The uploaded file is not a valid PDF.")
    # Early, friendly corrupt/encrypted check (same message style the upload
    # gate uses) so the subprocess never sees a file we can already reject.
    page_count(src)

    lang = str(language if language is not None else DEFAULT_LANGUAGE)
    if lang not in LANGUAGES:
        raise ToolError("Choose a supported OCR language: "
                        + ", ".join(LANGUAGES) + ".")

    # 3. run the OCR engine
    out = Path(output_dir) / "ocr.pdf"
    cmd = [sys.executable, "-m", "ocrmypdf", "--language", lang,
           str(src), str(out)]
    try:
        proc = subprocess.run(cmd, capture_output=True,
                              timeout=_OCR_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        out.unlink(missing_ok=True)
        raise ToolError(_TIMED_OUT_MESSAGE)
    except OSError:
        log.exception("failed to spawn ocrmypdf")
        raise ToolError("The OCR engine could not be started on this "
                        "server. Please try again later.")

    rc = proc.returncode
    if rc == EXIT_CODE_ALREADY_OCRD:
        out.unlink(missing_ok=True)
        raise ToolError(ALREADY_TEXT_MESSAGE)
    if _is_tagged_pdf_error(proc):
        out.unlink(missing_ok=True)
        raise ToolError(TAGGED_PDF_MESSAGE)
    if rc == EXIT_CODE_MISSING_DEPENDENCY:
        # e.g. the selected Tesseract language pack is not installed
        out.unlink(missing_ok=True)
        raise ToolError(MISSING_DEPENDENCY_MESSAGE)
    if rc != 0 or not out.is_file():
        # keep stderr on the server log only — never in the user's face
        stderr_tail = bytes(getattr(proc, "stderr", b"") or b"")[-500:]
        log.warning("ocrmypdf exited with code %s; stderr tail: %r", rc,
                    stderr_tail)
        out.unlink(missing_ok=True)
        raise ToolError(_FAILED_MESSAGE)
    return out
