"""Reproducible evaluation of retrieval and generation (docs/ai/evaluation.md).

Retrieval: for every question of a dataset (``data/evaluation/*.yaml``), the relevant evidence items
are resolved from declarative rules, the production retrieval query is run in keyword, semantic and
hybrid mode (optionally for several embedding models), and Recall@k, Precision@k, Hit@k, MRR,
duplicate rate, source coverage and latency are computed at evidence-item level.

Generation: questions are sent through the full /ai/ask pipeline with the configured provider and
deterministic checks are recorded (status, classification identical to the interaction service,
citation validity, removed/unsupported paragraphs, safety and directive flags, insufficient-evidence
handling, latency, tokens). Scientific quality is reviewed manually (procedure in the docs); no
LLM judge is used.
"""

from __future__ import annotations

import re
import statistics
import time
import uuid
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from herbaguard.ai.embeddings import EmbeddingProvider
from herbaguard.ai.query import analyse
from herbaguard.ai.retrieval import Mode, RetrievalQuery, retrieve
from herbaguard.core.config import Settings
from herbaguard.models import Chunk, EvidenceItem, HerbalSubstance, HerbalSubstanceEvidence
from herbaguard.repositories import drugs as drug_repo
from herbaguard.repositories import interactions as interaction_repo

# --------------------------------------------------------------------------- dataset


class HerbSections(BaseModel):
    herb: str
    sections: list[str]
    sources: list[str] = Field(default_factory=list)


class HerbSource(BaseModel):
    herb: str
    source: str
    external_id_contains: str | None = None


class HerbText(BaseModel):
    herb: str
    pattern: str
    sources: list[str] = Field(default_factory=list)
    evidence_types: list[str] = Field(default_factory=list)


class TextRule(BaseModel):
    pattern: str
    sources: list[str] = Field(default_factory=list)


class Pair(BaseModel):
    herb: str
    drug: str


class Relevance(BaseModel):
    assertion_pair: Pair | None = None
    herb_sections: HerbSections | None = None
    herb_source: HerbSource | None = None
    herb_text: HerbText | None = None
    text: TextRule | None = None
    external_ids: list[str] = Field(default_factory=list)


class Question(BaseModel):
    id: str
    category: str
    question: str
    relevant: Relevance = Field(default_factory=Relevance)
    expect_no_evidence: bool = False
    expect_ambiguous: bool = False  # the API must answer 409 with candidates
    catalogue_question: bool = False  # answered from catalogue facts, not retrieval
    expect_observations: bool = False  # v2: the answer must use experimental records (DDID)
    expect_only_nonhuman_observations: bool = False  # v2: all such records are animal/unstated
    allow_remote_drug_lookup: bool = False

    @property
    def retrieval_scored(self) -> bool:
        return not (self.expect_no_evidence or self.expect_ambiguous or self.catalogue_question)


class Dataset(BaseModel):
    version: int | str
    label: str
    questions: list[Question]


def load_dataset(path: Path) -> Dataset:
    return Dataset.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


# --------------------------------------------------------------------------- relevance


def _herb_ids(session: Session, pharmaceutical_name: str) -> list[uuid.UUID]:
    ids = list(
        session.scalars(
            select(HerbalSubstance.id).where(
                HerbalSubstance.pharmaceutical_name == pharmaceutical_name
            )
        )
    )
    if not ids:
        msg = f"Evaluation rule names an unknown herb: {pharmaceutical_name}"
        raise ValueError(msg)
    return ids


def _herb_evidence(session: Session, herb: str):  # type: ignore[no-untyped-def]
    return select(HerbalSubstanceEvidence.evidence_item_id).where(
        HerbalSubstanceEvidence.herbal_substance_id.in_(_herb_ids(session, herb))
    )


def _text_match(session: Session, pattern: str, base):  # type: ignore[no-untyped-def]
    matching = select(Chunk.evidence_item_id).where(Chunk.text.op("~*")(pattern))
    title = select(EvidenceItem.id).where(EvidenceItem.title.op("~*")(pattern))
    return base.where(EvidenceItem.id.in_(matching.union(title)))


