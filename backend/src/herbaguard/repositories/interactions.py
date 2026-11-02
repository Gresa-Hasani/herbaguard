"""Active interaction assertions for herbs and drugs."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from herbaguard.domain.enums import AssertionStatus
from herbaguard.models import (
    DataQualityIssue,
    Drug,
    DrugClass,
    EvidenceItem,
    InteractionAssertion,
    InteractionAssertionEvidence,
)


@dataclass(frozen=True, slots=True)
class AssertionRow:
    assertion: InteractionAssertion
    evidence: EvidenceItem
    drug_name: str | None
    drug_rxcui: str | None
    class_name: str | None


def active_assertions(
    session: Session,
    substance_ids: list[uuid.UUID],
    *,
    drug_id: uuid.UUID | None = None,
    class_codes: set[str] | None = None,
) -> list[AssertionRow]:
    """Active assertions for these substances; optionally only those naming the drug or one of
    the given class codes (ancestors of the drug's ATC codes)."""
    conditions = [
        InteractionAssertion.herbal_substance_id.in_(substance_ids),
        InteractionAssertion.status == AssertionStatus.ACTIVE.value,
    ]
    if drug_id is not None or class_codes is not None:
        alternatives = []
        if drug_id is not None:
            alternatives.append(InteractionAssertion.drug_id == drug_id)
        if class_codes:
            alternatives.append(InteractionAssertion.drug_class_code.in_(class_codes))
        conditions.append(or_(*alternatives) if alternatives else InteractionAssertion.id.is_(None))
    rows = session.execute(
        select(InteractionAssertion, EvidenceItem, Drug.name, Drug.rxcui, DrugClass.name)
        .join(
            InteractionAssertionEvidence,
            InteractionAssertionEvidence.interaction_assertion_id == InteractionAssertion.id,
        )
        .join(EvidenceItem, EvidenceItem.id == InteractionAssertionEvidence.evidence_item_id)
        .outerjoin(Drug, Drug.id == InteractionAssertion.drug_id)
        .outerjoin(DrugClass, DrugClass.code == InteractionAssertion.drug_class_code)
        .where(and_(*conditions))
        .order_by(
            InteractionAssertion.source_code,
            InteractionAssertion.source_section,
            InteractionAssertion.id,
        )
    ).all()
    return [AssertionRow(r[0], r[1], r[2], r[3], r[4]) for r in rows]


@dataclass(frozen=True, slots=True)
class NoneReportedSection:
    evidence_id: uuid.UUID
    document: str
    section: str
    use_category: str
    document_date: date | None
    text: str
    url: str | None


def none_reported_sections(
    session: Session, substance_ids: list[uuid.UUID]
) -> list[NoneReportedSection]:
    """EMA §4.5 sections whose whole text is 'None reported/known' for these substances."""
    from herbaguard.models import Chunk, HerbalSubstanceEvidence

    rows = session.execute(
        select(EvidenceItem, Chunk.text)
        .join(HerbalSubstanceEvidence, HerbalSubstanceEvidence.evidence_item_id == EvidenceItem.id)
        .join(Chunk, Chunk.evidence_item_id == EvidenceItem.id)
        .where(
            HerbalSubstanceEvidence.herbal_substance_id.in_(substance_ids),
            EvidenceItem.source_code == "ema_hmpc",
            EvidenceItem.is_superseded.is_(False),
            EvidenceItem.metadata_["section"].astext == "4.5",
            EvidenceItem.metadata_["section_statement"].astext == "none_reported",
        )
        .distinct()
    ).all()
    return [
        NoneReportedSection(
            evidence_id=e.id,
            document=str(e.metadata_.get("document", e.external_id)),
            section="4.5",
            use_category=str(e.metadata_.get("use_category", "")),
            document_date=e.document_date,
            text=text.split("\n\n")[0].strip(),
            url=e.url,
        )
        for e, text in rows
    ]


def label_coverage(session: Session, herb_key: str) -> DataQualityIssue | None:
    """Latest openFDA coverage record for a curated herb (written by the label pipeline)."""
    return session.scalar(
        select(DataQualityIssue)
        .where(
            DataQualityIssue.rule == "openfda_coverage",
            DataQualityIssue.context["herb"].astext == herb_key,
        )
        .order_by(DataQualityIssue.created_at.desc())
        .limit(1)
    )
