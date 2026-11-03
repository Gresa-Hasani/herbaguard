"""Phase 4 mechanism layer: enzymes/transporters, drug roles (FDA table) and herb effects.

Two runs, both started by ``herbaguard ingest mechanisms``:

* ``run_ema`` (source ``ema_hmpc``, no network): reads the EU monograph section 4.5 texts stored in
  Phase 2 and extracts herb → enzyme/transporter effects with the deterministic sentence rules in
  ``normalize/mechanisms.py``. Provenance points to the monograph PDF record and quotes the
  sentence.
* ``run_fda`` (source ``fda_cyp_table``): fetches FDA's "Examples of Drugs that Interact with CYP
  Enzymes and Transporter Systems", parses Table 1 and stores drug roles (substrate / inhibitor /
  inducer, with FDA's potency category and footnotes). The table's non-drug rows (St. John's
  wort, curcumin, …) are mapped by ``data/curated/mechanism_sources.yaml``; drug names are
  normalised through RxNorm exactly as in Phase 2 (nothing is guessed).

Both runs first load the curated enzyme/transporter list (``data/curated/targets.yaml``).
Edges are re-derived on every run; edges the current source no longer supports are removed with
their provenance links (only when the run had no error-level issues).
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from herbaguard.domain.enums import DrugTargetRole, EvidenceType, IssueSeverity, ModulationEffect
from herbaguard.ingestion.context import IngestionContext, stable_id
from herbaguard.ingestion.curation import (
    CURATED_DIR,
    FdaNonDrugRow,
    HerbEntry,
    load_herbs,
    load_mechanism_sources,
    load_targets,
)
from herbaguard.ingestion.drugs import DrugResolver
from herbaguard.ingestion.loaders import (
    link_constituent,
    remove_stale_edges,
    replace_chunks,
    substances_for_herb,
    upsert_constituent,
    upsert_drug_role,
    upsert_evidence,
    upsert_modulation,
    upsert_target,
)
from herbaguard.ingestion.normalize.mechanisms import (
    EXTRACTION_VERSION,
    Outcome,
    extract_mechanisms,
    subject_patterns,
)
from herbaguard.ingestion.normalize.statements import (
    is_condition_header,
    split_paragraphs,
    split_sentences,
)
from herbaguard.ingestion.normalize.targets import find_targets
from herbaguard.ingestion.parsers.fda_cyp_table import (
    PARSER_VERSION,
    CellEntry,
    FdaTable,
    FdaTableFormatError,
    Row,
    parse_fda_cyp_table,
)
from herbaguard.ingestion.raw_store import extension_for
from herbaguard.ingestion.sources import get_source
from herbaguard.models import (
    Chunk,
    DrugTargetRoleLink,
    EvidenceItem,
    Provenance,
    SourceRecord,
    TargetModulation,
)

FDA_SOURCE = "fda_cyp_table"
EMA_SOURCE = "ema_hmpc"
CURATED_SOURCE = "herbaguard_curated"
FDA_URL = get_source(FDA_SOURCE).homepage_url
FDA_EVIDENCE_ID = "fda-cyp-transporter-examples#table-1"
METHOD_TARGETS = "curated_targets_v1"
METHOD_FDA = "fda_cyp_table_pipeline_v1"
METHOD_EMA = "ema_mechanism_sentence_v1"
METHOD_CURATED = "curated_mechanism_sources_v1"
EMA_SECTIONS = ("4.5",)

_ROLE_TO_EFFECT = {
    DrugTargetRole.INHIBITOR: ModulationEffect.INHIBITS,
    DrugTargetRole.INDUCER: ModulationEffect.INDUCES,
}
_USE_LABEL = {
    "well_established_use": "well-established use",
    "traditional_use": "traditional use",
}


# --------------------------------------------------------------------------- shared


def ensure_targets(ctx: IngestionContext) -> dict[str, uuid.UUID]:
    """Upsert the curated enzymes/transporters; provenance → the committed targets.yaml."""
    record = ctx.register_local_file(
        CURATED_DIR / "targets.yaml",
        source_code=CURATED_SOURCE,
        native_id="data/curated/targets.yaml",
    )
    ids: dict[str, uuid.UUID] = {}
    for target in load_targets().targets:
        target_id = upsert_target(
            ctx.session,
            symbol=target.symbol,
            name=target.name,
            target_type=target.type,
            uniprot_accession=target.uniprot,
        )
        ctx.provenance(
            "target",
            target_id,
            record,
            METHOD_TARGETS,
            location=f"targets: {target.symbol}",
            excerpt=f"{target.symbol} = {target.name}; UniProt {target.uniprot or 'n/a'}",
        )
        ids[target.symbol] = target_id
    ctx.stats["targets"] = len(ids)
    return ids


# --------------------------------------------------------------------------- FDA table


def _saved_page(ctx: IngestionContext, path: Path) -> SourceRecord:
    """Register a copy of the FDA page saved from a browser (fallback when fda.gov refuses
    automated requests). The record keeps the page URL and says how it was obtained."""
    content = path.read_bytes()
    digest, stored = ctx.raw_store.save(FDA_SOURCE, content, extension_for("text/html", FDA_URL))
    record = ctx.session.scalar(
        select(SourceRecord).where(
            SourceRecord.source_code == FDA_SOURCE,
            SourceRecord.native_id == FDA_URL,
            SourceRecord.content_sha256 == digest,
        )
    )
    if record is None:
        record = SourceRecord(
            id=uuid.uuid4(),
            source_code=FDA_SOURCE,
            ingestion_run_id=ctx.run.id,
            native_id=FDA_URL,
            url=FDA_URL,
            request_parameters={"method": "saved_from_browser", "file_name": path.name},
            http_status=None,
            content_type="text/html",
            content_sha256=digest,
            raw_path=str(stored),
            payload=None,
            retrieved_at=datetime.now(UTC),
        )
        ctx.session.add(record)
        ctx.session.flush()
    ctx.issue(
        "fda_page_saved_copy",
        f"FDA page read from a saved copy ({path.name}), not fetched by HerbaGuard.",
        severity=IssueSeverity.INFO,
        record=record,
    )
    return record


def _page(ctx: IngestionContext, html_file: Path | None) -> tuple[SourceRecord, bytes] | None:
    if html_file is not None:
        record = _saved_page(ctx, html_file)
        return record, html_file.read_bytes()
    fetched = ctx.fetch(FDA_URL, native_id=FDA_URL)
    if not fetched.ok:
        ctx.issue(
            "fda_page_unavailable",
            f"HTTP {fetched.result.status_code} for {FDA_URL}. If fda.gov refuses automated "
            "requests, save the page from a browser and pass it with --fda-html-file.",
            severity=IssueSeverity.ERROR,
            record=fetched.record,
        )
        return None
    return fetched.record, fetched.content


def _footnotes(table: FdaTable, *ref_groups: tuple[str, ...]) -> str | None:
    refs = tuple(dict.fromkeys(ref for group in ref_groups for ref in group))
    text = table.footnote_text(refs)
    return f"FDA footnotes: {text}" if text else None


def _cell_issues(ctx: IngestionContext, row: Row, entry: CellEntry, record: SourceRecord) -> None:
    def issue(rule: str, message: str, severity: IssueSeverity = IssueSeverity.WARNING) -> None:
        ctx.issue(
            rule,
            message,
            severity=severity,
            record=record,
            row=row.name_verbatim,
            column=entry.column.header,
            cell=entry.cell_text,
        )

    if entry.unparsed:
        issue(
            "fda_cell_unparsed_text",
            f"Unrecognised words {list(entry.unparsed)} in '{entry.cell_text}' (targets still read).",
        )
    if entry.wording_note:
        issue("fda_cell_wording", entry.wording_note)
    if entry.wrong_system:
        issue(
            "fda_cell_wrong_system",
            f"{list(entry.wrong_system)} do not belong to column '{entry.column.header}'; ignored.",
        )
    if not entry.targets:
        issue(
            "fda_cell_no_target",
            f"No enzyme/transporter recognised in '{entry.cell_text}'.",
            IssueSeverity.ERROR,
        )


def _location(row: Row, entry: CellEntry) -> str:
    return f"Table 1, row {row.index} '{row.name_verbatim}', column '{entry.column.header}'"


def _excerpt(row: Row, entry: CellEntry) -> str:
    return f"{row.name_verbatim} | {entry.column.header}: {entry.cell_text}"


class _FdaRun:
    def __init__(
        self,
        ctx: IngestionContext,
        table: FdaTable,
        record: SourceRecord,
        evidence_id: uuid.UUID,
        targets: dict[str, uuid.UUID],
    ) -> None:
        self.ctx = ctx
        self.table = table
        self.record = record
        self.evidence_id = evidence_id
        self.targets = targets
        self.config = load_mechanism_sources()
        self.resolver = DrugResolver(ctx)
        self.kept_roles: set[uuid.UUID] = set()
        self.kept_modulations: set[uuid.UUID] = set()
        self._curated_record: SourceRecord | None = None

    def curated_record(self) -> SourceRecord:
        if self._curated_record is None:
            self._curated_record = self.ctx.register_local_file(
                CURATED_DIR / "mechanism_sources.yaml",
                source_code=CURATED_SOURCE,
                native_id="data/curated/mechanism_sources.yaml",
            )
        return self._curated_record

    def row(self, row: Row) -> None:
        self.ctx.stats["fda_rows"] += 1
        for entry in row.entries:
            _cell_issues(self.ctx, row, entry, self.record)
        non_drug = self.config.non_drug_row(row.name)
        if non_drug is not None:
            self.non_drug(row, non_drug)
            return
        for skip in self.config.fda_skip_patterns:
            if re.search(skip.pattern, row.name, re.IGNORECASE):
                self.ctx.issue(
                    "fda_row_skipped",
                    f"'{row.name_verbatim}' skipped: {skip.reason}",
                    severity=IssueSeverity.INFO,
                    record=self.record,
                    row=row.name_verbatim,
                )
                self.ctx.stats["fda_rows_skipped"] += 1
                return
        ingredient = self.resolver.by_name(row.name)
        if ingredient is None:
            self.ctx.stats["fda_rows_drug_unresolved"] += 1  # issue recorded by the resolver
            return
        self.store_roles(row, ingredient.drug_id)
        alias = self.config.drug_alias(row.name)
        for name in alias.also_for if alias else []:
            other = self.resolver.by_name(name)
            if other is None or other.drug_id == ingredient.drug_id:
                continue
            assert alias is not None  # noqa: S101 - loop is empty otherwise
            self.store_roles(
                row,
                other.drug_id,
                alias_note=f"FDA lists {row.name_verbatim}; applied to {name}: {alias.note}",
            )
            self.ctx.stats["drug_roles_via_alias"] += 1

    def store_roles(self, row: Row, drug_id: uuid.UUID, alias_note: str | None = None) -> None:
        for entry in row.entries:
            for symbol in entry.targets:
                target_id = self.targets.get(symbol)
                if target_id is None:
                    self.ctx.issue(
                        "target_not_curated",
                        f"{symbol} is not in targets.yaml.",
                        severity=IssueSeverity.ERROR,
                        record=self.record,
                        row=row.name_verbatim,
                    )
                    continue
                footnotes = _footnotes(self.table, row.footnote_refs, entry.footnote_refs)
                role_id = upsert_drug_role(
                    self.ctx.session,
                    drug_id=drug_id,
                    target_id=target_id,
                    role=entry.column.role.value,
                    source_code=FDA_SOURCE,
                    potency=entry.column.potency.value if entry.column.potency else None,
                    conditions="; ".join(c for c in (footnotes, alias_note) if c) or None,
                    evidence_item_id=self.evidence_id,
                )
                self.ctx.provenance(
                    "drug_target_role",
                    role_id,
                    self.record,
                    METHOD_FDA,
                    version=PARSER_VERSION,
                    location=_location(row, entry),
                    excerpt=_excerpt(row, entry),
                )
                if alias_note:
                    self.ctx.provenance(
                        "drug_target_role",
                        role_id,
                        self.curated_record(),
                        METHOD_FDA,
                        version=PARSER_VERSION,
                        location=f"fda_drug_aliases: {row.name_verbatim}",
                        excerpt=alias_note,
                    )
                self.kept_roles.add(role_id)
                self.ctx.stats[f"drug_roles_{entry.column.role.value}"] += 1

    def non_drug(self, row: Row, mapping: FdaNonDrugRow) -> None:
        if mapping.kind == "out_of_scope":
            self.ctx.issue(
                "fda_row_out_of_scope",
                f"'{row.name_verbatim}' is not stored: {mapping.note or 'out of scope'}",
                severity=IssueSeverity.INFO,
                record=self.record,
                row=row.name_verbatim,
            )
            self.ctx.stats["fda_rows_out_of_scope"] += 1
            return
        subjects: list[dict[str, uuid.UUID]] = []
        if mapping.kind == "herb" and mapping.herb_key:
            substances = substances_for_herb(self.ctx.session, mapping.herb_key)
            if not substances:
                self.ctx.issue(
                    "herb_without_substances",
                    f"Run taxonomy first: no substances for {mapping.herb_key}.",
                    severity=IssueSeverity.ERROR,
                    row=row.name_verbatim,
                )
                return
            subjects = [{"herbal_substance_id": s.id} for s in substances]
        elif mapping.kind == "constituent" and mapping.constituent:
            subjects = [{"constituent_id": self.constituent(mapping)}]
        for entry in row.entries:
            effect = _ROLE_TO_EFFECT.get(entry.column.role)
            if effect is None:
                self.ctx.issue(
                    "fda_non_drug_substrate",
                    f"'{row.name_verbatim}' is listed as a substrate; not stored as an effect.",
                    record=self.record,
                    row=row.name_verbatim,
                )
                continue
            conditions = _footnotes(self.table, row.footnote_refs, entry.footnote_refs)
            for symbol in entry.targets:
                target_id = self.targets.get(symbol)
                if target_id is None:
                    continue
                for subject in subjects:
                    modulation_id = upsert_modulation(
                        self.ctx.session,
                        target_id=target_id,
                        effect=effect.value,
                        evidence_type=EvidenceType.GOVERNMENT_SUMMARY.value,
                        potency=entry.column.potency.value if entry.column.potency else None,
                        conditions=conditions,
                        source_code=FDA_SOURCE,
                        evidence_item_id=self.evidence_id,
                        **subject,
                    )
                    self.ctx.provenance(
                        "target_modulation",
                        modulation_id,
                        self.record,
                        METHOD_FDA,
                        version=PARSER_VERSION,
                        location=_location(row, entry),
                        excerpt=_excerpt(row, entry),
                    )
                    self.kept_modulations.add(modulation_id)
                    self.ctx.stats[f"modulations_{mapping.kind}"] += 1

    def constituent(self, mapping: FdaNonDrugRow) -> uuid.UUID:
        assert mapping.constituent is not None  # noqa: S101 - checked by the caller
        entry = mapping.constituent
        record = self.curated_record()
        constituent_id = upsert_constituent(
            self.ctx.session,
            inchikey=entry.inchikey,
            name=entry.name,
            pubchem_cid=entry.pubchem_cid,
            chebi_id=entry.chebi_id,
            molecular_formula=entry.molecular_formula,
        )
        self.ctx.provenance(
            "constituent",
            constituent_id,
            record,
            METHOD_CURATED,
            location=f"fda_non_drug_rows: {mapping.name}",
        )
        for herb_key in mapping.found_in:
            for substance in substances_for_herb(self.ctx.session, herb_key):
                link_constituent(
                    self.ctx.session,
                    herbal_substance_id=substance.id,
                    constituent_id=constituent_id,
                    source_code=CURATED_SOURCE,
                )
                self.ctx.provenance(
                    "herbal_substance_constituent",
                    stable_id("herbal_substance_constituent", substance.id, constituent_id),
                    record,
                    METHOD_CURATED,
                    location=f"fda_non_drug_rows: {mapping.name}, found_in {herb_key}",
                    excerpt=mapping.note,
                )
        return constituent_id


def run_fda(ctx: IngestionContext, html_file: Path | None = None) -> None:
    targets = ensure_targets(ctx)
    ctx.session.commit()
    page = _page(ctx, html_file)
    if page is None:
        return
    record, content = page
    try:
        table = parse_fda_cyp_table(content.decode("utf-8", "replace"))
    except FdaTableFormatError as exc:
        ctx.issue("fda_table_format", str(exc), severity=IssueSeverity.ERROR, record=record)
        return
    current = table.content_current_as_of
    record.source_version = current.isoformat() if current else None
    evidence_id = upsert_evidence(
        ctx.session,
        source_code=FDA_SOURCE,
        external_id=FDA_EVIDENCE_ID,
        evidence_type=EvidenceType.GOVERNMENT_SUMMARY.value,
        title="FDA: Examples of Drugs that Interact with CYP Enzymes and Transporter Systems — Table 1",
        url=FDA_URL,
        document_date=current,
        publication_year=current.year if current else None,
        is_superseded=False,
        metadata_={
            "content_current_as_of": current.isoformat() if current else None,
            "rows": len(table.rows),
            "footnotes": table.footnotes,
            "parser": PARSER_VERSION,
            "note": "Examples, not a comprehensive list (FDA). Used only for mechanism-based class B.",
        },
    )
    chunks: list[tuple[str | None, str, dict[str, object]]] = [
        ("Introduction", "\n\n".join(table.intro), {}),
        (
            "Definitions",
            "\n".join(f"{d.kind} — {d.category}: {d.text}" for d in table.definitions),
            {},
        ),
        ("Footnotes", "\n".join(f"[{k}] {v}" for k, v in table.footnotes.items()), {}),
    ]
    replace_chunks(ctx.session, evidence_id, chunks)
    ctx.provenance(
        "evidence_item",
        evidence_id,
        record,
        METHOD_FDA,
        version=PARSER_VERSION,
        location="Table 1, legends and footnotes",
    )
    ctx.session.commit()

    run = _FdaRun(ctx, table, record, evidence_id, targets)
    for row in table.rows:
        with ctx.per_item(f"fda:{row.name}", run.resolver.reset):
            run.row(row)
    if ctx.error_issues:
        ctx.issue(
            "stale_edges_kept",
            "Run had errors: edges from earlier runs were not removed.",
            severity=IssueSeverity.INFO,
        )
        return
    ctx.stats["stale_drug_roles_removed"] += remove_stale_edges(
        ctx.session, DrugTargetRoleLink, source_code=FDA_SOURCE, kept_ids=run.kept_roles
    )
    ctx.stats["stale_modulations_removed"] += remove_stale_edges(
        ctx.session, TargetModulation, source_code=FDA_SOURCE, kept_ids=run.kept_modulations
    )
    ctx.session.commit()


# --------------------------------------------------------------------------- EMA monographs


def _pdf_record(ctx: IngestionContext, evidence_id: uuid.UUID) -> SourceRecord | None:
    """The monograph PDF record behind a stored EMA section (Phase 2 provenance)."""
    records = list(
        ctx.session.scalars(
            select(SourceRecord)
            .join(Provenance, Provenance.source_record_id == SourceRecord.id)
            .where(
                Provenance.entity_table == "evidence_item",
                Provenance.entity_id == str(evidence_id),
            )
            .order_by(SourceRecord.retrieved_at.desc())
        )
    )
    pdfs = [r for r in records if "pdf" in (r.content_type or "") or r.url.lower().endswith(".pdf")]
    candidates = pdfs or records
    return candidates[0] if candidates else None


def _section_text(ctx: IngestionContext, evidence_id: uuid.UUID) -> str:
    chunks = ctx.session.scalars(
        select(Chunk.text).where(Chunk.evidence_item_id == evidence_id).order_by(Chunk.ordinal)
    )
    return "\n\n".join(chunks)


def _ema_herb(
    ctx: IngestionContext, herb: HerbEntry, targets: dict[str, uuid.UUID], kept: set[uuid.UUID]
) -> list[uuid.UUID]:
    substances = substances_for_herb(ctx.session, herb.key)
    if not substances:
        ctx.issue(
            "herb_without_substances",
            f"Run taxonomy first: no substances for {herb.key}.",
            severity=IssueSeverity.ERROR,
            herb=herb.key,
        )
        return []
    substance_ids = [s.id for s in substances]
    terms = [*load_mechanism_sources().ema_subject_terms.get(herb.key, []), herb.common_name]
    patterns = subject_patterns([herb.ema_latin_name], terms)
    sections = ctx.session.scalars(
        select(EvidenceItem).where(
            EvidenceItem.source_code == EMA_SOURCE,
            EvidenceItem.is_superseded.is_(False),
            EvidenceItem.metadata_["herb_key"].astext == herb.key,
            EvidenceItem.metadata_["section"].astext.in_(EMA_SECTIONS),
        )
    ).all()
    for item in sections:
        record = _pdf_record(ctx, item.id)
        if record is None:
            ctx.issue(
                "ema_section_without_record",
                f"No source record for {item.external_id}.",
                severity=IssueSeverity.ERROR,
                herb=herb.key,
            )
            continue
        use = str(item.metadata_.get("use_category") or "")
        indication: str | None = None
        dose: str | None = None
        for paragraph in split_paragraphs(_section_text(ctx, item.id)):
            if re.match(r"^\[[^\]]+\] ", paragraph):
                continue  # footnote appended to the chunk by Phase 2
            if is_condition_header(paragraph):
                header = paragraph.rstrip(":")
                if header.lower().startswith("indication"):
                    indication, dose = header, None
                elif header.lower().startswith(("daily dose", "use as")):
                    dose = header
                continue
            conditions = "; ".join(
                c for c in (f"Use category: {_USE_LABEL.get(use, use)}", indication, dose) if c
            )
            for sentence in split_sentences(paragraph):
                result = extract_mechanisms(sentence, patterns)
                if result.outcome in (
                    Outcome.SUBJECT_UNCLEAR,
                    Outcome.OTHER_DRUGS,
                    Outcome.NEGATED,
                    Outcome.NO_EFFECT_VERB,
                ):
                    ctx.issue(
                        "ema_mechanism_sentence_not_used",
                        f"{result.outcome.value}: enzyme/transporter sentence not stored as an effect.",
                        severity=IssueSeverity.INFO,
                        record=record,
                        herb=herb.key,
                        sentence=sentence,
                        targets=[m.verbatim for m in find_targets(sentence)],
                    )
                for statement in result.statements:
                    evidence_type = {
                        "in_vitro": EvidenceType.IN_VITRO,
                        "animal": EvidenceType.ANIMAL,
                    }.get(statement.study_context or "", EvidenceType.REGULATORY)
                    for symbol in statement.targets:
                        target_id = targets.get(symbol)
                        if target_id is None:
                            ctx.issue(
                                "target_not_curated",
                                f"{symbol} is not in targets.yaml.",
                                severity=IssueSeverity.ERROR,
                                record=record,
                                herb=herb.key,
                            )
                            continue
                        for substance_id in substance_ids:
                            modulation_id = upsert_modulation(
                                ctx.session,
                                herbal_substance_id=substance_id,
                                target_id=target_id,
                                effect=statement.effect.value,
                                evidence_type=evidence_type.value,
                                potency=None,
                                hedge_wording=statement.hedge,
                                conditions=conditions,
                                source_code=EMA_SOURCE,
                                evidence_item_id=item.id,
                            )
                            ctx.provenance(
                                "target_modulation",
                                modulation_id,
                                record,
                                METHOD_EMA,
                                version=EXTRACTION_VERSION,
                                location=f"{item.external_id} (section 4.5, {use})",
                                excerpt=statement.sentence,
                            )
                            kept.add(modulation_id)
                            ctx.stats[f"modulations_ema_{evidence_type.value}"] += 1
    return substance_ids


def run_ema(ctx: IngestionContext, herb_keys: list[str] | None = None) -> None:
    targets = ensure_targets(ctx)
    ctx.session.commit()
    kept: set[uuid.UUID] = set()
    processed: list[uuid.UUID] = []
    for herb in load_herbs().herbs:
        if herb_keys and herb.key not in herb_keys:
            continue
        with ctx.per_item(f"ema-mechanisms:{herb.key}"):
            processed += _ema_herb(ctx, herb, targets, kept)
    if ctx.error_issues or not processed:
        return
    ctx.stats["stale_modulations_removed"] += remove_stale_edges(
        ctx.session,
        TargetModulation,
        source_code=EMA_SOURCE,
        kept_ids=kept,
        extra_conditions=[TargetModulation.herbal_substance_id.in_(processed)],
    )
    ctx.session.commit()
