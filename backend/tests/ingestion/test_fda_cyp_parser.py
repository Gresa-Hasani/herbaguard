"""FDA CYP/transporter table parser on a CAPTURED excerpt of the real page (see
tests/fixtures/captured/README.md): 33 of the 245 rows of Table 1, both legends and all footnotes,
exactly as served on 2026-11-02."""

from __future__ import annotations

from pathlib import Path

import pytest

from herbaguard.domain.enums import DrugTargetRole, Potency
from herbaguard.ingestion.parsers.fda_cyp_table import (
    FdaTable,
    FdaTableFormatError,
    Row,
    parse_fda_cyp_table,
)

FIXTURE = (
    Path(__file__).parents[1] / "fixtures" / "captured" / "fda_cyp_transporter_table_excerpt.html"
)


@pytest.fixture(scope="module")
def table() -> FdaTable:
    return parse_fda_cyp_table(FIXTURE.read_text(encoding="utf-8"))


def row(table: FdaTable, name: str, occurrence: int = 0) -> Row:
    return [r for r in table.rows if r.name.lower() == name.lower()][occurrence]


def test_page_metadata(table: FdaTable) -> None:
    assert len(table.rows) == 33
    assert table.content_current_as_of is not None
    assert table.content_current_as_of.isoformat() == "2026-05-29"
    assert len(table.footnotes) == 21
    assert table.footnotes["18"].startswith("The effect of St. John's wort varies widely")
    assert table.footnotes["19"] == "S-warfarin"
    assert any(d.category == "Strong Inhibitor" and "≥5-fold" in d.text for d in table.definitions)
    assert any(d.category == "P-gp" and d.kind == "Substrate" for d in table.definitions)


def test_column_decides_role_and_potency(table: FdaTable) -> None:
    (entry,) = row(table, "midazolam").entries
    assert entry.column.role is DrugTargetRole.SENSITIVE_SUBSTRATE
    assert entry.targets == ("CYP3A",)
    (entry,) = row(table, "St. John's wort").entries
    assert (entry.column.role, entry.column.potency, entry.targets) == (
        DrugTargetRole.INDUCER, Potency.STRONG, ("CYP3A",),
    )  # fmt: skip


def test_several_targets_and_separators(table: FdaTable) -> None:
    rifampin = {e.column.header: e for e in row(table, "rifampin").entries}
    assert rifampin["CYP Strg IND"].targets == ("CYP3A", "CYP2C19")
    # "1A2, 2B6; 2C8; 2C9" mixes commas and semicolons
    assert rifampin["CYP Mod IND"].targets == ("CYP1A2", "CYP2B6", "CYP2C8", "CYP2C9")
    # footnote markers inside the cell ("OATP1B1<sup>13</sup>") are footnotes, not targets
    assert rifampin["TRNSP INH"].targets == ("SLCO1B1", "SLCO1B3")
    assert rifampin["TRNSP INH"].footnote_refs == ("13",)
    loperamide = {e.column.header: e for e in row(table, "Loperamide").entries}
    assert loperamide["CYP Mod SENS SUB"].targets == ("CYP2C8", "CYP3A")  # "2C8 and 3A"
    assert loperamide["TRNSP SUB"].targets == ("ABCB1",)  # "P-gp transporter substrate"


def test_transporter_aliases(table: FdaTable) -> None:
    resmetirom = {e.column.header: e for e in row(table, "resmetirom").entries}
    # "OATP1B transporters" = OATP1B1 and OATP1B3
    assert resmetirom["TRNSP INH"].targets == ("ABCG2", "SLCO1B1", "SLCO1B3")
    teriflunomide = {e.column.header: e for e in row(table, "teriflunomide").entries}
    assert teriflunomide["TRNSP INH"].targets == ("ABCG2", "SLCO1B1", "SLC22A8")
    curcumin = row(table, "curcumin").entries[0]
    assert (curcumin.column.role, curcumin.targets) == (DrugTargetRole.INHIBITOR, ("ABCG2",))


def test_footnotes_on_names(table: FdaTable) -> None:
    assert row(table, "ritonavir").footnote_refs == ("14", "15", "16")
    warfarin = row(table, "warfarin")
    assert warfarin.footnote_refs == ("19",)
    assert table.footnote_text(warfarin.footnote_refs) == "[19] S-warfarin"
    assert row(table, "dabigatran etexilate").name == "dabigatran etexilate"  # &nbsp; decoded


def test_unparsed_cell_words_are_reported_not_guessed(table: FdaTable) -> None:
    cenobamate = {e.column.header: e for e in row(table, "cenobamate").entries}
    entry = cenobamate["CYP Mod IND"]  # "CYP3A moderate inducer b"
    assert entry.targets == ("CYP3A",)
    assert entry.unparsed == ("b",)


def test_duplicate_rows_are_kept(table: FdaTable) -> None:
    first, second = (r for r in table.rows if r.name == "aprepitant")
    assert {e.column.header for e in first.entries} == {"CYP WK IND", "CYP Mod SENS SUB"}
    assert {e.column.header for e in second.entries} == {"CYP Mod INH"}


def test_unexpected_header_fails_loudly() -> None:
    html = FIXTURE.read_text(encoding="utf-8").replace(">CYP WK IND<", ">CYP Weak Inducer<")
    with pytest.raises(FdaTableFormatError, match="Unexpected Table 1 header"):
        parse_fda_cyp_table(html)


def test_missing_table_fails_loudly() -> None:
    with pytest.raises(FdaTableFormatError, match="not found"):
        parse_fda_cyp_table("<main><p>Page moved</p></main>")
