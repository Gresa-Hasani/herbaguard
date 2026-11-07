"""SUPP.AI, LiverTox and NIH DSLD ingestion on the seeded test database.

Fixtures in tests/fixtures/{supp_ai,livertox,nih_dsld}/ use the real file formats (SUPP.AI's
4-space-indented JSON, LiverTox BITS XML chapters and master-list columns, the exact DSLD CSV
headers) with synthetic rows: resolved, candidate, ambiguous and unmatched names; duplicates;
rejected rows; a retracted paper; a master-list score that differs from its chapter. The real
downloads are never read by the tests. The LiverTox master list is written as .xlsx at test time.
"""

from __future__ import annotations

import hashlib
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import openpyxl
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from herbaguard.core.config import Settings
from herbaguard.ingestion.context import run_ingestion
from herbaguard.ingestion.loaders import ensure_sources
from herbaguard.ingestion.pipelines import ddid, livertox, nih_dsld, supp_ai
from herbaguard.models import (
    DataQualityIssue,
    Drug,
    EvidenceItem,
    ExperimentalObservation,
    ExternalEntity,
    ExternalRelation,
    InteractionAssertion,
    SourceRecord,
    Taxon,
)

pytestmark = pytest.mark.db
FIXTURES = Path(__file__).parents[1] / "fixtures"
PIPELINES: dict[str, Callable[..., None]] = {
    "supp_ai": supp_ai.run,
    "livertox": livertox.run,
    "nih_dsld": nih_dsld.run,
    "ddid": ddid.run,
}
MASTER_HEADER = ["Count", "Ingredient", "Brand Name", "Likelihood Score", "Chapter Title", "Last Update",
                 "Year Approved", "In LiverTox", "Primary Classification", "Secondary Classification"]  # fmt: skip


def write_master_list(folder: Path) -> None:
    book = openpyxl.Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.append(
        ["Drugs for LiverTox: Drug Classes", None, None, None, "Last Update: January 30, 2026"]
    )
    sheet.append(MASTER_HEADER)
    sheet.append(
        [
            1,
            "St John's Wort",
            "Generic",
            "D",
            "St. John's Wort",
            None,
            "NA",
            1,
            "HDS: Herbal Product",
            "Antidepressant",
        ]
    )
    sheet.append(
        [2, "Warfarin", "Coumadin", "C", "Warfarin", None, 1954, 1, "Hematologic", "Anticoagulant"]
    )
    sheet.append(
        [3, "Hawthorn", "Generic", "E", "Hawthorn", None, "NA", 1, "HDS: Herbal Product", "Cardiac"]
    )
    sheet.append(
        [4, "Unknownmab", "Brand", "X", "Unknownmab", None, 2025, 0, "Oncology", "Antibody"]
    )
    sheet.append(MASTER_HEADER)  # repeated header row inside the sheet
    sheet.append(
        [
            5,
            "St John's Wort",
            "Other brand",
            "E",
            "St. John's Wort",
            None,
            "NA",
            1,
            "HDS: Herbal Product",
            "Antidepressant",
        ]
    )
    sheet.append([None, None, None, None, None, None, None, 1705])  # totals row
    book.save(folder / "masterlist02-26.xlsx")


@pytest.fixture
def folders(tmp_path: Path) -> dict[str, Path]:
    out = {}
    for name in ("supp_ai", "livertox", "nih_dsld", "ddid"):
        out[name] = tmp_path / name
        shutil.copytree(FIXTURES / name, out[name])
    write_master_list(out["livertox"])
    return out


def run_import(session: Session, source: str, folder: Path) -> dict[str, int]:
    ensure_sources(session)
    with run_ingestion(session, source, Settings(_env_file=None)) as ctx:  # type: ignore[call-arg]
        PIPELINES[source](ctx, folder)
        return dict(ctx.stats)


def entity(session: Session, source: str, kind: str, external_id: str) -> ExternalEntity:
    return session.scalars(select(ExternalEntity).where(
        ExternalEntity.source_code == source, ExternalEntity.kind == kind,
        ExternalEntity.external_id == external_id)).one()  # fmt: skip


