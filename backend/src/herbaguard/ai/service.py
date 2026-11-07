"""AI request orchestration: question → entities → classification → graph context → retrieval →
evidence assembly → generation → validation → response.

The classification shown to users is always the interaction service's output (A–E rules of
Phases 3–4). The language model receives it as context and its answer is checked against it.
"""

from __future__ import annotations

import re
import threading
import time
from collections import Counter
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from herbaguard.ai import context as ctx
from herbaguard.ai.embeddings import EmbeddingProvider
from herbaguard.ai.generation import GenerationOutcome, extractive_answer, generate, load_prompt
from herbaguard.ai.guardrails import (
    DOSING_MESSAGE,
    EMERGENCY_MESSAGE,
    POSOLOGY_TERMS,
    REFERRAL,
    QuestionKind,
    screen,
)
from herbaguard.ai.providers.base import ProviderError
from herbaguard.ai.providers.registry import GenerationChain
from herbaguard.ai.query import Intent, QuestionAnalysis, analyse
from herbaguard.ai.retrieval import RetrievalFilters, RetrievalQuery, RetrievalResult, retrieve
from herbaguard.ai.validation import Paragraph, ValidationResult
from herbaguard.api.schemas.ai import (
    AskResponse,
    CitationOut,
    EntityOut,
    GenerationInfo,
    PairClassification,
    ParagraphOut,
    RetrievalInfo,
    ValidationIssueOut,
)
from herbaguard.api.schemas.provenance import EvidenceTypeInfo, ProvenanceOut
from herbaguard.api.schemas.resources import DrugCheckResult
from herbaguard.core.config import DISCLAIMER, Settings
from herbaguard.core.errors import (
    AmbiguousEntityError,
    BadRequestError,
    ServiceUnavailableError,
    TooManyRequestsError,
)
from herbaguard.models import (
    DrugTargetRoleLink,
    EvidenceItem,
    ExperimentalObservation,
    ExternalEntity,
    HerbalSubstance,
    Source,
    SourceRecord,
    Target,
)
from herbaguard.repositories import mechanisms as mechanism_repo
from herbaguard.services import evidence as evidence_service
from herbaguard.services import interactions as interaction_service
from herbaguard.services import mechanisms as mechanism_service

logger = structlog.get_logger("herbaguard.ai")

MAX_HERBS_PER_QUESTION = 3
MAX_DRUGS_PER_QUESTION = 5
_slots: dict[int, threading.BoundedSemaphore] = {}
_slots_lock = threading.Lock()


def _semaphore(size: int) -> threading.BoundedSemaphore:
    with _slots_lock:
        if size not in _slots:
            _slots[size] = threading.BoundedSemaphore(size)
        return _slots[size]


def ask(
    session: Session,
    settings: Settings,
    *,
    question: str,
    allow_remote_drug_lookup: bool,
    chain: GenerationChain,
    embeddings: EmbeddingProvider | None,
) -> AskResponse:
    if len(question) > settings.ai_question_max_chars:
        raise BadRequestError(
            f"The question is longer than {settings.ai_question_max_chars} characters."
        )
    semaphore = _semaphore(settings.ai_max_concurrent_requests)
    if not semaphore.acquire(blocking=False):
        raise TooManyRequestsError("The AI service is busy; try again shortly.")
    started = time.perf_counter()
    try:
        response = _ask(
            session, settings, question.strip(), allow_remote_drug_lookup, chain, embeddings
        )
    finally:
        semaphore.release()
    logger.info(
        "ai_request",
        intent=response.intent,
        status=response.status,
        provider=response.generation.provider,
        model=response.generation.model,
        generation_mode=response.generation.mode,
        duration_ms=int((time.perf_counter() - started) * 1000),
        generation_ms=response.generation.duration_ms,
        retrieval_ms=response.retrieval.duration_ms if response.retrieval else None,
        retrieved=len(response.citations),
        sources=len({c.source_code for c in response.citations if c.source_code}),
        input_tokens=response.generation.input_tokens,
        output_tokens=response.generation.output_tokens,
        validation_issues=dict(Counter(i.rule for i in response.validation)),
        failed_attempts=len(response.generation.failed_attempts),
    )  # the question and answer text are never logged
    return response


