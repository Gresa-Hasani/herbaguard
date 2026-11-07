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
from sqlalchemy.orm import Session, aliased

from herbaguard.ai import answer_cache
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
from herbaguard.ai.mentions import (
    CONSISTENT_FLAGS,
    STUDY_ORDER,
    pair_negation,
    study_type,
    tagged_span,
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
    ExternalRelation,
    HerbalSubstance,
    Source,
    SourceRecord,
    Target,
)
from herbaguard.repositories import mechanisms as mechanism_repo
from herbaguard.repositories.external import DDID, LIVERTOX, NIH_DSLD, SUPP_AI, resolved_entity_ids
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
    refresh_answer_cache: bool = False,
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
            session, settings, question.strip(), allow_remote_drug_lookup, chain, embeddings,
            refresh_answer_cache,
        )  # fmt: skip
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
        answer_cache_hit=response.cache is not None,
    )  # the question and answer text are never logged
    return response


def _ask(
    session: Session,
    settings: Settings,
    question: str,
    allow_remote: bool,
    chain: GenerationChain,
    embeddings: EmbeddingProvider | None,
    refresh_answer_cache: bool = False,
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
    if analysis.ambiguous and dosing:
        # A dosing request is declined whatever the plant; an ambiguous name is never resolved just to
        # quote posology, so no herb-specific passage is shown (and no unscoped retrieval runs).
        return _dosing_decline_without_herb(question, analysis)
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
                items += _supplementary_mentions(session, herb, drug)

    # 1b. NIH DSLD product-label information: labels for the herb itself, never interaction evidence.
    if (
        analysis.herbs
        and not analysis.drugs
        and analysis.intent
        in (Intent.PLANT_INFORMATION, Intent.PLANT_SAFETY, Intent.EVIDENCE_COMPARISON)
    ):
        for herb in analysis.herbs[:MAX_HERBS_PER_QUESTION]:
            items += _product_label_items(session, herb)

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

    # 2b. LiverTox hepatotoxicity evidence: liver questions only, resolved herb mappings only
    if analysis.herbs and LIVER_QUESTION.search(question):
        for herb in analysis.herbs[:MAX_HERBS_PER_QUESTION]:
            items += _hepatotoxicity_items(session, herb)

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
    reserved = dict(ctx.RESERVED_SLOTS)
    if any(item.kind == "product_label" for item in items):
        reserved["product_label"] = (
            1  # herb-only answers always show one label; interaction answers get none
        )
    context = ctx.assemble(
        items, max_tokens=settings.ai_context_max_tokens, max_items=settings.ai_context_max_items,
        redistributable=redistributable, cloud_only_redistributable=cloud and settings.ai_cloud_send_source_text,
        reserved=reserved,
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
        # Suggested questions only: a validated answer prepared earlier is served when it is still
        # valid for exactly this evidence context. Every other question skips this block entirely.
        cache_id = (
            answer_cache.suggested_question_id(question)
            if settings.ai_answer_cache_enabled
            else None
        )
        fingerprint: str | None = None
        if cache_id is not None:
            fingerprint = answer_cache.compute_fingerprint(
                settings=settings, chain_names=tuple(n.value for n in chain.names), qid=cache_id,
                intent=analysis.intent, expected=expected,
                personal_advice=analysis.asks_for_personal_advice, partial=partial, context=context,
                citations=_citations(context, [i.label for i in context.items]),
                classifications=classifications,
            )  # fmt: skip
            if not refresh_answer_cache:
                hit = answer_cache.lookup(session, settings, cache_id, fingerprint)
                if hit is not None:
                    entry, stored = hit
                    return answer_cache.servable_response(
                        entry, stored, question=question, retrieval=_retrieval_info(retrieval)
                    )
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
        response = _response(
            question, analysis, classifications, context, outcome, status, retrieval
        )
        if (
            cache_id is not None
            and fingerprint is not None
            and answer_cache.eligible_for_storage(
                response, mode=outcome.mode, failed_attempts=len(outcome.attempts)
            )
        ):
            answer_cache.store(
                session, qid=cache_id, question=question, fingerprint=fingerprint, response=response
            )
        return response
    return _response(question, analysis, classifications, context, outcome, status, retrieval)


# --------------------------------------------------------------------------- helpers

# Questions about liver injury (LiverTox context is used for these only).
LIVER_QUESTION = re.compile(
    r"\b(liver|livers|hepat\w*|jaundice|cholesta\w*|cirrho\w*|dili|transaminases?|livertox)\b", re.I
)
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z(])")
LIVERTOX_PASSAGE_CHARS = 900


def _first_passage(text: str, limit: int = LIVERTOX_PASSAGE_CHARS) -> tuple[str, bool]:
    """Leading whole sentences of ``text`` up to ``limit`` characters (at least one sentence); never
    cut inside a sentence. Returns (passage, whether the text continues)."""
    out: list[str] = []
    for sentence in _SENTENCE_END.split(text.strip()):
        if out and len(" ".join([*out, sentence])) > limit:
            return " ".join(out), True
        out.append(sentence)
    return " ".join(out), False


def _livertox_provenance(
    record: SourceRecord, source: Source, method: str, location: str
) -> ProvenanceOut:
    return ProvenanceOut(source_code=source.code, source_name=source.name, licence=source.licence,
                         licence_status=source.licence_status, retrieved_url=record.url,
                         retrieved_at=record.retrieved_at, source_version=record.content_sha256[:12],
                         extraction_method=method, location=location, excerpt=None)  # fmt: skip


def _hepatotoxicity_items(session: Session, herb: Any) -> list[ctx.ContextItem]:
    """LiverTox evidence for a resolved herb: the published likelihood assessments (master list and
    chapter, both shown when they differ) and the opening of the chapter's Hepatotoxicity section.
    Only LiverTox agents mapped to the herb's species by a resolved (exact, reviewed) name match are
    used. Without one, a fact states that having no record is not evidence of safety."""
    herb_name = herb.herb.common_name or herb.herb.pharmaceutical_name
    taxa = select(HerbalSubstance.taxon_id).where(HerbalSubstance.id.in_(herb.substance_ids))
    agents = session.execute(
        select(ExternalEntity, SourceRecord, Source)
        .join(SourceRecord, SourceRecord.id == ExternalEntity.source_record_id)
        .join(Source, Source.code == ExternalEntity.source_code)
        .where(ExternalEntity.id.in_(resolved_entity_ids(LIVERTOX, "taxon", taxa)),
               ExternalEntity.kind == "livertox_agent")
        .order_by(ExternalEntity.external_id)
    ).all()  # fmt: skip
    if not agents:
        return [ctx.fact_item(
            f"HerbaGuard has no LiverTox record mapped to {herb_name} by a confirmed name match. This can "
            "mean that LiverTox has no entry for it or that its entry could not be matched unambiguously. "
            "It does not show that the herb is safe for the liver or free of liver risk.",
            source_code=LIVERTOX, priority=22)]  # fmt: skip

    items: list[ctx.ContextItem] = []
    for rank, (agent, master_record, source) in enumerate(agents[:2]):
        row = agent.attributes or {}
        chapter_row = session.execute(
            select(ExternalEntity, SourceRecord)
            .join(ExternalRelation, ExternalRelation.object_id == ExternalEntity.id)
            .join(SourceRecord, SourceRecord.id == ExternalEntity.source_record_id)
            .where(ExternalRelation.subject_id == agent.id, ExternalRelation.predicate == "described_in")
        ).first()  # fmt: skip
        master_score = str(row.get("Likelihood Score") or "not given").strip()
        rows = ", ".join(map(str, agent.source_row_numbers[:3]))
        sources = [_livertox_provenance(master_record, source, "livertox_masterlist_v1",
                                        f"{master_record.native_id}, row(s) {rows}")]  # fmt: skip
        parts = [f"LiverTox entry '{agent.label}' (LiverTox classification: "
                 f"{row.get('Primary Classification', 'not stated')}). LiverTox master list likelihood score: "
                 f"{master_score} (master list last updated {row.get('Last Update', 'not stated')})."]  # fmt: skip
        extra = ["mapped to the herb's species by a resolved name match; the plant part or preparation "
                 "LiverTox describes may differ"]  # fmt: skip
        chapter = None
        url = None
        if chapter_row is not None:
            chapter, chapter_record = chapter_row
            attrs = chapter.attributes or {}
            url = attrs.get("url")
            statements = [x["statement"] for x in attrs.get("likelihood", [])]
            parts.append(f"LiverTox chapter '{chapter.label}' (updated {attrs.get('updated_on') or 'not stated'}) "
                         + (f"states: {' '.join(st + '.' for st in statements)}" if statements
                            else "states no likelihood score."))  # fmt: skip
            sources.append(
                _livertox_provenance(
                    chapter_record, source, "livertox_nxml_v1", chapter_record.native_id
                )
            )
            scores = {x["score"].replace(" ", "").upper() for x in attrs.get("likelihood", [])}
            if scores and master_score.replace(" ", "").upper() not in scores:
                parts.append("The master list and the chapter give different scores; LiverTox publishes both "
                             "and HerbaGuard does not choose between them.")  # fmt: skip
                extra.append(
                    "LiverTox master list and chapter assessments differ; both shown as published"
                )
        else:
            parts.append("No LiverTox chapter is linked to this entry in HerbaGuard.")
        items.append(ctx.hepatotoxicity_item(
            text=" ".join(parts), title=f"LiverTox: {chapter.label if chapter is not None else agent.label}",
            location="likelihood assessment (master list and chapter)", url=url,
            external_id=chapter.external_id if chapter is not None else agent.external_id,
            provenance=sources, extra_qualifiers=extra, priority=22 + rank))  # fmt: skip
        if chapter is None:
            continue
        section = ((chapter.attributes or {}).get("sections") or {}).get("hepatotoxicity")
        if section:
            passage, more = _first_passage(section)
            items.append(ctx.hepatotoxicity_item(
                text=passage, title=f"LiverTox: {chapter.label}",
                location="Hepatotoxicity section, opening passage" + (" (continues in the chapter)" if more else ""),
                url=url, external_id=chapter.external_id, provenance=sources[-1:],
                extra_qualifiers=["verbatim LiverTox text"], priority=24 + rank))  # fmt: skip
    return items


MAX_DSLD_PRODUCTS = 4


def _dsld_provenance(record: SourceRecord, source: Source, location: str) -> ProvenanceOut:
    return ProvenanceOut(
        source_code=source.code, source_name=source.name, licence=source.licence,
        licence_status=source.licence_status, retrieved_url=record.url,
        retrieved_at=record.retrieved_at, source_version=record.content_sha256[:12],
        extraction_method="dsld_csv_v1", location=location, excerpt=None,
    )  # fmt: skip


def _label_statement_text(product: ExternalEntity) -> tuple[list[str], int]:
    statements = (product.attributes or {}).get("label_statements") or []
    precautions = [
        str(s.get("Statement")).strip()
        for s in statements
        if (s.get("Statement Type") or "").strip() == "Precautions"
        and (s.get("Statement") or "").strip()
    ]
    return precautions, len(statements)


def _product_label_items(session: Session, herb: Any) -> list[ctx.ContextItem]:
    """NIH DSLD product-label information for a herb, from labels whose matched ingredient entity is
    mapped to the herb's species with status ``resolved`` only. A label is manufacturer information:
    never evidence of an interaction, efficacy or safety, and never part of the A–E class.

    Only herb-only questions receive these items (see ``_ask``). No item is added when no label is
    mapped, because a missing product is not evidence of anything."""
    taxa = select(HerbalSubstance.taxon_id).where(HerbalSubstance.id.in_(herb.substance_ids))
    ingredient_ids = resolved_entity_ids(NIH_DSLD, "taxon", taxa)
    ingredient_record = aliased(SourceRecord, name="dsld_ingredient_record")
    rows = session.execute(
        select(ExternalRelation, ExternalEntity, SourceRecord, Source, ingredient_record)
        .join(ExternalEntity, ExternalEntity.id == ExternalRelation.subject_id)
        .join(SourceRecord, SourceRecord.id == ExternalEntity.source_record_id)
        .join(Source, Source.code == ExternalEntity.source_code)
        .join(ingredient_record, ingredient_record.id == ExternalRelation.source_record_id)
        .where(
            ExternalRelation.source_code == NIH_DSLD,
            ExternalRelation.predicate == "lists_ingredient",
            ExternalRelation.object_id.in_(ingredient_ids),
            ExternalEntity.kind == "dsld_product",
        )
    ).all()
    if not rows:
        return []
    products: dict[Any, dict[str, Any]] = {}
    for relation, product, record, source, facts_record in rows:
        entry = products.setdefault(
            product.id,
            {"product": product, "record": record, "source": source, "relations": [],
             "facts_records": []},
        )  # fmt: skip
        entry["relations"].append(relation)
        entry["facts_records"].append(facts_record)

    def rank(entry: dict[str, Any]) -> tuple[bool, bool, int, str]:
        overview = (entry["product"].attributes or {}).get("overview") or {}
        precautions, _ = _label_statement_text(entry["product"])
        on_market = (overview.get("Market Status") or "").strip().lower() == "on market"
        return (not on_market, not overview, -len(precautions), entry["product"].external_id)

    shown = sorted(products.values(), key=rank)[:MAX_DSLD_PRODUCTS]
    herb_name = herb.herb.common_name or herb.herb.pharmaceutical_name
    first = shown[0]
    first_rows = ", ".join(map(str, first["product"].source_row_numbers[:5]))
    summary = ctx.product_label_item(
        text=(
            f"NIH DSLD holds {len(products)} product label(s) that list {herb_name} by an exact, "
            f"resolved ingredient name; {len(shown)} label(s) are shown. Product labels are "
            "manufacturer information, not clinical evidence: a listing, or a missing listing, does "
            "not show that the herb or product is effective, safe or free of interactions."
        ),
        title="NIH DSLD product-label coverage",
        location="product-label coverage",
        url=None,
        external_id=None,
        provenance=[
            _dsld_provenance(
                first["record"],
                first["source"],
                f"{first['record'].native_id}, row(s) {first_rows}",
            )
        ],
        priority=56,
    )
    items = [summary]
    for rank_index, entry in enumerate(shown):
        product = entry["product"]
        attrs = product.attributes or {}
        overview = attrs.get("overview") or {}
        label = product.label or overview.get("Product Name") or product.external_id
        identifiers = product.identifiers or {}
        identity = (
            f"NIH DSLD product label '{label}' (DSLD ID: {product.external_id}; market status: "
            f"{overview.get('Market Status') or 'not stated'}"
        )
        if identifiers.get("upc"):
            identity += f"; UPC: {identifiers['upc']}"
        parts = [identity + ")."]
        labelled = []
        for relation in entry["relations"]:
            row = relation.attributes or {}
            amount = " ".join(
                x
                for x in (
                    (row.get("Amount Per Serving") or "").strip(),
                    (row.get("Amount Per Serving Unit") or "").strip(),
                )
                if x
            )
            category = (row.get("DSLD Ingredient Categories") or "").strip()
            labelled.append(
                f"{(row.get('Ingredient') or '').strip()} — {amount or 'amount not stated'} per serving"
                + (f" (label ingredient category: {category})" if category else "")
            )
        parts.append("Labelled ingredient: " + "; ".join(dict.fromkeys(labelled)) + ".")
        precautions, statements = _label_statement_text(product)
        for statement in precautions[:2]:
            parts.append(f'Manufacturer\'s "Precautions" statement: "{statement}"')
        parts.append(f"Label statements stored for this product: {statements}.")
        location = (
            f"{entry['record'].native_id}, row(s) "
            f"{', '.join(map(str, product.source_row_numbers[:5]))}"
        )
        provenance = [_dsld_provenance(entry["record"], entry["source"], location)]
        for relation, facts_record in zip(entry["relations"], entry["facts_records"], strict=False):
            fact_location = (
                f"{facts_record.native_id}, row(s) "
                f"{', '.join(map(str, relation.source_row_numbers[:5]))}"
            )
            if all(p.location != fact_location for p in provenance):
                provenance.append(_dsld_provenance(facts_record, entry["source"], fact_location))
        items.append(
            ctx.product_label_item(
                text=" ".join(parts),
                title=f"NIH DSLD: {label}",
                location="product label",
                url=identifiers.get("url"),
                external_id=product.external_id,
                provenance=provenance,
                extra_qualifiers=[
                    f"the label lists '{entry['relations'][0].attributes.get('Ingredient', '')}', matched "
                    f"to {herb.herb.pharmaceutical_name} only by an exact, resolved name; the product's "
                    "plant part or preparation may differ",
                    "the product label is manufacturer information; HerbaGuard does not verify its "
                    "composition or claims",
                ],
                priority=55 + rank_index,
            )
        )
    return items


MAX_OBSERVATIONS_PER_PAIR = 4
_CONTEXT_ORDER = {"human": 0, "animal": 1, "unknown": 2}


def _experimental_observations(session: Session, herb: Any, drug: Any) -> list[ctx.ContextItem]:
    """Experimental records of external datasets (DDID) for a herb–drug pair: herb entries mapped
    to the herb's species and drug entries mapped to the drug. They are context only; the A–E class
    never uses them. Human records first, then records with a PMID."""
    taxa = select(HerbalSubstance.taxon_id).where(HerbalSubstance.id.in_(herb.substance_ids))
    # DDID only, resolved mappings only: other external datasets (SUPP.AI, LiverTox, NIH DSLD) and
    # candidate/ambiguous/unresolved entities can never enter this context.
    herb_entities = resolved_entity_ids(DDID, "taxon", taxa)
    drug_entities = resolved_entity_ids(DDID, "drug", [drug.drug_id])
    rows = session.execute(
        select(ExperimentalObservation, ExternalEntity, SourceRecord, Source)
        .join(ExternalEntity, ExternalEntity.id == ExperimentalObservation.interactant_entity_id)
        .join(SourceRecord, SourceRecord.id == ExperimentalObservation.source_record_id)
        .join(Source, Source.code == ExperimentalObservation.source_code)
        .where(ExperimentalObservation.source_code == DDID,
               ExperimentalObservation.interactant_entity_id.in_(herb_entities),
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


# --------------------------------------------------------------------------- SUPP.AI mentions

# Only the highest-ranked eligible mention of a pair is built; `context.assemble` then includes at
# most one mention (context.MENTION_LIMIT) across the whole context, and only from free capacity.
MAX_MENTIONS_PER_PAIR = 1
# After every other kind of evidence (statements 5/35, mechanisms 10/30, excerpts 20+, DDID 23-28,
# LiverTox 22-25, facts 25-40): mentions only fill slots and tokens that nothing stronger uses.
MENTION_PRIORITY = 60


def _supplementary_mentions(session: Session, herb: Any, drug: Any) -> list[ctx.ContextItem]:
    """SUPP.AI interaction mentions for a herb–drug pair: only when the SUPP.AI supplement is mapped
    to the herb's species and the SUPP.AI drug to the drug, both by a resolved name match. Mentions
    from retracted papers, or whose paper metadata is missing (retraction status unknown), are
    excluded. Supplementary context only: never a confirmed interaction, never part of the class."""
    taxa = select(HerbalSubstance.taxon_id).where(HerbalSubstance.id.in_(herb.substance_ids))
    supplements = resolved_entity_ids(SUPP_AI, "taxon", taxa).where(
        ExternalEntity.kind == "supplement"
    )
    drugs = resolved_entity_ids(SUPP_AI, "drug", [drug.drug_id]).where(
        ExternalEntity.kind == "drug"
    )
    subject, obj = aliased(ExternalEntity), aliased(ExternalEntity)
    rows = session.execute(
        select(ExternalRelation, SourceRecord, Source, subject, obj)
        .join(SourceRecord, SourceRecord.id == ExternalRelation.source_record_id)
        .join(Source, Source.code == ExternalRelation.source_code)
        .join(subject, subject.id == ExternalRelation.subject_id)
        .join(obj, obj.id == ExternalRelation.object_id)
        .where(ExternalRelation.source_code == SUPP_AI, ExternalRelation.predicate == "interaction_mentioned",
               ExternalRelation.subject_id.in_(supplements), ExternalRelation.object_id.in_(drugs))
    ).all()  # fmt: skip
    herb_name = herb.herb.common_name or herb.herb.pharmaceutical_name
    if not rows:
        return []
    eligible, retracted, no_paper = [], 0, 0
    for row in rows:
        paper = (row[0].attributes or {}).get("paper")
        if not paper:
            no_paper += 1
        elif paper.get("retraction"):
            retracted += 1
        else:
            eligible.append(row)
    excluded = (f" {retracted} mention(s) from retracted papers and {no_paper} without paper metadata "
                "(retraction status unknown) were excluded.") if retracted or no_paper else ""  # fmt: skip
    if not eligible:
        return [ctx.fact_item(
            f"SUPP.AI holds no eligible machine-extracted mention for {herb_name} with {drug.name}.{excluded} "
            "This does not show that no interaction exists.", source_code=SUPP_AI,
            priority=MENTION_PRIORITY + MAX_MENTIONS_PER_PAIR)]  # fmt: skip

    def kind_of(row: Any) -> str:
        attrs = row[0].attributes or {}
        return study_type(attrs.get("paper"), (attrs.get("sentence") or {}).get("sentence"))

    eligible.sort(key=lambda r: (STUDY_ORDER[kind_of(r)], -int(((r[0].attributes or {}).get("paper") or {}).get("year") or 0),
                                 str(r[0].id)))  # fmt: skip
    counts: dict[str, int] = {}
    for row in eligible:
        counts[kind_of(row)] = counts.get(kind_of(row), 0) + 1
    summary = ", ".join(
        f"{n} {k.replace('_', ' ')}"
        for k, n in sorted(counts.items(), key=lambda x: STUDY_ORDER[x[0]])
    )
    names = [herb.herb.common_name, herb.herb.pharmaceutical_name]
    items: list[ctx.ContextItem] = []
    for rank, (relation, record, source, sup, drg) in enumerate(eligible[:MAX_MENTIONS_PER_PAIR]):
        attrs = relation.attributes or {}
        sentence = attrs.get("sentence") or {}
        paper = attrs.get("paper") or {}
        text_ = str(sentence.get("sentence") or "")
        kind = kind_of((relation,))
        args = [a for a in (sentence.get("arg1"), sentence.get("arg2")) if isinstance(a, dict)]
        tag = {a.get("id"): tagged_span(text_, a) for a in args}
        herb_terms = [*filter(None, names), sup.label or "", *((sup.attributes or {}).get("synonyms") or []),
                      tag.get(sup.external_id) or ""]  # fmt: skip
        drug_terms = [drug.name, drg.label or "", *((drg.attributes or {}).get("synonyms") or []),
                      tag.get(drg.external_id) or ""]  # fmt: skip
        negation = pair_negation(text_, herb_terms, drug_terms)
        pmid = paper.get("pmid")
        tagged = [t for t in tag.values() if t]
        if kind in CONSISTENT_FLAGS:
            flags = "SUPP.AI paper flags: " + ", ".join(
                f"{f}={str(bool(paper.get(f))).lower()}" for f in ("clinical_study", "human_study", "animal_study", "retraction")) + ". "  # fmt: skip
        else:  # the flags contradict the paper; showing them would invite a wrong study type
            flags = (
                "SUPP.AI paper flags are not shown: they do not match the paper (see study type). "
            )
        lead = (f"SUPP.AI holds {len(eligible)} eligible machine-extracted mention(s) for {herb_name} with "
                f"{drug.name} (study type: {summary}).{excluded} " if rank == 0 else "")  # fmt: skip
        text = (f'{lead}SUPP.AI machine-extracted mention: "{text_}" '
                f"Paper: {paper.get('title') or 'title not stated'} ({paper.get('venue') or 'venue not stated'}, "
                f"{paper.get('year') or 'year not stated'}); PMID {pmid or 'not stated'}"
                + (f"; DOI {paper['doi']}" if paper.get("doi") else "") + ". " + flags
                + (f"Terms tagged by SUPP.AI: {', '.join(repr(t) for t in tagged)}. " if tagged else "")
                + f"Negation applying to this pair: {repr(negation.negated) if negation.negated else 'none detected'}. "
                + (f"Warning wording: {negation.warning!r}. " if negation.warning else "")
                + f"SUPP.AI release {str(attrs.get('release') or 'not stated')[:10]}.")  # fmt: skip
        location = (f"{record.native_id}, interaction {attrs.get('interaction_id')}, sentence uid {sentence.get('uid')}"
                    f", line(s) {', '.join(map(str, relation.source_row_numbers[:2]))}")  # fmt: skip
        provenance = [ProvenanceOut(
            source_code=source.code, source_name=source.name, licence=source.licence,
            licence_status=source.licence_status, retrieved_url=record.url, retrieved_at=record.retrieved_at,
            source_version=record.content_sha256[:12], extraction_method="supp_ai_json_v1",
            location=location, excerpt=None)]  # fmt: skip
        items.append(ctx.mention_item(
            text=text, study_type=kind, negation_cue=negation.negated, warning_cue=negation.warning,
            other_negation_cue=negation.elsewhere, external_id=f"PMID:{pmid}" if pmid else None,
            url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else None,
            title=paper.get("title"), location=location, provenance=provenance,
            priority=MENTION_PRIORITY + rank))  # fmt: skip
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


def _dosing_decline_without_herb(question: str, analysis: QuestionAnalysis) -> AskResponse:
    """Dosing decline when a plant or drug name in the question is ambiguous: the decline message
    and referral only. No species is assumed, so no posology passage is quoted."""
    names = "; ".join(f"'{m.mention}' matches more than one {m.kind}" for m in analysis.ambiguous)
    limitations = [
        f"{names}, so no official posology passage is shown; HerbaGuard does not assume a species.",
        REFERRAL,
    ]
    return AskResponse(
        status="declined_dosing", question=question, intent=analysis.intent.value,
        answer=DOSING_MESSAGE, paragraphs=[ParagraphOut(text=DOSING_MESSAGE, citations=[])],
        classification=[], citations=[], limitations=limitations, insufficient_evidence=True, entities=[],
        personal_advice_requested=True, validation=[],
        generation=GenerationInfo(mode="none", provider="none", model=None, prompts=[], input_tokens=None,
                                  output_tokens=None, duration_ms=0, failed_attempts=[]),
        retrieval=None, disclaimer=DISCLAIMER,
    )  # fmt: skip


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
        retrieval=_retrieval_info(retrieval),
        disclaimer=DISCLAIMER,
    )


def _retrieval_info(retrieval: RetrievalResult | None) -> RetrievalInfo | None:
    if retrieval is None:
        return None
    return RetrievalInfo(
        mode_requested=retrieval.mode_requested,
        mode_used=retrieval.mode_used,
        embedding_model=retrieval.embedding_model,
        candidates=retrieval.candidates,
        duration_ms=retrieval.duration_ms,
        notes=retrieval.notes,
    )


__all__ = ["ask", "load_prompt"]
