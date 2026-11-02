"""Declarative base, naming convention and reusable column helpers."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, MetaData, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Deterministic constraint names keep Alembic autogenerate diffs stable. Names use only the
# first column so they stay below PostgreSQL's 63-character identifier limit (longer names
# would be truncated silently and drift from the metadata).
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s",
    "pk": "pk_%(table_name)s",
}
MAX_IDENTIFIER_LENGTH = 63


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def created_at_column() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


def updated_at_column() -> Mapped[datetime]:
    return mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


def enum_check(column: str, enum_cls: type[StrEnum], name: str | None = None) -> CheckConstraint:
    """CHECK constraint restricting a text column to the values of a StrEnum.

    Plain text + CHECK is used instead of native PostgreSQL ENUM types because it is
    simpler to migrate when vocabularies grow.
    """
    values = ", ".join(f"'{member.value}'" for member in enum_cls)
    return CheckConstraint(f"{column} IN ({values})", name=name or f"{column}_valid")