def _ask(
    session: Session,
    settings: Settings,
    question: str,
    allow_remote: bool,
    chain: GenerationChain,
    embeddings: EmbeddingProvider | None,
) -> AskResponse:
    screening = screen(question)
    if screening.kind is QuestionKind.EMPTY:
        raise BadRequestError("The question contains no words.")
    if screening.kind is QuestionKind.EMERGENCY:
        return _emergency_response(question)
    dosing = screening.kind is QuestionKind.DOSING
    analysis = analyse(session, settings, question, allow_remote_drug_lookup=allow_remote)
    if dosing:
        analysis.intent = (
            Intent.PLANT_INFORMATION if analysis.herbs and not analysis.drugs else analysis.intent
        )
    if analysis.ambiguous:
        mention = analysis.ambiguous[0]
        raise AmbiguousEntityError(
            f"'{mention.mention}' matches more than one {mention.kind}; please name one of the candidates.",
            details={"mention": mention.mention, "kind": mention.kind,
                     "candidates": list(mention.candidates)},
        )  # fmt: skip

    items: list[ctx.ContextItem] = []
    classifications: list[PairClassification] = []
    expected: set[str] = set()
    has_statements = False

    # 1. deterministic classification + its statements and mechanism paths (graph context)
    if analysis.herbs and analysis.drugs:
        for herb in analysis.herbs[:MAX_HERBS_PER_QUESTION]:
            check = interaction_service.check(
                session, settings, herb_query=herb.herb.pharmaceutical_name,
                drug_queries=[d.rxcui for d in analysis.drugs[:MAX_DRUGS_PER_QUESTION]], allow_remote=False,
            )  # fmt: skip
            label = herb.herb.common_name or herb.herb.pharmaceutical_name
            items += ctx.classification_items(check.results, label)
            for result in check.results:
                classifications.append(_pair(label, result))
                expected.add(result.classification.interaction_class.value)
                for s in result.decisive_statements:
                    if (item := ctx.statement_item(s, priority=5)) is not None:
                        items.append(item)
                        has_statements = True
                for s in result.context_statements:
                    if (item := ctx.statement_item(s, priority=35)) is not None:
                        items.append(item)
                items += [ctx.mechanism_path_item(p) for p in result.mechanism_paths[:6]]
            for drug in analysis.drugs[:MAX_DRUGS_PER_QUESTION]:
                items += _experimental_observations(session, herb, drug)

    # 2. herb and target mechanism context (stored effects with their hedging and study type)
    if not analysis.drugs:
        for herb in analysis.herbs[:MAX_HERBS_PER_QUESTION]:
            if herb.wfo_ids and analysis.intent in (Intent.MECHANISM, Intent.PLANT_SAFETY,
                                                    Intent.PLANT_INFORMATION, Intent.EVIDENCE_COMPARISON):  # fmt: skip
                effects = mechanism_service.list_herb_effects(
                    session, target=None, evidence_types=None, effect=None, subject_kind=None,
                    wfo_id=herb.wfo_ids[0], limit=10, offset=0,
                )  # fmt: skip
                items += [ctx.herb_effect_item(e) for e in effects.items]
    for symbol, target_id in analysis.targets[:3]:
        effects = mechanism_service.list_herb_effects(
            session, target=symbol, evidence_types=None, effect=None, subject_kind=None,
            wfo_id=None, limit=10, offset=0,
        )  # fmt: skip
        items += [ctx.herb_effect_item(e) for e in effects.items if not analysis.herbs
                  or e.herb in {h.herb.pharmaceutical_name for h in analysis.herbs}]  # fmt: skip
        items.append(_target_roles_fact(session, symbol, target_id))
    if analysis.intent in (Intent.DRUG_INFORMATION, Intent.MECHANISM):
        for drug in analysis.drugs[:MAX_DRUGS_PER_QUESTION]:
            if (fact := _drug_roles_fact(session, drug.drug_id, drug.name)) is not None:
                items.append(fact)

    # 3. catalogue facts
    if analysis.intent in (Intent.DATA_COVERAGE, Intent.SOURCE_PROVENANCE):
        items += _catalogue_facts(session)

    # 4. hybrid retrieval within the resolved entities
    retrieval: RetrievalResult | None = None
    if analysis.intent not in (Intent.DATA_COVERAGE,):
        query = pipeline_query(analysis, question)
        if dosing:  # look for official posology passages of the recognised herbs
            query = RetrievalQuery(query.text, (*query.expansions, *POSOLOGY_TERMS), query.filters)
        retrieval = retrieve(session, settings, query, embeddings)
        scoped = bool(analysis.herbs or analysis.drugs or analysis.targets or analysis.constituents)
        kept = [r for r in retrieval.items
                if scoped or (r.similarity is not None and r.similarity >= settings.ai_unscoped_min_similarity)]  # fmt: skip
        if not scoped and len(kept) < len(retrieval.items):
            retrieval.notes.append(
                "No herb, drug, enzyme, transporter or constituent was recognised in the question; only "
                "passages with high semantic similarity were used."
            )
        items += [ctx.excerpt_item(r, rank=i + 1) for i, r in enumerate(kept)]

    cloud = any(p is not None and p.is_cloud for p in chain.providers)
    redistributable: dict[str, bool] = dict(
        session.execute(select(Source.code, Source.redistributable)).tuples().all()
    )
    context = ctx.assemble(
        items, max_tokens=settings.ai_context_max_tokens, max_items=settings.ai_context_max_items,
        redistributable=redistributable, cloud_only_redistributable=cloud and settings.ai_cloud_send_source_text,
    )  # fmt: skip

    # 5. generation (no model call when nothing citable was found)
    partial = bool(expected & {"D", "E"}) or (
        bool(analysis.drugs and analysis.herbs) and not has_statements
    )
    if dosing:
        outcome = GenerationOutcome("answered", "none", "none", None, _dosing_answer(context), [])
        status = "declined_dosing"
    elif not context.citable:
        validation = extractive_answer(
            context, reason="HerbaGuard found no stored evidence for this question."
        )
        validation.insufficient_evidence = True
        outcome = GenerationOutcome("answered", "none", "none", None, validation, [], duration_ms=0)
        status = "insufficient_evidence"
    else:
        try:
            outcome = generate(settings, chain, question=question, intent=analysis.intent, context=context,
                               expected_classes=expected, personal_advice=analysis.asks_for_personal_advice,
                               partial_coverage=partial)  # fmt: skip
        except ProviderError as exc:
            raise ServiceUnavailableError(
                f"The answer generator is not available: {exc.message}",
                details={"provider": exc.provider, "kind": exc.kind.value,
                         "hint": "POST /api/v1/ai/retrieve returns the evidence without generation."},
            ) from None  # fmt: skip
        status = "rejected_by_validation" if outcome.status == "rejected" else (
            "insufficient_evidence" if outcome.validation.insufficient_evidence else "answered")  # fmt: skip
    return _response(question, analysis, classifications, context, outcome, status, retrieval)


