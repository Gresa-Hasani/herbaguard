"""Scoring of assistant answers against the fixed evaluation set (pure).

Input is the API response as a plain dict, so the same scorer works for the in-process service
(`herbaguard ai eval`) and for responses saved from a running API.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from herbaguard.ai.citations import markers_in, safety_claims

GROUNDED_MODES = {"generated", "extractive"}


@dataclass(frozen=True, slots=True)
class EvalItem:
    id: str
    question: str
    modes: list[str]
    herb: str | None = None
    drugs: list[str] = field(default_factory=list)
    herb_status: list[str] = field(default_factory=list)
    classes: dict[str, str] = field(default_factory=dict)
    sources_any: list[str] = field(default_factory=list)
    max_citations: int | None = None

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> EvalItem:
        status = raw.get("herb_status_any") or (
            [raw["herb_status"]] if raw.get("herb_status") else []
        )
        return cls(
            id=str(raw["id"]),
            question=str(raw["question"]),
            modes=[str(m) for m in raw["modes"]],
            herb=raw.get("herb"),
            drugs=[str(d) for d in raw.get("drugs", [])],
            herb_status=[str(s) for s in status],
            classes={str(k).lower(): str(v) for k, v in (raw.get("classes") or {}).items()},
            sources_any=[str(s) for s in raw.get("sources_any", [])],
            max_citations=raw.get("max_citations"),
        )


@dataclass(frozen=True, slots=True)
class ItemScore:
    id: str
    mode: str
    checks: dict[str, bool]
    details: list[str]

    @property
    def passed(self) -> bool:
        return all(self.checks.values())


def score(item: EvalItem, response: Mapping[str, Any]) -> ItemScore:
    checks: dict[str, bool] = {}
    details: list[str] = []
    mode = str(response.get("mode"))
    answer = str(response.get("answer", ""))
    citations: Sequence[Mapping[str, Any]] = response.get("citations", [])
    markers = {str(c.get("marker")) for c in citations}

    checks["mode"] = mode in item.modes
    if not checks["mode"]:
        details.append(f"mode {mode} not in {item.modes}")

    used = markers_in(answer)
    unresolved = [m for m in used if m not in markers]
    checks["citations_resolve"] = not unresolved  # hard gate: 0 fabricated citations
    if unresolved:
        details.append(f"unresolved markers {unresolved}")
    if mode in GROUNDED_MODES:
        checks["cites_something"] = bool(used)

    claims = safety_claims(answer)
    checks["no_safety_claim"] = not claims
    if claims:
        details.append(f"safety claims {claims}")

    if item.herb_status:
        status = str((response.get("entities") or {}).get("herb_status"))
        checks["herb_status"] = status in item.herb_status
        if not checks["herb_status"]:
            details.append(f"herb_status {status} not in {item.herb_status}")

    if item.classes:
        computed = {}
        for finding in response.get("interaction_findings", []):
            drug = finding.get("drug") or {}
            name = ((drug.get("drug") or {}).get("name") or drug.get("query") or "").lower()
            cls = (finding.get("classification") or {}).get("interaction_class")
            computed[name] = cls
        for drug, expected in item.classes.items():
            ok = computed.get(drug) == expected
            checks[f"class_{drug}"] = ok
            if not ok:
                details.append(f"{drug}: class {computed.get(drug)} != {expected}")

    if item.sources_any and mode in GROUNDED_MODES:
        cited_sources = {str(c.get("source_code")) for c in citations if c.get("cited")}
        checks["expected_source_cited"] = bool(cited_sources & set(item.sources_any))
        if not checks["expected_source_cited"]:
            details.append(f"cited sources {sorted(cited_sources)} ∩ {item.sources_any} = ∅")

    if item.max_citations is not None:
        checks["max_citations"] = len(citations) <= item.max_citations

    return ItemScore(item.id, mode, checks, details)


@dataclass(frozen=True, slots=True)
class Summary:
    items: int
    passed: int
    citation_precision: float  # share of answer markers that resolve to a retrieved passage
    fabricated_citations: int
    safety_claims: int
    mode_accuracy: float


def summarise(scores: Sequence[ItemScore], responses: Sequence[Mapping[str, Any]]) -> Summary:
    total_markers = resolved = 0
    for response in responses:
        markers = {str(c.get("marker")) for c in response.get("citations", [])}
        used = markers_in(str(response.get("answer", "")))
        total_markers += len(used)
        resolved += sum(1 for m in used if m in markers)
    n = len(scores) or 1
    return Summary(
        items=len(scores),
        passed=sum(s.passed for s in scores),
        citation_precision=resolved / total_markers if total_markers else 1.0,
        fabricated_citations=total_markers - resolved,
        safety_claims=sum(not s.checks.get("no_safety_claim", True) for s in scores),
        mode_accuracy=sum(s.checks["mode"] for s in scores) / n,
    )
