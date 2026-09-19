"""Tests for the split tool: service-level (pure, no Flask) + route."""
import io

import pytest

from app.errors import ToolError
from app.helpers import page_count
from app.services.split import parse_page_ranges, run


def _upload(pdf_bytes, filename="doc.pdf"):
    return {"files": [(io.BytesIO(pdf_bytes), filename)]}


# ---------------- parse_page_ranges (unit) ----------------

def test_parser_basic():
    assert parse_page_ranges("1-3,5", 8) == [(1, 3), (5, 5)]


def test_parser_single_pages_and_spaces():
    assert parse_page_ranges(" 1 , 3 ", 3) == [(1, 1), (3, 3)]
    # spaces *inside* a token are only allowed around the hyphen
    assert parse_page_ranges("1 - 2", 3) == [(1, 2)]
    assert parse_page_ranges(" 1 - 2 , 3 ", 3) == [(1, 2), (3, 3)]


def test_parser_empty_is_all_pages():
    assert parse_page_ranges("", 3) == [(1, 3)]
    assert parse_page_ranges("   ", 3) == [(1, 3)]
    assert parse_page_ranges(None, 3) == [(1, 3)]


@pytest.mark.parametrize("bad", ["abc", "1-", "-2", "1--2", "1..3", "1;3",
                                 "1-3,", "+2", "1 2", "3-1-2"])
def test_parser_malformed_tokens(bad):
    with pytest.raises(ToolError):
        parse_page_ranges(bad, 8)


def test_parser_zero_page_rejected():
    with pytest.raises(ToolError) as ei:
        parse_page_ranges("0", 8)
    assert "start at 1" in str(ei.value)
    with pytest.raises(ToolError):
        parse_page_ranges("0-2", 8)


def test_parser_reversed_range_rejected():
    with pytest.raises(ToolError) as ei:
        parse_page_ranges("5-2", 8)
    assert "2-5" in str(ei.value)          # suggests the fix


def test_parser_page_beyond_total_rejected():
    with pytest.raises(ToolError) as ei:
        parse_page_ranges("9", 3)
    assert "3 pages" in str(ei.value)
    with pytest.raises(ToolError):
        parse_page_ranges("2-4", 3)


@pytest.mark.parametrize("evil", ["٣", "１-３", "1٣", "\U0001d7ce"])
def test_parser_rejects_non_ascii_digits(evil):
    """Unicode digit forms must never silently parse as a page number."""
    with pytest.raises(ToolError):
        parse_page_ranges(evil, 8)


def test_parser_huge_number_is_toolerror_not_valueerror():
    """5000 digits: must stay a ToolError (int() str-limit safety) and the
    user-facing message must stay short/safe."""
    with pytest.raises(ToolError) as ei:
        parse_page_ranges("9" * 5000, 8)
    assert "Traceback" not in str(ei.value)
    assert len(str(ei.value)) < 300


def test_parser_overlapping_and_ordered():
    assert parse_page_ranges("5,1-2", 8) == [(5, 5), (1, 2)]
    assert parse_page_ranges("1-3,2-3", 3) == [(1, 3), (2, 3)]
    assert parse_page_ranges("1,1", 3) == [(1, 1), (1, 1)]


# ---------------- extract mode (service, pure) ----------------

def test_extract_pages(sample_pdf_3p, tmp_path):
    out = run([sample_pdf_3p], tmp_path, mode="extract", ranges="1,3")
    assert out.is_file()
    assert page_count(out) == 2
    from pypdf import PdfReader
    texts = [p.extract_text().strip() for p in PdfReader(str(out)).pages]
    assert texts[0].startswith("Page 1 of 3")
    assert texts[1].startswith("Page 3 of 3")


def test_extract_range_and_page_mix(sample_pdf_3p, tmp_path):
    out = run([sample_pdf_3p], tmp_path, mode="extract", ranges="1-2,3")
    assert page_count(out) == 3


def test_extract_empty_ranges_is_all_pages(sample_pdf_3p, tmp_path):
    out = run([sample_pdf_3p], tmp_path, mode="extract")
    assert page_count(out) == 3


def test_extract_bad_range_raises_toolerror(sample_pdf_3p, tmp_path):
    with pytest.raises(ToolError):
        run([sample_pdf_3p], tmp_path, mode="extract", ranges="5-2")
    with pytest.raises(ToolError):
        run([sample_pdf_3p], tmp_path, mode="extract", ranges="4")


def test_extract_preserves_spec_order_and_duplicates(sample_pdf_3p, tmp_path):
    """Pages come out in the order given; overlapping ranges repeat pages."""
    from pypdf import PdfReader
    out = run([sample_pdf_3p], tmp_path, mode="extract", ranges="3,1,2-3")
    texts = [p.extract_text() for p in PdfReader(str(out)).pages]
    assert page_count(out) == 4
    assert [t.splitlines()[0] for t in texts] == [
        "Page 3 of 3", "Page 1 of 3", "Page 2 of 3", "Page 3 of 3"]


