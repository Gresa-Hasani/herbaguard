"""Deterministic evidence-type classification for PubMed records (no LLM).

Precedence (strongest human evidence first): SR > RCT > CLIN > CASE > REV > ANIMAL > INVITRO >
OTHER. Based on NLM Publication Types and MeSH descriptors, which are assigned by indexers.
Publication type describes study *design*, not study *quality*.
"""

from __future__ import annotations

from herbaguard.domain.enums import EvidenceType

_SR = {"Systematic Review", "Meta-Analysis"}
_RCT = {"Randomized Controlled Trial"}
_CLIN = {
    "Clinical Trial", "Clinical Trial, Phase I", "Clinical Trial, Phase II",
    "Clinical Trial, Phase III", "Clinical Trial, Phase IV", "Controlled Clinical Trial",
    "Observational Study", "Pragmatic Clinical Trial", "Multicenter Study", "Clinical Study",
    "Equivalence Trial", "Comparative Study",
}  # fmt: skip
_CASE = {"Case Reports"}
_REVIEW = {"Review", "Scoping Review"}
_IN_VITRO_MESH = {
    "In Vitro Techniques", "Microsomes, Liver", "Cell Line", "Cell Line, Tumor", "Cells, Cultured",
    "Hep G2 Cells", "Caco-2 Cells", "Hepatocytes",
}  # fmt: skip


def classify_pubmed(publication_types: list[str], mesh_terms: list[str]) -> EvidenceType:
    types = set(publication_types)
    mesh = set(mesh_terms)
    humans = "Humans" in mesh
    if types & _SR:
        return EvidenceType.SYSTEMATIC_REVIEW
    if types & _RCT:
        return EvidenceType.RANDOMISED_CONTROLLED_TRIAL
    clinical = types & _CLIN
    # "Comparative Study" / "Multicenter Study" are also used for animal work, so on their own
    # they only count as clinical when the MeSH terms include Humans.
    if clinical and (clinical - {"Comparative Study", "Multicenter Study"} or humans):
        return EvidenceType.CLINICAL_STUDY
    if types & _CASE:
        return EvidenceType.CASE_REPORT
    if types & _REVIEW:
        return EvidenceType.NARRATIVE_REVIEW
    if "Animals" in mesh and not humans:
        return EvidenceType.ANIMAL
    if mesh & _IN_VITRO_MESH:
        return EvidenceType.IN_VITRO
    return EvidenceType.OTHER