def relations(session: Session, source: str) -> list[ExternalRelation]:
    return list(
        session.scalars(select(ExternalRelation).where(ExternalRelation.source_code == source))
    )


def taxon_id(session: Session, name: str) -> Any:
    return session.scalar(select(Taxon.id).where(Taxon.scientific_name == name))


# --------------------------------------------------------------------------- SUPP.AI


def test_supp_ai_counts_mapping_and_provenance(db_session: Session, seeded: dict[str, object],
                                               folders: dict[str, Path]) -> None:  # fmt: skip
    stats = run_import(db_session, "supp_ai", folders["supp_ai"])
    assert (
        stats["supplements_in_release"] == 4 and stats["supplements_skipped_no_curated_herb"] == 1
    )
    assert stats["pairs_kept"] == 4 and stats["pairs_skipped_supplement_supplement"] == 1
    assert stats["pairs_rejected_unknown_cui"] == 1
    assert stats["sentences_read"] == 7 and stats["relations_stored"] == 5
    assert stats["sentences_duplicate_uid"] == 1 and stats["sentences_rejected_incomplete"] == 1
    assert stats["sentences_from_retracted_papers"] == 1 and stats["papers_missing_metadata"] == 1

    sjw = entity(db_session, "supp_ai", "supplement", "C0813171")
    assert (sjw.mapping_status, sjw.mapped_table, sjw.mapping_method) == (
        "resolved",
        "taxon",
        "exact_common_name",
    )
    assert sjw.mapped_id == taxon_id(db_session, "Hypericum perforatum")
    assert sjw.identifiers == {"umls_cui": "C0813171"} and sjw.attributes["synonyms"] == [
        "Hypericum",
        "SJW",
    ]
    cohosh = entity(db_session, "supp_ai", "supplement", "C0771967")
    assert cohosh.mapping_status == "candidate"  # only the UMLS synonym "Black cohosh" matches
    assert (
        entity(db_session, "supp_ai", "supplement", "C9000001").mapping_status == "ambiguous"
    )  # hawthorn
    warfarin = entity(db_session, "supp_ai", "drug", "C0043031")
    assert warfarin.mapping_status == "resolved" and warfarin.mapping_method == "exact_name"
    assert entity(db_session, "supp_ai", "drug", "C0074393").mapping_method == "exact_synonym"
    assert entity(db_session, "supp_ai", "drug", "C9000003").mapping_status == "unresolved"

    rels = relations(db_session, "supp_ai")
    assert {r.predicate for r in rels} == {"interaction_mentioned"}
    retracted = next(
        r for r in rels if r.attributes["paper"] and r.attributes["paper"]["retraction"]
    )
    assert (
        retracted.attributes["sentence"]["uid"] == 101
        and retracted.attributes["paper"]["pmid"] == 900002
    )
    assert "not a confirmed interaction" in retracted.attributes["extraction"]
    assert all(r.source_row_numbers and r.source_row_numbers[0] > 1 for r in rels)
    records = db_session.scalars(
        select(SourceRecord).where(SourceRecord.source_code == "supp_ai")
    ).all()
    assert len(records) == 5
    path = folders["supp_ai"] / "sentence_dict.json"
    assert (
        next(r for r in records if r.native_id == path.name).content_sha256
        == hashlib.sha256(path.read_bytes()).hexdigest()
    )


def test_supp_ai_rejects_an_unexpected_file_layout(db_session: Session, seeded: dict[str, object],
                                                   folders: dict[str, Path]) -> None:  # fmt: skip
    path = folders["supp_ai"] / "sentence_dict.json"
    path.write_text(
        path.read_text(encoding="utf-8").replace("\n", ""), encoding="utf-8"
    )  # one-line JSON
    with pytest.raises(ValueError, match=r"format changed|own line"):
        run_import(db_session, "supp_ai", folders["supp_ai"])


# --------------------------------------------------------------------------- LiverTox


