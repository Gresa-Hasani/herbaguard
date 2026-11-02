"""FDA "Examples of Drugs that Interact with CYP Enzymes and Transporter Systems" → typed rows.

Page (For Healthcare Professionals, content current as of 05/29/2026 when first parsed):
https://www.fda.gov/drugs/drug-interactions-labeling/healthcare-professionals-fdas-examples-drugs-interact-cyp-enzymes-and-transporter-systems

Table 1 has one row per drug or other substance and eleven columns. The column decides the role
(inhibitor / inducer / substrate) and, for CYP inhibitors and inducers, the potency; the cell lists
the enzymes or transporters (``"2D6; 3A  weak  inhibitor"``). Footnote markers are ``<sup>``
elements in the name or role cell. The parser is strict about the header (an unknown layout raises
``FdaTableFormatError``) and lenient about cell wording: anything it cannot read is returned in
``unparsed`` so the pipeline can record it as a data-quality issue instead of guessing.

No I/O. Input: the page HTML exactly as retrieved.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from datetime import date

from bs4 import BeautifulSoup, Tag

from herbaguard.domain.enums import DrugTargetRole, Potency
from herbaguard.ingestion.normalize.targets import find_targets, remove_mentions

PARSER_VERSION = "fda_cyp_table_v1"


class FdaTableFormatError(ValueError):
    """The page no longer has the expected Table 1 layout."""


@dataclass(frozen=True, slots=True)
class Column:
    header: str  # header text exactly as on the page, e.g. "CYP Strg INH"
    role: DrugTargetRole
    potency: Potency | None
    system: str  # "cyp" | "transporter"
    expected_words: tuple[str, ...]  # wording expected in a cell of this column


COLUMNS: tuple[Column, ...] = (
    Column("CYP Strg INH", DrugTargetRole.INHIBITOR, Potency.STRONG, "cyp", ("strong", "inhibitor")),
    Column("CYP Mod INH", DrugTargetRole.INHIBITOR, Potency.MODERATE, "cyp", ("moderate", "inhibitor")),
    Column("CYP WK INH", DrugTargetRole.INHIBITOR, Potency.WEAK, "cyp", ("weak", "inhibitor")),
    Column("CYP Strg IND", DrugTargetRole.INDUCER, Potency.STRONG, "cyp", ("strong", "inducer")),
    Column("CYP Mod IND", DrugTargetRole.INDUCER, Potency.MODERATE, "cyp", ("moderate", "inducer")),
    Column("CYP WK IND", DrugTargetRole.INDUCER, Potency.WEAK, "cyp", ("weak", "inducer")),
    Column("CYP SENS SUB", DrugTargetRole.SENSITIVE_SUBSTRATE, None, "cyp", ("sensitive", "substrate")),
    Column("CYP Mod SENS SUB", DrugTargetRole.MODERATELY_SENSITIVE_SUBSTRATE, None, "cyp",
           ("moderate", "substrate")),
    Column("TRNSP INH", DrugTargetRole.INHIBITOR, None, "transporter", ("inhibitor",)),
    Column("TRNSP SUB", DrugTargetRole.SUBSTRATE, None, "transporter", ("substrate",)),
)  # fmt: skip
NAME_HEADER = "Drug or Other Substance"
EXPECTED_HEADER = (NAME_HEADER, *(c.header for c in COLUMNS))

# Words that may legitimately appear in a role cell besides target names.
_KNOWN_WORDS = {
    "strong", "moderate", "moderately", "weak", "sensitive", "inhibitor", "inhibitors",
    "inducer", "inducers", "substrate", "substrates", "transporter", "transporters", "and",
}  # fmt: skip
_OPPOSITE_ROLE_WORD = {
    DrugTargetRole.INHIBITOR: ("inducer", "substrate"),
    DrugTargetRole.INDUCER: ("inhibitor", "substrate"),
    DrugTargetRole.SENSITIVE_SUBSTRATE: ("inhibitor", "inducer"),
    DrugTargetRole.MODERATELY_SENSITIVE_SUBSTRATE: ("inhibitor", "inducer"),
    DrugTargetRole.SUBSTRATE: ("inhibitor", "inducer"),
}


@dataclass(frozen=True, slots=True)
class CellEntry:
    column: Column
    cell_text: str  # normalised cell text without footnote markers
    targets: tuple[str, ...]  # target symbols, in order, de-duplicated
    target_labels: tuple[str, ...]  # the source's own spelling of each mention
    footnote_refs: tuple[str, ...]
    unparsed: tuple[str, ...] = ()  # leftover words the parser does not understand
    wording_note: str | None = None  # cell wording that disagrees with the column
    wrong_system: tuple[str, ...] = ()  # e.g. a transporter named in a CYP column (ignored)


@dataclass(frozen=True, slots=True)
class Row:
    index: int  # 1-based position in Table 1
    name: str  # normalised name, e.g. "St. John's wort"
    name_verbatim: str  # cell text as on the page (markers removed)
    footnote_refs: tuple[str, ...]
    entries: tuple[CellEntry, ...]


@dataclass(frozen=True, slots=True)
class Definition:
    legend: str  # e.g. "Table 2: Legend for Inhibitors, Inducers, and Substrates of CYP Enzymes"
    kind: str  # "Inhibitor" | "Inducer" | "Substrate"
    category: str  # e.g. "Strong Inhibitor", "P-gp"
    text: str


@dataclass(frozen=True, slots=True)
class FdaTable:
    rows: tuple[Row, ...]
    footnotes: dict[str, str]
    content_current_as_of: date | None
    definitions: tuple[Definition, ...] = field(default_factory=tuple)
    intro: tuple[str, ...] = field(default_factory=tuple)

    def footnote_text(self, refs: tuple[str, ...]) -> str | None:
        notes = [f"[{r}] {self.footnotes[r]}" for r in refs if r in self.footnotes]
        return " ".join(notes) or None


def normalise_text(value: str) -> str:
    """Collapse whitespace, decode (also double-encoded) non-breaking spaces, straighten quotes."""
    value = html.unescape(value).replace("\xa0", " ").replace("&nbsp;", " ")
    value = value.replace("’", "'").replace("‘", "'")
    return re.sub(r"\s+", " ", value).strip()


def _footnotes_in(cell: Tag) -> tuple[str, ...]:
    refs: list[str] = []
    for sup in cell.find_all("sup"):
        refs += re.findall(r"\d+", sup.get_text(" "))
        sup.decompose()
    return tuple(dict.fromkeys(refs))


def _parse_cell(column: Column, cell: Tag) -> CellEntry | None:
    refs = _footnotes_in(cell)
    text = normalise_text(cell.get_text(" "))
    if not text:
        return None
    mentions = find_targets(text, cyp_prefix_required=False)
    targets: list[str] = []
    labels: list[str] = []
    wrong: list[str] = []
    for mention in mentions:
        if mention.system != column.system:
            wrong.append(mention.verbatim)
            continue
        labels.append(mention.verbatim)
        for symbol in mention.symbols:
            if symbol not in targets:
                targets.append(symbol)
    leftover = remove_mentions(text, mentions)
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9-]*", leftover)
    lowered = [w.lower() for w in words]
    unparsed = tuple(
        w for w in words if w.lower() not in _KNOWN_WORDS and w.upper() != "CYP" and not w.isdigit()
    )
    # Digits left over are footnote numbers whose <sup> markup was lost.
    refs = tuple(dict.fromkeys([*refs, *(w for w in words if w.isdigit())]))
    note = None
    if any(word in lowered for word in _OPPOSITE_ROLE_WORD[column.role]):
        note = f"cell wording '{text}' names a different role than column '{column.header}'"
    elif column.potency is not None:
        stated = {p.value for p in Potency} & set(lowered)
        if stated and stated != {column.potency.value}:
            note = f"cell wording '{text}' states potency {sorted(stated)}, column says {column.potency.value}"
    return CellEntry(
        column=column,
        cell_text=text,
        targets=tuple(targets),
        target_labels=tuple(labels),
        footnote_refs=refs,
        unparsed=unparsed,
        wording_note=note,
        wrong_system=tuple(wrong),
    )


def _table_one(soup: BeautifulSoup) -> Tag:
    for table in soup.find_all("table"):
        head = table.find("thead") or table
        first = head.find("tr")
        if first is None:
            continue
        headers = tuple(normalise_text(th.get_text(" ")) for th in first.find_all(["th", "td"]))
        if headers and headers[0] == NAME_HEADER:
            if headers != EXPECTED_HEADER:
                msg = f"Unexpected Table 1 header: {headers!r}"
                raise FdaTableFormatError(msg)
            return table
    msg = "Table 1 ('Drug or Other Substance') not found"
    raise FdaTableFormatError(msg)


def _footnotes(soup: BeautifulSoup) -> dict[str, str]:
    heading = next(
        (h for h in soup.find_all(["h2", "h3"]) if normalise_text(h.get_text()) == "Footnotes"),
        None,
    )
    notes: dict[str, str] = {}
    if heading is None:
        return notes
    for sibling in heading.find_next_siblings():
        if sibling.name in ("h1", "h2", "h3"):
            break
        if sibling.name != "p":
            continue
        sup = sibling.find("sup")
        if sup is None:
            continue
        number = normalise_text(sup.get_text())
        sup.extract()
        text = normalise_text(sibling.get_text(" "))
        if number.isdigit() and text:
            notes[number] = text
    return notes


def _content_date(soup: BeautifulSoup) -> date | None:
    heading = next(
        (
            h
            for h in soup.find_all(["h2", "h3", "dt", "span"])
            if normalise_text(h.get_text()).startswith("Content current as of")
        ),
        None,
    )
    time = heading.find_next("time") if heading is not None else soup.find("time")
    value = time.get("datetime") if isinstance(time, Tag) else None
    if isinstance(value, str) and re.match(r"\d{4}-\d{2}-\d{2}", value):
        return date.fromisoformat(value[:10])
    return None


def _definitions(soup: BeautifulSoup) -> tuple[Definition, ...]:
    out: list[Definition] = []
    for table in soup.find_all("table"):
        first = table.find("tr")
        if first is None:
            continue
        headers = [normalise_text(c.get_text(" ")) for c in first.find_all(["th", "td"])]
        if len(headers) != 2 or headers[0] not in ("Potency Category", "Transporter System"):
            continue
        kind_heading = table.find_previous("h3")
        legend_heading = table.find_previous("h2")
        kind = normalise_text(kind_heading.get_text()) if kind_heading else ""
        legend = normalise_text(legend_heading.get_text()) if legend_heading else ""
        for row in table.find_all("tr")[1:]:
            cells = [normalise_text(c.get_text(" ")) for c in row.find_all(["td", "th"])]
            if len(cells) == 2 and cells[0] and cells[1]:
                out.append(Definition(legend, kind, cells[0], cells[1]))
    return tuple(out)


def _intro(soup: BeautifulSoup, table: Tag) -> tuple[str, ...]:
    paragraphs = []
    for p in table.find_all_previous("p"):
        text = normalise_text(p.get_text(" "))
        if text.startswith(("Drug-drug interactions", "Cytochrome P-450", "Table 1 provides",
                            "The field of metabolic", "This website contains")):  # fmt: skip
            paragraphs.append(text)
    return tuple(reversed(paragraphs))


def parse_fda_cyp_table(page_html: str) -> FdaTable:
    soup = BeautifulSoup(page_html, "html.parser")
    table = _table_one(soup)
    body = table.find("tbody") or table
    rows: list[Row] = []
    for index, tr in enumerate(
        (r for r in body.find_all("tr") if r.find("td") is not None), start=1
    ):
        cells = tr.find_all("td")
        if len(cells) != len(EXPECTED_HEADER):
            msg = f"Row {index} has {len(cells)} cells, expected {len(EXPECTED_HEADER)}"
            raise FdaTableFormatError(msg)
        name_refs = _footnotes_in(cells[0])
        verbatim = normalise_text(cells[0].get_text(" "))
        entries = tuple(
            entry
            for column, cell in zip(COLUMNS, cells[1:], strict=True)
            if (entry := _parse_cell(column, cell)) is not None
        )
        rows.append(Row(index, verbatim, verbatim, name_refs, entries))
    return FdaTable(
        rows=tuple(rows),
        footnotes=_footnotes(soup),
        content_current_as_of=_content_date(soup),
        definitions=_definitions(soup),
        intro=_intro(soup, table),
    )
