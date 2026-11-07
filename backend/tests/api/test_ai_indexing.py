"""Incremental indexing: segments, embeddings, stale detection, invalidation, retries, model
coexistence, question understanding and evaluation metrics — on the seeded test database."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from herbaguard.ai.embeddings import EmbeddingError, EmbeddingModelInfo, Kind
from herbaguard.ai.evaluation import Relevance, resolve_relevant, score
from herbaguard.ai.indexing.indexer import embed_pending, index_status, sync_segments
from herbaguard.ai.query import Intent, analyse
from herbaguard.core.config import Settings
from herbaguard.ingestion.context import run_ingestion
from herbaguard.ingestion.loaders import ensure_sources
from herbaguard.models import (
    Chunk,
    DataQualityIssue,
    EvidenceItem,
    RetrievalSegment,
    SegmentEmbedding,
)
from tests.api.test_ai_api import HashEmbeddings

pytestmark = pytest.mark.db
SETTINGS = Settings(_env_file=None)  # type: ignore[call-arg]


def run_index(
    session: Session, embeddings: Any | None = None, settings: Settings = SETTINGS
) -> dict[str, int]:
    ensure_sources(session)
    with run_ingestion(session, "herbaguard_ai_index", settings) as ctx:
        sync_segments(ctx, settings)
        if embeddings is not None:
            embed_pending(ctx, embeddings, settings)
        return dict(ctx.stats)


def count(session: Session, model: type, *where: Any) -> int:
    return session.scalar(select(func.count()).select_from(model).where(*where)) or 0


def test_index_is_incremental_and_idempotent(
    db_session: Session, seeded: dict[str, object]
) -> None:
    first = run_index(db_session, HashEmbeddings())
    assert first["segments_created"] > 0 and first["segments_embedded"] == first["segments_created"]
    segments = count(db_session, RetrievalSegment)
    second = run_index(db_session, HashEmbeddings())
    assert second.get("segments_created", 0) == 0 and second.get("segments_embedded", 0) == 0
    assert second["chunks_unchanged"] == second["chunks_seen"]
    assert count(db_session, RetrievalSegment) == segments
    assert count(db_session, SegmentEmbedding) == segments  # no duplicates


def test_changed_text_is_resegmented_and_reembedded_only(
    db_session: Session, seeded: dict[str, object]
) -> None:
    run_index(db_session, HashEmbeddings())
    chunk = db_session.scalars(
        select(Chunk)
        .join(EvidenceItem)
        .where(EvidenceItem.external_id == "EMA/HMPC/7695/2021#4.5#WEU")
    ).one()
    chunk.text = chunk.text + " A new sentence was added by a monograph revision."
    db_session.flush()
    stats = run_index(db_session, HashEmbeddings())
    assert stats["chunks_resegmented"] == 1
    assert stats["segments_embedded"] == stats["segments_created"] >= 1
    status = index_status(db_session, model="hash-64", version="v1", dimension=64)
    assert status.stale_or_missing == 0


def test_superseded_evidence_leaves_the_index_but_is_kept(
    db_session: Session, seeded: dict[str, object]
) -> None:
    run_index(db_session, HashEmbeddings())
    item = db_session.scalars(
        select(EvidenceItem).where(EvidenceItem.external_id == "st-johns-wort#safety")
    ).one()
    db_session.execute(
        update(EvidenceItem).where(EvidenceItem.id == item.id).values(is_superseded=True)
    )
    db_session.flush()
    stats = run_index(db_session)
    assert stats["segments_removed_superseded"] >= 1
    assert count(db_session, RetrievalSegment, RetrievalSegment.evidence_item_id == item.id) == 0
    assert db_session.get(EvidenceItem, item.id) is not None  # the evidence itself is untouched
    assert count(db_session, Chunk, Chunk.evidence_item_id == item.id) == 1


def test_new_model_version_makes_vectors_stale(
    db_session: Session, seeded: dict[str, object]
) -> None:
    run_index(db_session, HashEmbeddings())

    class Updated(HashEmbeddings):
        def info(self) -> EmbeddingModelInfo:
            return EmbeddingModelInfo("test", self.model, "v2", 64)

    assert index_status(db_session, model="hash-64", version="v2", dimension=64).embedded == 0
    stats = run_index(db_session, Updated())
    assert stats["segments_embedded"] == count(db_session, RetrievalSegment)
    assert set(db_session.scalars(select(SegmentEmbedding.model_version))) == {"v2"}


def test_two_models_coexist_without_mixing(db_session: Session, seeded: dict[str, object]) -> None:
    run_index(db_session, HashEmbeddings())

    class Small(HashEmbeddings):
        model = "hash-16"

        def info(self) -> EmbeddingModelInfo:
            return EmbeddingModelInfo("test", self.model, "v1", 16)

        def embed(self, texts: list[str], kind: Kind) -> list[list[float]]:
            return [
                v[:16] if any(v[:16]) else [1.0] + [0.0] * 15 for v in super().embed(texts, kind)
            ]

    run_index(db_session, Small())
    dims = dict(db_session.execute(select(SegmentEmbedding.model, func.max(SegmentEmbedding.dimension))
                                   .group_by(SegmentEmbedding.model)).tuples().all())  # fmt: skip
    assert dims == {"hash-64": 64, "hash-16": 16}


def test_embedding_failures_are_recorded_and_retried(
    db_session: Session, seeded: dict[str, object]
) -> None:
    class Flaky(HashEmbeddings):
        def embed(self, texts: list[str], kind: Kind) -> list[list[float]]:
            if any("contraindicated" in t for t in texts):
                msg = "The embedding model failed (HTTP 500)."
                raise EmbeddingError(msg)
            return super().embed(texts, kind)

    stats = run_index(db_session, Flaky())
    assert stats["segments_failed"] >= 1
    issues = db_session.scalars(
        select(DataQualityIssue).where(DataQualityIssue.rule == "embedding_failed")
    ).all()
    assert len(issues) == stats["segments_failed"]
    retried = run_index(db_session, HashEmbeddings())  # next run picks up only the failed ones
    assert retried["segments_embedded"] == stats["segments_failed"]


# --------------------------------------------------------------------------- question understanding


@pytest.mark.parametrize(
    ("question", "intent", "herbs", "drugs"),
    [
        ("Does St John's wort interact with warfarin?", Intent.HERB_DRUG_INTERACTION, ["Hyperici herba"], ["warfarin"]),
        ("Cimicifuga racemosa and warfarin", Intent.HERB_DRUG_INTERACTION, ["Cimicifugae rhizoma"], ["warfarin"]),
        ("How does Hypericum perforatum affect CYP3A4?", Intent.MECHANISM, ["Hyperici herba"], []),
        ("Is hawthorn safe in pregnancy?", Intent.PLANT_SAFETY, ["Crataegi folium cum flore"], []),
        ("Compare St John's wort and hawthorn", Intent.EVIDENCE_COMPARISON, ["Hyperici herba", "Crataegi folium cum flore"], []),
        ("Which herbs does the database cover?", Intent.DATA_COVERAGE, [], []),
        ("Tell me about metformin", Intent.DRUG_INFORMATION, [], ["metformin"]),
    ],
)  # fmt: skip
def test_question_understanding(
    db_session: Session,
    seeded: dict[str, object],
    question: str,
    intent: Intent,
    herbs: list[str],
    drugs: list[str],
) -> None:
    a = analyse(db_session, SETTINGS, question, allow_remote_drug_lookup=False)
    assert a.intent is intent
    assert [h.herb.pharmaceutical_name for h in a.herbs] == herbs
    assert [d.name for d in a.drugs] == drugs


def test_ambiguity_and_personal_advice(db_session: Session, seeded: dict[str, object]) -> None:
    a = analyse(
        db_session,
        SETTINGS,
        "Should I stop warfarin because of ginseng?",
        allow_remote_drug_lookup=False,
    )
    assert a.asks_for_personal_advice
    assert [(m.mention, m.kind, len(m.candidates)) for m in a.ambiguous] == [("ginseng", "herb", 2)]
    assert a.herbs == []  # never guessed


# --------------------------------------------------------------------------- evaluation


def test_relevance_rules_resolve_from_the_database(
    db_session: Session, seeded: dict[str, object]
) -> None:
    pair = resolve_relevant(db_session, Relevance.model_validate(
        {"assertion_pair": {"herb": "Hyperici herba", "drug": "warfarin"}}))  # fmt: skip
    external = set(
        db_session.scalars(select(EvidenceItem.external_id).where(EvidenceItem.id.in_(pair)))
    )
    assert external == {"EMA/HMPC/7695/2021#4.5#WEU"}
    text = resolve_relevant(db_session, Relevance.model_validate(
        {"herb_text": {"herb": "Hyperici herba", "pattern": "conflicting evidence"}}))  # fmt: skip
    assert len(text) == 1
    with pytest.raises(ValueError, match="unknown herb"):
        resolve_relevant(
            db_session,
            Relevance.model_validate(
                {"herb_sections": {"herb": "Nonexistus", "sections": ["4.5"]}}
            ),
        )


def test_metrics() -> None:
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    metrics, ranks = score([c, a, a, b], {a, b}, ["x", "y", "y", "z"], ks=(2, 4))
    assert ranks == [2, 4]
    assert metrics["mrr"] == 0.5
    assert metrics["recall@2"] == 0.5 and metrics["recall@4"] == 1.0
    assert metrics["precision@2"] == 0.5 and metrics["precision@4"] == 0.75
    assert (
        metrics["hit@2"] == 1.0
        and metrics["duplicate_rate@4"] == 0.25
        and metrics["sources@4"] == 3.0
    )
    empty, _ = score([], {a}, [], ks=(5,))
    assert empty["mrr"] == 0.0 and empty["recall@5"] == 0.0


@pytest.mark.parametrize(("model", "version"), [("other-64", "v1"), ("hash-64", "v2")])
def test_semantic_search_never_uses_vectors_of_another_model_or_version(
    db_session: Session, seeded: dict[str, object], model: str, version: str
) -> None:
    """Same dimension (64) but a different model name or model version: no stored vector may be
    compared with the query; retrieval reports it and falls back to keyword search."""
    from herbaguard.ai.retrieval import RetrievalQuery, retrieve

    run_index(db_session, HashEmbeddings())  # stores hash-64 / v1 vectors

    class Other(HashEmbeddings):
        def info(self) -> EmbeddingModelInfo:
            return EmbeddingModelInfo("test", model, version, 64)

    result = retrieve(
        db_session, SETTINGS, RetrievalQuery("coumarin anticoagulants", mode="semantic"), Other()
    )  # type: ignore[arg-type]
    assert result.mode_used == "keyword"
    assert any(f"model '{model}'" in note for note in result.notes)
    assert all(item.similarity is None for item in result.items)