def test_livertox_chapters_agents_and_scores(db_session: Session, seeded: dict[str, object],
                                             folders: dict[str, Path]) -> None:  # fmt: skip
    stats = run_import(db_session, "livertox", folders["livertox"])
    assert stats["chapter_files"] == 4 and stats["chapter_files_rejected"] == 1
    assert stats["chapters_with_likelihood"] == 2 and stats["chapters_overview"] == 1
    assert stats["files_skipped_pdf"] == 1 and stats["files_skipped_jpg"] == 1
    assert stats["agent_rows"] == 5 and stats["agent_rows_duplicate"] == 1
    assert stats["agent_rows_skipped_non_agent"] == 2  # repeated header + totals row
    assert (
        stats["agents_without_chapter_file"] == 2
        and stats["agents_score_differs_from_chapter"] == 1
    )
    assert stats["relations_stored"] == 2

    chapter = entity(db_session, "livertox", "livertox_chapter", "StJohnsWort")
    assert chapter.label == "St. John's Wort" and chapter.attributes["updated_on"] == "2020-03-28"
    assert chapter.attributes["likelihood"] == [{"score": "E", "statement":
        "Likelihood score: E (unlikely cause of clinically apparent liver injury)"}]  # fmt: skip
    assert chapter.attributes["sections"]["hepatotoxicity"].startswith(
        "Synthetic hepatotoxicity text"
    )
    assert chapter.identifiers["pmids"] == ["900001", "900002"]

    sjw = entity(db_session, "livertox", "livertox_agent", "stjohnswort")
    assert sjw.mapping_status == "resolved" and sjw.mapped_id == taxon_id(
        db_session, "Hypericum perforatum"
    )
    assert sjw.attributes["Likelihood Score"] == "D" and sjw.source_row_numbers == [
        3,
        8,
    ]  # first row kept
    warfarin = entity(db_session, "livertox", "livertox_agent", "warfarin")
    assert warfarin.mapped_table == "drug"
    assert warfarin.mapped_id == db_session.scalar(select(Drug.id).where(Drug.name == "warfarin"))
    assert (
        entity(db_session, "livertox", "livertox_agent", "hawthorn").mapping_status == "ambiguous"
    )
    assert (
        entity(db_session, "livertox", "livertox_agent", "unknownmab").mapping_status
        == "unresolved"
    )
    rules = set(db_session.scalars(select(DataQualityIssue.rule)))
    assert {"livertox_score_differs", "livertox_agent_conflicting_rows"} <= rules


# --------------------------------------------------------------------------- NIH DSLD


def test_dsld_products_ingredients_and_labels(db_session: Session, seeded: dict[str, object],
                                              folders: dict[str, Path]) -> None:  # fmt: skip
    stats = run_import(db_session, "nih_dsld", folders["nih_dsld"])
    assert stats["facts_rows"] == 9 and stats["labels_with_curated_herb"] == 4
    assert stats["labels_in_download"] == 5 and stats["labels_skipped_no_curated_herb"] == 2
    assert stats["overview_rows_rejected_no_id"] == 1 and stats["labels_without_overview_row"] == 1
    assert stats["relations_stored"] == 5 and stats["relations_duplicate_rows"] == 1
    assert stats["files_skipped_company_information"] == 1 and stats["label_statements_stored"] == 2

    product = entity(db_session, "nih_dsld", "dsld_product", "1001")
    assert (
        product.label == "SJW 300"
        and product.identifiers["url"] == "https://dsld.od.nih.gov/label/1001"
    )
    assert product.attributes["label_statements"][0]["Statement"].startswith(
        "Consult your physician"
    )
    assert (
        len(product.attributes["supplement_facts"]) == 2
    )  # full composition, not only the herb row
    assert product.mapping_status == "not_applicable"
    sjw = entity(db_session, "nih_dsld", "dsld_ingredient", "st john's wort")
    assert sjw.mapping_status == "resolved" and sjw.mapped_id == taxon_id(
        db_session, "Hypericum perforatum"
    )
    assert (
        entity(db_session, "nih_dsld", "dsld_ingredient", "hawthorn").mapping_status == "ambiguous"
    )
    assert (
        entity(db_session, "nih_dsld", "dsld_ingredient", "black cohosh").mapping_status
        == "resolved"
    )
    link = next(r for r in relations(db_session, "nih_dsld") if r.subject_id == product.id)
    assert (link.predicate, link.attributes["Amount Per Serving"], link.attributes["Amount Per Serving Unit"]) == \
        ("lists_ingredient", "300", "mg")  # fmt: skip