def resolve_relevant(session: Session, rel: Relevance) -> set[uuid.UUID]:
    current = select(EvidenceItem.id).where(EvidenceItem.is_superseded.is_(False))
    found: set[uuid.UUID] = set()
    if rel.assertion_pair:
        substance_ids = _herb_ids(session, rel.assertion_pair.herb)
        drug = drug_repo.drug_by_name(session, rel.assertion_pair.drug)
        if drug is not None:
            codes = drug_repo.atc_prefixes(
                [c.code for c in drug_repo.classes_for_drug(session, drug.id)]
            )
            rows = interaction_repo.active_assertions(
                session, substance_ids, drug_id=drug.id, class_codes=codes
            )
            found |= {r.evidence.id for r in rows}
    if rel.herb_sections:
        r = rel.herb_sections
        stmt = current.where(EvidenceItem.id.in_(_herb_evidence(session, r.herb)),
                             EvidenceItem.metadata_["section"].astext.in_(r.sections))  # fmt: skip
        if r.sources:
            stmt = stmt.where(EvidenceItem.source_code.in_(r.sources))
        found |= set(session.scalars(stmt))
    if rel.herb_source:
        r2 = rel.herb_source
        stmt = current.where(
            EvidenceItem.id.in_(_herb_evidence(session, r2.herb)),
            EvidenceItem.source_code == r2.source,
        )
        if r2.external_id_contains:
            stmt = stmt.where(EvidenceItem.external_id.contains(r2.external_id_contains))
        found |= set(session.scalars(stmt))
    if rel.herb_text:
        r3 = rel.herb_text
        stmt = current.where(EvidenceItem.id.in_(_herb_evidence(session, r3.herb)))
        if r3.sources:
            stmt = stmt.where(EvidenceItem.source_code.in_(r3.sources))
        if r3.evidence_types:
            stmt = stmt.where(EvidenceItem.evidence_type.in_(r3.evidence_types))
        found |= set(session.scalars(_text_match(session, r3.pattern, stmt)))
    if rel.text:
        stmt = current
        if rel.text.sources:
            stmt = stmt.where(EvidenceItem.source_code.in_(rel.text.sources))
        found |= set(session.scalars(_text_match(session, rel.text.pattern, stmt)))
    if rel.external_ids:
        found |= set(session.scalars(current.where(EvidenceItem.external_id.in_(rel.external_ids))))
    return found


# --------------------------------------------------------------------------- retrieval metrics


@dataclass(slots=True)
class QuestionMetrics:
    id: str
    category: str
    relevant: int
    ranks: list[int]  # 1-based ranks (segment positions) of relevant evidence items' first hit
    latency_ms: int
    metrics: dict[str, float]
    sources: list[str]
    notes: list[str] = field(default_factory=list)


def score(evidence_order: Sequence[uuid.UUID], relevant: set[uuid.UUID], sources: Sequence[str],
          ks: Sequence[int]) -> tuple[dict[str, float], list[int]]:  # fmt: skip
    """Metrics for one ranked list of evidence ids (segment order; repeats allowed)."""
    out: dict[str, float] = {}
    first_rank: dict[uuid.UUID, int] = {}
    for position, evidence_id in enumerate(evidence_order, start=1):
        first_rank.setdefault(evidence_id, position)
    hit_ranks = sorted(rank for eid, rank in first_rank.items() if eid in relevant)
    for k in ks:
        top = list(evidence_order[:k])
        found = {e for e in top if e in relevant}
        out[f"recall@{k}"] = len(found) / len(relevant) if relevant else 0.0
        out[f"precision@{k}"] = sum(1 for e in top if e in relevant) / k
        out[f"hit@{k}"] = 1.0 if found else 0.0
        out[f"duplicate_rate@{k}"] = (len(top) - len(set(top))) / len(top) if top else 0.0
        out[f"sources@{k}"] = float(len(set(sources[:k])))
    out["mrr"] = 1.0 / hit_ranks[0] if hit_ranks else 0.0
    return out, hit_ranks


def rxnav_reachable(timeout: float = 5.0) -> bool:
    """Questions that need a live RxNav lookup (brand names) are externally blocked without it."""
    import httpx

    try:
        return (
            httpx.get("https://rxnav.nlm.nih.gov/REST/version.json", timeout=timeout).status_code
            == 200
        )
    except httpx.HTTPError:
        return False