# --------------------------------------------------------------------------- helpers

MAX_OBSERVATIONS_PER_PAIR = 4
_CONTEXT_ORDER = {"human": 0, "animal": 1, "unknown": 2}


def _experimental_observations(session: Session, herb: Any, drug: Any) -> list[ctx.ContextItem]:
    """Experimental records of external datasets (DDID) for a herb–drug pair: herb entries mapped
    to the herb's species and drug entries mapped to the drug. They are context only; the A–E class
    never uses them. Human records first, then records with a PMID."""
    taxa = select(HerbalSubstance.taxon_id).where(HerbalSubstance.id.in_(herb.substance_ids))
    herb_entities = select(ExternalEntity.id).where(
        ExternalEntity.mapped_table == "taxon",
        ExternalEntity.mapped_id.in_(taxa),
        ExternalEntity.mapping_status
        == "resolved",  # candidates (synonym matches) need review first
    )
    drug_entities = select(ExternalEntity.id).where(
        ExternalEntity.mapped_table == "drug",
        ExternalEntity.mapped_id == drug.drug_id,
        ExternalEntity.mapping_status == "resolved",
    )
    rows = session.execute(
        select(ExperimentalObservation, ExternalEntity, SourceRecord, Source)
        .join(ExternalEntity, ExternalEntity.id == ExperimentalObservation.interactant_entity_id)
        .join(SourceRecord, SourceRecord.id == ExperimentalObservation.source_record_id)
        .join(Source, Source.code == ExperimentalObservation.source_code)
        .where(ExperimentalObservation.interactant_entity_id.in_(herb_entities),
               ExperimentalObservation.drug_entity_id.in_(drug_entities))
    ).all()  # fmt: skip
    if not rows:
        return []
    counts: dict[str, int] = {}
    for obs, *_ in rows:
        counts[obs.derived_study_context] = counts.get(obs.derived_study_context, 0) + 1
    ranked = sorted(
        rows,
        key=lambda r: (
            _CONTEXT_ORDER.get(r[0].derived_study_context, 3),
            r[0].pmid is None,
            str(r[0].id),
        ),
    )
    evidence = {
        e.id: e for e in session.scalars(
            select(EvidenceItem).where(EvidenceItem.id.in_([r[0].evidence_item_id for r in ranked if r[0].evidence_item_id])))
    }  # fmt: skip
    herb_name = herb.herb.common_name or herb.herb.pharmaceutical_name
    summary = ", ".join(
        f"{n} {c if c != 'unknown' else 'species not stated'}" for c, n in sorted(counts.items())
    )
    items = [ctx.fact_item(
        f"The external dataset DDID holds {len(rows)} experimental record(s) for {herb_name} (species level) "
        f"with {drug.name}: {summary}. These are individual study records, not a HerbaGuard classification.",
        source_code="ddid", priority=23)]  # fmt: skip
    for rank, (obs, entity, record, source) in enumerate(ranked[:MAX_OBSERVATIONS_PER_PAIR]):
        o = obs.original
        part = (entity.attributes or {}).get("Use_Part") or "not stated"
        details = [f"{k}: {o.get(col)}" for k, col in (("design", "Experimental_Design"), ("n", "Experimental_Individuals_Number"),
                   ("drug dose", "Drug_Dose"), ("dosage form", "Dosage_Form"), ("herb/food dose", "Dose"),
                   ("timing", "Time"), ("method", "Test_Method"), ("sample", "Test_Sample"))
                   if (o.get(col) or "").strip() not in ("", "NA")]  # fmt: skip
        text = (f"DDID record: {entity.label or o.get('Food_Herb_Name')} with {o.get('Drug_Name')}. "
                f"Species: {obs.species or 'not stated'}. " + ("; ".join(details) + ". " if details else "")
                + f"Result: {obs.result or 'not stated'}. Conclusion: {obs.conclusion or 'not stated'}. "
                f"DDID label: {obs.effect_label}.")  # fmt: skip
        item = evidence.get(obs.evidence_item_id) if obs.evidence_item_id else None
        provenance = [ProvenanceOut(
            source_code=source.code, source_name=source.name, licence=source.licence,
            licence_status=source.licence_status, retrieved_url=record.url, retrieved_at=record.retrieved_at,
            source_version=record.content_sha256[:12], extraction_method="ddid_csv_v1",
            location=f"{record.native_id}, row(s) {', '.join(map(str, obs.source_row_numbers[:5]))}", excerpt=None)]  # fmt: skip
        items.append(
            ctx.observation_item(
                text=text,
                study_context=obs.derived_study_context,
                effect_label=obs.effect_label,
                evidence_item_id=str(item.id) if item else None,
                external_id=item.external_id if item else None,
                url=item.url if item else None,
                title=item.title if item else obs.reference,
                location=f"{record.native_id}, row(s) {', '.join(map(str, obs.source_row_numbers[:5]))}",
                provenance=provenance,
                plant_part_note=f"DDID herb entry '{entity.label}' (plant part: {part}) is matched to the species "
                f"of {herb.herb.pharmaceutical_name}; the part may differ.",
                priority=24 + rank,
            )
        )  # fmt: skip — keeps human-first order in the reserved slots
    return items


