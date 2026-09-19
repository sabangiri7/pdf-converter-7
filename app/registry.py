"""Tool discovery.

A *tool* is a pair of files inside app/tools/:

    app/tools/<slug>.json   manifest  (title/description/icon/...)
    app/tools/<slug>.py     module    (defines `bp`, a Flask Blueprint)

discover() scans every *.json manifest and, for each one whose *.py sibling
exists, imports it and returns its blueprint. A tool module that fails to
import NEVER crashes the app: the error is logged, the tool is skipped for
routing, and its manifest is still surfaced to the landing page as
"coming soon".
"""
import importlib
import importlib.util
import logging
from pathlib import Path

log = logging.getLogger(__name__)

TOOLS_DIR = Path(__file__).resolve().parent / "tools"


class ToolEntry:
    __slots__ = ("slug", "manifest", "bp", "error")

    def __init__(self, slug, manifest, bp=None, error=None):
        self.slug = slug          # e.g. "merge"
        self.manifest = manifest  # dict loaded from <slug>.json
        self.bp = bp              # Blueprint or None (module missing/broken)
        self.error = error        # str error message, or None

    @property
    def available(self) -> bool:
        return self.bp is not None

    def url(self) -> str:
        return self.manifest.get("url") or f"/t/{self.slug}"


def load_manifests() -> dict[str, dict]:
    """slug -> manifest dict for every *.json in app/tools/ (invalid JSON ->
    skipped with a warning)."""
    import json
    out: dict[str, dict] = {}
    if not TOOLS_DIR.is_dir():
        return out
    for mf in sorted(TOOLS_DIR.glob("*.json")):
        try:
            data = json.loads(mf.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("title"):
                out[mf.stem] = data
            else:
                log.warning("tool manifest %s ignored: no 'title'", mf.name)
        except (OSError, ValueError) as exc:
            log.warning("tool manifest %s ignored: %s", mf.name, exc)
    return out


def discover() -> dict[str, ToolEntry]:
    """Import tool modules + match manifests. Returns slug -> ToolEntry for
    every manifest found (modules with a manifest). Broken modules are
    logged and reported with `.error`, never raised."""
    manifests = load_manifests()
    entries: dict[str, ToolEntry] = {}
    for slug, manifest in manifests.items():
        module_path = TOOLS_DIR / f"{slug}.py"
        if not module_path.is_file():
            log.info("tool '%s': manifest present but no %s.py — shown as "
                     "coming soon", slug, slug)
            entries[slug] = ToolEntry(slug, manifest)
            continue
        try:
            module = importlib.import_module(f"app.tools.{slug}")
        except Exception as exc:
            log.exception("tool '%s' failed to import — skipping it", slug)
            entries[slug] = ToolEntry(slug, manifest, error=str(exc))
            continue
        bp = getattr(module, "bp", None) or getattr(module, "blueprint", None)
        if bp is None:
            msg = (f"app/tools/{slug}.py defines no `bp` Blueprint")
            log.error("tool '%s' skipped: %s", slug, msg)
            entries[slug] = ToolEntry(slug, manifest, error=msg)
            continue
        entries[slug] = ToolEntry(slug, manifest, bp=bp)
    for py in sorted(TOOLS_DIR.glob("*.py")):
        if py.stem not in manifests and py.stem != "__init__":
            log.warning("app/tools/%s.py has no matching .json manifest - it "
                        "will not be routed (create app/tools/%s.json)",
                        py.stem, py.stem)
    return entries
