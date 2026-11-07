"""DDID (Drug–Diet Interaction Database) ingestion — first external experimental dataset.

Input: the five CSV files downloaded manually from https://bddg.hznu.edu.cn/ddid/download/ into
``data/raw/ddid/`` (never modified or copied; their SHA-256 is recorded in ``source_record``).

Rules (docs/data/ddid.md):

* Every original column is stored verbatim (``attributes`` / ``original``). Derived values are in
  separate columns with a rule version (``ddid_species_v1``) and never overwrite source values.
* Study context is derived from ``Experimental_Species`` only: Homo sapiens → human (CLIN);
  listed laboratory animals → animal (ANIMAL); "NA", empty or any other value → **unknown**
  (OTHER), never human. Unknown species values are reported.
* DDID's ``Effect`` label (Possible, No Effect, Positive, Negative, Harmful) is kept as the source's
  own label. It is not mapped to HerbaGuard's A–E classes, and nothing here is read by the A–E rules.
* Mappings: a herb to a HerbaGuard **taxon** only by exact scientific name (never to a herbal
  substance, whose plant part may differ); a drug to a HerbaGuard drug only by exact name or exact
  synonym; interaction ``Target_ID`` values (UniProt) only to ``target.uniprot_accession``. The TTD
  identifiers of the Target file are never joined to UniProt (no cross-reference in the data).
  Several candidates → ``ambiguous``; none → ``unresolved``. Both are kept for review.
* Exact duplicate rows are collapsed into one record that lists all source row numbers; rows that
  differ in any field are separate observations.
* Idempotent: deterministic ids and upserts; records from an earlier version of a file that are no
  longer present are removed (only after an error-free run).
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import uuid
from collections import defaultdict
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert

from herbaguard.domain.enums import EvidenceType, IssueSeverity
from herbaguard.ingestion.context import IngestionContext, stable_id
from herbaguard.ingestion.normalize.names import normalize_for_lookup
from herbaguard.models import (
    Drug,
    EvidenceItem,
    ExperimentalObservation,
    ExternalEntity,
    ExternalRelation,
    SourceRecord,
    Target,
    TaxonName,
)

SOURCE = "ddid"
DOWNLOAD_PAGE = "https://bddg.hznu.edu.cn/ddid/download/"
DERIVATION_RULE = "ddid_species_v1"
FILES = {
    "herb": "Herb Information.csv",
    "drug": "Drug Information.csv",
    "np": "NP Information.csv",
    "target": "Target Information.csv",
    "interaction": "Interaction Information.csv",
}
NA_VALUES = {"", "NA", "N/A", "NULL", "NONE", "-"}
HUMAN_SPECIES = {"homo sapiens", "human", "humans"}
ANIMAL_SPECIES = {
    "rat",
    "rats",
    "rabbit",
    "dog",
    "mice",
    "mouse",
    "pig",
    "zebrafish",
    "monkey",
    "beagle dog",
}
KNOWN_EFFECTS = {"possible", "no effect", "positive", "negative", "harmful"}
UNIPROT = re.compile(
    r"^(?:[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9](?:[A-Z][A-Z0-9]{2}[0-9]){1,2})$"
)
BATCH = 1000


def value(raw: str | None) -> str | None:
    """Source value with surrounding whitespace removed; the DDID placeholders become None."""
    if raw is None:
        return None
    text = raw.strip()
    return None if text.upper() in NA_VALUES else text


def sha(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=False).encode("utf-8")
    ).hexdigest()


def study_context(species: str | None) -> tuple[str, str]:
    """(derived_study_context, derived_evidence_type) from the species value only."""
    key = (species or "").strip().lower()
    if key in HUMAN_SPECIES:
        return "human", EvidenceType.CLINICAL_STUDY.value
    if key in ANIMAL_SPECIES:
        return "animal", EvidenceType.ANIMAL.value
    return "unknown", EvidenceType.OTHER.value


def read_rows(path: Path) -> Iterator[tuple[int, dict[str, str]]]:
    """Stream (CSV line number, row) without loading the file; header is line 1."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        yield from enumerate(csv.DictReader(handle), start=2)


def entity_id(kind: str, external_id: str) -> uuid.UUID:
    return stable_id("external_entity", SOURCE, kind, external_id)


