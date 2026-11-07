"""LiverTox ingestion — hepatotoxicity evidence (NIDDK/NLM, NCBI Bookshelf NBK547852).

Input: the LiverTox book download in ``data/raw/livertox/`` — one NXML (BITS XML) file per chapter
and the agent master list ``masterlist*.xlsx`` (never modified; SHA-256 recorded per file). PDFs,
images and DOCX files duplicate or illustrate the NXML content and are skipped (counted).

Rules (docs/data/external-datasets.md):

* ``livertox_agent`` — one entity per master-list row (every column kept verbatim, including
  LiverTox's own **likelihood score A–E/X**). That score grades how likely an agent is to cause
  clinically apparent liver injury; it is *not* HerbaGuard's A–E interaction class and is never
  mapped to it. Herbal and dietary supplement agents are mapped to a HerbaGuard taxon by exact name,
  other agents to a HerbaGuard drug by exact name; everything else stays unresolved for review.
* ``livertox_chapter`` — one entity per chapter: id, title, update date, the likelihood score
  statements as written, the verbatim Hepatotoxicity / Mechanism of Injury / Outcome and Management
  sections, and the cited PMIDs. LiverTox is copyright free (NIDDK; acknowledgement requested).
* ``described_in`` relation from an agent to its chapter when the chapter title or file id
  matches the master list. Master-list scores and chapter statements are both kept as written; a
  difference is reported, never reconciled.
* Hepatotoxicity is kept apart from interaction evidence: nothing here is written to
  ``interaction_assertion`` or read by the A–E classification.
"""

from __future__ import annotations

import re
import warnings
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any

import openpyxl
from bs4 import BeautifulSoup, Tag, XMLParsedAsHTMLWarning

from herbaguard.domain.enums import IssueSeverity
from herbaguard.ingestion.context import IngestionContext
from herbaguard.ingestion.pipelines.external_common import (
    UNRESOLVED,
    DrugMatcher,
    ExternalWriter,
    HerbMatcher,
    Mapping,
    delete_stale,
)

SOURCE = "livertox"
DOWNLOAD_PAGE = "https://www.ncbi.nlm.nih.gov/books/NBK547852/"
CHAPTER_URL = "https://www.ncbi.nlm.nih.gov/books/n/livertox/{}/"
SECTIONS = {
    "hepatotoxicity": "hepatotoxicity",
    "mechanism of injury": "mechanism_of_injury",
    "outcome and management": "outcome_and_management",
}
LIKELIHOOD = re.compile(r"Likelihood score:\s*([A-EX]\*?(?:\s*\[HD\])?)\s*(\([^)]*\))?", re.I)
SKIPPED_SUFFIXES = (".pdf", ".jpg", ".jpeg", ".png", ".gif", ".docx", ".doc")


def compact(text: str | None) -> str:
    """Key for linking a master-list row to a chapter document (letters and digits only)."""
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def _text(node: Tag | None) -> str | None:
    if node is None:
        return None
    return re.sub(r"\s+", " ", node.get_text(" ")).strip() or None


def parse_chapter(xml: str) -> dict[str, Any] | None:
    """Fields of one LiverTox chapter (BITS XML); None if the file is not a book-part chapter."""
    # Deliberately the stdlib-based HTML parser: no extra dependency (lxml) and no XML entity
    # expansion; the chapters use plain, lower-case element names, which it reads correctly.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", XMLParsedAsHTMLWarning)
        soup = BeautifulSoup(xml, "html.parser")
    meta = soup.find("book-part-meta")
    if not isinstance(meta, Tag):
        return None
    # Most chapters state their id in <book-part-id>; some only in the wrapper's id attribute.
    wrapper = soup.find("book-part-wrapper")
    chapter_id = _text(meta.find("book-part-id")) or (
        str(wrapper.get("id") or "").strip() if isinstance(wrapper, Tag) else ""
    )
    if not chapter_id:
        return None
    title_group = meta.find("title-group")
    updated = meta.find("date", attrs={"date-type": "updated"})
    updated_on = None
    if isinstance(updated, Tag):
        parts = [_text(updated.find(k)) for k in ("year", "month", "day")]
        if all(p and p.isdigit() for p in parts):
            updated_on = date(int(parts[0]), int(parts[1]), int(parts[2])).isoformat()  # type: ignore[arg-type]
    body = soup.find("body") or soup
    sections: dict[str, str] = {}
    for sec in body.find_all("sec") if isinstance(body, Tag) else []:
        heading = _text(sec.find("title", recursive=False))
        field = SECTIONS.get((heading or "").strip().lower())
        if field and field not in sections:
            text = _text(sec)
            if text and heading and text.startswith(heading):
                text = text[len(heading) :].strip()
            if text:
                sections[field] = text
    full_text = _text(body) or ""
    likelihood = [
        {"score": re.sub(r"\s+", "", m.group(1)).upper(), "statement": m.group(0).strip()}
        for m in LIKELIHOOD.finditer(full_text)
    ]
    pmids = sorted(
        {
            p.get_text().strip()
            for p in soup.find_all("pub-id", attrs={"pub-id-type": "pmid"})
            if p.get_text().strip().isdigit()
        },
        key=int,
    )
    return {
        "chapter_id": chapter_id,
        "title": _text(title_group.find("title")) if isinstance(title_group, Tag) else None,
        "updated_on": updated_on,
        "likelihood": likelihood,
        "sections": sections,
        "cited_pmids": pmids,
    }


def _cell(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, str):
        return value.strip()
    return value


