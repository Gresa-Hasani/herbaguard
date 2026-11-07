"""P0 regression tests from the 2026-11-07 dataset audit.

P0.1 — reviewed plant-name overrides (``domain.name_overrides``): "blessed thistle" never resolves
to milk thistle; bare "ginseng" and "black snakeroot" are always ambiguous. Checked for
``/plants/resolve``, plant search, the interaction check and the bulk mapping of external datasets.
Legitimate names and synonyms are unaffected and the stored name rows are kept.

P0.2 — DDID isolation: the AI's DDID lookup uses only DDID records with resolved mappings, so SUPP.AI,
LiverTox and NIH DSLD records (or candidate/ambiguous/unresolved entities) can never enter it.
"""

from __future__ import annotations

import shutil
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from herbaguard.ai.service import _experimental_observations
from herbaguard.core.config import Settings
from herbaguard.ingestion.context import run_ingestion
from herbaguard.ingestion.loaders import ensure_sources
from herbaguard.ingestion.pipelines import livertox, nih_dsld, supp_ai
from herbaguard.ingestion.pipelines.external_common import HerbMatcher
from herbaguard.models import (
    Drug,
    ExperimentalObservation,
    ExternalEntity,
    HerbalSubstance,
    SourceRecord,
    Taxon,
    TaxonName,
)

pytestmark = pytest.mark.db
FIXTURES = Path(__file__).parents[1] / "fixtures"


def _name(session: Session, taxon_id: uuid.UUID, name: str, kind: str, source: str) -> None:
    session.add(TaxonName(taxon_id=taxon_id, name=name, normalized_name=name.lower(), name_type=kind,
                          language="en", source_code=source))  # fmt: skip


@pytest.fixture
def milk_thistle(db_session: Session, seeded: dict[str, object]) -> Taxon:
    """Milk thistle with GBIF's vernacular name 'Blessed thistle' (the real source row)."""
    taxon = Taxon(id=uuid.uuid4(), wfo_id="wfo-0000014591", scientific_name="Silybum marianum",
                  authorship="(L.) Gaertn.", family="Asteraceae")  # fmt: skip
    db_session.add(taxon)
    db_session.flush()
    _name(db_session, taxon.id, "Silybum marianum", "accepted", "herbaguard_curated")
    _name(db_session, taxon.id, "Milk thistle", "common", "herbaguard_curated")
    _name(db_session, taxon.id, "Blessed thistle", "common", "gbif")
    _name(db_session, taxon.id, "Holy Thistle", "common", "gbif")
    db_session.add(HerbalSubstance(id=uuid.uuid4(), taxon_id=taxon.id, plant_part="fructus",
                                   pharmaceutical_name="Silybi mariani fructus", common_name_en="Milk thistle",
                                   in_curated_scope=True))  # fmt: skip
    db_session.flush()
    return taxon


def taxon_id(session: Session, scientific: str) -> uuid.UUID:
    found = session.scalar(select(Taxon.id).where(Taxon.scientific_name == scientific))
    assert found is not None
    return found


def resolve(api: TestClient, name: str) -> dict[str, Any]:
    response = api.get("/api/v1/plants/resolve", params={"name": name})
    assert response.status_code == 200, response.text
    result: dict[str, Any] = response.json()
    return result


# --------------------------------------------------------------------------- P0.1 /plants/resolve


def test_blessed_thistle_never_resolves_to_milk_thistle(api: TestClient, db_session: Session,
                                                        milk_thistle: Taxon) -> None:  # fmt: skip
    blessed = resolve(api, "Blessed Thistle")
    assert blessed["status"] == "not_found" and "Centaurea benedicta" in blessed["note"]
    assert resolve(api, "Milk thistle")["status"] == "resolved"
    assert resolve(api, "Silybum marianum")["status"] == "resolved"
    # no partial-match fallback, and plant search does not offer milk thistle for it
    search = api.get("/api/v1/plants", params={"q": "blessed thistle"}).json()
    assert all(item["scientific_name"] != "Silybum marianum" for item in search["items"])
    # the source row is kept (provenance), only its use is overridden
    assert db_session.scalar(
        select(TaxonName.id).where(TaxonName.normalized_name == "blessed thistle")
    )


def test_bare_ginseng_is_ambiguous_even_with_one_curated_species(api: TestClient, db_session: Session,
                                                                 check: Callable[..., dict[str, Any]]) -> None:  # fmt: skip
    # remove the test seed's second 'ginseng' herb so that only Panax ginseng holds the name (as in real data)
    db_session.execute(delete(TaxonName).where(TaxonName.normalized_name == "ginseng",
                                               TaxonName.taxon_id == taxon_id(db_session, "Eleutherococcus senticosus")))  # fmt: skip
    db_session.flush()
    ginseng = resolve(api, "Ginseng")
    assert ginseng["status"] == "ambiguous" and "American ginseng" in ginseng["note"]
    assert [c["pharmaceutical_name"] for c in ginseng["candidates"]] == ["Ginseng radix"]
    for specific in ("Panax ginseng", "Ginseng radix"):
        assert resolve(api, specific)["status"] == "resolved"
    assert check("ginseng", ["warfarin"], status=409)["error"]["code"]


