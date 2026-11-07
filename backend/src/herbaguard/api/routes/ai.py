"""AI endpoints (Phase 5): ask, retrieve, providers, health.

The rest of the API does not depend on this module's providers: a missing or unreachable model
only affects these endpoints, and ``/ai/retrieve`` works without any generation provider.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from herbaguard.ai import service as ai_service
from herbaguard.ai.embeddings import EmbeddingError, EmbeddingProvider, build_embeddings
from herbaguard.ai.indexing.indexer import index_status
from herbaguard.ai.providers.base import ProviderError
from herbaguard.ai.providers.registry import GenerationChain, generation_chain, provider_statuses
from herbaguard.ai.retrieval import RetrievalFilters, RetrievalQuery, retrieve
from herbaguard.api.schemas.ai import (
    AIHealthResponse,
    AskRequest,
    AskResponse,
    ComponentStatus,
    ProviderOut,
    ProvidersResponse,
    RetrievalInfo,
    RetrievedItemOut,
    RetrieveRequest,
    RetrieveResponse,
)
from herbaguard.api.schemas.common import ErrorResponse
from herbaguard.api.schemas.provenance import EvidenceTypeInfo
from herbaguard.core.config import Settings, get_settings
from herbaguard.core.db import check_database, get_session
from herbaguard.core.errors import AmbiguousEntityError, NotFoundError, ServiceUnavailableError
from herbaguard.models import Target
from herbaguard.repositories import drugs as drug_repo
from herbaguard.repositories import plants as plant_repo
from herbaguard.services import plants as plant_service
from herbaguard.services.mappers import provenance_out

router = APIRouter(prefix="/ai", tags=["ai"])
SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_generation_chain(settings: SettingsDep) -> GenerationChain:
    """Dependency (replaceable in tests). Configuration errors become a clear 503 for AI calls."""
    try:
        return generation_chain(settings)
    except ProviderError as exc:
        raise ServiceUnavailableError(
            f"The configured answer generator is not usable: {exc.message}",
            details={"provider": exc.provider, "kind": exc.kind.value},
        ) from None


def get_embedding_provider(settings: SettingsDep) -> EmbeddingProvider | None:
    return build_embeddings(settings)


ChainDep = Annotated[GenerationChain, Depends(get_generation_chain)]
EmbeddingsDep = Annotated[EmbeddingProvider | None, Depends(get_embedding_provider)]
ERRORS: dict[int | str, dict[str, object]] = {
    409: {"model": ErrorResponse, "description": "An entity in the question is ambiguous"},
    422: {"model": ErrorResponse},
    429: {"model": ErrorResponse, "description": "The AI service is busy"},
    503: {
        "model": ErrorResponse,
        "description": "The answer generator is not configured or not reachable",
    },
}


@router.post("/ask", response_model=AskResponse, summary="Evidence-grounded answer to a question",
             responses=ERRORS)  # fmt: skip
def ask(
    body: AskRequest,
    session: SessionDep,
    settings: SettingsDep,
    chain: ChainDep,
    embeddings: EmbeddingsDep,
) -> AskResponse:
    return ai_service.ask(session, settings, question=body.question,
                          allow_remote_drug_lookup=body.allow_remote_drug_lookup,
                          chain=chain, embeddings=embeddings)  # fmt: skip


@router.post("/retrieve", response_model=RetrieveResponse,
             summary="Hybrid retrieval only (no language model)",
             responses={404: {"model": ErrorResponse}, 409: ERRORS[409], 422: ERRORS[422]})  # fmt: skip
def retrieve_evidence(
    body: RetrieveRequest, session: SessionDep, settings: SettingsDep, embeddings: EmbeddingsDep
) -> RetrieveResponse:
    herb_ids: tuple[uuid.UUID, ...] = ()
    drug_ids: tuple[uuid.UUID, ...] = ()
    target_ids: tuple[uuid.UUID, ...] = ()
    expansions: list[str] = []
    if body.herb:
        resolution = plant_service.resolve_herb(session, body.herb)
        if resolution.status == "ambiguous":
            raise AmbiguousEntityError(f"'{body.herb}' matches more than one herb.",
                                       details={"candidates": [c.model_dump() for c in resolution.candidates]})  # fmt: skip
        if resolution.herb is None:
            raise NotFoundError(f"No herb matches '{body.herb}'.")
        herb_ids = tuple(
            s.id for s in plant_repo.herb_group(session, resolution.herb.pharmaceutical_name)
        )
        expansions.append(resolution.herb.pharmaceutical_name)
    if body.drug:
        drug = drug_repo.drug_by_name(session, body.drug) or drug_repo.drug_by_rxcui(
            session, body.drug
        )
        if drug is None:
            raise NotFoundError(f"No drug in the database matches '{body.drug}'.")
        drug_ids = (drug.id,)
        expansions.append(drug.name)
    if body.target:
        target = session.query(Target).filter(Target.symbol.ilike(body.target)).one_or_none()
        if target is None:
            raise NotFoundError(f"No enzyme or transporter with symbol {body.target}.")
        target_ids = (target.id,)
        expansions.append(target.symbol)
    filters = RetrievalFilters(
        sources=tuple(body.sources), evidence_types=tuple(body.evidence_types),
        herb_substance_ids=herb_ids, drug_ids=drug_ids, target_ids=target_ids, entity_match="all",
    )  # fmt: skip
    result = retrieve(session, settings,
                      RetrievalQuery(body.query, tuple(expansions), filters, body.mode, body.top_k), embeddings)  # fmt: skip
    return RetrieveResponse(
        query=body.query,
        items=[
            RetrievedItemOut(
                segment_id=str(r.segment_id), evidence_item_id=str(r.evidence_item_id),
                external_id=r.external_id, source_code=r.source_code, source_name=r.source_name,
                licence=r.licence, licence_status=r.licence_status, redistributable=r.redistributable,
                evidence_type=EvidenceTypeInfo.of(r.evidence_type, r.source_code), title=r.title, url=r.url,
                document_date=r.document_date, publication_year=r.publication_year, section=r.section,
                excerpt=r.excerpt, char_start=r.char_start, char_end=r.char_end, herbs=list(r.herbs),
                provenance=[provenance_out(p) for p in r.provenance], fused_score=r.fused_score,
                ranks=r.ranks, similarity=r.similarity, keyword_score=r.keyword_score,
            )
            for r in result.items
        ],
        retrieval=RetrievalInfo(mode_requested=result.mode_requested, mode_used=result.mode_used,
                                embedding_model=result.embedding_model, candidates=result.candidates,
                                duration_ms=result.duration_ms, notes=result.notes),
    )  # fmt: skip


@router.get("/providers", response_model=ProvidersResponse,
            summary="Generation and embedding providers (no secrets; cloud providers are not called)")  # fmt: skip
def providers(settings: SettingsDep, embeddings: EmbeddingsDep) -> ProvidersResponse:
    rows = provider_statuses(settings, probe_local=True)
    return ProvidersResponse(
        generation=[ProviderOut(name=s.name, model=s.model, selected=sel, fallback=fb, configured=s.configured,
                                reachable=s.reachable, detail=s.detail) for s, sel, fb in rows],
        embedding=_embedding_status(settings, embeddings),
        cloud_source_text_allowed=settings.ai_cloud_send_source_text,
    )  # fmt: skip


def _embedding_status(settings: Settings, embeddings: EmbeddingProvider | None) -> ProviderOut:
    if embeddings is None:
        return ProviderOut(name="none", model=None, selected=True, fallback=False, configured=False,
                           reachable=None, detail="Keyword retrieval only.")  # fmt: skip
    try:
        info = embeddings.info()
        return ProviderOut(name=info.provider, model=f"{info.model} ({info.dimension}-d, {info.version})",
                           selected=True, fallback=False, configured=True, reachable=True, detail=None)  # fmt: skip
    except EmbeddingError as exc:
        return ProviderOut(name=embeddings.name, model=embeddings.model, selected=True, fallback=False,
                           configured=True, reachable=False, detail=str(exc))  # fmt: skip


@router.get(
    "/health", response_model=AIHealthResponse, summary="AI subsystem health (no paid API calls)"
)
def health(
    session: SessionDep, settings: SettingsDep, embeddings: EmbeddingsDep
) -> AIHealthResponse:
    components: list[ComponentStatus] = []
    try:
        check_database()
        components.append(ComponentStatus(name="database", status="ok"))
    except Exception:
        components.append(ComponentStatus(name="database", status="unavailable"))
    embedding = _embedding_status(settings, embeddings)
    info = None
    if embeddings is not None and embedding.reachable:
        info = embeddings.info()
    status_emb = (
        "not_configured" if embeddings is None else ("ok" if embedding.reachable else "unavailable")
    )
    components.append(
        ComponentStatus(
            name="embedding", status=status_emb, detail=embedding.detail or embedding.model
        )
    )
    st = index_status(session, model=info.model if info else None, version=info.version if info else None,
                      dimension=info.dimension if info else None)  # fmt: skip
    retrieval_status = (
        "ok" if st.segments and (info is None or st.stale_or_missing == 0) else "degraded"
    )
    detail = None if retrieval_status == "ok" else (
        "No segments indexed (herbaguard ai index)." if not st.segments
        else f"{st.stale_or_missing} segments have no current embedding; semantic search covers the rest.")  # fmt: skip
    if info is None and st.segments:
        retrieval_status, detail = "degraded", "Keyword search only (no embedding model available)."
    components.append(ComponentStatus(name="retrieval", status=retrieval_status, detail=detail))
    selected = next(s for s, sel, _ in provider_statuses(settings, probe_local=True) if sel)
    if not selected.configured:
        gen = ComponentStatus(name="generation", status="not_configured", detail=selected.detail)
    elif selected.reachable is False:
        gen = ComponentStatus(name="generation", status="unavailable", detail=selected.detail)
    else:
        gen = ComponentStatus(name="generation", status="ok",
                              detail=f"{selected.name}: {selected.model or 'no model'}"
                              + (" (cloud; not probed)" if selected.reachable is None else ""))  # fmt: skip
    components.append(gen)
    states = {c.status for c in components}
    overall = "unavailable" if "unavailable" in {components[0].status} else (
        "ok" if states == {"ok"} else "degraded")  # fmt: skip
    return AIHealthResponse(
        status=overall,
        components=components,
        index={"segments": st.segments, "evidence_items_indexed": st.evidence_items_indexed,
               "evidence_items_current": st.evidence_items_current, "embedded_current": st.embedded,
               "stale_or_missing": st.stale_or_missing, "embedding_model": st.model,
               "embedding_model_version": st.model_version, "dimension": st.dimension},
    )  # fmt: skip
