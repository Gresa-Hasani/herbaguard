"""Mechanism output objects shared by the interaction check and the mechanism endpoints."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from herbaguard.api.schemas.provenance import EvidenceRef, EvidenceTypeInfo, ProvenanceOut

ROLE_LABELS: dict[str, str] = {
    "sensitive_substrate": "sensitive substrate (AUC ≥5-fold with strong inhibitors)",
    "moderately_sensitive_substrate": "moderately sensitive substrate (AUC ≥2- to <5-fold with strong inhibitors)",
    "substrate": "substrate",
    "inhibitor": "inhibitor",
    "inducer": "inducer",
}


class TargetRef(BaseModel):
    symbol: str = Field(examples=["CYP3A"])
    name: str
    target_type: Literal["enzyme", "transporter", "receptor", "other"]


class TargetOut(TargetRef):
    uniprot_accession: str | None = Field(examples=["P08684"])
    uniprot_url: str | None
    herb_effects: int = Field(description="Stored herb/constituent effects on this target")
    drug_roles: int = Field(description="Stored drug roles (substrate/inhibitor/inducer)")


class DrugRef(BaseModel):
    rxcui: str
    name: str


class HerbEffectOut(BaseModel):
    """A stored statement that a herb (or one of its constituents) affects an enzyme/transporter."""

    id: str
    herb: str = Field(
        description="Pharmaceutical name of the herbal substance", examples=["Hyperici herba"]
    )
    subject_kind: Literal["herbal_substance", "constituent"]
    subject_label: str = Field(
        description="The herbal substance, or the constituent the source names"
    )
    target: TargetRef
    effect: str = Field(examples=["induces"])
    potency: str | None = Field(
        description="Strength as stated by the source (FDA: strong/moderate/weak); never computed"
    )
    evidence_type: EvidenceTypeInfo
    source_code: str
    conditions: str | None = Field(description="Use category, dose condition or source footnotes")
    evidence: EvidenceRef | None
    provenance: list[ProvenanceOut]


class DrugRoleOut(BaseModel):
    """A stored statement that a drug is a substrate, inhibitor or inducer of an enzyme/transporter."""

    id: str
    drug: DrugRef
    target: TargetRef
    role: str = Field(examples=["sensitive_substrate"])
    role_label: str
    potency: str | None
    conditions: str | None
    source_code: str
    evidence: EvidenceRef | None
    provenance: list[ProvenanceOut]


class MechanismPathOut(BaseModel):
    """Herb effect + drug role on the same enzyme/transporter."""

    target_symbols: str = Field(examples=["CYP3A4 / CYP3A"])
    herb_effect: HerbEffectOut
    drug_role: DrugRoleOut
    qualifies_for_class_b: bool = Field(
        description="True if the path meets every rule in docs/api/mechanism-paths.md"
    )
    reasons_not_qualifying: list[str]
    description: str
