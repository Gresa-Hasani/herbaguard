"""Queries over external datasets (``external_entity``; migration 0006).

Every consumer that turns an external record into something HerbaGuard shows or reasons about must
go through ``resolved_entity_ids``: it names the source explicitly and returns only entities whose
mapping is ``resolved``. ``candidate`` (synonym or name-variant matches that need review),
``ambiguous``, ``unresolved`` and ``not_applicable`` entities never qualify, even though candidates
store a ``mapped_id`` for review.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Any

from sqlalchemy import Select, select

from herbaguard.models import ExternalEntity

DDID = "ddid"
LIVERTOX = "livertox"
SUPP_AI = "supp_ai"
NIH_DSLD = "nih_dsld"
RESOLVED = "resolved"


def resolved_entity_ids(
    source: str, mapped_table: str, mapped_ids: Iterable[uuid.UUID] | Select[Any]
) -> Select[tuple[uuid.UUID]]:
    """Ids of ``source``'s entities mapped to ``mapped_table`` rows ``mapped_ids`` with status
    ``resolved`` only (a subquery; ``mapped_ids`` may itself be a subquery)."""
    ids = mapped_ids if isinstance(mapped_ids, Select) else list(mapped_ids)
    return select(ExternalEntity.id).where(
        ExternalEntity.source_code == source,
        ExternalEntity.mapped_table == mapped_table,
        ExternalEntity.mapped_id.in_(ids),
        ExternalEntity.mapping_status == RESOLVED,
    )
