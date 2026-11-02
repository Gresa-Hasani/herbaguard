"""SQLAlchemy ORM models — schema v1. See ``docs/architecture/data-model.md``.

Importing this package registers every table on ``Base.metadata`` (used by Alembic).
"""

from herbaguard.models.base import Base
from herbaguard.models.evidence import (
    Chunk,
    EvidenceItem,
    Indication,
    InteractionAssertion,
    InteractionAssertionEvidence,
)
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
    "HerbalSubstance",
    "HerbalSubstanceConstituent",
    "Indication",
    "IngestionRun",
    "InteractionAssertion",
    "InteractionAssertionEvidence",
    "Provenance",
    "Source",
    "SourceRecord",
    "Target",
    "TargetModulation",
    "Taxon",
    "TaxonName",
]
