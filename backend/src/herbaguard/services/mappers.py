"""ORM rows → API schemas. Keeps provenance attached to everything scientific."""

from __future__ import annotations

from herbaguard.api.schemas.provenance import EvidenceRef, EvidenceTypeInfo, ProvenanceOut
from herbaguard.api.schemas.resources import DrugClassOut, DrugOut, NameOut
from herbaguard.domain.enums import StatementType
from herbaguard.models import Drug, DrugClass, EvidenceItem, TaxonName
from herbaguard.repositories.evidence import ProvenanceRow

STATEMENT_TYPE_NOTES: dict[str, str] = {
    StatementType.INTERACTION: "The source states an interaction, contraindication or effect.",
    StatementType.PRECAUTION: "The source advises caution or monitoring; it does not state that an interaction occurs.",
    StatementType.NO_INTERACTION_REPORTED: "The source states that no interaction was found or reported.",
    StatementType.UNCERTAIN: "The source itself describes the evidence as conflicting or unclear.",
    StatementType.UNCLASSIFIED: (
        "The herb is mentioned without explicit interaction wording — context only, not a confirmed interaction."
    ),
}


def provenance_out(row: ProvenanceRow) -> ProvenanceOut:
    return ProvenanceOut(
        source_code=row.source_code,
        source_name=row.source_name,
        licence=row.licence,
        licence_status=row.licence_status,
        retrieved_url=row.record_url,
        retrieved_at=row.retrieved_at,
        source_version=row.source_version,
        extraction_method=row.extraction_method,
        location=row.location,
        excerpt=row.excerpt,
    )


def evidence_ref(item: EvidenceItem) -> EvidenceRef:
    return EvidenceRef(
        id=str(item.id),
        source_code=item.source_code,
        external_id=item.external_id,
        title=item.title,
        url=item.url,
        evidence_type=EvidenceTypeInfo.of(item.evidence_type, item.source_code),
        document_date=item.document_date,
        publication_year=item.publication_year,
    )


def name_out(name: TaxonName) -> NameOut:
    return NameOut(
        name=name.name,
        name_type=name.name_type,
        language=name.language,
        source_code=name.source_code,
    )


def class_out(cls: DrugClass) -> DrugClassOut:
    return DrugClassOut(code=cls.code, name=cls.name, level=cls.level, system=cls.system)


def drug_out(drug: Drug, classes: list[DrugClass]) -> DrugOut:
    return DrugOut(rxcui=drug.rxcui, name=drug.name, atc_classes=[class_out(c) for c in classes])