def test_black_snakeroot_is_ambiguous_and_real_synonyms_still_work(api: TestClient, db_session: Session,
                                                                   seeded: dict[str, object]) -> None:  # fmt: skip
    _name(db_session, taxon_id(db_session, "Actaea racemosa"), "black snakeroot", "common", "gbif")
    db_session.flush()
    snakeroot = resolve(api, "Black Snakeroot")
    assert snakeroot["status"] == "ambiguous" and "Asarum canadense" in snakeroot["note"]
    assert resolve(api, "Black cohosh")["status"] == "resolved"
    assert (
        resolve(api, "Cimicifuga racemosa")["status"] == "resolved"
    )  # legitimate synonym unaffected


# --------------------------------------------------------------------------- P0.1 bulk mapping


def test_bulk_matcher_applies_the_same_overrides(db_session: Session, milk_thistle: Taxon) -> None:
    _name(db_session, taxon_id(db_session, "Actaea racemosa"), "black snakeroot", "common", "gbif")
    db_session.flush()
    herbs = HerbMatcher(db_session)
    blessed = herbs.map("Blessed Thistle")
    assert (blessed.status, blessed.target, blessed.method) == (
        "unresolved",
        None,
        "reviewed_override",
    )
    assert herbs.map("Ginseng").status == "ambiguous" and herbs.map("Ginseng").target is None
    assert herbs.map("Black Snakeroot").status == "ambiguous"
    # an ambiguous name variant cannot identify the plant; the unambiguous one still does
    cohosh = herbs.map("Black Cohosh Extract", ["black snakeroot", "Black cohosh"])
    assert cohosh.status == "candidate" and cohosh.target == taxon_id(db_session, "Actaea racemosa")
    # a variant naming blessed thistle never reaches milk thistle
    assert (
        herbs.map(
            "Centaurea Benedicta", ["blessed thistle", "holy thistle", "Cnicus benedictus"]
        ).status
        == "unresolved"
    )
    assert herbs.map("Milk thistle").target == milk_thistle.id
    assert herbs.map("Hypericum perforatum").status == "resolved"


def test_dsld_import_applies_overrides(
    db_session: Session, milk_thistle: Taxon, tmp_path: Path
) -> None:
    folder = tmp_path / "nih_dsld"
    shutil.copytree(FIXTURES / "nih_dsld", folder)
    url = "https://dsld.od.nih.gov/label/{}"
    with (folder / "ProductOverview_1.csv").open("a", encoding="utf-8") as fh:
        fh.write(
            f"{url.format(1007)},1007,Blessed Thistle Caps,Brand,,60 Capsule(s),1 Capsule(s),Botanical,Capsule,2020-01-01,On Market,Take one.\n"
        )
        fh.write(
            f"{url.format(1008)},1008,Ginseng Energy,Brand,,60 Capsule(s),1 Capsule(s),Botanical,Capsule,2020-01-01,On Market,Take one.\n"
        )
    with (folder / "DietarySupplementFacts_1.csv").open("a", encoding="utf-8") as fh:
        fh.write(
            f"{url.format(1007)},1007,Blessed Thistle Caps,1 Capsule(s),Blessed Thistle,botanical,400,mg,,\n"
        )
        fh.write(
            f"{url.format(1008)},1008,Ginseng Energy,1 Capsule(s),Ginseng,botanical,200,mg,,\n"
        )
    ensure_sources(db_session)
    with run_ingestion(db_session, "nih_dsld", Settings(_env_file=None)) as ctx:  # type: ignore[call-arg]
        nih_dsld.run(ctx, folder)
    products = set(db_session.scalars(select(ExternalEntity.external_id).where(
        ExternalEntity.source_code == "nih_dsld", ExternalEntity.kind == "dsld_product")))  # fmt: skip
    assert "1007" not in products  # blessed thistle is not a curated herb → label out of scope
    assert "1008" in products
    ginseng = db_session.scalars(select(ExternalEntity).where(ExternalEntity.source_code == "nih_dsld",
                                                              ExternalEntity.external_id == "ginseng")).one()  # fmt: skip
    assert ginseng.mapping_status == "ambiguous" and ginseng.mapped_id is None
    assert ginseng.mapping_method == "reviewed_override"


# --------------------------------------------------------------------------- P0.2 DDID isolation


