"""SQLAlchemy ORM models — schema v1. See ``docs/architecture/data-model.md``.

Importing this package registers every table on ``Base.metadata`` (used by Alembic).
"""

from herbaguard.models.base import Base
from herbaguard.models.evidence import (
    Chunk,
    EvidenceItem,
    HerbalSubstanceEvidence,
    Indication,
    InteractionAssertion,
    InteractionAssertionEvidence,
)
from herbaguard.models.external import ExperimentalObservation, ExternalEntity, ExternalRelation
from herbaguard.models.pharmacology import (
    Constituent,
    Drug,
    DrugClass,
    DrugClassMembership,
    DrugTargetRoleLink,
    HerbalSubstanceConstituent,
    Target,
    TargetModulation,
)
from herbaguard.models.provenance import (
    DataQualityIssue,
    IngestionRun,
    Provenance,
    Source,
    SourceRecord,
)
from herbaguard.models.retrieval import RetrievalSegment, SegmentEmbedding
from herbaguard.models.taxonomy import HerbalSubstance, Taxon, TaxonName

__all__ = [
    "Base",
    "Chunk",
    "Constituent",
    "DataQualityIssue",
    "Drug",
    "DrugClass",
    "DrugClassMembership",
    "DrugTargetRoleLink",
    "EvidenceItem",
    "ExperimentalObservation",
    "ExternalEntity",
    "ExternalRelation",
    "HerbalSubstance",
    "HerbalSubstanceConstituent",
    "HerbalSubstanceEvidence",
    "Indication",
    "IngestionRun",
    "InteractionAssertion",
    "InteractionAssertionEvidence",
    "Provenance",
    "RetrievalSegment",
    "SegmentEmbedding",
    "Source",
    "SourceRecord",
    "Target",
    "TargetModulation",
    "Taxon",
    "TaxonName",
]
