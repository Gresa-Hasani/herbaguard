"""Reciprocal Rank Fusion (pure, deterministic).

``score(d) = Σ_r  w_r / (k + rank_r(d))`` over the ranked lists ``r`` that contain ``d`` (rank 1 =
best). RRF uses ranks only, so keyword scores (ts_rank) and cosine similarities, which are on
different scales, never need to be compared. ``k`` (default 60, Cormack et al. 2009) dampens the
influence of top ranks; weights and ``k`` are configuration to be benchmarked, not scientific
assumptions. Optional per-source multipliers express a configured preference and are reported with
every result. None of these numbers is a measure of evidence quality.

Ties are broken by the identifier, so identical inputs always give identical output.
"""

from __future__ import annotations

from collections.abc import Hashable, Mapping, Sequence
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Fused[T: Hashable]:
    key: T
    score: float
    ranks: dict[str, int] = field(default_factory=dict)


def rrf[T: Hashable](
    ranked: Mapping[str, Sequence[T]],
    *,
    k: int = 60,
    weights: Mapping[str, float] | None = None,
    multipliers: Mapping[T, float] | None = None,
) -> list[Fused[T]]:
    scores: dict[T, float] = {}
    ranks: dict[T, dict[str, int]] = {}
    for name, items in ranked.items():
        weight = (weights or {}).get(name, 1.0)
        seen: set[T] = set()
        rank = 0
        for item in items:
            if item in seen:  # a list may not vote twice for the same item
                continue
            seen.add(item)
            rank += 1
            scores[item] = scores.get(item, 0.0) + weight / (k + rank)
            ranks.setdefault(item, {})[name] = rank
    out = [
        Fused(key, score * (multipliers or {}).get(key, 1.0), ranks[key])
        for key, score in scores.items()
    ]
    return sorted(out, key=lambda f: (-f.score, str(f.key)))
