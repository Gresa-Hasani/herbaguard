"""Phase 4: mechanism edges carry potency, conditions and their citable evidence item.

- ``target_modulation``: new columns ``potency`` and ``evidence_item_id``; the unique key now
  includes ``evidence_item_id``, so the same effect stated in two documents (e.g. EMA
  well-established-use and traditional-use columns) is kept as two rows, never merged.
- ``drug_target_role``: new columns ``potency``, ``conditions`` and ``evidence_item_id``; the role
  vocabulary gains ``moderately_sensitive_substrate`` (FDA definition: AUC increase ≥2- to
  <5-fold with strong inhibitors). Autogenerate does not detect CHECK changes, so those are
  written by hand below.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-02 18:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_ROLES = "'substrate', 'sensitive_substrate', 'inhibitor', 'inducer'"
_NEW_ROLES = (
    "'substrate', 'sensitive_substrate', 'moderately_sensitive_substrate', 'inhibitor', 'inducer'"
)
_POTENCY = "potency IN ('strong', 'moderate', 'weak')"
_OLD_UNIQUE = ["herbal_substance_id", "constituent_id", "target_id", "effect", "source_code"]


def upgrade() -> None:
    # --- target_modulation
    op.add_column("target_modulation", sa.Column("potency", sa.String(length=16), nullable=True))
    op.add_column("target_modulation", sa.Column("evidence_item_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        op.f("fk_target_modulation_evidence_item_id"),
        "target_modulation",
        "evidence_item",
        ["evidence_item_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        op.f("ix_target_modulation_evidence_item_id"),
        "target_modulation",
        ["evidence_item_id"],
        unique=False,
    )
    op.create_check_constraint(
        op.f("ck_target_modulation_potency_valid"), "target_modulation", _POTENCY
    )
    op.drop_constraint(
        op.f("uq_target_modulation_herbal_substance_id"), "target_modulation", type_="unique"
    )
    op.create_unique_constraint(
        op.f("uq_target_modulation_herbal_substance_id"),
        "target_modulation",
        [*_OLD_UNIQUE, "evidence_item_id"],
        postgresql_nulls_not_distinct=True,
    )

    # --- drug_target_role
    op.add_column("drug_target_role", sa.Column("potency", sa.String(length=16), nullable=True))
    op.add_column("drug_target_role", sa.Column("conditions", sa.Text(), nullable=True))
    op.add_column("drug_target_role", sa.Column("evidence_item_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        op.f("fk_drug_target_role_evidence_item_id"),
        "drug_target_role",
        "evidence_item",
        ["evidence_item_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        op.f("ix_drug_target_role_evidence_item_id"),
        "drug_target_role",
        ["evidence_item_id"],
        unique=False,
    )
    op.create_check_constraint(
        op.f("ck_drug_target_role_potency_valid"), "drug_target_role", _POTENCY
    )
    op.drop_constraint(op.f("ck_drug_target_role_role_valid"), "drug_target_role", type_="check")
    op.create_check_constraint(
        op.f("ck_drug_target_role_role_valid"), "drug_target_role", f"role IN ({_NEW_ROLES})"
    )


def downgrade() -> None:
    # Refuse to downgrade when data uses vocabulary or keys that revision 0002 cannot hold;
    # silently deleting or merging mechanism evidence would destroy provenance.
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM drug_target_role WHERE role = 'moderately_sensitive_substrate')
             OR EXISTS (
               SELECT 1 FROM target_modulation
               GROUP BY herbal_substance_id, constituent_id, target_id, effect, source_code
               HAVING count(*) > 1
             ) THEN
            RAISE EXCEPTION 'Cannot downgrade 0003: mechanism rows use values introduced in 0003 '
              '(moderately_sensitive_substrate, or one effect stated by several evidence items). '
              'Delete them first (or reset the development database).';
          END IF;
        END $$;
        """
    )
    op.drop_constraint(op.f("ck_drug_target_role_role_valid"), "drug_target_role", type_="check")
    op.create_check_constraint(
        op.f("ck_drug_target_role_role_valid"), "drug_target_role", f"role IN ({_OLD_ROLES})"
    )
    op.drop_constraint(op.f("ck_drug_target_role_potency_valid"), "drug_target_role", type_="check")
    op.drop_index(op.f("ix_drug_target_role_evidence_item_id"), table_name="drug_target_role")
    op.drop_constraint(
        op.f("fk_drug_target_role_evidence_item_id"), "drug_target_role", type_="foreignkey"
    )
    op.drop_column("drug_target_role", "evidence_item_id")
    op.drop_column("drug_target_role", "conditions")
    op.drop_column("drug_target_role", "potency")

    op.drop_constraint(
        op.f("uq_target_modulation_herbal_substance_id"), "target_modulation", type_="unique"
    )
    op.create_unique_constraint(
        op.f("uq_target_modulation_herbal_substance_id"),
        "target_modulation",
        _OLD_UNIQUE,
        postgresql_nulls_not_distinct=True,
    )
    op.drop_constraint(
        op.f("ck_target_modulation_potency_valid"), "target_modulation", type_="check"
    )
    op.drop_index(op.f("ix_target_modulation_evidence_item_id"), table_name="target_modulation")
    op.drop_constraint(
        op.f("fk_target_modulation_evidence_item_id"), "target_modulation", type_="foreignkey"
    )
    op.drop_column("target_modulation", "evidence_item_id")
    op.drop_column("target_modulation", "potency")