_POSOLOGY = re.compile(
    r"posology|method of administration|daily dose|dosage|duration of use|4\.2", re.I
)


def _dosing_answer(context: ctx.EvidenceContext) -> ValidationResult:
    """Deterministic reply to a dosing question: the decline message, the classification lines (if
    a pair was asked about) and up to three official posology passages quoted verbatim."""
    paragraphs = [Paragraph(DOSING_MESSAGE, ())]
    for item in context.items:
        if item.kind == "classification":
            paragraphs.append(Paragraph(" ".join(item.text.splitlines()[:3]), (item.label,)))
    posology = [i for i in context.items if i.kind in ("excerpt", "statement")
                and _POSOLOGY.search(f"{i.location or ''} {i.title or ''} {i.text}")][:3]  # fmt: skip
    for item in posology:
        paragraphs.append(
            Paragraph(f'{item.title or item.source_code}: "{item.text}"', (item.label,))
        )
    limitations = [REFERRAL]
    if not posology:
        limitations.insert(0, "No official posology passage was found for this question.")
    return ValidationResult(paragraphs, limitations, insufficient_evidence=not posology)


def _emergency_response(question: str) -> AskResponse:
    return AskResponse(
        status="emergency_referral", question=question, intent=Intent.GENERAL.value,
        answer=EMERGENCY_MESSAGE, paragraphs=[ParagraphOut(text=EMERGENCY_MESSAGE, citations=[])],
        classification=[], citations=[], limitations=[], insufficient_evidence=False, entities=[],
        personal_advice_requested=True, validation=[],
        generation=GenerationInfo(mode="none", provider="none", model=None, prompts=[], input_tokens=None,
                                  output_tokens=None, duration_ms=0, failed_attempts=[]),
        retrieval=None, disclaimer=DISCLAIMER,
    )  # fmt: skip


