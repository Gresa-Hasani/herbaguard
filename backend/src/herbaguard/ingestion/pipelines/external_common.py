"""Shared helpers for external datasets stored in the generic tables of migration 0006.

Used by the SUPP.AI, LiverTox and NIH DSLD pipelines (the DDID pipeline keeps its own copy of
these rules and is not changed). Everything here follows the DDID rules (docs/data/ddid.md):

* Each raw file gets a ``source_record`` with its SHA-256; files are never modified or copied.
* Entities and relations have deterministic ids and are upserted, so a re-run creates no duplicates.
* Name mapping reuses HerbaGuard's exact name lookup (``repositories.plants.match_names`` with
  ``exact_only=True``: ``normalize_for_lookup`` against ``taxon_name.normalized_name``; drugs: exact
  name, as ``repositories.drugs.drug_by_name``). Nothing is mapped by partial or fuzzy matching:
  one taxon → ``resolved`` (or ``candidate`` when only a synonym or a dataset-provided name variant
  matches); several taxa or drugs → ``ambiguous``; none → ``unresolved``.
* Nothing written here is read by the deterministic A–E classification (``domain.interactions``),
  which uses only ``interaction_assertion``.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import any_, bindparam, delete, func, not_, select
from sqlalchemy.dialects.postgresql import ARRAY, insert
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from herbaguard.domain.name_overrides import override_for
from herbaguard.ingestion.context import IngestionContext, stable_id
from herbaguard.ingestion.normalize.names import normalize_for_lookup
from herbaguard.models import Drug, ExternalEntity, ExternalRelation, SourceRecord, Taxon, TaxonName

BATCH = 1000

# mapping_status values (same vocabulary as DDID)
RESOLVED, CANDIDATE, AMBIGUOUS, UNRESOLVED = "resolved", "candidate", "ambiguous", "unresolved"


def sha(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class Mapping:
    status: str
    table: str | None = None
    target: uuid.UUID | None = None
    method: str | None = None
    note: str | None = None


class HerbMatcher:
    """Exact-name mapping of plant names to HerbaGuard taxa (same rule as ``match_names``)."""

    def __init__(self, session: Any) -> None:
        self.by_name: dict[str, list[tuple[uuid.UUID, str, str]]] = defaultdict(list)
        self.scientific: dict[uuid.UUID, str] = dict(
            session.execute(select(Taxon.id, Taxon.scientific_name)).tuples().all()
        )
        for taxon_id, normalized, name_type, source in session.execute(
            select(
                TaxonName.taxon_id,
                TaxonName.normalized_name,
                TaxonName.name_type,
                TaxonName.source_code,
            ).where(TaxonName.taxon_id.is_not(None))
        ):
            self.by_name[normalized].append((taxon_id, name_type, source))

    def lookup(self, name: str | None) -> list[tuple[uuid.UUID, str, str]]:
        """Exact-name rows, minus rows that a reviewed override excludes for their taxon."""
        key = normalize_for_lookup(name or "")
        rows = self.by_name.get(key, []) if key else []
        override = override_for(name)
        if override is not None and override.action == "not_this_taxon":
            rows = [r for r in rows if self.scientific.get(r[0]) not in override.excluded_taxa]
        return rows

    def map(self, primary: str | None, variants: Iterable[str] = ()) -> Mapping:
        """``primary``: the dataset's own name for the entity; ``variants``: other names the
        dataset lists for it (e.g. UMLS synonyms). A match through variants only is a candidate."""
        override = override_for(primary)
        if override is not None and override.action == "ambiguous":
            return Mapping(AMBIGUOUS, method="reviewed_override", note=override.reason)
        rows = self.lookup(primary)
        via_variant = False
        if not rows:
            # a variant that a reviewed override marks as ambiguous cannot identify the plant
            usable = [
                v for v in variants if (o := override_for(v)) is None or o.action != "ambiguous"
            ]
            rows = [r for v in usable for r in self.lookup(v)]
            via_variant = bool(rows)
        taxa = {r[0] for r in rows}
        if not taxa:
            if override is not None:  # e.g. blessed thistle: refers to a plant not in HerbaGuard
                return Mapping(UNRESOLVED, method="reviewed_override", note=override.reason)
            return Mapping(UNRESOLVED, note="No HerbaGuard taxon has this exact name.")
        if len(taxa) > 1:
            names = ", ".join(sorted(self.scientific.get(t, str(t)) for t in taxa))
            return Mapping(
                AMBIGUOUS,
                note=f"The name matches {len(taxa)} HerbaGuard taxa ({names}); not mapped.",
            )
        taxon = next(iter(taxa))
        types = sorted({r[1] for r in rows})
        sources = ", ".join(sorted({r[2] for r in rows}))
        if via_variant:
            return Mapping(CANDIDATE, "taxon", taxon, "exact_name_variant_needs_review",
                           f"Only a name variant listed by the dataset matches a {'/'.join(types)} name ({sources}); "
                           "needs review before use.")  # fmt: skip
        if types == ["synonym"]:
            return Mapping(CANDIDATE, "taxon", taxon, "exact_synonym_needs_review",
                           f"Matches only a synonym ({sources}); synonym lists can contain names that are not "
                           "equivalent, so this needs review before use.")  # fmt: skip
        best = next(t for t in ("accepted", "pharmaceutical", "common") if t in types)
        return Mapping(RESOLVED, "taxon", taxon, f"exact_{best}_name",
                       f"Mapped to the species only ({sources}); the plant part or preparation may differ.")  # fmt: skip


class DrugMatcher:
    """Exact-name mapping to HerbaGuard drugs (RxNorm ingredients); no RxNav lookup."""

    def __init__(self, session: Any) -> None:
        self.by_name: dict[str, set[uuid.UUID]] = defaultdict(set)
        for drug_id, name in session.execute(select(Drug.id, Drug.name)):
            self.by_name[name.strip().lower()].add(drug_id)

    def map(self, primary: str | None, variants: Iterable[str] = ()) -> Mapping:
        exact = self.by_name.get((primary or "").strip().lower(), set())
        if len(exact) == 1:
            return Mapping(RESOLVED, "drug", next(iter(exact)), "exact_name")
        if len(exact) > 1:
            return Mapping(AMBIGUOUS, note="Several HerbaGuard drugs have this exact name.")
        via = (
            set().union(*(self.by_name.get(v.strip().lower(), set()) for v in variants))
            if variants
            else set()
        )
        if len(via) == 1:
            return Mapping(RESOLVED, "drug", next(iter(via)), "exact_synonym")
        if len(via) > 1:
            return Mapping(AMBIGUOUS, note="Name variants match several HerbaGuard drugs.")
        return Mapping(UNRESOLVED, note="Not in HerbaGuard's RxNorm drug index by exact name or synonym "
                                        "(RxNav lookup not run).")  # fmt: skip


class ExternalWriter:
    """Provenance and idempotent upserts for one source."""

    def __init__(self, ctx: IngestionContext, source: str, download_page: str) -> None:
        self.ctx = ctx
        self.session = ctx.session
        self.source = source
        self.download_page = download_page

    def register(self, path: Path, relative: str, content_type: str) -> SourceRecord:
        if not path.is_file():
            msg = f"{self.source}: file missing: {path}"
            raise FileNotFoundError(msg)
        digest = file_sha256(path)
        record = self.session.scalar(
            select(SourceRecord).where(SourceRecord.source_code == self.source, SourceRecord.native_id == path.name,
                                       SourceRecord.content_sha256 == digest)
        )  # fmt: skip
        if record is None:
            record = SourceRecord(
                id=uuid.uuid4(), source_code=self.source, ingestion_run_id=self.ctx.run.id, native_id=path.name,
                url=self.download_page, http_status=None, content_type=content_type, content_sha256=digest,
                raw_path=str(path), request_parameters={"method": "manual_download", "local_file": relative},
                retrieved_at=datetime.fromtimestamp(path.stat().st_mtime, tz=UTC),
            )  # fmt: skip
            self.session.add(record)
            self.session.flush()
            self.ctx.stats["source_records_new"] += 1
        else:
            self.ctx.stats["source_records_unchanged"] += 1
        return record

    def entity_id(self, kind: str, external_id: str) -> uuid.UUID:
        return stable_id("external_entity", self.source, kind, external_id)

    def entity(self, kind: str, external_id: str, label: str | None, attributes: dict[str, Any],
               identifiers: dict[str, Any], record: SourceRecord, rows: list[int], mapping: Mapping) -> dict[str, Any]:  # fmt: skip
        self.ctx.stats[f"entities_{kind}_{mapping.status}"] += 1
        return {
            "id": self.entity_id(kind, external_id), "source_code": self.source, "kind": kind,
            "external_id": external_id, "label": label, "attributes": attributes,
            "identifiers": {k: v for k, v in identifiers.items() if v}, "mapping_status": mapping.status,
            "mapped_table": mapping.table, "mapped_id": mapping.target, "mapping_method": mapping.method,
            "mapping_note": mapping.note, "source_record_id": record.id, "source_row_numbers": rows,
        }  # fmt: skip

    def upsert_entities(self, rows: list[dict[str, Any]]) -> None:
        for i in range(0, len(rows), BATCH):
            chunk = rows[i : i + BATCH]
            stmt = insert(ExternalEntity).values(chunk)
            keep = ("id", "source_code", "kind", "external_id")
            self.session.execute(stmt.on_conflict_do_update(
                index_elements=["id"],
                set_={**{c: stmt.excluded[c] for c in chunk[0] if c not in keep}, "updated_at": func.now()}))  # fmt: skip

    def relation(self, subject: uuid.UUID, predicate: str, obj: uuid.UUID, attributes: dict[str, Any],
                 record: SourceRecord, rows: list[int]) -> dict[str, Any]:  # fmt: skip
        digest = sha(attributes)
        return {
            "id": stable_id("external_relation", self.source, subject, predicate, obj, digest),
            "source_code": self.source, "subject_id": subject, "predicate": predicate, "object_id": obj,
            "attributes": attributes, "attributes_sha256": digest, "source_record_id": record.id,
            "source_row_numbers": rows,
        }  # fmt: skip

    def upsert_relations(self, rows: Iterable[dict[str, Any]]) -> int:
        values = list({r["id"]: r for r in rows}.values())  # identical relations collapse to one
        for i in range(0, len(values), BATCH):
            chunk = values[i : i + BATCH]
            stmt = insert(ExternalRelation).values(chunk)
            self.session.execute(stmt.on_conflict_do_update(
                index_elements=["source_code", "subject_id", "predicate", "object_id", "attributes_sha256"],
                set_={"source_row_numbers": stmt.excluded.source_row_numbers,
                      "source_record_id": stmt.excluded.source_record_id}))  # fmt: skip
        return len(values)


def delete_stale(ctx: IngestionContext, source: str, keep_entities: set[uuid.UUID],
                 keep_relations: set[uuid.UUID]) -> None:  # fmt: skip
    """Remove this source's relations and entities that the current run did not produce (rows of an
    earlier file version). Called only after an error-free run. One array parameter per query, so
    large keep-sets do not hit the driver's parameter limit."""
    if ctx.error_issues:
        ctx.stats["stale_removal_skipped_due_to_errors"] = 1
        return
    for model, keep, stat in ((ExternalRelation, keep_relations, "relations_stale_removed"),
                              (ExternalEntity, keep_entities, "entities_stale_removed")):  # fmt: skip
        ids = bindparam("keep", list(keep), type_=ARRAY(PG_UUID(as_uuid=True)))
        result = ctx.session.execute(
            delete(model).where(model.source_code == source, not_(model.id == any_(ids)))
        )
        ctx.stats[stat] = result.rowcount or 0  # type: ignore[attr-defined]
