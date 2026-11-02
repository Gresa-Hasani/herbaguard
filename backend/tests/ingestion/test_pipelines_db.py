"""Pipelines end-to-end against PostgreSQL, replaying CAPTURED real API responses (respx).

These tests prove the pipeline logic (lineage, provenance, idempotency, normalisation) on real
response structures. They do not prove that the live APIs are reachable today — that is what the
opt-in ``live`` tests are for.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import respx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from herbaguard.core.config import Settings
from herbaguard.domain.enums import NameType
from herbaguard.ingestion.context import run_ingestion
from herbaguard.ingestion.drugs import DrugResolver
from herbaguard.ingestion.http import HttpClient
from herbaguard.ingestion.loaders import ensure_sources
from herbaguard.ingestion.pipelines import labels, taxonomy
from herbaguard.models import (
    DataQualityIssue,
    DrugClassMembership,
    EvidenceItem,
    HerbalSubstance,
    InteractionAssertion,
    Provenance,
    SourceRecord,
    Taxon,
    TaxonName,
)

pytestmark = pytest.mark.db

FIXTURES = Path(__file__).parents[1] / "fixtures" / "captured"
E = "ethcstwin.di.uoa.gr:65000"
RX = "https://rxnav.nlm.nih.gov/REST"


def fixture(name: str) -> httpx.Response:
    path = FIXTURES / name
    if path.suffix == ".json":
        return httpx.Response(200, json=json.loads(path.read_text(encoding="utf-8")))
    return httpx.Response(200, content=path.read_bytes())


@pytest.fixture
def mocked_apis() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as router:
        router.get(
            f"https://wfo.{E}/names/", params={"full_name_no_authors": "Hypericum perforatum"}
        ).mock(return_value=fixture("wfo_names_hypericum_perforatum.json"))
        router.get(
            f"https://wfo.{E}/names/", params={"full_name_no_authors": "Glycyrrhiza uralensis"}
        ).mock(return_value=fixture("wfo_names_glycyrrhiza_uralensis.json"))
        router.get(f"https://wcvp.{E}/plants/", params={"taxon_name": "Hypericum perforatum"}).mock(
            return_value=fixture("wcvp_plants_hypericum_perforatum.json")
        )
        router.get(f"https://wcvp.{E}/plants/", params={"accepted_plant_name_id": "516286"}).mock(
            return_value=fixture("wcvp_synonyms_516286.json")
        )
        router.get(f"https://taxtree.{E}/names/search/").mock(
            return_value=fixture("taxtree_hypericum_perforatum.json")
        )
        router.get("https://api.gbif.org/v1/species/match").mock(
            return_value=fixture("gbif_match_hypericum_perforatum.json")
        )
        router.get("https://api.gbif.org/v1/species/3189486/vernacularNames").mock(
            return_value=fixture("gbif_vernacular_3189486.json")
        )
        router.get("https://query.wikidata.org/sparql").mock(
            return_value=fixture("wikidata_wfo-0000728093.json")
        )
        for rxcui in ("11289", "251201", "410584", "214182", "36437"):
            router.get(f"{RX}/rxcui/{rxcui}/properties.json").mock(
                return_value=fixture(f"rxnav_properties_{rxcui}.json")
            )
        for rxcui in ("251201", "410584", "214182"):
            router.get(url__regex=rf"{RX}/rxcui/{rxcui}/related\.json\?tty=IN\+MIN$").mock(
                return_value=fixture(f"rxnav_related_{rxcui}.json")
            )
        router.get(f"{RX}/rxcui.json", params={"name": "warfarin"}).mock(
            return_value=fixture("rxnav_rxcui_name_warfarin.json")
        )
        router.get(f"{RX}/rxclass/class/byRxcui.json", params={"rxcui": "11289"}).mock(
            return_value=fixture("rxnav_atc_11289.json")
        )
        router.get(f"{RX}/rxclass/class/byRxcui.json", params={"rxcui": "36437"}).mock(
            return_value=fixture("rxnav_atc_36437.json")
        )
        router.get(f"{RX}/rxclass/class/byId.json", params={"classId": "B01AA"}).mock(
            return_value=fixture("rxnav_class_B01AA.json")
        )
        # SYNTHETIC catch-all (registered last, so captured routes win): "no ATC classes" for
        # ingredients whose ATC response was not captured (e.g. combination-product ingredients).
        router.get(f"{RX}/rxclass/class/byRxcui.json").mock(
            return_value=httpx.Response(200, json={})
        )
        yield router


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(raw_data_dir=tmp_path / "raw")


@pytest.fixture
def http(settings: Settings) -> Iterator[HttpClient]:
    client = HttpClient(settings, retry_wait_max=0.01, rate_limit=False)
    yield client
    client.close()


def _run_taxonomy(session: Session, settings: Settings, http: HttpClient) -> None:
    ensure_sources(session)
    session.commit()
    with run_ingestion(session, "wfo_ethcstwin", settings, http=http) as ctx:
        taxonomy.run(ctx, ["st_johns_wort"])


def test_taxonomy_pipeline_on_captured_responses(
    db_session: Session, settings: Settings, http: HttpClient, mocked_apis: respx.MockRouter
) -> None:
    _run_taxonomy(db_session, settings, http)

    taxon = db_session.scalars(select(Taxon)).one()
    assert (taxon.wfo_id, taxon.scientific_name, taxon.authorship, taxon.family) == (
        "wfo-0000728093", "Hypericum perforatum", "L.", "Hypericaceae",
    )  # fmt: skip
    assert (taxon.ipni_id, taxon.wcvp_plant_name_id, taxon.gbif_key, taxon.ncbi_tax_id) == (
        "433719-1",
        516286,
        3189486,
        65561,
    )
    assert taxon.wikidata_id == "Q158289"
    assert taxon.native_range == "Europe to China, NW. Africa"

    substance = db_session.scalars(select(HerbalSubstance)).one()
    assert (substance.plant_part, substance.pharmaceutical_name, substance.in_curated_scope) == (
        "herba",
        "Hyperici herba",
        True,
    )

    names = {(n.name_type, n.name) for n in db_session.scalars(select(TaxonName))}
    assert (NameType.ACCEPTED.value, "Hypericum perforatum") in names
    assert (NameType.PHARMACEUTICAL.value, "Hyperici herba") in names
    assert (NameType.COMMON.value, "St John's wort") in names
    assert any(t == NameType.SYNONYM.value for t, _ in names)

    # Every taxon field group has provenance to the exact raw record it came from.
    locations = {
        p.location
        for p in db_session.scalars(select(Provenance).where(Provenance.entity_table == "taxon"))
    }
    assert "ncbi_tax_id" in locations and "gbif_key" in locations
    for record in db_session.scalars(select(SourceRecord)):
        assert record.content_sha256 and record.raw_path and Path(record.raw_path).exists()

    mismatches = db_session.scalar(
        select(func.count())
        .select_from(DataQualityIssue)
        .where(DataQualityIssue.rule == "identifier_mismatch")
    )
    assert mismatches == 0


def test_taxonomy_pipeline_is_idempotent(
    db_session: Session, settings: Settings, http: HttpClient, mocked_apis: respx.MockRouter
) -> None:
    def counts() -> tuple[int, ...]:
        return tuple(
            db_session.scalar(select(func.count()).select_from(model)) or 0
            for model in (Taxon, TaxonName, HerbalSubstance, SourceRecord, Provenance)
        )

    _run_taxonomy(db_session, settings, http)
    first = counts()
    _run_taxonomy(db_session, settings, http)
    assert counts() == first


def test_wfo_homonym_picks_the_accepted_record(
    db_session: Session, settings: Settings, http: HttpClient, mocked_apis: respx.MockRouter
) -> None:
    """Captured case: 'Glycyrrhiza uralensis' has an unplaced (Fisch.) and an accepted (Fisch. ex DC.) record."""
    ensure_sources(db_session)
    db_session.commit()
    with run_ingestion(db_session, "wfo_ethcstwin", settings, http=http) as ctx:
        match = taxonomy.wfo_lookup(ctx, "Glycyrrhiza uralensis")
    assert match is not None
    assert (match.wfo_id, match.role, match.full_name) == (
        "wfo-0001053609",
        "accepted",
        "Glycyrrhiza uralensis Fisch. ex DC.",
    )


def test_drug_resolver_on_captured_rxnav(
    db_session: Session, settings: Settings, http: HttpClient, mocked_apis: respx.MockRouter
) -> None:
    ensure_sources(db_session)
    db_session.commit()
    with run_ingestion(db_session, "rxnav", settings, http=http) as ctx:
        resolver = DrugResolver(ctx)
        warfarin = resolver.by_name("warfarin")
        sertraline_product = resolver.by_product_rxcui("251201")  # Sertraline HCl capsule (SCD)
        combination = resolver.by_product_rxcui("214182")  # acetaminophen / hydrocodone
        b01aa = resolver.drug_class("B01AA")
    assert warfarin is not None and (warfarin.rxcui, warfarin.name) == ("11289", "warfarin")
    assert sertraline_product is not None and not sertraline_product.multi_ingredient
    assert [i.name for i in sertraline_product.ingredients] == ["sertraline"]
    assert combination is not None and combination.multi_ingredient
    assert b01aa == "B01AA"
    memberships = {m.drug_class_code for m in db_session.scalars(select(DrugClassMembership))}
    assert "B01AA" in memberships  # warfarin's ATC class from RxClass


def test_label_pipeline_attributes_sentence_to_label_drug(
    db_session: Session, settings: Settings, http: HttpClient, mocked_apis: respx.MockRouter
) -> None:
    _run_taxonomy(db_session, settings, http)
    label_page = json.loads((FIXTURES / "openfda_label_sertraline.json").read_text())
    mocked_apis.get(
        "https://api.fda.gov/drug/label.json", params={"count": "openfda.generic_name.exact"}
    ).mock(
        return_value=httpx.Response(
            200, json={"results": [{"term": "SERTRALINE HYDROCHLORIDE", "count": 1}]}
        )
    )
    mocked_apis.get("https://api.fda.gov/drug/label.json", params={"skip": "0"}).mock(
        return_value=httpx.Response(200, json=label_page)
    )

    with run_ingestion(db_session, "openfda_label", settings, http=http) as ctx:
        labels.run(ctx, ["st_johns_wort"], max_pages=1)

    assertion = db_session.scalars(select(InteractionAssertion)).first()
    assert assertion is not None
    assert (
        assertion.source_code == "openfda_label" and assertion.source_section == "drug_interactions"
    )
    assert assertion.subject_label_verbatim and "John" in assertion.subject_label_verbatim
    assert assertion.object_label_verbatim == "SERTRALINE HYDROCHLORIDE"
    evidence = db_session.scalars(select(EvidenceItem)).one()
    assert evidence.external_id.endswith("#drug_interactions")
    excerpt = db_session.scalars(
        select(Provenance.verbatim_excerpt).where(
            Provenance.entity_table == "interaction_assertion"
        )
    ).first()
    assert excerpt and excerpt in " ".join(label_page["results"][0]["drug_interactions"])


def test_label_with_products_of_different_ingredients_is_not_attributed(
    db_session: Session, settings: Settings, http: HttpClient, mocked_apis: respx.MockRouter
) -> None:
    """Regression: an oral-contraceptive pack listed an iron placebo product first and the
    statement was attributed to ferrous fumarate. All product RxCUIs must agree on ONE ingredient.
    (Product RxCUIs here: captured sertraline SCD + captured warfarin IN.)"""
    ensure_sources(db_session)
    db_session.commit()
    with run_ingestion(db_session, "openfda_label", settings, http=http) as ctx:
        resolver = DrugResolver(ctx)
        label = {"openfda": {"generic_name": ["TEST PACK"], "rxcui": ["251201", "11289"]}}
        ingredient, status = labels._label_ingredient(ctx, resolver, label)
        same = {"openfda": {"generic_name": ["SERTRALINE"], "rxcui": ["251201", "410584"]}}
        sertraline, ok = labels._label_ingredient(ctx, resolver, same)
    assert (ingredient, status) == (None, "multi_ingredient")
    assert ok == "ok" and sertraline.name == "sertraline"
