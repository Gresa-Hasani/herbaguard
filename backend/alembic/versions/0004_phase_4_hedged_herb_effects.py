"""Phase 4 completion: herb effects keep the source's hedging word.

``target_modulation.hedge_wording`` stores the modal word the source puts before the effect verb
("may", "might", "could" …), e.g. EU monograph for Ginkgo folium: "G. biloba may inhibit
P-glycoprotein". NULL means the source states the effect without hedging (or the source is a
table). The word is shown with every path and effect; it never upgrades or downgrades a class.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-03 09:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "target_modulation", sa.Column("hedge_wording", sa.String(length=32), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("target_modulation", "hedge_wording")
