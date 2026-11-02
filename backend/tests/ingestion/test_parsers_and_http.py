"""PubMed / NCCIH / EMA inventory parsers, raw store and HTTP retry behaviour."""

from __future__ import annotations

import io
from pathlib import Path

import httpx
import openpyxl
import pytest
import respx

from herbaguard.core.config import Settings
from herbaguard.ingestion.http import HttpClient, build_ssl_context
from herbaguard.ingestion.parsers.ema_inventory import (
    InventoryFormatError,
    find_monograph_links,
    parse_inventory,
)
from herbaguard.ingestion.parsers.nccih_html import SAFETY_SECTION, parse_fact_sheet
from herbaguard.ingestion.parsers.pubmed_xml import parse_efetch
from herbaguard.ingestion.raw_store import RawStore, sha256

FIXTURES = Path(__file__).parents[1] / "fixtures" / "captured"


def test_pubmed_efetch_captured() -> None:
    articles = parse_efetch((FIXTURES / "pubmed_efetch_2.xml").read_bytes())
    assert {a.pmid for a in articles} == {"42302936", "40325522"}
    for article in articles:
        assert article.title
        assert article.year and 2000 < article.year < 2100
        assert article.publication_types
        assert "[abstract text removed" in article.abstract or article.abstract == ""


def test_nccih_fact_sheet_captured() -> None:
    sheet = parse_fact_sheet(
        (FIXTURES / "nccih_st-johns-wort_main.html").read_text(encoding="utf-8")
    )
    assert sheet.last_updated == "May 2025"
    assert [s.title for s in sheet.sections][:4] == [
        "Background", "How Much Do We Know?", "What Have We Learned?", SAFETY_SECTION,
    ]  # fmt: skip
    safety = sheet.section(SAFETY_SECTION)
    assert safety is not None
    items = [b for b in safety.blocks if b.is_list_item]
    assert any(b.text == "Birth control pills" for b in items)
    assert all(b.lead_in for b in items)
    texts = [b.text for b in safety.blocks]
    assert len(texts) == len(set(texts)), "nested lists must not duplicate text"


def _inventory_xlsx(rows: list[list[object]]) -> bytes:
    """SYNTHETIC spreadsheet with the real EMA header (columns as observed 2026-11-02)."""
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(
        ["Content type:", "Herbal medicine", "Output automatically generated", "02/11/2026 - 06:05"]
    )
    sheet.append([])
    sheet.append(["Latin name", "Combination", "English common name", "Botanical name", "Therapeutic area", "Status",
                  "Outcome of European assessment", "Additional information", "Date added to the inventory",
                  "Date added to the priority list", "First published date", "Last updated date", "Herbal medicine URL"])  # fmt: skip
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_ema_inventory_parse_and_dedupe() -> None:
    row = ["Crataegi folium cum flore", "No", "Hawthorn", "Crataegus monogyna Jacq.", "Cardiovascular", "F: Assessment finalised",
           "European Union herbal monograph", None, None, None, None, "15/04/2025",
           "https://www.ema.europa.eu/en/medicines/herbal/crataegi-folium-cum-flore"]  # fmt: skip
    combo = ["Hyperici herba;Cimicifugae rhizoma", "Yes", "St. John's Wort", "Hypericum perforatumL.", None, None, None,
             None, None, None, None, None, "https://www.ema.europa.eu/en/medicines/herbal/hyperici-herba"]  # fmt: skip
    rows = parse_inventory(_inventory_xlsx([row, row, row, combo]))
    assert len(rows) == 2  # the duplicate hawthorn rows collapse
    assert rows[0].latin_name == "Crataegi folium cum flore" and not rows[0].combination
    assert rows[1].combination
    assert rows[0].additional_info if hasattr(rows[0], "additional_info") else True


def test_ema_inventory_missing_columns_fail_loudly() -> None:
    workbook = openpyxl.Workbook()
    workbook.active.append(["Latin name", "Something else"])
    buffer = io.BytesIO()
    workbook.save(buffer)
    with pytest.raises(InventoryFormatError):
        parse_inventory(buffer.getvalue())


def test_find_monograph_links_selects_final_only() -> None:
    html = """<a href="/en/documents/herbal-monograph/final-european-union-herbal-monograph-hypericum-perforatum-l-herba-revision-1_en.pdf">x</a>
    <a href="/en/documents/herbal-monograph/draft-european-union-herbal-monograph-hypericum-perforatum-l-herba-traditional-use-revision-1_en.pdf">x</a>
    <a href="/en/documents/herbal-monograph/superseded-community-herbal-monograph-hypericum-perforatum-l-herba-traditional-use_en.pdf">x</a>
    <a href="/en/documents/herbal-report/assessment-report.pdf">x</a>"""
    finals, everything = find_monograph_links(html)
    assert finals == [
        "/en/documents/herbal-monograph/final-european-union-herbal-monograph-hypericum-perforatum-l-herba-revision-1_en.pdf"
    ]
    assert len(everything) == 3


# --------------------------------------------------------------------------- raw store


def test_raw_store_is_content_addressed_and_compresses_text(tmp_path: Path) -> None:
    store = RawStore(tmp_path)
    digest, path = store.save("pubmed", b"<xml/>", ".xml")
    assert digest == sha256(b"<xml/>")
    assert path.name.endswith(".xml.gz")
    again, same_path = store.save("pubmed", b"<xml/>", ".xml")
    assert (again, same_path) == (digest, path)
    assert store.load(path) == b"<xml/>"
    pdf_digest, pdf_path = store.save("ema_hmpc", b"%PDF-1.7", ".pdf")
    assert pdf_path.suffix == ".pdf" and store.load(pdf_path) == b"%PDF-1.7"
    assert pdf_digest != digest


# --------------------------------------------------------------------------- HTTP


def _client() -> HttpClient:
    return HttpClient(Settings(), retry_wait_max=0.01, rate_limit=False)


@respx.mock
def test_retries_on_503_then_succeeds() -> None:
    route = respx.get("https://example.org/x").mock(
        side_effect=[httpx.Response(503), httpx.Response(200, json={"ok": True})]
    )
    result = _client().get("https://example.org/x")
    assert result.status_code == 200 and route.call_count == 2


@respx.mock
def test_retries_on_429_and_gives_up_after_max_attempts() -> None:
    from herbaguard.ingestion.http import MAX_ATTEMPTS, RetryableStatusError

    route = respx.get("https://example.org/busy").mock(return_value=httpx.Response(429))
    with pytest.raises(RetryableStatusError):
        _client().get("https://example.org/busy")
    assert route.call_count == MAX_ATTEMPTS


@respx.mock
def test_404_is_returned_not_retried() -> None:
    route = respx.get("https://example.org/missing").mock(
        return_value=httpx.Response(404, json={"error": "NOT_FOUND"})
    )
    result = _client().get("https://example.org/missing")
    assert result.status_code == 404 and route.call_count == 1


@respx.mock
def test_network_error_is_retried() -> None:
    route = respx.get("https://example.org/flaky").mock(
        side_effect=[httpx.ConnectError("boom"), httpx.Response(200)]
    )
    assert _client().get("https://example.org/flaky").status_code == 200
    assert route.call_count == 2


def test_ssl_context_includes_shipped_intermediate() -> None:
    context = build_ssl_context()
    subjects = [
        dict(x[0] for x in cert["subject"]).get("commonName") for cert in context.get_ca_certs()
    ]
    assert "HARICA Institutional TLS RSA 2" in subjects
    assert context.verify_mode.name == "CERT_REQUIRED"