def pipeline_query(analysis: QuestionAnalysis, question: str) -> RetrievalQuery:
    """The retrieval query /ai/ask uses: the question, entity names as expansions, and evidence
    scoped to the recognised herbs, drugs and enzymes/transporters (any of them). Shared with the
    evaluation so the benchmark measures the production configuration."""
    filters = RetrievalFilters(
        herb_substance_ids=tuple(i for h in analysis.herbs for i in h.substance_ids),
        drug_ids=tuple(d.drug_id for d in analysis.drugs),
        target_ids=tuple(t for _, t in analysis.targets),
        entity_match="any",
    )
    return RetrievalQuery(question, analysis.expansions, filters)


def _pair(herb: str, result: DrugCheckResult) -> PairClassification:
    c = result.classification
    return PairClassification(
        herb=herb, drug=result.drug.drug.name if result.drug.drug else result.drug.query,
        interaction_class=c.interaction_class.value, class_label=c.class_label, finding=c.finding.value,
        finding_label=c.finding_label, explanation=c.explanation, severity_wordings=c.severity_wordings,
        caveats=c.caveats, mechanism_assessment=result.mechanism_assessment, method=c.method,
    )  # fmt: skip


def _target_roles_fact(session: Session, symbol: str, target_id: object) -> ctx.ContextItem:
    rows = mechanism_repo.drug_roles(session, target_ids=[target_id])  # type: ignore[list-item]
    by_role: dict[str, list[str]] = {}
    for r in rows:
        by_role.setdefault(r.role.role.replace("_", " "), []).append(r.drug.name)
    parts = [
        f"{role}: {len(names)} (e.g. {', '.join(sorted(names)[:6])})"
        for role, names in sorted(by_role.items())
    ]
    text = (
        f"FDA's table of drugs interacting with CYP enzymes and transporters lists for {symbol}: "
        + ("; ".join(parts) if parts else "no drugs")
        + ". FDA lists examples only. Being listed for the same enzyme or transporter does not by itself "
        "mean that two substances interact."
    )
    return ctx.fact_item(text, source_code="fda_cyp_table", priority=25)


def _drug_roles_fact(session: Session, drug_id: object, name: str) -> ctx.ContextItem | None:
    rows = mechanism_repo.drug_roles(session, drug_id=drug_id)  # type: ignore[arg-type]
    if not rows:
        return None
    roles = sorted({f"{r.role.role.replace('_', ' ')} of {r.target.symbol}" for r in rows})
    return ctx.fact_item(
        f"FDA's CYP/transporter table lists {name} as: {'; '.join(roles)}.",
        source_code="fda_cyp_table",
        priority=25,
    )


def _catalogue_facts(session: Session) -> list[ctx.ContextItem]:
    sources = evidence_service.sources(session)
    coverage = evidence_service.coverage(session)
    herbs = ", ".join(
        sorted(
            f"{r.herb.common_name or r.herb.pharmaceutical_name} ({r.herb.pharmaceutical_name})"
            for r in coverage
        )
    )
    lines = [f"HerbaGuard currently covers {len(coverage)} curated herbs: {herbs}."]
    used = [s for s in sources if s.records]
    lines.append("Sources with stored records: " + "; ".join(
        f"{s.name} [{s.code}] — {s.records} records, licence status {s.licence_status}" for s in used))  # fmt: skip
    targets = session.scalar(select(func.count()).select_from(Target)) or 0
    roles = session.scalar(select(func.count()).select_from(DrugTargetRoleLink)) or 0
    lines.append(
        f"Mechanism layer: {targets} enzymes/transporters and {roles} FDA drug-role entries."
    )
    return [ctx.fact_item(line, priority=5) for line in lines]


