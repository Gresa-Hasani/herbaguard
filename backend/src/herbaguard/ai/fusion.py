"""Merging ranked retrieval lists (Reciprocal Rank Fusion) and choosing passages for a prompt."""

from __future__ import annotations

from collections.abc import Hashable, Sequence
from dataclasses import dataclass

RRF_K = 60  # Cormack et al. (2009); the usual constant, dampens the weight of top ranks


def reciprocal_rank_fusion[T: Hashable](
    rankings: Sequence[Sequence[T]], *, k: int = RRF_K
) -> list[tuple[T, float]]:
    """Fuse several best-first rankings into one: score(d) = Σ 1 / (k + rank_i(d)).

    Ties are broken by the first ranking in which an item appears earliest, so the result is
    deterministic.
    """
    scores: dict[T, float] = {}
    first_seen: dict[T, tuple[int, int]] = {}
    for list_index, ranking in enumerate(rankings):
        for rank, item in enumerate(dict.fromkeys(ranking), start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
            first_seen.setdefault(item, (rank, list_index))
    return sorted(scores.items(), key=lambda kv: (-kv[1], first_seen[kv[0]]))


@dataclass(frozen=True, slots=True)
class Candidate:
    chunk_id: str
    evidence_id: str
    pinned: bool = False  # evidence that decided a deterministic interaction result


def select_passages(
    ranked: Sequence[Candidate], *, limit: int, per_evidence: int = 2
) -> list[Candidate]:
    """Pinned candidates first, then the ranking; at most ``per_evidence`` chunks per item."""
    ordered = [c for c in ranked if c.pinned] + [c for c in ranked if not c.pinned]
    chosen: list[Candidate] = []
    seen_chunks: set[str] = set()
    per_item: dict[str, int] = {}
    for candidate in ordered:
        if len(chosen) >= limit:
            break
        if candidate.chunk_id in seen_chunks:
            continue
        if per_item.get(candidate.evidence_id, 0) >= per_evidence:
            continue
        chosen.append(candidate)
        seen_chunks.add(candidate.chunk_id)
        per_item[candidate.evidence_id] = per_item.get(candidate.evidence_id, 0) + 1
    return chosen