def read_master_list(path: Path) -> tuple[list[str], list[tuple[int, dict[str, Any]]]]:
    sheet = openpyxl.load_workbook(path, read_only=True, data_only=True).worksheets[0]
    rows = list(sheet.iter_rows(values_only=True))
    header_index = next(
        (i for i, r in enumerate(rows) if r and "Ingredient" in [str(c).strip() for c in r if c]),
        None,
    )
    if header_index is None:
        msg = f"{path.name}: no header row with an 'Ingredient' column"
        raise ValueError(msg)
    header = [str(c).strip() if c is not None else "" for c in rows[header_index]]
    out = []
    for number, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
        record = {
            h: _cell(v)
            for h, v in zip(header, row, strict=False)
            if h and v is not None and v != ""
        }
        out.append((number, record))
    return header, out


def run(ctx: IngestionContext, directory: Path) -> None:
    writer = ExternalWriter(ctx, SOURCE, DOWNLOAD_PAGE)
    stats: Counter[str] = ctx.stats
    herbs, drugs = HerbMatcher(ctx.session), DrugMatcher(ctx.session)
    licence = directory / "license.txt"
    if licence.is_file():
        writer.register(licence, "data/raw/livertox/license.txt", "text/plain")

    # 1. chapters
    chapters: dict[str, dict[str, Any]] = {}
    chapter_keys: dict[str, str] = {}
    for path in sorted(directory.iterdir()):
        suffix = path.suffix.lower()
        if suffix in SKIPPED_SUFFIXES:
            stats[f"files_skipped_{suffix.lstrip('.')}"] += 1
            continue
        if suffix != ".nxml":
            continue
        stats["chapter_files"] += 1
        record = writer.register(path, f"data/raw/livertox/{path.name}", "application/xml")
        try:
            parsed = parse_chapter(path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            parsed = None
            ctx.issue(
                "livertox_chapter_unreadable", f"{path.name}: {type(exc).__name__}", record=record
            )
        if parsed is None:
            stats["chapter_files_rejected"] += 1
            continue
        cid = parsed["chapter_id"]
        if cid in chapters:
            stats["chapter_duplicate_ids"] += 1
            continue
        stats["chapters_with_likelihood" if parsed["likelihood"] else "chapters_overview"] += 1
        attributes = {**parsed, "file": path.name, "url": CHAPTER_URL.format(cid)}
        chapters[cid] = writer.entity("livertox_chapter", cid, parsed["title"], attributes,
                                      {"livertox_chapter": cid, "pmids": parsed["cited_pmids"]}, record, [],
                                      Mapping("not_applicable", note="A document; agents are mapped, not chapters."))  # fmt: skip
        for key in {compact(cid), compact(parsed["title"])} - {""}:
            chapter_keys.setdefault(key, cid)
    writer.upsert_entities(list(chapters.values()))

    # 2. master list agents
    masters = sorted(directory.glob("masterlist*.xlsx"))
    if not masters:
        msg = f"LiverTox master list (masterlist*.xlsx) missing in {directory}"
        raise FileNotFoundError(msg)
    master = masters[-1]
    record = writer.register(
        master,
        f"data/raw/livertox/{master.name}",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    _, rows = read_master_list(master)
    agents: dict[str, dict[str, Any]] = {}
    relations: list[dict[str, Any]] = []
    for number, row in rows:
        ingredient = row.get("Ingredient")
        count = row.get("Count")
        if (
            not isinstance(ingredient, str)
            or not ingredient
            or ingredient == "Ingredient"
            or not isinstance(count, int)
        ):
            stats["agent_rows_skipped_non_agent"] += 1  # repeated headers, totals, blank rows
            continue
        stats["agent_rows"] += 1
        key = compact(ingredient)
        if key in agents:
            agents[key]["source_row_numbers"].append(number)
            stats["agent_rows_duplicate"] += 1
            if agents[key]["attributes"] != row:
                ctx.issue("livertox_agent_conflicting_rows",
                          f"'{ingredient}' appears on several master-list rows with different values; the first is kept.",
                          severity=IssueSeverity.WARNING, record=record, row=number)  # fmt: skip
            continue
        is_hds = str(row.get("Primary Classification", "")).upper().startswith("HDS")
        mapping = herbs.map(ingredient) if is_hds else drugs.map(ingredient)
        if is_hds and mapping.status == UNRESOLVED:
            stats["agents_hds_not_curated"] += 1
        agents[key] = writer.entity("livertox_agent", key, ingredient, row,
                                    {"livertox_agent": ingredient}, record, [number], mapping)  # fmt: skip
        chapter = chapter_keys.get(compact(str(row.get("Chapter Title", "")))) or chapter_keys.get(
            key
        )
        if chapter is None:
            stats["agents_without_chapter_file"] += 1
            continue
        stated = [x["score"] for x in chapters[chapter]["attributes"]["likelihood"]]
        score = str(row.get("Likelihood Score", "")).replace(" ", "").upper()
        if len(stated) == 1 and score and stated[0] != score:
            stats["agents_score_differs_from_chapter"] += 1
            ctx.issue("livertox_score_differs",
                      f"'{ingredient}': master list '{row.get('Likelihood Score')}', chapter '{stated[0]}'; both kept.",
                      severity=IssueSeverity.INFO, record=record, row=number)  # fmt: skip
        relations.append(writer.relation(writer.entity_id("livertox_agent", key), "described_in",
                                         writer.entity_id("livertox_chapter", chapter),
                                         {"master_list_chapter_title": row.get("Chapter Title")}, record, [number]))  # fmt: skip
    writer.upsert_entities(list(agents.values()))
    stats["relations_stored"] = writer.upsert_relations(relations)

    # 3. stale rows of earlier downloads (only after an error-free run)
    delete_stale(
        ctx,
        SOURCE,
        {e["id"] for e in [*chapters.values(), *agents.values()]},
        {r["id"] for r in relations},
    )
    ctx.session.flush()