def evaluate_retrieval(
    session: Session,
    settings: Settings,
    dataset: Dataset,
    *,
    mode: Mode,
    embeddings: EmbeddingProvider | None,
    ks: Sequence[int] = (5, 10),
    rxnav_available: bool = True,
) -> dict[str, Any]:
    per_question: list[QuestionMetrics] = []
    blocked: list[str] = []
    top_k = max(ks)
    for q in dataset.questions:
        if not q.retrieval_scored:
            continue
        if q.allow_remote_drug_lookup and not rxnav_available:
            blocked.append(q.id)  # externally blocked, not a retrieval failure
            continue
        relevant = resolve_relevant(session, q.relevant)
        analysis = analyse(
            session, settings, q.question, allow_remote_drug_lookup=q.allow_remote_drug_lookup
        )
        from herbaguard.ai.service import pipeline_query

        query = pipeline_query(analysis, q.question)
        query = RetrievalQuery(query.text, query.expansions, query.filters, mode, top_k)
        started = time.perf_counter()
        result = retrieve(session, settings, query, embeddings)
        latency = int((time.perf_counter() - started) * 1000)
        order = [r.evidence_item_id for r in result.items]
        metrics, ranks = score(order, relevant, [r.source_code for r in result.items], ks)
        per_question.append(QuestionMetrics(q.id, q.category, len(relevant), ranks, latency, metrics,
                                            sorted({r.source_code for r in result.items}), result.notes))  # fmt: skip
    keys = list(per_question[0].metrics) if per_question else []
    with_relevant = [m for m in per_question if m.relevant]
    summary = (
        {k: round(statistics.fmean(m.metrics[k] for m in with_relevant), 4) for k in keys}
        if with_relevant
        else {}
    )
    latencies = [m.latency_ms for m in per_question]
    summary["latency_ms_median"] = statistics.median(latencies) if latencies else 0
    summary["latency_ms_p95"] = (
        sorted(latencies)[int(0.95 * (len(latencies) - 1))] if latencies else 0
    )
    by_category: dict[str, dict[str, float]] = {}
    for cat in sorted({m.category for m in with_relevant}):
        rows = [m for m in with_relevant if m.category == cat]
        by_category[cat] = {
            k: round(statistics.fmean(r.metrics[k] for r in rows), 3)
            for k in ("hit@5", "recall@10", "mrr")
        }
    return {
        "mode": mode,
        "embedding_model": embeddings.model
        if embeddings is not None and mode != "keyword"
        else None,
        "questions_scored": len(with_relevant),
        "questions_without_relevant_items": [m.id for m in per_question if not m.relevant],
        "externally_blocked_rxnav": blocked,
        "summary": summary,
        "by_category": by_category,
        "per_question": [asdict(m) for m in per_question],
    }


def corpus_snapshot(session: Session) -> dict[str, Any]:
    """Corpus size at evaluation time, recorded with every report (not used by any metric)."""
    rows = session.execute(
        select(EvidenceItem.source_code, func.count()).where(EvidenceItem.is_superseded.is_(False)).group_by(EvidenceItem.source_code)
    ).all()  # fmt: skip
    from herbaguard.models import RetrievalSegment

    segments = session.scalar(select(func.count()).select_from(RetrievalSegment)) or 0
    return {
        "evidence_items_by_source": {code: int(n) for code, n in rows},
        "segments": int(segments),
    }


# --------------------------------------------------------------------------- generation checks


_CLASS_IN_TEXT = re.compile(r"\bclass\s*([A-E])\b", re.I)


