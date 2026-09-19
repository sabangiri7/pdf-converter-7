"""Office -> PDF via LibreOffice, as a pure service (no Flask).

`run()` resolves the soffice/libreoffice binary through app.helpers on
every call (so tests can monkeypatch ``app.helpers.shutil.which`` and turn
a missing binary into a friendly ToolError instead of a 500), shells out one
headless conversion per input, and returns the produced PDF path(s).

Inputs are the uuid-named upload paths; soffice writes
``<input-stem>.pdf`` into the output dir, which is already a safe unique
name, so nothing user-facing is derived from the inputs here.
"""
import shutil
import subprocess
import tempfile
from pathlib import Path

from app import helpers
from app.errors import ToolError

_TIMEOUT_SECONDS = 120

_CONVERT_FAILED = (
    "The document could not be converted. Please make sure it is a valid, "
    "unencrypted Word, Excel or PowerPoint file and try again.")


def _soffice_binary() -> str:
    """Path of the LibreOffice launcher, or a friendly ToolError.

    Try ``soffice`` first, then ``libreoffice``; if neither is on PATH,
    ``require_binary`` raises the user-safe error the spec asks for.
    """
    for name in ("soffice", "libreoffice"):
        path = helpers.binary_path(name)
        if path:
            return path
    return helpers.require_binary("soffice")


def run(inputs: list[Path], output_dir: Path, **options) -> Path | list[Path]:
    """Convert each Office document to PDF with headless LibreOffice.

    Returns a single ``Path`` when exactly one input was given, otherwise
    the ``list[Path]`` of produced PDFs. Raises ``ToolError`` (never a raw
    exception) for missing binary, failed or timed-out conversions, and
    missing/empty output files.
    """
    soffice = _soffice_binary()
    outdir = Path(output_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    paths = [Path(p) for p in inputs]
    if not paths:
        raise ToolError("No files were provided for conversion.")

    # Dedicated, throwaway LibreOffice user profile (file:// URI as soffice
    # requires). Without -env:UserInstallation, concurrent soffice runs fight
    # over the default profile (lock errors / silent corruption). The dir
    # lives in the system temp area — never inside the job trees — and is
    # always removed, so no junk is left behind.
    profile_dir = tempfile.mkdtemp(prefix="lo_profile_")
    profile_uri = Path(profile_dir).as_uri()
    produced: list[Path] = []
    try:
        for src in paths:
            cmd = [soffice, f"-env:UserInstallation={profile_uri}",
                   "--headless", "--convert-to", "pdf",
                   "--outdir", str(outdir), str(src)]
            try:
                proc = subprocess.run(cmd, timeout=_TIMEOUT_SECONDS,
                                      capture_output=True)
            except subprocess.TimeoutExpired:
                raise ToolError(
                    "The conversion timed out after two minutes. Please try a "
                    "smaller or simpler document.")
            except OSError:
                raise ToolError(
                    "The converter program could not be started. Please try "
                    "again in a moment.")
            if getattr(proc, "returncode", 1) != 0:
                raise ToolError(_CONVERT_FAILED)
            # soffice names its output after the (uuid) input stem
            target = outdir / (src.stem + ".pdf")
            result = target if (target.is_file() and target.stat().st_size > 0) \
                else None
            if result is None:  # defensive: some builds append a suffix
                # (prefix scan, not glob: a weird stem must not raise)
                matches = [m for m in sorted(outdir.iterdir())
                           if m.is_file() and m.name.startswith(src.stem)
                           and m.suffix.lower() == ".pdf"
                           and m.stat().st_size > 0]
                result = matches[0] if matches else None
            if result is None:
                raise ToolError(_CONVERT_FAILED)
            produced.append(result)
    finally:
        shutil.rmtree(profile_dir, ignore_errors=True)

    if len(produced) == 1:
        return produced[0]
    return produced
