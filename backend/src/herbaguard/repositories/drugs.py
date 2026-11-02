"""Drugs (RxNorm ingredients) and ATC classes."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from herbaguard.models import Drug, DrugClass, DrugClassMembership


def search_drugs(
    session: Session, query: str | None, *, limit: int, offset: int
) -> tuple[list[Drug], int]:
    stmt = select(Drug)
    if query:
        key = query.strip().lower().replace("%", "").replace("_", "")
        stmt = stmt.where(func.lower(Drug.name).like(f"%{key}%"))
        order = [func.lower(Drug.name) != key, func.lower(Drug.name).not_like(f"{key}%"), Drug.name]
    else:
        order = [Drug.name]
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = session.scalars(stmt.order_by(*order).limit(limit).offset(offset)).all()
    return list(rows), total


def drug_by_name(session: Session, name: str) -> Drug | None:
    return session.scalar(select(Drug).where(func.lower(Drug.name) == name.strip().lower()))


def drug_by_rxcui(session: Session, rxcui: str) -> Drug | None:
    return session.scalar(select(Drug).where(Drug.rxcui == rxcui))


def classes_for_drug(session: Session, drug_id: uuid.UUID) -> list[DrugClass]:
    return list(
        session.scalars(
            select(DrugClass)
            .join(DrugClassMembership, DrugClassMembership.drug_class_code == DrugClass.code)
            .where(DrugClassMembership.drug_id == drug_id)
            .order_by(DrugClass.code)
        )
    )


def get_class(session: Session, code: str) -> DrugClass | None:
    return session.get(DrugClass, code)


def drugs_in_class(session: Session, code: str, *, limit: int) -> list[Drug]:
    """Drugs whose ATC class code starts with ``code`` (ATC is hierarchical)."""
    return list(
        session.scalars(
            select(Drug)
            .join(DrugClassMembership, DrugClassMembership.drug_id == Drug.id)
            .where(DrugClassMembership.drug_class_code.like(f"{code}%"))
            .distinct()
            .order_by(Drug.name)
            .limit(limit)
        )
    )


def atc_prefixes(codes: list[str]) -> set[str]:
    """All ancestor codes of the given ATC codes: 'B01AA' -> {B, B01, B01A, B01AA}."""
    out: set[str] = set()
    for code in codes:
        for length in (1, 3, 4, 5, 7):
            if len(code) >= length:
                out.add(code[:length])
    return out