def generation_checks(
    response: Any, expected_classes: set[str], question: Question
) -> dict[str, Any]:
    """Deterministic checks on one /ai/ask response (an AskResponse)."""
    cited = [c for p in response.paragraphs for c in p.citations]
    available = {c.label for c in response.citations}
    removed = [i for i in response.validation if i.severity == "removed"]
    critical = [i for i in response.validation if i.severity == "critical"]
    classes = {c.interaction_class for c in response.classification}
    mentioned = {m.upper() for m in _CLASS_IN_TEXT.findall(response.answer or "")}
    return {
        "id": question.id,
        "category": question.category,
        "status": response.status,
        "generation_mode": response.generation.mode,
        "provider": response.generation.provider,
        "model": response.generation.model,
        "classification_matches_service": classes == expected_classes,
        "class_mentions_consistent": mentioned <= classes,
        "paragraphs": len(response.paragraphs),
        "citations": len(cited),
        "citation_validity": 1.0 if all(c in available for c in cited) else 0.0,
        "removed_paragraphs": sum(1 for i in removed if i.rule != "invalid_citation"),
        "invalid_citations_removed": sum(1 for i in removed if i.rule == "invalid_citation"),
        "critical_issues": sorted({i.rule for i in critical}),
        # audit trail (final attempt): every validator issue with its message and the text it refers to
        "validation_issues": [
            {
                "rule": i.rule,
                "severity": i.severity,
                "message": i.message,
                "paragraph": i.paragraph,
                "text": i.text,
            }
            for i in response.validation
        ],
        "rejected_text": _rejected_text(response),
        "removed_texts": [i.text for i in removed if i.text],
        "insufficient_evidence": response.insufficient_evidence,
        "expected_insufficient": question.expect_no_evidence,
        "latency_ms": response.generation.duration_ms,
        "input_tokens": response.generation.input_tokens,
        "output_tokens": response.generation.output_tokens,
        "answer": response.answer,
        "cited_labels": sorted(set(cited)),
        "regenerations": response.generation.regenerations,
        "observation_items": sum(1 for c in response.citations if c.kind == "observation"),
        "observations_cited": sum(1 for c in set(cited) if c.startswith("X")),
        "experimental_as_clinical_removed": sum(
            1 for i in response.validation if i.rule == "experimental_as_clinical"
        ),
        "expected_observations": question.expect_observations,
        "nonhuman_stated_as_such": (not question.expect_only_nonhuman_observations)
        or bool(
            re.search(
                r"\b(animal|rats?|mice|dogs?|rabbits?|species (?:is |was )?not (?:stated|reported)|not (?:stated|reported))",
                response.answer or "",
                re.I,
            )
        ),
    }


def summarise_generation(rows: list[dict[str, Any]]) -> dict[str, Any]:
    answered = [r for r in rows if r.get("status") == "answered"]
    rows_checked = [r for r in rows if "classification_matches_service" in r]
    model_rows = [r for r in rows if r.get("generation_mode") == "model"]

    def rate(items: list[dict[str, Any]], key: str) -> float:
        return round(sum(1 for r in items if r.get(key)) / len(items), 3) if items else 0.0

    return {
        "questions": len(rows),
        "answered": len(answered),
        "rejected_by_validation": sum(
            1 for r in rows if r.get("status") == "rejected_by_validation"
        ),
        "insufficient_evidence": sum(1 for r in rows if r.get("status") == "insufficient_evidence"),
        "errors": sum(1 for r in rows if r.get("error")),
        "externally_blocked_rxnav": [
            r["id"] for r in rows if r.get("status") == "externally_blocked_rxnav"
        ],
        "status_distribution": dict(
            sorted(Counter(r.get("status", "error") for r in rows).items())
        ),
        "mode_distribution": dict(
            sorted(Counter(r.get("generation_mode", "-") for r in rows).items())
        ),
        "regenerations": sum(r.get("regenerations", 0) for r in rows),
        "ambiguous_questions_handled": sum(1 for r in rows if r.get("ambiguity_handled")),
        "classification_matches_service": rate(rows_checked, "classification_matches_service"),
        "class_mentions_consistent": rate(rows_checked, "class_mentions_consistent"),
        "citation_validity": rate([r for r in rows if r.get("citations")], "citation_validity"),
        "paragraphs_removed_per_answer": round(
            statistics.fmean(r["removed_paragraphs"] for r in model_rows), 3
        )
        if model_rows
        else 0.0,
        "unknown_entity_reported_insufficient": rate(
            [r for r in rows_checked if r.get("expected_insufficient")],
            "insufficient_evidence",
        ),
        "latency_ms_median": statistics.median([r["latency_ms"] for r in model_rows])
        if model_rows
        else 0,
        "output_tokens_median": statistics.median([r["output_tokens"] or 0 for r in model_rows])
        if model_rows
        else 0,
    }


def _rejected_text(response: Any) -> str | None:
    """The withheld text of a rejected answer: every paragraph or limitation a critical issue
    refers to (final attempt), so each rejection can be audited."""
    if response.status != "rejected_by_validation":
        return None
    texts = dict.fromkeys(
        i.text for i in response.validation if i.severity == "critical" and i.text
    )
    return "\n\n".join(texts) or None
