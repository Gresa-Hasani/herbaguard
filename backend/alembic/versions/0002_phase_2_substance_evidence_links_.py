"""Phase 2: herbal substance ↔ evidence links, statement types, extra evidence types.

- New table ``herbal_substance_evidence`` (monographs, fact sheets, labels, literature).
- ``interaction_assertion.subject_label_verbatim`` and ``statement_type``.
- Evidence-type vocabulary gains ``REV`` (narrative review) and ``OTHER``. Autogenerate does
  not detect CHECK changes, so those are written by hand below.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-02 13:05:47.927601
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_TYPES = (
    "'REG', 'GOV', 'SR', 'RCT', 'CLIN', 'CASE', 'ANIMAL', 'INVITRO', 'TRAD', 'SPONT', 'COMP'"
)
_NEW_TYPES = f"{_OLD_TYPES}, 'REV', 'OTHER'"
_TYPE_CHECKS = (
    ("evidence_item", "ck_evidence_item_evidence_type_valid"),
    ("interaction_assertion", "ck_interaction_assertion_evidence_type_valid"),
    ("target_modulation", "ck_target_modulation_evidence_type_valid"),
)


def upgrade() -> None:
    op.create_table(
        "herbal_substance_evidence",
        sa.Column("herbal_substance_id", sa.UUID(), nullable=False),
        sa.Column("evidence_item_id", sa.UUID(), nullable=False),
        sa.Column("relation", sa.String(length=32), nullable=False),
        sa.CheckConstraint(
            "relation IN ('monograph', 'fact_sheet', 'label_mention', "
            "'literature_interaction', 'literature_clinical')",
            name=op.f("ck_herbal_substance_evidence_relation_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["evidence_item_id"],
            ["evidence_item.id"],
            name=op.f("fk_herbal_substance_evidence_evidence_item_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["herbal_substance_id"],
            ["herbal_substance.id"],
            name=op.f("fk_herbal_substance_evidence_herbal_substance_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "herbal_substance_id",
            "evidence_item_id",
            "relation",
            name=op.f("pk_herbal_substance_evidence"),
        ),
    )
    op.create_index(
        op.f("ix_herbal_substance_evidence_evidence_item_id"),
        "herbal_substance_evidence",
        ["evidence_item_id"],
        unique=False,
    )
    op.add_column(
        "interaction_assertion", sa.Column("subject_label_verbatim", sa.Text(), nullable=True)
    )
    op.add_column(
        "interaction_assertion",
        sa.Column(
            "statement_type", sa.String(length=32), nullable=False, server_default="unclassified"
        ),
    )
    op.alter_column("interaction_assertion", "statement_type", server_default=None)
    op.create_check_constraint(
        op.f("ck_interaction_assertion_statement_type_valid"),
        "interaction_assertion",
        "statement_type IN ('interaction', 'precaution', 'no_interaction_reported', 'uncertain', 'unclassified')",
    )
    for table, name in _TYPE_CHECKS:
        op.drop_constraint(op.f(name), table, type_="check")
        op.create_check_constraint(op.f(name), table, f"evidence_type IN ({_NEW_TYPES})")


def downgrade() -> None:
    # Refuse to downgrade if data uses vocabulary that revision 0001 does not allow; dropping or
    # rewriting evidence silently would destroy provenance.
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM evidence_item WHERE evidence_type IN ('REV', 'OTHER'))
             OR EXISTS (SELECT 1 FROM interaction_assertion WHERE evidence_type IN ('REV', 'OTHER'))
             OR EXISTS (SELECT 1 FROM target_modulation WHERE evidence_type IN ('REV', 'OTHER')) THEN
            RAISE EXCEPTION 'Cannot downgrade 0002: rows use evidence types REV/OTHER introduced in 0002. '
              'Delete or re-classify them first (or reset the development database).';
          END IF;
        END $$;
        """
    )
    for table, name in _TYPE_CHECKS:
        op.drop_constraint(op.f(name), table, type_="check")
        op.create_check_constraint(op.f(name), table, f"evidence_type IN ({_OLD_TYPES})")
    op.drop_constraint(
        op.f("ck_interaction_assertion_statement_type_valid"),
        "interaction_assertion",
        type_="check",
    )
    op.drop_column("interaction_assertion", "statement_type")
    op.drop_column("interaction_assertion", "subject_label_verbatim")
    op.drop_index(
        op.f("ix_herbal_substance_evidence_evidence_item_id"),
        table_name="herbal_substance_evidence",
    )
    op.drop_table("herbal_substance_evidence")
