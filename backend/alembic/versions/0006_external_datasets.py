"""External research datasets (first: DDID): entities, relations, experimental observations.

Generic tables so later datasets need no new schema (docs/data/ddid.md):

- ``external_entity``: an entity as the dataset defines it, all original columns in ``attributes``,
  other identifier namespaces in ``identifiers``, and an explicit mapping status (resolved /
  ambiguous / unresolved / not_applicable) with method and note.
- ``external_relation``: relations exactly as stated by the dataset (e.g. herb → natural product).
- ``experimental_observation``: one experimental record with the complete original row, typed copies
  for querying and derived fields (study context, evidence type, rule version) in separate columns.

None of these tables is read by the A–E classification. The downgrade refuses to run while any of
them holds rows, so imported data is never dropped silently.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-06 23:30:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_EVIDENCE_TYPES = "'REG', 'GOV', 'SR', 'RCT', 'CLIN', 'CASE', 'ANIMAL', 'INVITRO', 'TRAD', 'SPONT', 'COMP', 'REV', 'OTHER'"


def _timestamps() -> list[sa.Column]:  # type: ignore[type-arg]
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "external_entity",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("source_code", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("external_id", sa.String(length=128), nullable=False),
        sa.Column("label", sa.Text(), nullable=True),
        sa.Column("attributes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("identifiers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("mapping_status", sa.String(length=16), nullable=False),
        sa.Column("mapped_table", sa.String(length=32), nullable=True),
        sa.Column("mapped_id", sa.UUID(), nullable=True),
        sa.Column("mapping_method", sa.String(length=64), nullable=True),
        sa.Column("mapping_note", sa.Text(), nullable=True),
        sa.Column("source_record_id", sa.UUID(), nullable=False),
        sa.Column("source_row_numbers", postgresql.ARRAY(sa.Integer()), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["source_code"], ["source.code"], name=op.f("fk_external_entity_source_code")),
        sa.ForeignKeyConstraint(["source_record_id"], ["source_record.id"], ondelete="RESTRICT",
                                name=op.f("fk_external_entity_source_record_id")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_external_entity")),
        sa.UniqueConstraint("source_code", "kind", "external_id", name=op.f("uq_external_entity_source_code")),
    )  # fmt: skip
    op.create_index("ix_external_entity_mapping", "external_entity", ["mapped_table", "mapped_id"])

    op.create_table(
        "external_relation",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("source_code", sa.String(length=64), nullable=False),
        sa.Column("subject_id", sa.UUID(), nullable=False),
        sa.Column("predicate", sa.String(length=64), nullable=False),
        sa.Column("object_id", sa.UUID(), nullable=False),
        sa.Column("attributes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("attributes_sha256", sa.String(length=64), nullable=False),
        sa.Column("source_record_id", sa.UUID(), nullable=False),
        sa.Column("source_row_numbers", postgresql.ARRAY(sa.Integer()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["source_code"], ["source.code"], name=op.f("fk_external_relation_source_code")),
        sa.ForeignKeyConstraint(["subject_id"], ["external_entity.id"], ondelete="CASCADE",
                                name=op.f("fk_external_relation_subject_id")),
        sa.ForeignKeyConstraint(["object_id"], ["external_entity.id"], ondelete="CASCADE",
                                name=op.f("fk_external_relation_object_id")),
        sa.ForeignKeyConstraint(["source_record_id"], ["source_record.id"], ondelete="RESTRICT",
                                name=op.f("fk_external_relation_source_record_id")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_external_relation")),
        sa.UniqueConstraint("source_code", "subject_id", "predicate", "object_id", "attributes_sha256",
                            name=op.f("uq_external_relation_source_code")),
    )  # fmt: skip
    op.create_index(op.f("ix_external_relation_subject_id"), "external_relation", ["subject_id"])
    op.create_index(op.f("ix_external_relation_object_id"), "external_relation", ["object_id"])

    op.create_table(
        "experimental_observation",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("source_code", sa.String(length=64), nullable=False),
        sa.Column("record_sha256", sa.String(length=64), nullable=False),
        sa.Column("original", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("interactant_entity_id", sa.UUID(), nullable=False),
        sa.Column("drug_entity_id", sa.UUID(), nullable=False),
        sa.Column("interactant_kind", sa.String(length=16), nullable=False),
        sa.Column("effect_label", sa.String(length=32), nullable=False),
        sa.Column("species", sa.String(length=64), nullable=True),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("conclusion", sa.Text(), nullable=True),
        sa.Column("pmid", sa.String(length=16), nullable=True),
        sa.Column("doi", sa.String(length=255), nullable=True),
        sa.Column("reference", sa.Text(), nullable=True),
        sa.Column("target_accessions", postgresql.ARRAY(sa.String(length=16)), nullable=False),
        sa.Column("mapped_target_ids", postgresql.ARRAY(sa.String(length=36)), nullable=False),
        sa.Column("derived_study_context", sa.String(length=16), nullable=False),
        sa.Column("derived_evidence_type", sa.String(length=8), nullable=False),
        sa.Column("derivation_rule", sa.String(length=64), nullable=False),
        sa.Column("evidence_item_id", sa.UUID(), nullable=True),
        sa.Column("source_record_id", sa.UUID(), nullable=False),
        sa.Column("source_row_numbers", postgresql.ARRAY(sa.Integer()), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(f"derived_evidence_type IN ({_EVIDENCE_TYPES})",
                           name=op.f("ck_experimental_observation_derived_evidence_type_valid")),
        sa.ForeignKeyConstraint(["source_code"], ["source.code"],
                                name=op.f("fk_experimental_observation_source_code")),
        sa.ForeignKeyConstraint(["interactant_entity_id"], ["external_entity.id"], ondelete="RESTRICT",
                                name=op.f("fk_experimental_observation_interactant_entity_id")),
        sa.ForeignKeyConstraint(["drug_entity_id"], ["external_entity.id"], ondelete="RESTRICT",
                                name=op.f("fk_experimental_observation_drug_entity_id")),
        sa.ForeignKeyConstraint(["evidence_item_id"], ["evidence_item.id"], ondelete="SET NULL",
                                name=op.f("fk_experimental_observation_evidence_item_id")),
        sa.ForeignKeyConstraint(["source_record_id"], ["source_record.id"], ondelete="RESTRICT",
                                name=op.f("fk_experimental_observation_source_record_id")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_experimental_observation")),
        sa.UniqueConstraint("source_code", "record_sha256", name=op.f("uq_experimental_observation_source_code")),
    )  # fmt: skip
    op.create_index("ix_experimental_observation_pair", "experimental_observation",
                    ["interactant_entity_id", "drug_entity_id"])  # fmt: skip
    op.create_index(op.f("ix_experimental_observation_pmid"), "experimental_observation", ["pmid"])
    op.create_index(op.f("ix_experimental_observation_evidence_item_id"), "experimental_observation",
                    ["evidence_item_id"])  # fmt: skip


def downgrade() -> None:
    bind = op.get_bind()
    for table in ("experimental_observation", "external_relation", "external_entity"):
        count = bind.execute(sa.text(f"SELECT count(*) FROM {table}")).scalar_one()  # noqa: S608 - fixed names
        if count:
            msg = f"{table} holds {count} rows; delete the imported dataset explicitly before downgrading."
            raise RuntimeError(msg)
    op.drop_table("experimental_observation")
    op.drop_table("external_relation")
    op.drop_table("external_entity")
