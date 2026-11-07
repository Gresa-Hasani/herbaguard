"""Read-only NIH DSLD product labels for one plant (UI; product information only).

Only labels whose matched ingredient entity is mapped to the plant's taxon with status
``resolved`` are returned. Nothing here feeds the A–E classification, the retrieval index or AI
context: the endpoint exposes stored manufacturer label rows with their provenance so the web app
can show them in a separate, clearly labelled section.

The source is ``to_verify`` and not redistributable. The response therefore carries
``licence_status`` and ``redistributable: false``; clients must not export or republish the text.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from herbaguard.api.schemas.provenance import ProvenanceOut
from herbaguard.api.schemas.resources import ProductLabelIngredient, ProductLabelOut
from herbaguard.core.errors import NotFoundError
from herbaguard.models import (
    ExternalEntity,
    ExternalRelation,
    HerbalSubstance,
    Source,
    SourceRecord,
)
from herbaguard.repositories import plants as plant_repo
from herbaguard.repositories.external import NIH_DSLD, resolved_entity_ids


def _provenance(record: SourceRecord, source: Source, location: str) -> ProvenanceOut:
    return ProvenanceOut(
        source_code=source.code,
        source_name=source.name,
        licence=source.licence,
        licence_status=source.licence_status,
        retrieved_url=record.url,
        retrieved_at=record.retrieved_at,
        source_version=record.content_sha256[:12],
        extraction_method="dsld_csv_v1",
        location=location,
        excerpt=None,
    )


def _location(record: SourceRecord, rows: list[int]) -> str:
    return f"{record.native_id}, row(s) {', '.join(map(str, rows[:5]))}"


def list_for_plant(
    session: Session, wfo_id: str, *, limit: int, offset: int
) -> tuple[list[ProductLabelOut], int]:
    """Paginated labels for a plant, on-market products first, then DSLD id."""
    taxon = plant_repo.get_taxon(session, wfo_id)
    if taxon is None:
        raise NotFoundError(f"No plant with WFO ID {wfo_id}.")
    substances = plant_repo.substances_for_taxa(session, [taxon.id])
    if not substances:
        return [], 0
    taxa = select(HerbalSubstance.taxon_id).where(
        HerbalSubstance.id.in_([s.id for s in substances])
    )
    ingredient_ids = resolved_entity_ids(NIH_DSLD, "taxon", taxa)
    product_ids = (
        select(ExternalEntity.id, ExternalEntity.external_id)
        .join(ExternalRelation, ExternalRelation.subject_id == ExternalEntity.id)
        .where(
            ExternalRelation.source_code == NIH_DSLD,
            ExternalRelation.predicate == "lists_ingredient",
            ExternalRelation.object_id.in_(ingredient_ids),
            ExternalEntity.kind == "dsld_product",
        )
        .distinct()
    )
    total = session.scalar(select(func.count()).select_from(product_ids.subquery())) or 0
    page_ids = list(
        session.scalars(
            product_ids.order_by(ExternalEntity.external_id).limit(limit).offset(offset)
        )
    )
    if not page_ids:
        return [], total

    facts_record = aliased(SourceRecord, name="dsld_product_facts_record")
    rows = session.execute(
        select(ExternalRelation, ExternalEntity, SourceRecord, Source, facts_record)
        .join(ExternalEntity, ExternalEntity.id == ExternalRelation.subject_id)
        .join(SourceRecord, SourceRecord.id == ExternalEntity.source_record_id)
        .join(Source, Source.code == ExternalEntity.source_code)
        .join(facts_record, facts_record.id == ExternalRelation.source_record_id)
        .where(
            ExternalRelation.source_code == NIH_DSLD,
            ExternalRelation.predicate == "lists_ingredient",
            ExternalRelation.subject_id.in_(page_ids),
            ExternalRelation.object_id.in_(ingredient_ids),
            ExternalEntity.kind == "dsld_product",
        )
        .order_by(ExternalEntity.external_id)
    ).all()

    grouped: dict[uuid.UUID, dict[str, Any]] = {}
    for relation, product, record, source, facts in rows:
        entry = grouped.setdefault(
            product.id,
            {
                "product": product,
                "record": record,
                "source": source,
                "relations": [],
                "facts_records": [],
            },
        )
        entry["relations"].append(relation)
        entry["facts_records"].append(facts)

    by_id = {item["product"].id: item for item in grouped.values()}
    out: list[ProductLabelOut] = []
    for product_id in page_ids:
        page_entry = by_id.get(product_id)
        if page_entry is None:
            continue
        product_entity: ExternalEntity = page_entry["product"]
        product_record: SourceRecord = page_entry["record"]
        label_source: Source = page_entry["source"]
        attrs = product_entity.attributes or {}
        overview: dict[str, Any] = attrs.get("overview") or {}
        statements: list[dict[str, Any]] = attrs.get("label_statements") or []
        ingredients: list[ProductLabelIngredient] = []
        seen: set[tuple[str, str | None, str | None, str | None]] = set()
        for relation in page_entry["relations"]:
            row = relation.attributes or {}
            ingredient = str(row.get("Ingredient") or "").strip()
            amount = str(row.get("Amount Per Serving") or "").strip() or None
            unit = str(row.get("Amount Per Serving Unit") or "").strip() or None
            category = str(row.get("DSLD Ingredient Categories") or "").strip() or None
            key = (ingredient, amount, unit, category)
            if ingredient and key not in seen:
                seen.add(key)
                ingredients.append(
                    ProductLabelIngredient(
                        ingredient=ingredient,
                        amount_per_serving=amount,
                        unit=unit,
                        category=category,
                    )
                )
        precautions = [
            str(s.get("Statement")).strip()
            for s in statements
            if (s.get("Statement Type") or "").strip() == "Precautions"
            and (s.get("Statement") or "").strip()
        ]
        provenance = [
            _provenance(
                product_record,
                label_source,
                _location(product_record, list(product_entity.source_row_numbers or [])),
            )
        ]
        for relation, facts in zip(
            page_entry["relations"], page_entry["facts_records"], strict=False
        ):
            location = _location(facts, list(relation.source_row_numbers or []))
            if all(p.location != location for p in provenance):
                provenance.append(_provenance(facts, label_source, location))
        out.append(
            ProductLabelOut(
                dsld_id=product_entity.external_id,
                product_name=product_entity.label or overview.get("Product Name"),
                brand=overview.get("Brand Name") or None,
                market_status=overview.get("Market Status") or None,
                upc=product_entity.identifiers.get("upc") or overview.get("Bar Code") or None,
                label_url=product_entity.identifiers.get("url") or overview.get("URL") or None,
                ingredients=ingredients,
                precautions=precautions,
                label_statement_count=len(statements),
                licence_status=label_source.licence_status,
                provenance=provenance,
            )
        )
    return out, total
