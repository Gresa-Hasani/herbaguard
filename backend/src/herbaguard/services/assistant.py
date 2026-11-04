"""AI evidence assistant (Phase 5): question → grounded, cited answer.

Pipeline (docs/api/assistant.md):
1. screen the question (emergency / dosing) with fixed rules;
2. recognise the herb and drugs (request fields, else names from HerbaGuard's index);
3. run the deterministic interaction check for recognised pairs (classes A–E, unchanged);
4. retrieve passages: evidence that decided those results, then hybrid full-text + vector
   search restricted to the herb's evidence, fused with Reciprocal Rank Fusion;
5. generate with the local LLM, validate citations, retry once, else answer extractively.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Literal

import structlog
from sqlalchemy.orm import Session

from herbaguard.ai import citations as citation_rules
from herbaguard.ai.extractive import ExtractivePassage, best_quotes, compose
from herbaguard.ai.fusion import Candidate, reciprocal_rank_fusion, select_passages
from herbaguard.ai.guardrails import (
    DOSING_MESSAGE,
    EMERGENCY_MESSAGE,
    REFERRAL,
    QuestionKind,
    screen,
)
from herbaguard.ai.llm import (
    ChatMessage,
    ChatModel,
    Embedder,
    LLMUnavailableError,
    OllamaChatModel,
    OllamaEmbedder,
    ollama_status,
)
from herbaguard.ai.prompting import (
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    PromptFact,
    PromptPassage,
    build_user_prompt,
    retry_message,
)
from herbaguard.ai.text import TermMatch, content_terms, spot_terms, truncate
from herbaguard.api.schemas.assistant import (
    AnswerMode,
    AssistantRequest,
    AssistantResponse,
    AssistantStatus,
    Citation,
    EntitiesOut,
    GenerationInfo,
    InteractionFinding,
)
from herbaguard.api.schemas.provenance import EvidenceTypeInfo
from herbaguard.api.schemas.resources import DrugResolution, HerbResolution
from herbaguard.core.config import DISCLAIMER, AssistantProvider, Settings
from herbaguard.models.evidence import EMBEDDING_DIMENSION
from herbaguard.repositories import plants as plant_repo
from herbaguard.repositories import retrieval as repo
from herbaguard.services import drugs as drug_service
from herbaguard.services import interactions as interaction_service
from herbaguard.services import plants as plant_service

logger = structlog.get_logger(__name__)

RetrievalKind = Literal["interaction_result", "full_text", "vector"]
FTS_CANDIDATES = 30
VECTOR_CANDIDATES = 30
EXCERPT_CHARS = 900
DOSING_TERMS = ["posology", "dose", "dosage", "daily", "method", "administration", "duration"]


# --------------------------------------------------------------------------- dependencies


def chat_model_for(settings: Settings) -> ChatModel | None:
    if settings.assistant_provider is AssistantProvider.NONE:
        return None
    return OllamaChatModel(settings)


def embedder_for(settings: Settings) -> Embedder | None:
    if settings.assistant_provider is AssistantProvider.NONE:
        return None
    return OllamaEmbedder(settings, dimension=EMBEDDING_DIMENSION)


# --------------------------------------------------------------------------- entities


@dataclass
class Entities:
    herb: HerbResolution | None = None
    herb_query: str | None = None
    substance_ids: list[uuid.UUID] = field(default_factory=list)
    drugs: list[DrugResolution] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def herb_resolved(self) -> bool:
        return self.herb is not None and self.herb.status == "resolved" and bool(self.substance_ids)

    def out(self) -> EntitiesOut:
        if self.herb is None:
            return EntitiesOut(herb_status="not_mentioned", drugs=self.drugs)
        return EntitiesOut(
            herb_status=self.herb.status,
            herb=self.herb.herb,
            herb_matched_text=self.herb_query,
            herb_candidates=self.herb.candidates,
            drugs=self.drugs,
        )

    def names(self) -> list[str]:
        out: list[str] = []
        if self.herb is not None and self.herb.herb is not None:
            ref = self.herb.herb
            out.extend(n for n in (ref.common_name, ref.pharmaceutical_name) if n)
        if self.herb_query:
            out.append(self.herb_query)
        out.extend(d.drug.name for d in self.drugs if d.drug is not None)
        return list(dict.fromkeys(out))


def recognise(session: Session, settings: Settings, request: AssistantRequest) -> Entities:
    entities = Entities()
    herb_queries: list[str]
    herb_spans: list[TermMatch] = []
    if request.herb:
        herb_queries = [request.herb]
    else:
        lexicon = {name: name for name in repo.herb_names(session)}
        herb_spans = spot_terms(request.question, lexicon)
        herb_queries = [m.name for m in herb_spans]

    resolved: dict[str, tuple[str, HerbResolution]] = {}
    ambiguous: tuple[str, HerbResolution] | None = None
    for query in herb_queries:
        resolution = plant_service.resolve_herb(session, query)
        if resolution.status == "resolved" and resolution.herb is not None:
            resolved.setdefault(resolution.herb.pharmaceutical_name, (query, resolution))
        elif resolution.status == "ambiguous" and ambiguous is None:
            ambiguous = (query, resolution)
        elif request.herb:
            entities.herb, entities.herb_query = resolution, query
    if resolved:
        query, resolution = next(iter(resolved.values()))
        entities.herb, entities.herb_query = resolution, query
        assert resolution.herb is not None  # noqa: S101
        entities.substance_ids = [
            s.id for s in plant_repo.herb_group(session, resolution.herb.pharmaceutical_name)
        ]
        if len(resolved) > 1:
            others = ", ".join(r.herb.common_name or p for p, (_, r) in resolved.items() if r.herb)
            entities.notes.append(
                f"Several herbs were recognised ({others}); this answer covers only the first. "
                "Ask about one herb at a time."
            )
    elif ambiguous is not None:
        entities.herb_query, entities.herb = ambiguous

    if request.drugs:
        drug_queries = request.drugs
    else:
        lexicon = repo.drug_names(session)
        # A name already read as a herb ("garlic") is not also read as a drug ingredient.
        drug_queries = [
            m.name
            for m in spot_terms(request.question, lexicon)
            if all(m.end <= h.start or m.start >= h.end for h in herb_spans)
        ]
    for query in dict.fromkeys(drug_queries):
        entities.drugs.append(drug_service.resolve(session, settings, query, allow_remote=False))
    return entities


# --------------------------------------------------------------------------- findings


@dataclass
class Findings:
    items: list[InteractionFinding] = field(default_factory=list)
    facts: list[PromptFact] = field(default_factory=list)
    pinned_evidence: list[uuid.UUID] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)

    def summary_lines(self) -> list[str]:
        return [f.text for f in self.facts]


def interaction_findings(session: Session, settings: Settings, entities: Entities) -> Findings:
    findings = Findings()
    drug_queries = [d.query for d in entities.drugs if d.status == "resolved" and d.drug]
    if not entities.herb_resolved or not drug_queries or entities.herb_query is None:
        return findings
    check = interaction_service.check(
        session,
        settings,
        herb_query=entities.herb_query,
        drug_queries=drug_queries,
        allow_remote=False,
    )
    herb_label = entities.names()[0] if entities.names() else entities.herb_query
    for result in check.results:
        c = result.classification
        drug_name = result.drug.drug.name if result.drug.drug else result.drug.query
        mechanism = result.mechanism_assessment.finding if result.mechanism_assessment else None
        findings.items.append(
            InteractionFinding(drug=result.drug, classification=c, mechanism_finding=mechanism)
        )
        findings.classes.append(c.interaction_class.value)
        findings.facts.append(
            PromptFact(
                f"{herb_label} + {drug_name}: class {c.interaction_class.value} "
                f"({c.class_label}); finding: {c.finding_label}. {c.explanation}"
            )
        )
        for statement in result.decisive_statements:
            evidence_id = uuid.UUID(statement.evidence.id)
            if evidence_id not in findings.pinned_evidence:
                findings.pinned_evidence.append(evidence_id)
    return findings


# --------------------------------------------------------------------------- retrieval


@dataclass
class Retrieved:
    candidates: list[Candidate]
    rows: dict[uuid.UUID, repo.PassageRow]
    sources: dict[uuid.UUID, list[RetrievalKind]]
    notes: list[str] = field(default_factory=list)


def retrieve(
    session: Session,
    settings: Settings,
    question: str,
    entities: Entities,
    findings: Findings,
    *,
    embedder: Embedder | None,
    extra_terms: list[str] | None = None,
) -> Retrieved:
    notes: list[str] = []
    scope = entities.substance_ids if entities.herb_resolved else None
    terms = content_terms(question) + [t for n in entities.names() for t in content_terms(n)]
    terms += extra_terms or []
    fts = repo.full_text_search(session, terms, substance_ids=scope, limit=FTS_CANDIDATES)

    vectors: list[uuid.UUID] = []
    if embedder is not None:
        embedded, _ = repo.embedding_counts(session, model=embedder.name)
        if embedded:
            try:
                query_vector = embedder.embed([question])[0]
                vectors = repo.vector_search(
                    session,
                    query_vector,
                    model=embedder.name,
                    substance_ids=scope,
                    limit=VECTOR_CANDIDATES,
                )
            except LLMUnavailableError as exc:
                logger.warning("assistant_embedding_failed", error=str(exc))
                notes.append("Vector search was skipped (embedding model unavailable).")
        else:
            notes.append(
                "Vector search is off until chunks are embedded (`herbaguard ai embed`); "
                "full-text search only."
            )

    pinned = repo.chunks_for_evidence(session, findings.pinned_evidence)
    fused = [chunk_id for chunk_id, _ in reciprocal_rank_fusion([fts, vectors])]
    rows = repo.passages(session, list(dict.fromkeys(pinned + fused)))
    sources: dict[uuid.UUID, list[RetrievalKind]] = {}
    lists: list[tuple[RetrievalKind, list[uuid.UUID]]] = [
        ("interaction_result", pinned),
        ("full_text", fts),
        ("vector", vectors),
    ]
    for label, ids in lists:
        for chunk_id in ids:
            sources.setdefault(chunk_id, []).append(label)
    ranked = [
        Candidate(str(cid), str(rows[cid].evidence.id), pinned=cid in set(pinned))
        for cid in list(dict.fromkeys(pinned + fused))
        if cid in rows
    ]
    chosen = select_passages(ranked, limit=settings.assistant_max_passages)
    return Retrieved(chosen, rows, sources, notes)


# --------------------------------------------------------------------------- answer


def _source_label(row: repo.PassageRow) -> str:
    info = EvidenceTypeInfo.of(row.evidence.evidence_type, row.evidence.source_code)
    return f"{row.source_name} ({info.label})"


def _citations(retrieved: Retrieved, cited: set[str]) -> list[Citation]:
    out = []
    for i, candidate in enumerate(retrieved.candidates, start=1):
        chunk_id = uuid.UUID(candidate.chunk_id)
        row = retrieved.rows[chunk_id]
        marker = f"S{i}"
        e = row.evidence
        out.append(
            Citation(
                marker=marker,
                evidence_id=str(e.id),
                chunk_id=candidate.chunk_id,
                href=f"/api/v1/evidence/{e.id}",
                source_code=e.source_code,
                source_name=row.source_name,
                title=e.title,
                section=row.chunk.section,
                url=e.url,
                evidence_type=EvidenceTypeInfo.of(e.evidence_type, e.source_code),
                document_date=e.document_date,
                publication_year=e.publication_year,
                excerpt=truncate(row.chunk.text, EXCERPT_CHARS),
                cited=marker in cited,
                retrieval=retrieved.sources.get(chunk_id, []),
            )
        )
    return out


def _prompt_passages(retrieved: Retrieved) -> list[PromptPassage]:
    passages = []
    for i, candidate in enumerate(retrieved.candidates, start=1):
        row = retrieved.rows[uuid.UUID(candidate.chunk_id)]
        passages.append(
            PromptPassage(
                marker=f"S{i}",
                source_label=_source_label(row),
                title=row.evidence.title,
                section=row.chunk.section,
                text=row.chunk.text,
            )
        )
    return passages


def _extractive(question: str, retrieved: Retrieved, entities: Entities, findings: Findings) -> str:
    passages = [
        ExtractivePassage(
            marker=f"S{i}",
            title=retrieved.rows[uuid.UUID(c.chunk_id)].evidence.title,
            text=retrieved.rows[uuid.UUID(c.chunk_id)].chunk.text,
            pinned=c.pinned,
        )
        for i, c in enumerate(retrieved.candidates, start=1)
    ]
    quotes = best_quotes(question, passages, entity_names=entities.names())
    lead = _findings_lead(findings) + "The retrieved sources say:"
    return compose(quotes, lead=lead)


def _findings_lead(findings: Findings) -> str:
    if not findings.facts:
        return ""
    lines = "\n".join(f"- {line}" for line in findings.summary_lines())
    return f"HerbaGuard's interaction check (deterministic rules):\n{lines}\n\n"


def _response(
    request: AssistantRequest,
    mode: AnswerMode,
    answer: str,
    entities: Entities,
    findings: Findings,
    citations: list[Citation],
    generation: GenerationInfo,
    notes: list[str],
) -> AssistantResponse:
    return AssistantResponse(
        question=request.question,
        mode=mode,
        answer=answer,
        referral=REFERRAL,
        entities=entities.out(),
        interaction_findings=findings.items,
        citations=citations,
        generation=generation,
        notes=list(dict.fromkeys(notes)),
        disclaimer=DISCLAIMER,
    )


def _no_generation(settings: Settings, reason: str | None = None) -> GenerationInfo:
    return GenerationInfo(
        provider=settings.assistant_provider.value,
        model=None,
        prompt_version=PROMPT_VERSION,
        attempts=0,
        citation_check="not_applicable",
        fallback_reason=reason,
    )


def ask(
    session: Session,
    settings: Settings,
    request: AssistantRequest,
    *,
    chat_model: ChatModel | None,
    embedder: Embedder | None,
) -> AssistantResponse:
    screening = screen(request.question)
    if screening.kind is QuestionKind.EMERGENCY:
        return _response(
            request,
            "emergency_referral",
            EMERGENCY_MESSAGE,
            Entities(),
            Findings(),
            [],
            _no_generation(settings, "emergency wording: no retrieval, no generation"),
            [],
        )

    entities = recognise(session, settings, request)
    notes = list(entities.notes)
    if entities.herb is not None and entities.herb.status == "ambiguous":
        names = "; ".join(
            f"{c.common_name or c.pharmaceutical_name} ({c.pharmaceutical_name})"
            for c in entities.herb.candidates
        )
        answer = (
            f"'{entities.herb_query}' can mean more than one herb: {names}. These are different "
            "plants with different evidence. Please ask again naming the one you mean."
        )
        return _response(
            request,
            "needs_clarification",
            answer,
            entities,
            Findings(),
            [],
            _no_generation(settings, "ambiguous herb name"),
            notes,
        )
    if entities.herb is not None and entities.herb.status == "not_found":
        notes.append(
            f"'{entities.herb_query}' is not one of HerbaGuard's curated herbs; "
            "the search was not limited to a herb."
        )
    if entities.herb is None and not entities.drugs:
        notes.append(
            "No herb or drug from HerbaGuard's index was recognised in the question; the "
            "passages come from a general search and may be off-topic."
        )
    unresolved = [d.query for d in entities.drugs if d.status != "resolved"]
    if unresolved:
        notes.append(
            f"Not in HerbaGuard's drug index: {', '.join(unresolved)} (the assistant does not "
            "look drugs up remotely; use the interaction check for that)."
        )

    findings = interaction_findings(session, settings, entities)
    dosing = screening.kind is QuestionKind.DOSING
    retrieved = retrieve(
        session,
        settings,
        request.question,
        entities,
        findings,
        embedder=embedder,
        extra_terms=DOSING_TERMS if dosing else None,
    )
    notes.extend(retrieved.notes)

    if dosing:
        return _response(
            request,
            "declined_dosing",
            DOSING_MESSAGE,
            entities,
            findings,
            _citations(retrieved, set()),
            _no_generation(settings, "dosing question: no generated advice"),
            notes,
        )

    if not retrieved.candidates:
        subject = (
            f" about {entities.names()[0]}" if entities.herb_resolved and entities.names() else ""
        )
        answer = (
            _findings_lead(findings)
            + f"HerbaGuard's sources contain no passage that answers this question{subject}. "
            "This does not mean that a product or combination is safe; it means the "
            "documents HerbaGuard holds do not address it."
        )
        return _response(
            request,
            "insufficient_evidence",
            answer,
            entities,
            findings,
            [],
            _no_generation(settings, "no relevant passage retrieved"),
            notes,
        )

    if request.mode == "extractive" or chat_model is None:
        reason = (
            "extractive mode requested"
            if request.mode == "extractive"
            else "no LLM configured (HERBAGUARD_ASSISTANT_PROVIDER=none)"
        )
        answer = _extractive(request.question, retrieved, entities, findings)
        return _response(
            request,
            "extractive",
            answer,
            entities,
            findings,
            _citations(retrieved, set(citation_rules.markers_in(answer))),
            _no_generation(settings, reason),
            notes,
        )

    return _generate(request, settings, chat_model, retrieved, entities, findings, notes)


def _generate(
    request: AssistantRequest,
    settings: Settings,
    chat_model: ChatModel,
    retrieved: Retrieved,
    entities: Entities,
    findings: Findings,
    notes: list[str],
) -> AssistantResponse:
    passages = _prompt_passages(retrieved)
    allowed = [p.marker for p in passages]
    reference = "\n".join(p.text for p in passages)
    messages = [
        ChatMessage("system", SYSTEM_PROMPT),
        ChatMessage("user", build_user_prompt(request.question, passages, findings.facts)),
    ]
    attempts = 0
    duration = 0
    issues: list[str] = []
    model_name: str | None = chat_model.name
    try:
        for _ in range(2):
            attempts += 1
            completion = chat_model.chat(messages)
            model_name = completion.model
            duration += completion.duration_ms or 0
            text = citation_rules.normalise_markers(completion.text)
            check = citation_rules.check_answer(text, allowed, reference_text=reference)
            issues = list(check.issues)
            mismatched = citation_rules.class_mismatches(text, findings.classes)
            if mismatched:
                issues.append(
                    f"mentions interaction class {', '.join(mismatched)}, which HerbaGuard did "
                    "not compute"
                )
            if not issues:
                return _response(
                    request,
                    "generated",
                    text,
                    entities,
                    findings,
                    _citations(retrieved, set(check.cited)),
                    GenerationInfo(
                        provider="ollama",
                        model=model_name,
                        prompt_version=PROMPT_VERSION,
                        attempts=attempts,
                        duration_ms=duration or None,
                        citation_check="passed",
                    ),
                    notes,
                )
            logger.info("assistant_citation_check_failed", attempt=attempts, issues=issues)
            messages += [
                ChatMessage("assistant", completion.text),
                ChatMessage("user", retry_message(issues, len(passages))),
            ]
        reason = "the generated answer failed the citation check twice"
        check_state: Literal["failed", "not_applicable"] = "failed"
    except LLMUnavailableError as exc:
        logger.warning("assistant_llm_unavailable", error=str(exc))
        reason = f"local LLM unavailable ({exc})"
        check_state = "not_applicable"

    answer = _extractive(request.question, retrieved, entities, findings)
    return _response(
        request,
        "extractive",
        answer,
        entities,
        findings,
        _citations(retrieved, set(citation_rules.markers_in(answer))),
        GenerationInfo(
            provider="ollama",
            model=model_name,
            prompt_version=PROMPT_VERSION,
            attempts=attempts,
            duration_ms=duration or None,
            citation_check=check_state,
            citation_issues=issues if check_state == "failed" else [],
            fallback_reason=reason,
        ),
        notes,
    )


# --------------------------------------------------------------------------- status


def status(session: Session, settings: Settings) -> AssistantStatus:
    modes = ["extractive", "insufficient_evidence", "needs_clarification", "declined_dosing",
             "emergency_referral"]  # fmt: skip
    if settings.assistant_provider is AssistantProvider.NONE:
        _, total = repo.embedding_counts(session, model=settings.ollama_embed_model)
        return AssistantStatus(
            provider="none",
            ollama_url=None,
            ollama_reachable=False,
            chat_model=None,
            chat_model_available=False,
            embedding_model=None,
            embedding_model_available=False,
            chunks_total=total,
            chunks_embedded=0,
            retrieval="full_text_only",
            answer_modes=modes,
            notes=["LLM disabled; answers are extractive (verbatim quotes with citations)."],
        )
    state = ollama_status(settings)
    embedded, total = repo.embedding_counts(session, model=settings.ollama_embed_model)
    notes: list[str] = []
    if not state.reachable:
        notes.append(
            f"Ollama is not reachable at {settings.ollama_base_url}; answers fall back to "
            "extractive mode. Start it with `ollama serve`."
        )
    chat_ok = state.has(settings.ollama_chat_model)
    embed_ok = state.has(settings.ollama_embed_model)
    if state.reachable and not chat_ok:
        notes.append(f"Run `ollama pull {settings.ollama_chat_model}`.")
    if state.reachable and not embed_ok:
        notes.append(f"Run `ollama pull {settings.ollama_embed_model}`.")
    if embedded < total:
        notes.append(f"{total - embedded} chunks have no embedding; run `herbaguard ai embed`.")
    return AssistantStatus(
        provider="ollama",
        ollama_url=settings.ollama_base_url,
        ollama_reachable=state.reachable,
        chat_model=settings.ollama_chat_model,
        chat_model_available=chat_ok,
        embedding_model=settings.ollama_embed_model,
        embedding_model_available=embed_ok,
        chunks_total=total,
        chunks_embedded=embedded,
        retrieval="hybrid" if embedded and embed_ok else "full_text_only",
        answer_modes=(["generated", *modes] if chat_ok else modes),
        notes=notes,
    )