def test_extract_encrypted_pdf_raises_toolerror(sample_pdf_3p, tmp_path):
    from pypdf import PdfWriter
    enc = tmp_path / "enc.pdf"
    w = PdfWriter()
    w.append(str(sample_pdf_3p))
    w.encrypt("secret")
    with open(enc, "wb") as fh:
        w.write(fh)
    with pytest.raises(ToolError) as ei:
        run([enc], tmp_path / "o", mode="extract", ranges="1")
    assert "password" in str(ei.value).lower()


def test_zero_page_pdf_raises_toolerror(tmp_path):
    """A readable but page-less PDF must give a friendly error, in both modes."""
    from pypdf import PdfWriter
    zero = tmp_path / "zero.pdf"
    w = PdfWriter()
    with open(zero, "wb") as fh:
        w.write(fh)
    assert page_count(zero) == 0
    for mode in ("extract", "all", "odd", "even"):
        with pytest.raises(ToolError) as ei:
            run([zero], tmp_path / f"o-{mode}", mode=mode, ranges="1")
        assert "any pages" in str(ei.value)


# ---------------- all-pages mode (service, pure) ----------------

def test_all_mode_one_pdf_per_page(sample_pdf_3p, tmp_path):
    outs = run([sample_pdf_3p], tmp_path, mode="all")
    assert isinstance(outs, list)
    assert [p.name for p in outs] == ["page-1.pdf", "page-2.pdf", "page-3.pdf"]
    for p in outs:
        assert p.is_file()
        assert page_count(p) == 1


def test_all_mode_page_count_matches_input(sample_pdf_2p, tmp_path):
    outs = run([sample_pdf_2p], tmp_path, mode="all")
    assert len(outs) == page_count(sample_pdf_2p)


# ---------------- odd / even / from / to / chunks ----------------

def test_odd_pages(sample_pdf_3p, tmp_path):
    from pypdf import PdfReader
    out = run([sample_pdf_3p], tmp_path, mode="odd")
    assert out.name == "odd-pages.pdf"
    assert page_count(out) == 2
    texts = [p.extract_text().splitlines()[0]
             for p in PdfReader(str(out)).pages]
    assert texts == ["Page 1 of 3", "Page 3 of 3"]


def test_even_pages(sample_pdf_3p, tmp_path):
    from pypdf import PdfReader
    out = run([sample_pdf_3p], tmp_path, mode="even")
    assert out.name == "even-pages.pdf"
    assert page_count(out) == 1
    assert PdfReader(str(out)).pages[0].extract_text().startswith("Page 2 of 3")


def test_even_pages_single_page_pdf_errors(sample_pdf_3p, tmp_path):
    """A 1-page PDF has no even pages."""
    from pypdf import PdfReader, PdfWriter
    one = tmp_path / "one.pdf"
    w = PdfWriter()
    w.add_page(PdfReader(str(sample_pdf_3p)).pages[0])
    with open(one, "wb") as fh:
        w.write(fh)
    with pytest.raises(ToolError) as ei:
        run([one], tmp_path / "o", mode="even")
    assert "even" in str(ei.value).lower()


def test_from_page(sample_pdf_3p, tmp_path):
    from pypdf import PdfReader
    out = run([sample_pdf_3p], tmp_path, mode="from", page="2")
    assert page_count(out) == 2
    texts = [p.extract_text().splitlines()[0]
             for p in PdfReader(str(out)).pages]
    assert texts == ["Page 2 of 3", "Page 3 of 3"]


def test_to_page(sample_pdf_3p, tmp_path):
    from pypdf import PdfReader
    out = run([sample_pdf_3p], tmp_path, mode="to", page="2")
    assert page_count(out) == 2
    texts = [p.extract_text().splitlines()[0]
             for p in PdfReader(str(out)).pages]
    assert texts == ["Page 1 of 3", "Page 2 of 3"]


def test_from_to_require_page_number(sample_pdf_3p, tmp_path):
    with pytest.raises(ToolError):
        run([sample_pdf_3p], tmp_path, mode="from", page="")
    with pytest.raises(ToolError):
        run([sample_pdf_3p], tmp_path, mode="to", page="abc")
    with pytest.raises(ToolError):
        run([sample_pdf_3p], tmp_path, mode="from", page="9")


def test_chunks_mode(sample_pdf_3p, tmp_path):
    outs = run([sample_pdf_3p], tmp_path, mode="chunks", chunk_size="2")
    assert [p.name for p in outs] == ["part-1.pdf", "part-2.pdf"]
    assert page_count(outs[0]) == 2
    assert page_count(outs[1]) == 1


def test_chunks_rejects_bad_size(sample_pdf_3p, tmp_path):
    with pytest.raises(ToolError):
        run([sample_pdf_3p], tmp_path, mode="chunks", chunk_size="")
    with pytest.raises(ToolError):
        run([sample_pdf_3p], tmp_path, mode="chunks", chunk_size="0")
    with pytest.raises(ToolError):
        run([sample_pdf_3p], tmp_path, mode="chunks", chunk_size="99")


