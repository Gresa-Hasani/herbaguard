"""Parser for the EMA herbal inventory spreadsheet ("Download medicine data", herbal report).

Verified on 2026-11-02: one sheet; a few metadata rows; a header row starting with
"Latin name"; 251 data rows. Some rows are exact duplicates (e.g. 'Crataegi folium cum flore'
appears four times) and are de-duplicated by (Latin name, Combination, URL).
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import openpyxl

EXPECTED_COLUMNS = (
    "Latin name",
    "Combination",
    "English common name",
    "Botanical name",
    "Therapeutic area",
    "Status",
    "Outcome of European assessment",
    "Herbal medicine URL",
)


class InventoryFormatError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class InventoryRow:
    latin_name: str
    combination: bool
    english_name: str | None
    botanical_name: str | None
    therapeutic_area: str | None
    status: str | None
    outcome: str | None
    first_published: str | None
    last_updated: str | None
    url: str
    row_number: int


def parse_inventory(content: bytes) -> list[InventoryRow]:
    workbook = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    sheet = workbook.worksheets[0]
    rows = list(sheet.iter_rows(values_only=True))
    header_index = next(
        (i for i, row in enumerate(rows) if row and str(row[0] or "").strip() == "Latin name"), None
    )
    if header_index is None:
        msg = "Header row starting with 'Latin name' not found"
        raise InventoryFormatError(msg)
    header = [str(c).strip() if c is not None else "" for c in rows[header_index]]
    missing = [c for c in EXPECTED_COLUMNS if c not in header]
    if missing:
        msg = f"Inventory columns missing: {missing}"
        raise InventoryFormatError(msg)
    col = {name: header.index(name) for name in header if name}

    def cell(row: tuple[object, ...], name: str) -> str | None:
        i = col.get(name)
        if i is None or i >= len(row) or row[i] is None:
            return None
        text = str(row[i]).strip()
        return text or None

    seen: set[tuple[str, str, str]] = set()
    result: list[InventoryRow] = []
    for offset, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
        latin = cell(row, "Latin name")
        url = cell(row, "Herbal medicine URL")
        if not latin or not url:
            continue
        combination = (cell(row, "Combination") or "").lower() == "yes"
        key = (latin, str(combination), url)
        if key in seen:
            continue
        seen.add(key)
        result.append(
            InventoryRow(
                latin_name=latin,
                combination=combination,
                english_name=cell(row, "English common name"),
                botanical_name=cell(row, "Botanical name"),
                therapeutic_area=cell(row, "Therapeutic area"),
                status=cell(row, "Status"),
                outcome=cell(row, "Outcome of European assessment"),
                first_published=cell(row, "First published date"),
                last_updated=cell(row, "Last updated date"),
                url=url,
                row_number=offset,
            )
        )
    return result


def find_monograph_links(html: str) -> tuple[list[str], list[str]]:
    """From an EMA herbal page: (final non-superseded monograph PDF links, all monograph links)."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    links = sorted(
        {
            a["href"]
            for a in soup.find_all("a", href=True)
            if "/herbal-monograph/" in str(a["href"]) and str(a["href"]).endswith(".pdf")
        }
    )
    texts = [str(link) for link in links]
    finals = [link for link in texts if "draft" not in link and "superseded" not in link]
    return finals, texts