def test_dsld_changed_file_removes_stale_rows(db_session: Session, seeded: dict[str, object],
                                              folders: dict[str, Path]) -> None:  # fmt: skip
    run_import(db_session, "nih_dsld", folders["nih_dsld"])
    facts = folders["nih_dsld"] / "DietarySupplementFacts_1.csv"
    facts.write_text("\n".join(line for line in facts.read_text(encoding="utf-8").splitlines()
                               if ",1002," not in line) + "\n", encoding="utf-8")  # fmt: skip
    stats = run_import(db_session, "nih_dsld", folders["nih_dsld"])
    assert stats["entities_stale_removed"] == 2  # product 1002 and the hawthorn ingredient
    assert db_session.scalar(select(func.count()).select_from(ExternalEntity).where(
        ExternalEntity.source_code == "nih_dsld", ExternalEntity.external_id == "1002")) == 0  # fmt: skip


# --------------------------------------------------------------------------- all three


def _snapshot(session: Session, source: str) -> tuple[int, int, int]:
    return (
        session.scalar(select(func.count()).select_from(ExternalEntity).where(ExternalEntity.source_code == source)) or 0,
        session.scalar(select(func.count()).select_from(ExternalRelation).where(ExternalRelation.source_code == source)) or 0,
        session.scalar(select(func.count()).select_from(SourceRecord).where(SourceRecord.source_code == source)) or 0,
    )  # fmt: skip


@pytest.mark.parametrize("source", ["supp_ai", "livertox", "nih_dsld"])
def test_reimport_is_idempotent(db_session: Session, seeded: dict[str, object], folders: dict[str, Path],
                                source: str) -> None:  # fmt: skip
    run_import(db_session, source, folders[source])
    first = _snapshot(db_session, source)
    stats = run_import(db_session, source, folders[source])
    assert _snapshot(db_session, source) == first
    assert stats.get("source_records_new", 0) == 0 and stats["source_records_unchanged"] == first[2]
    assert (
        stats.get("entities_stale_removed", 0) == 0 and stats.get("relations_stale_removed", 0) == 0
    )


def _evidence_state(session: Session) -> dict[str, Any]:
    def ids(model: Any, where: Any = None) -> list[str]:
        stmt = select(model.id) if where is None else select(model.id).where(where)
        return sorted(str(i) for i in session.scalars(stmt))

    return {
        "evidence_item": ids(EvidenceItem),
        "interaction_assertion": ids(InteractionAssertion),
        "experimental_observation": ids(ExperimentalObservation),
        "ddid_entities": ids(ExternalEntity, ExternalEntity.source_code == "ddid"),
        "ddid_relations": ids(ExternalRelation, ExternalRelation.source_code == "ddid"),
        "ema_nccih_text": sorted(
            (e.external_id, e.title or "")
            for e in session.scalars(
                select(EvidenceItem).where(EvidenceItem.source_code.in_(["ema_hmpc", "nccih"]))
            )
        ),
    }


def test_existing_evidence_and_classification_are_unchanged(
    db_session: Session,
    seeded: dict[str, object],
    folders: dict[str, Path],
    check: Callable[..., dict[str, Any]],
) -> None:
    run_import(db_session, "ddid", folders["ddid"])
    before = _evidence_state(db_session)
    classes_before = [
        r["classification"] for r in check("St John's wort", ["warfarin", "sertraline"])["results"]
    ]
    for source in ("supp_ai", "livertox", "nih_dsld"):
        run_import(db_session, source, folders[source])
    assert (
        _evidence_state(db_session) == before
    )  # no evidence items, assertions or DDID rows added or changed
    assert before["ema_nccih_text"]  # the seed has EMA evidence, so the comparison is not vacuous
    classes_after = [
        r["classification"] for r in check("St John's wort", ["warfarin", "sertraline"])["results"]
    ]
    assert classes_after == classes_before