def _record(ctx: Any, source: str) -> SourceRecord:
    record = SourceRecord(id=uuid.uuid4(), source_code=source, ingestion_run_id=ctx.run.id, native_id=f"{source}.test",
                          url="https://example.org/", http_status=None, content_type="text/csv",
                          content_sha256=uuid.uuid4().hex * 2, raw_path=f"{source}.test",
                          request_parameters={}, retrieved_at=datetime.now(UTC))  # fmt: skip
    ctx.session.add(record)
    ctx.session.flush()
    return record


def _entity(session: Session, record: SourceRecord, kind: str, status: str, table: str, target: uuid.UUID | None,
            label: str) -> uuid.UUID:  # fmt: skip
    entity = ExternalEntity(id=uuid.uuid4(), source_code=record.source_code, kind=kind, external_id=uuid.uuid4().hex,
                            label=label, attributes={}, identifiers={}, mapping_status=status, mapped_table=table,
                            mapped_id=target, source_record_id=record.id, source_row_numbers=[2])  # fmt: skip
    session.add(entity)
    session.flush()
    return entity.id


def _observation(
    session: Session, record: SourceRecord, herb: uuid.UUID, drug: uuid.UUID, text: str
) -> None:
    session.add(ExperimentalObservation(
        id=uuid.uuid4(), source_code=record.source_code, record_sha256=uuid.uuid4().hex * 2, original={"Result": text},
        interactant_entity_id=herb, drug_entity_id=drug, interactant_kind="herb", effect_label="Possible", species="Homo sapiens",
        result=text, conclusion=None, pmid=None, doi=None, reference=None, target_accessions=[], mapped_target_ids=[],
        derived_study_context="human", derived_evidence_type="CLIN", derivation_rule="test",
        source_record_id=record.id, source_row_numbers=[2]))  # fmt: skip
    session.flush()


def test_ddid_lookup_ignores_other_sources_and_unresolved_mappings(db_session: Session, seeded: dict[str, object],
                                                                    tmp_path: Path) -> None:  # fmt: skip
    ensure_sources(db_session)
    for name, run in (
        ("supp_ai", supp_ai.run),
        ("livertox", livertox.run),
        ("nih_dsld", nih_dsld.run),
    ):
        folder = tmp_path / name
        shutil.copytree(FIXTURES / name, folder)
        if name == "livertox":
            from tests.api.test_external_datasets import write_master_list

            write_master_list(folder)
        with run_ingestion(db_session, name, Settings(_env_file=None)) as ctx:  # type: ignore[call-arg]
            run(ctx, folder)
    sjw = taxon_id(db_session, "Hypericum perforatum")
    warfarin = db_session.scalar(select(Drug).where(Drug.name == "warfarin"))
    assert warfarin is not None
    with run_ingestion(db_session, "ddid", Settings(_env_file=None)) as ctx:  # type: ignore[call-arg]
        ddid_record, other_record = _record(ctx, "ddid"), _record(ctx, "supp_ai")
    # the genuine DDID record (resolved herb and drug)
    _observation(db_session, ddid_record, _entity(db_session, ddid_record, "herb", "resolved", "taxon", sjw, "Hypericum"),
                 _entity(db_session, ddid_record, "drug", "resolved", "drug", warfarin.id, "Warfarin"), "DDID human record")  # fmt: skip
    # a DDID record whose herb is only a candidate (synonym match): must not be used
    _observation(db_session, ddid_record, _entity(db_session, ddid_record, "herb", "candidate", "taxon", sjw, "Syn"),
                 _entity(db_session, ddid_record, "drug", "resolved", "drug", warfarin.id, "Warfarin"), "DDID candidate record")  # fmt: skip
    # worst case: an observation row of another source with *resolved* entities mapped to the same pair
    _observation(db_session, other_record, _entity(db_session, other_record, "supplement", "resolved", "taxon", sjw, "SJW"),
                 _entity(db_session, other_record, "drug", "resolved", "drug", warfarin.id, "Warfarin"), "SUPP.AI leak")  # fmt: skip
    substance_ids = tuple(
        db_session.scalars(select(HerbalSubstance.id).where(HerbalSubstance.taxon_id == sjw))
    )
    herb = SimpleNamespace(substance_ids=substance_ids, herb=SimpleNamespace(common_name="St John's wort",
                                                                              pharmaceutical_name="Hyperici herba"))  # fmt: skip
    drug = SimpleNamespace(drug_id=warfarin.id, name="warfarin")
    items = _experimental_observations(db_session, herb, drug)
    observations = [i for i in items if i.kind == "observation"]
    assert [i.text.count("DDID human record") for i in observations] == [1]
    assert not any("leak" in i.text or "candidate record" in i.text for i in items)
    assert all(p.source_code == "ddid" for i in observations for p in i.provenance)