# ---------------- other service guards ----------------

def test_mode_must_be_known(sample_pdf_3p, tmp_path):
    with pytest.raises(ToolError):
        run([sample_pdf_3p], tmp_path, mode="sideways")


def test_requires_exactly_one_pdf(sample_pdf_3p, sample_pdf_2p, tmp_path):
    with pytest.raises(ToolError):
        run([sample_pdf_3p, sample_pdf_2p], tmp_path, mode="extract")


def test_corrupt_pdf_raises_toolerror(tmp_path):
    junk = tmp_path / "junk.pdf"
    junk.write_bytes(b"%PDF-1.1 \x00not a real pdf")
    with pytest.raises(ToolError):
        run([junk], tmp_path, mode="extract")


# ---------------- routes ----------------

def test_get_page(client):
    r = client.get("/t/split")
    assert r.status_code == 200
    assert b"Split PDF" in r.data
    assert b'name="ranges"' in r.data
    assert b'name="mode"' in r.data
    assert b'value="odd"' in r.data
    assert b'value="even"' in r.data
    assert b'value="from"' in r.data
    assert b'value="chunks"' in r.data
    assert b'name="page"' in r.data
    assert b'name="chunk_size"' in r.data


def test_extract_roundtrip(client, sample_pdf_3p):
    r = client.post("/t/split",
                    data={**_upload(sample_pdf_3p.read_bytes()),
                          "mode": "extract", "ranges": "1,3"},
                    content_type="multipart/form-data")
    assert r.status_code == 200
    assert b"/dl/" in r.data
    # actually fetch the produced PDF and verify its content: 2 pages,
    # pages 1 and 3 of the original
    import io as _io
    import re
    from pypdf import PdfReader
    url = re.search(rb'href="(/dl/[0-9a-f]+/0)"', r.data).group(1).decode()
    d = client.get(url)
    assert d.status_code == 200
    assert d.data.startswith(b"%PDF")
    pages = PdfReader(_io.BytesIO(d.data)).pages
    assert len(pages) == 2
    assert pages[0].extract_text().startswith("Page 1 of 3")
    assert pages[1].extract_text().startswith("Page 3 of 3")


def test_trailing_slash_url_works(client):
    """strict_slashes=False deviation: both canonical /t/split and
    /t/split/ serve the page without a redirect."""
    assert client.get("/t/split").status_code == 200
    assert client.get("/t/split/").status_code == 200


def test_injection_shaped_range_route_400(client, sample_pdf_3p):
    r = client.post("/t/split",
                    data={**_upload(sample_pdf_3p.read_bytes()),
                          "mode": "extract", "ranges": "1;rm -rf /"},
                    content_type="multipart/form-data")
    assert r.status_code == 400
    assert b"not a valid page range" in r.data


def test_all_mode_roundtrip_offers_zip(client, sample_pdf_3p):
    r = client.post("/t/split",
                    data={**_upload(sample_pdf_3p.read_bytes()),
                          "mode": "all"},
                    content_type="multipart/form-data")
    assert r.status_code == 200
    assert b"/dl/" in r.data
    assert b"all.zip" in r.data          # 3 outputs -> zip download


def test_odd_mode_roundtrip(client, sample_pdf_3p):
    r = client.post("/t/split",
                    data={**_upload(sample_pdf_3p.read_bytes()),
                          "mode": "odd"},
                    content_type="multipart/form-data")
    assert r.status_code == 200
    assert b"/dl/" in r.data


def test_from_mode_roundtrip(client, sample_pdf_3p):
    r = client.post("/t/split",
                    data={**_upload(sample_pdf_3p.read_bytes()),
                          "mode": "from", "page": "2"},
                    content_type="multipart/form-data")
    assert r.status_code == 200
    assert b"/dl/" in r.data


def test_chunks_mode_roundtrip_offers_zip(client, sample_pdf_3p):
    r = client.post("/t/split",
                    data={**_upload(sample_pdf_3p.read_bytes()),
                          "mode": "chunks", "chunk_size": "2"},
                    content_type="multipart/form-data")
    assert r.status_code == 200
    assert b"all.zip" in r.data


def test_bad_range_route_friendly_400(client, sample_pdf_3p):
    r = client.post("/t/split",
                    data={**_upload(sample_pdf_3p.read_bytes()),
                          "mode": "extract", "ranges": "9"},
                    content_type="multipart/form-data")
    assert r.status_code == 400
    assert b"does not exist" in r.data


def test_bad_mode_route_friendly_400(client, sample_pdf_3p):
    r = client.post("/t/split",
                    data={**_upload(sample_pdf_3p.read_bytes()),
                          "mode": "nonsense"},
                    content_type="multipart/form-data")
    assert r.status_code == 400