def _citations(context: ctx.EvidenceContext, labels: list[str]) -> list[CitationOut]:
    items = context.by_label()
    out = []
    for label in labels:
        item = items[label]
        out.append(
            CitationOut(
                label=label, kind=item.kind, role=item.role, evidence_item_id=item.evidence_item_id,
                external_id=item.external_id, source_code=item.source_code,
                evidence_type=EvidenceTypeInfo.of(item.evidence_type, item.source_code or "") if item.evidence_type else None,
                title=item.title, url=item.url, location=item.location, excerpt=item.text,
                qualifiers=item.qualifiers, provenance=item.provenance,
            )
        )  # fmt: skip
    return out


def _response(
    question: str,
    analysis: QuestionAnalysis,
    classifications: list[PairClassification],
    context: ctx.EvidenceContext,
    outcome: GenerationOutcome,
    status: str,
    retrieval: RetrievalResult | None,
) -> AskResponse:
    validation: ValidationResult = outcome.validation
    rejected = status == "rejected_by_validation"
    paragraphs = (
        []
        if rejected
        else [ParagraphOut(text=p.text, citations=list(p.citations)) for p in validation.paragraphs]
    )
    cited = list(dict.fromkeys(c for p in paragraphs for c in p.citations))
    for item in context.items:  # classification blocks are always shown with their source
        if item.kind == "classification" and item.label not in cited:
            cited.append(item.label)
    limitations = list(dict.fromkeys(validation.limitations))
    if analysis.asks_for_personal_advice and REFERRAL not in limitations:
        limitations.append(REFERRAL)
    if rejected:
        limitations.insert(0, "The generated answer failed HerbaGuard's validation and is not shown; the "
                              "classification and evidence below are unaffected.")  # fmt: skip
    entities = (
        [EntityOut(kind="herb", mention=h.mention, name=h.herb.common_name or h.herb.pharmaceutical_name,
                   identifier=h.herb.pharmaceutical_name, note=h.note) for h in analysis.herbs]
        + [EntityOut(kind="drug", mention=d.mention, name=d.name, identifier=d.rxcui) for d in analysis.drugs]
        + [EntityOut(kind="target", mention=s, name=s, identifier=s) for s, _ in analysis.targets]
        + [EntityOut(kind="constituent", mention=n, name=n, identifier=None) for n, _ in analysis.constituents]
    )  # fmt: skip
    return AskResponse(
        status=status,
        question=question,
        intent=analysis.intent.value,
        answer=None if rejected or not paragraphs else "\n\n".join(p.text for p in paragraphs),
        paragraphs=paragraphs,
        classification=classifications,
        citations=_citations(context, cited),
        limitations=limitations,
        insufficient_evidence=validation.insufficient_evidence or status == "insufficient_evidence",
        entities=entities,
        personal_advice_requested=analysis.asks_for_personal_advice,
        validation=[
            ValidationIssueOut(
                rule=i.rule,
                severity=i.severity,
                message=i.message,
                paragraph=i.paragraph,
                text=i.text,
            )
            for i in validation.issues
        ],
        generation=GenerationInfo(
            mode=outcome.mode,
            provider=outcome.provider,
            model=outcome.model,
            prompts=outcome.prompts,
            input_tokens=outcome.usage.input_tokens,
            output_tokens=outcome.usage.output_tokens,
            duration_ms=outcome.duration_ms,
            failed_attempts=outcome.attempts,
            regenerations=outcome.regenerations,
        ),
        retrieval=RetrievalInfo(
            mode_requested=retrieval.mode_requested,
            mode_used=retrieval.mode_used,
            embedding_model=retrieval.embedding_model,
            candidates=retrieval.candidates,
            duration_ms=retrieval.duration_ms,
            notes=retrieval.notes,
        )
        if retrieval
        else None,
        disclaimer=DISCLAIMER,
    )


__all__ = ["ask", "load_prompt"]