class DdidImport:
    def __init__(self, ctx: IngestionContext, directory: Path) -> None:
        self.ctx = ctx
        self.session = ctx.session
        self.directory = directory
        self.records: dict[str, SourceRecord] = {}
        self.entities_seen: set[uuid.UUID] = set()
        self.target_by_accession = {
            t.uniprot_accession: str(t.id)
            for t in self.session.scalars(
                select(Target).where(Target.uniprot_accession.is_not(None))
            )
        }

    # ------------------------------------------------------------------ provenance
    def register(self, key: str) -> SourceRecord:
        path = self.directory / FILES[key]
        if not path.is_file():
            msg = f"DDID file missing: {path}"
            raise FileNotFoundError(msg)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        record = self.session.scalar(
            select(SourceRecord).where(SourceRecord.source_code == SOURCE, SourceRecord.native_id == FILES[key],
                                       SourceRecord.content_sha256 == digest)
        )  # fmt: skip
        if record is None:
            record = SourceRecord(
                id=uuid.uuid4(), source_code=SOURCE, ingestion_run_id=self.ctx.run.id, native_id=FILES[key],
                url=DOWNLOAD_PAGE, http_status=None, content_type="text/csv", content_sha256=digest,
                raw_path=str(path), request_parameters={"method": "manual_download",
                                                        "local_file": f"data/raw/ddid/{FILES[key]}"},
                retrieved_at=datetime.fromtimestamp(path.stat().st_mtime, tz=UTC),
            )  # fmt: skip
            self.session.add(record)
            self.session.flush()
            self.ctx.stats["source_records_new"] += 1
        self.records[key] = record
        return record

    # ------------------------------------------------------------------ entities
    def upsert_entities(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        stmt = insert(ExternalEntity).values(rows)
        update_cols = {
            c: stmt.excluded[c]
            for c in rows[0]
            if c not in ("id", "source_code", "kind", "external_id")
        }
        self.session.execute(
            stmt.on_conflict_do_update(
                index_elements=["id"], set_={**update_cols, "updated_at": func.now()}
            )
        )
        self.entities_seen |= {r["id"] for r in rows}

    def _entity(self, kind: str, external_id: str, label: str | None, attributes: dict[str, Any],
                identifiers: dict[str, Any], record: SourceRecord, rows: list[int], status: str,
                mapped: tuple[str, uuid.UUID] | None = None, method: str | None = None,
                note: str | None = None) -> dict[str, Any]:  # fmt: skip
        self.ctx.stats[f"entities_{kind}_{status}"] += 1
        return {
            "id": entity_id(kind, external_id), "source_code": SOURCE, "kind": kind, "external_id": external_id,
            "label": label, "attributes": attributes, "identifiers": {k: v for k, v in identifiers.items() if v},
            "mapping_status": status, "mapped_table": mapped[0] if mapped else None,
            "mapped_id": mapped[1] if mapped else None, "mapping_method": method, "mapping_note": note,
            "source_record_id": record.id, "source_row_numbers": rows,
        }  # fmt: skip

    def herbs(self) -> None:
        record = self.register("herb")
        batch: list[dict[str, Any]] = []
        for number, row in read_rows(self.directory / FILES["herb"]):
            self.ctx.stats["herb_rows"] += 1
            hid = value(row.get("FHDI_Herb_ID"))
            if hid is None:
                self.ctx.stats["herb_rows_rejected"] += 1
                self.ctx.issue(
                    "ddid_row_without_id",
                    "Herb row without FHDI_Herb_ID.",
                    record=record,
                    row=number,
                )
                continue
            latin = value(row.get("Herb_Latin_Name"))
            status, mapped, method, note = self.map_taxon(latin, value(row.get("Use_Part")))
            batch.append(self._entity("herb", hid, latin or value(row.get("Herb_English_Name")), dict(row),
                {"ncbi_taxonomy": value(row.get("Taxonomy_ID")), "npass_org": value(row.get("NPASS_ID")),
                 "herb_db": value(row.get("HERB_ID")), "symmap": value(row.get("SymMap_ID"))},
                record, [number], status, mapped, method, note))  # fmt: skip
            if len(batch) >= BATCH:
                self.upsert_entities(batch)
                batch = []
        self.upsert_entities(batch)

    def map_taxon(
        self, latin: str | None, part: str | None
    ) -> tuple[str, tuple[str, uuid.UUID] | None, str | None, str]:
        if not latin:
            return "unresolved", None, None, "No Latin name in DDID."
        rows = self.session.execute(
            select(TaxonName.taxon_id, TaxonName.name_type, TaxonName.source_code).where(
                TaxonName.normalized_name == normalize_for_lookup(latin),
                TaxonName.taxon_id.is_not(None),
            )
        ).all()
        taxa = {r[0] for r in rows}
        part_note = (f"DDID plant part: {part or 'not stated'}; not mapped to a HerbaGuard herbal substance "
                     "because the plant part may differ.")  # fmt: skip
        if len(taxa) == 1:
            taxon = next(iter(taxa))
            assert taxon is not None  # noqa: S101 - filtered
            if any(r[1] == "accepted" for r in rows):
                return ("resolved", ("taxon", taxon), "exact_accepted_name",
                        f"Mapped to the species only (exact accepted name). {part_note}")  # fmt: skip
            sources = ", ".join(sorted({r[2] for r in rows}))
            return ("candidate", ("taxon", taxon), "exact_synonym_needs_review",
                    f"Matches a name listed as a {'/'.join(sorted({r[1] for r in rows}))} in {sources}; synonym "
                    f"lists can contain names that are not equivalent, so this needs review before use. {part_note}")  # fmt: skip
        if len(taxa) > 1:
            return "ambiguous", None, None, f"'{latin}' matches {len(taxa)} taxa."
        return "unresolved", None, None, "No taxon with this exact name in HerbaGuard's taxonomy."

    def drugs(self) -> None:
        record = self.register("drug")
        by_name: dict[str, set[uuid.UUID]] = defaultdict(set)
        for drug_id, name in self.session.execute(select(Drug.id, Drug.name)):
            by_name[name.strip().lower()].add(drug_id)
        batch: list[dict[str, Any]] = []
        for number, row in read_rows(self.directory / FILES["drug"]):
            self.ctx.stats["drug_rows"] += 1
            did = value(row.get("FHDI_Drug_ID"))
            if did is None:
                self.ctx.stats["drug_rows_rejected"] += 1
                self.ctx.issue(
                    "ddid_row_without_id",
                    "Drug row without FHDI_Drug_ID.",
                    record=record,
                    row=number,
                )
                continue
            name = value(row.get("Drug_Name"))
            exact = by_name.get((name or "").lower(), set())
            synonyms = [
                s.strip().lower()
                for s in (value(row.get("Synonyms")) or "").split(";")
                if s.strip()
            ]
            via_synonym = (
                set().union(*(by_name.get(s, set()) for s in synonyms)) if synonyms else set()
            )
            if len(exact) == 1:
                status, mapped, method, note = (
                    "resolved",
                    ("drug", next(iter(exact))),
                    "exact_name",
                    None,
                )
            elif len(exact) > 1 or (not exact and len(via_synonym) > 1):
                status, mapped, method, note = (
                    "ambiguous",
                    None,
                    None,
                    "Several HerbaGuard drugs match.",
                )
            elif len(via_synonym) == 1:
                status, mapped, method, note = (
                    "resolved",
                    ("drug", next(iter(via_synonym))),
                    "exact_synonym",
                    None,
                )
            else:
                status, mapped, method = "unresolved", None, None
                note = "Not in HerbaGuard's RxNorm drug index by exact name or synonym (RxNav lookup not run)."
            batch.append(self._entity("drug", did, name, dict(row),
                {"drugbank": value(row.get("DrugBank_ID")), "pubchem_cid": value(row.get("PubChem_Compound_ID")),
                 "chebi": value(row.get("ChEBI_ID")), "inchikey": value(row.get("InChIKey")),
                 "cas": value(row.get("CAS_Number")), "ttd_drug": value(row.get("TTD_ID")),
                 "adrecs": value(row.get("ADReCS_Drug_ID"))},
                record, [number], status, mapped, method, note))  # fmt: skip
            if len(batch) >= BATCH:
                self.upsert_entities(batch)
                batch = []
        self.upsert_entities(batch)

    def _placeholder(self, kind: str, external_id: str, label: str | None, record: SourceRecord, row: int,
                     why: str) -> None:  # fmt: skip
        if entity_id(kind, external_id) in self.entities_seen:
            return
        status = "not_applicable" if kind == "food" else "unresolved"
        self.upsert_entities(
            [self._entity(kind, external_id, label, {}, {}, record, [row], status, note=why)]
        )

    # ------------------------------------------------------------------ relations
    def upsert_relations(
        self, rows: dict[tuple[uuid.UUID, str, uuid.UUID, str], dict[str, Any]]
    ) -> None:
        if not rows:
            return
        values = list(rows.values())
        stmt = insert(ExternalRelation).values(values)
        self.session.execute(stmt.on_conflict_do_update(
            index_elements=["source_code", "subject_id", "predicate", "object_id", "attributes_sha256"],
            set_={"source_row_numbers": stmt.excluded.source_row_numbers, "source_record_id": stmt.excluded.source_record_id}))  # fmt: skip
        self.ctx.stats["relations_upserted"] += len(values)

    def natural_products(self) -> None:
        record = self.register("np")
        entities: dict[str, dict[str, Any]] = {}
        relations: dict[tuple[uuid.UUID, str, uuid.UUID, str], dict[str, Any]] = {}
        for number, row in read_rows(self.directory / FILES["np"]):
            self.ctx.stats["np_rows"] += 1
            np_id, herb = value(row.get("np_id")), value(row.get("FHDI_Herb_ID"))
            if np_id is None or herb is None:
                self.ctx.stats["np_rows_rejected"] += 1
                continue
            attrs: dict[str, Any] = {
                k: row[k]
                for k in ("SMILES", "pref_name", "pubchem_cid", "Molecular_Weight")
                if k in row
            }
            known = entities.get(np_id)
            if known is None:
                entities[np_id] = self._entity("natural_product", np_id, value(row.get("pref_name")), attrs,
                    {"pubchem_cid": value(row.get("pubchem_cid")), "npass_compound": np_id},
                    record, [number], "unresolved", note="No InChIKey in DDID; not mapped to HerbaGuard constituents.")  # fmt: skip
            else:
                known["source_row_numbers"].append(number)
                if known["attributes"] != attrs:
                    self.ctx.stats["np_attribute_conflicts"] += 1
            self._placeholder("herb", herb, None, record, number, "Referenced only by the NP file.")
            rel_attrs = {"org_id": row.get("org_id", "")}
            key = (
                entity_id("herb", herb),
                "contains_natural_product",
                entity_id("natural_product", np_id),
                sha(rel_attrs),
            )
            if key in relations:
                relations[key]["source_row_numbers"].append(number)
                self.ctx.stats["np_duplicate_rows"] += 1
            else:
                relations[key] = {"id": stable_id("external_relation", SOURCE, *key), "source_code": SOURCE,
                                  "subject_id": key[0], "predicate": key[1], "object_id": key[2],
                                  "attributes": rel_attrs, "attributes_sha256": key[3],
                                  "source_record_id": record.id, "source_row_numbers": [number]}  # fmt: skip
        self.ctx.stats["entities_natural_product_unresolved"] = 0
        rows = list(entities.values())
        self.ctx.stats["entities_natural_product_unresolved"] = len(rows)
        for i in range(0, len(rows), BATCH):
            self.upsert_entities(rows[i : i + BATCH])
        items = list(relations.items())
        for i in range(0, len(items), BATCH):
            self.upsert_relations(dict(items[i : i + BATCH]))

    def targets(self) -> None:
        record = self.register("target")
        entities: dict[str, dict[str, Any]] = {}
        relations: dict[tuple[uuid.UUID, str, uuid.UUID, str], dict[str, Any]] = {}
        for number, row in read_rows(self.directory / FILES["target"]):
            self.ctx.stats["target_rows"] += 1
            tid, drug = value(row.get("Target_ID")), value(row.get("FHDI_Drug_ID"))
            if tid is None or drug is None:
                self.ctx.stats["target_rows_rejected"] += 1
                continue
            if tid not in entities:
                entities[tid] = self._entity("ttd_target", tid, value(row.get("Target_Name")),
                    {"Target_Name": row.get("Target_Name", "")}, {"ttd_target": tid}, record, [number], "unresolved",
                    note="TTD target identifier; DDID gives no UniProt cross-reference, so it is not joined to "
                         "HerbaGuard targets.")  # fmt: skip
            else:
                entities[tid]["source_row_numbers"].append(number)
            attrs = {"TTD_ID": row.get("TTD_ID", ""), "Highest_status": row.get("Highest_status", ""),
                     "MOA(Mechanisms of Action)": row.get("MOA(Mechanisms of Action)", "")}  # fmt: skip
            key = (
                entity_id("drug", drug),
                "has_therapeutic_target",
                entity_id("ttd_target", tid),
                sha(attrs),
            )
            if key in relations:
                relations[key]["source_row_numbers"].append(number)
            else:
                relations[key] = {"id": stable_id("external_relation", SOURCE, *key), "source_code": SOURCE,
                                  "subject_id": key[0], "predicate": key[1], "object_id": key[2],
                                  "attributes": attrs, "attributes_sha256": key[3],
                                  "source_record_id": record.id, "source_row_numbers": [number]}  # fmt: skip
        self.ctx.stats["entities_ttd_target_unresolved"] = len(entities)
        self.upsert_entities(list(entities.values()))
        self.upsert_relations(relations)

    # ------------------------------------------------------------------ observations
    def interactions(self) -> None:
        record = self.register("interaction")
        evidence_cache: dict[str, uuid.UUID] = {}
        seen: dict[str, uuid.UUID] = {}
        buffer: dict[str, dict[str, Any]] = {}
        unknown_species: set[str] = set()

        def flush() -> None:
            if not buffer:
                return
            values = list(buffer.values())
            stmt = insert(ExperimentalObservation).values(values)
            keep = ("id", "source_code", "record_sha256", "created_at")
            self.session.execute(stmt.on_conflict_do_update(
                index_elements=["source_code", "record_sha256"],
                set_={**{c: stmt.excluded[c] for c in values[0] if c not in keep}, "updated_at": func.now()}))  # fmt: skip
            buffer.clear()

        for number, row in read_rows(self.directory / FILES["interaction"]):
            self.ctx.stats["interaction_rows"] += 1
            drug, other = value(row.get("Drug_ID")), value(row.get("Food_Herb_ID"))
            if drug is None or other is None:
                self.ctx.stats["interaction_rows_rejected"] += 1
                self.ctx.issue("ddid_row_without_id", "Interaction row without drug or herb/food id.",
                               record=record, row=number)  # fmt: skip
                continue
            digest = sha(row)
            if digest in seen:  # exact duplicate of an earlier row: one record, all row numbers
                self.ctx.stats["interaction_exact_duplicates"] += 1
                if digest in buffer:
                    buffer[digest]["source_row_numbers"].append(number)
                else:
                    self.session.execute(update(ExperimentalObservation).where(ExperimentalObservation.id == seen[digest])
                                         .values(source_row_numbers=func.array_append(ExperimentalObservation.source_row_numbers, number)))  # fmt: skip
                continue
            kind = "herb" if other.startswith("H") else "food"
            stated = (value(row.get("Type")) or "").lower()
            if stated in ("herb", "food") and stated != kind:
                self.ctx.stats["interaction_type_prefix_mismatch"] += 1
            if kind == "herb" and entity_id("herb", other) not in self.entities_seen:
                self._placeholder("herb", other, value(row.get("Food_Herb_Name")), record, number,
                                  "Referenced only by the interaction file (not in Herb Information).")  # fmt: skip
                self.ctx.stats["interaction_herb_not_in_herb_file"] += 1
            if kind == "food":
                self._placeholder("food", other, value(row.get("Food_Herb_Name")), record, number,
                                  "Food item; HerbaGuard has no food entities.")  # fmt: skip
            if entity_id("drug", drug) not in self.entities_seen:
                self._placeholder("drug", drug, value(row.get("Drug_Name")), record, number,
                                  "Referenced only by the interaction file (not in Drug Information).")  # fmt: skip
                self.ctx.stats["interaction_drug_not_in_drug_file"] += 1
            species = value(row.get("Experimental_Species"))
            context, etype = study_context(species)
            if species and context == "unknown":
                unknown_species.add(species)
            effect = (row.get("Effect") or "").strip()
            if effect.lower() not in KNOWN_EFFECTS:
                self.ctx.stats["interaction_unknown_effect_label"] += 1
            accessions = [
                a for a in re.split(r"[;,/\s]+", row.get("Target_ID") or "") if UNIPROT.match(a)
            ]
            mapped_targets = sorted(
                {self.target_by_accession[a] for a in accessions if a in self.target_by_accession}
            )
            pmid, doi, reference = (
                value(row.get("PMID")),
                value(row.get("DOI")),
                value(row.get("Reference")),
            )
            observation_id = stable_id("experimental_observation", SOURCE, digest)
            seen[digest] = observation_id
            self.ctx.stats[f"observations_{context}"] += 1
            if mapped_targets:
                self.ctx.stats["observations_with_mapped_target"] += 1
            buffer[digest] = {
                "id": observation_id, "source_code": SOURCE, "record_sha256": digest, "original": dict(row),
                "interactant_entity_id": entity_id(kind, other), "drug_entity_id": entity_id("drug", drug),
                "interactant_kind": kind, "effect_label": effect, "species": species,
                "result": value(row.get("Result")), "conclusion": value(row.get("Conclusion")),
                "pmid": pmid if pmid and pmid.isdigit() else None, "doi": doi, "reference": reference,
                "target_accessions": accessions, "mapped_target_ids": mapped_targets,
                "derived_study_context": context, "derived_evidence_type": etype, "derivation_rule": DERIVATION_RULE,
                "evidence_item_id": self.evidence_for(pmid, doi, reference, evidence_cache),
                "source_record_id": record.id, "source_row_numbers": [number],
            }  # fmt: skip
            if len(buffer) >= BATCH:
                flush()
        flush()
        self.ctx.stats["observations_stored"] = len(seen)
        for species in sorted(unknown_species):
            self.ctx.issue("ddid_species_not_classified", f"Species value '{species}' is treated as unknown.",
                           severity=IssueSeverity.INFO, record=record)  # fmt: skip
        self._evidence_types()
        if not self.ctx.error_issues:  # stale records of earlier file versions
            removed = self.session.execute(delete(ExperimentalObservation).where(
                ExperimentalObservation.source_code == SOURCE,
                ExperimentalObservation.source_record_id != record.id)).rowcount  # type: ignore[attr-defined]  # fmt: skip
            self.ctx.stats["observations_stale_removed"] = removed or 0

    def evidence_for(self, pmid: str | None, doi: str | None, reference: str | None,
                     cache: dict[str, uuid.UUID]) -> uuid.UUID | None:  # fmt: skip
        """The citable unit for an observation: an existing evidence item with the same PMID (any
        source) is reused; otherwise one DDID evidence item per reference."""
        if pmid and pmid.isdigit():
            key = f"PMID:{pmid}"
        elif doi:
            key = f"DOI:{doi.lower()}"
        elif reference:
            key = f"REF:{hashlib.sha256(reference.encode()).hexdigest()[:16]}"
        else:
            self.ctx.stats["observations_without_reference"] += 1
            return None
        if key in cache:
            return cache[key]
        if key.startswith("PMID:"):
            existing = self.session.scalar(select(EvidenceItem.id).where(EvidenceItem.pmid == pmid,
                                                                         EvidenceItem.source_code != SOURCE).limit(1))  # fmt: skip
            if existing is not None:
                cache[key] = existing
                self.ctx.stats["evidence_reused_existing_pmid"] += 1
                return existing
        evidence_id = stable_id("evidence_item", SOURCE, key)
        stmt = insert(EvidenceItem).values(
            id=evidence_id, source_code=SOURCE, external_id=f"ddid:{key}", evidence_type=EvidenceType.OTHER.value,
            title=(reference or key)[:2000], url=(f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if key.startswith("PMID:")
                                                 else f"https://doi.org/{doi}" if doi else None),
            pmid=pmid if key.startswith("PMID:") else None, doi=doi,
            metadata_={"dataset": "DDID", "note": "Reference cited by DDID records; evidence type set from the records' species."},
        )  # fmt: skip
        self.session.execute(stmt.on_conflict_do_nothing(index_elements=["id"]))
        cache[key] = evidence_id
        self.ctx.stats["evidence_items_ddid"] += 1
        return evidence_id

    def _evidence_types(self) -> None:
        """A DDID evidence item is CLIN only if all its records are human, ANIMAL only if all are animal."""
        rows = self.session.execute(
            select(ExperimentalObservation.evidence_item_id, func.array_agg(func.distinct(ExperimentalObservation.derived_study_context)))
            .join(EvidenceItem, EvidenceItem.id == ExperimentalObservation.evidence_item_id)
            .where(EvidenceItem.source_code == SOURCE).group_by(ExperimentalObservation.evidence_item_id)
        ).all()  # fmt: skip
        for evidence_id, contexts in rows:
            etype = {("human",): "CLIN", ("animal",): "ANIMAL"}.get(
                tuple(sorted(contexts)), "OTHER"
            )
            self.session.execute(
                update(EvidenceItem)
                .where(EvidenceItem.id == evidence_id)
                .values(evidence_type=etype)
            )


def run(ctx: IngestionContext, directory: Path) -> None:
    job = DdidImport(ctx, directory)
    job.herbs()
    job.drugs()
    job.targets()
    job.natural_products()
    job.interactions()
    ctx.session.flush()
