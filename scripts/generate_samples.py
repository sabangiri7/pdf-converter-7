#!/usr/bin/env python3
"""Generate the sample fixture files used by the test suite.

Creates in <repo>/samples/:
    sample_3p.pdf     3-page PDF, page text "Page 1 of 3" ... (reportlab)
    sample_2p.pdf     2-page PDF, page text "Page 1 of 2" ... (reportlab)
    sample_red.jpg    800x600 solid red (Pillow)
    sample_green.jpg  800x600 solid green
    sample_blue.png   800x600 solid blue
    sample_red.png / sample_green.png   (PNG twins for images_to_pdf tests)

Run:  python scripts/generate_samples.py
Idempotent: always rewrites the files.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"


def make_pdf(path: Path, pages: int) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(str(path), pagesize=A4)
    w, h = A4
    for i in range(1, pages + 1):
        c.setFont("Helvetica-Bold", 28)
        c.drawCentredString(w / 2, h / 2 + 20, f"Page {i} of {pages}")
        c.setFont("Helvetica", 14)
        c.drawCentredString(w / 2, h / 2 - 20, "PDF Tools sample document")
        c.showPage()
    c.save()


def make_images(dir_: Path) -> None:
    from PIL import Image
    specs = [("sample_red", (220, 40, 40)), ("sample_green", (40, 180, 80)),
             ("sample_blue", (40, 80, 220))]
    for name, rgb in specs:
        img = Image.new("RGB", (800, 600), rgb)
        img.save(dir_ / f"{name}.jpg", "JPEG", quality=90)
        img.save(dir_ / f"{name}.png", "PNG")


def main() -> int:
    SAMPLES.mkdir(exist_ok=True)
    make_pdf(SAMPLES / "sample_3p.pdf", 3)
    make_pdf(SAMPLES / "sample_2p.pdf", 2)
    make_images(SAMPLES)
    made = sorted(p.name for p in SAMPLES.iterdir())
    print("samples/ now contains:", ", ".join(made))
    return 0


if __name__ == "__main__":
    sys.exit(main())
