"""Tests for xlsx_to_csv."""
import csv
import io
from pathlib import Path

import pytest
from openpyxl import Workbook

from app.errors import ToolError
from app.services.xlsx_to_csv import run

ROOT = Path(__file__).resolve().parent.parent


def _xlsx(tmp_path, rows, name="data.xlsx") -> Path:
    wb = Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    p = tmp_path / name
    wb.save(p)
    return p


def test_happy_path(tmp_path):
    src = _xlsx(tmp_path, [["name", "score"], ["Ada", 10], ["Bob", 9]])
    out = run([src], tmp_path / "out")
    assert out.suffix == ".csv"
    with open(out, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.reader(fh))
    assert rows[0] == ["name", "score"]
    assert rows[1] == ["Ada", "10"]


def test_rejects_non_xlsx(sample_image_png, tmp_path):
    with pytest.raises(ToolError):
        run([sample_image_png], tmp_path)


def test_requires_single(tmp_path):
    a = _xlsx(tmp_path, [["a"]], "a.xlsx")
    b = _xlsx(tmp_path, [["b"]], "b.xlsx")
    with pytest.raises(ToolError):
        run([a, b], tmp_path / "o")


def test_service_pure_no_flask():
    src = (ROOT / "app" / "services" / "xlsx_to_csv.py").read_text("utf-8")
    for token in ("from flask", "import flask", "Blueprint"):
        assert token not in src


def test_get_page(client):
    r = client.get("/t/xlsx_to_csv/")
    assert r.status_code == 200
    assert b"Excel" in r.data or b"CSV" in r.data


def test_route_roundtrip(client, tmp_path):
    src = _xlsx(tmp_path, [["x", "y"], [1, 2]])
    r = client.post(
        "/t/xlsx_to_csv/",
        data={"files": [(io.BytesIO(src.read_bytes()), "sheet.xlsx")]},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert b"/dl/" in r.data
