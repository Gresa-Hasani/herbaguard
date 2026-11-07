"""Source registry rules (no database): every definition fits the ``source`` table, and the
external-dataset licences stay conservative until permissions are established."""

from __future__ import annotations

from herbaguard.domain.enums import LicenceStatus
from herbaguard.ingestion.sources import SOURCES
from herbaguard.models import Source


def test_every_source_fits_the_source_table() -> None:
    limit = Source.__table__.c.licence.type.length  # String(255)
    for source in SOURCES:
        assert source.licence is None or len(source.licence) <= limit, source.code
    assert len({s.code for s in SOURCES}) == len(SOURCES)


def test_external_dataset_licences_are_conservative() -> None:
    """SUPP.AI and NIH DSLD stay unverified and not redistributable until permission is confirmed
    (2026-11-07 audit, P0.3); LiverTox is verified from its downloaded terms."""
    statuses = {s.code: (s.licence_status, s.redistributable) for s in SOURCES}
    assert statuses["supp_ai"] == (LicenceStatus.TO_VERIFY, False)
    assert statuses["nih_dsld"] == (LicenceStatus.TO_VERIFY, False)
    assert statuses["livertox"] == (LicenceStatus.VERIFIED, True)
