"""Drug search, detail and resolution (database first, optional live RxNav lookup)."""

from __future__ import annotations

import httpx
from sqlalchemy.orm import Session

from herbaguard.api.schemas.resources import DrugClassOut, DrugDetail, DrugOut, DrugResolution
from herbaguard.core.config import Settings
from herbaguard.core.errors import NotFoundError
from herbaguard.core.logging import get_logger
from herbaguard.models import Drug
from herbaguard.repositories import drugs as repo
from herbaguard.repositories import evidence as evidence_repo
from herbaguard.services.mappers import class_out, drug_out, provenance_out

logger = get_logger("herbaguard.drugs")


def as_out(session: Session, drug: Drug) -> DrugOut:
    return drug_out(drug, repo.classes_for_drug(session, drug.id))


def search(
    session: Session, query: str | None, *, limit: int, offset: int
) -> tuple[list[DrugOut], int]:
    rows, total = repo.search_drugs(session, query, limit=limit, offset=offset)
    return [as_out(session, d) for d in rows], total


def detail(session: Session, rxcui: str) -> DrugDetail:
    drug = repo.drug_by_rxcui(session, rxcui)
    if drug is None:
        raise NotFoundError(f"No drug with RxCUI {rxcui} in HerbaGuard.")
    prov = evidence_repo.provenance_for(session, "drug", [str(drug.id)]).get(str(drug.id), [])
    out = as_out(session, drug)
    return DrugDetail(**out.model_dump(), provenance=[provenance_out(p) for p in prov])


def drug_class(session: Session, code: str) -> tuple[DrugClassOut, list[DrugOut]]:
    cls = repo.get_class(session, code)
    if cls is None:
        raise NotFoundError(f"No ATC class {code} in HerbaGuard.")
    return class_out(cls), [
        as_out(session, d) for d in repo.drugs_in_class(session, code, limit=200)
    ]


def resolve(
    session: Session, settings: Settings, name: str, *, allow_remote: bool
) -> DrugResolution:
    """Name or RxCUI → RxNorm ingredient. Live RxNav lookups are recorded like any ingestion
    (ingestion_run 'rxnav', raw snapshot, provenance)."""
    query = name.strip()
    drug = (
        repo.drug_by_rxcui(session, query) if query.isdigit() else repo.drug_by_name(session, query)
    )
    if drug is not None:
        return DrugResolution(
            query=name, status="resolved", resolved_via="database", drug=as_out(session, drug)
        )
    if not allow_remote:
        return DrugResolution(
            query=name,
            status="not_found",
            note="Not in the HerbaGuard drug index; remote lookup disabled.",
        )

    from herbaguard.ingestion.context import run_ingestion
    from herbaguard.ingestion.drugs import DrugResolver, Ingredient
    from herbaguard.ingestion.http import RetryableStatusError
    from herbaguard.ingestion.loaders import ensure_sources

    single: Ingredient | None = None
    try:
        ensure_sources(session)
        session.commit()
        with run_ingestion(session, "rxnav", settings, parameters={"on_demand": True}) as ctx:
            resolver = DrugResolver(ctx)
            if query.isdigit():
                product = resolver.by_product_rxcui(query)
                if (
                    product is not None
                    and not product.multi_ingredient
                    and len(product.ingredients) == 1
                ):
                    single = product.ingredients[0]
            else:
                single = resolver.by_name(query)
    except (httpx.HTTPError, RetryableStatusError) as exc:
        logger.warning("rxnav_lookup_failed", error_type=type(exc).__name__)
        return DrugResolution(
            query=name,
            status="lookup_failed",
            note="The RxNorm service could not be reached; the drug could not be identified.",
        )
    if single is None:
        return DrugResolution(
            query=name,
            status="not_found",
            note="RxNorm did not identify exactly one ingredient for this name (combination products are not assessed).",
        )
    drug = repo.drug_by_rxcui(session, single.rxcui)
    assert drug is not None  # noqa: S101 - just upserted by the resolver
    return DrugResolution(
        query=name, status="resolved", resolved_via="rxnav", drug=as_out(session, drug)
    )
