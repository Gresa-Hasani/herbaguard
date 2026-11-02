"""Mechanism layer (Phase 4): enzymes/transporters, herb effects, drug roles, paths and graphs."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from herbaguard.api.schemas.mechanism_core import (
    DrugRoleOut,
    HerbEffectOut,
    MechanismPathOut,
    TargetOut,
)
from herbaguard.api.schemas.resources import DrugResolution, HerbRef, HerbResolution


class TargetDetail(TargetOut):
    herb_effect_statements: list[HerbEffectOut]
    drug_role_statements: list[DrugRoleOut]
    drug_roles_total: int
    note: str


class GraphNode(BaseModel):
    id: str = Field(examples=["target:CYP3A"])
    kind: Literal["herb", "constituent", "target", "drug"]
    label: str
    data: dict[str, object] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    kind: Literal["contains", "induces", "inhibits", "activates", "other", "substrate_of"]
    label: str
    evidence_type: str | None = None
    statement_ids: list[str] = Field(description="herb_effect / drug_role ids behind this edge")


class HerbMechanismGraph(BaseModel):
    herb: HerbRef
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    herb_effects: list[HerbEffectOut]
    drugs_truncated: bool
    note: str
    rules: str


class MechanismPathsRequest(BaseModel):
    herb: str = Field(min_length=1, max_length=200, examples=["St John's wort"])
    drug: str = Field(min_length=1, max_length=200, examples=["midazolam"])
    allow_remote_drug_lookup: bool = Field(
        default=False, description="Query RxNav if the drug is not yet in the database"
    )


class MechanismPathsResponse(BaseModel):
    herb: HerbResolution
    drug: DrugResolution
    paths: list[MechanismPathOut]
    qualifying_paths: int
    rules: str
    note: str
    disclaimer: str
