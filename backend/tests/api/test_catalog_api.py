"""Plants, drugs, evidence, sources and coverage endpoints on the seeded database."""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.db


def test_plant_search_ranks_exact_and_paginates(api: TestClient) -> None:
    body = api.get("/api/v1/plants", params={"q": "hypericum perforatum"}).json()
    assert body["items"][0]["wfo_id"] == "wfo-0000728093"
    assert body["items"][0]["matched_name"]["name_type"] == "accepted"
    page = api.get("/api/v1/plants", params={"limit": 2, "offset": 0}).json()
    assert page["limit"] == 2 and len(page["items"]) == 2 and page["total"] >= 6


def test_plant_resolve_groups_species_of_one_herb(api: TestClient) -> None:
    body = api.get("/api/v1/plants/resolve", params={"name": "Hawthorn"}).json()
    assert body["status"] == "resolved"
    assert body["herb"]["pharmaceutical_name"] == "Crataegi folium cum flore"
    assert len(body["taxa"]) == 2
    assert "common name" in body["note"]


def test_plant_resolve_not_found(api: TestClient) -> None:
    assert api.get("/api/v1/plants/resolve", params={"name": "zzz"}).json()["status"] == "not_found"


def test_plant_detail_has_identifiers_indications_and_monograph_state(api: TestClient) -> None:
    body = api.get("/api/v1/plants/wfo-0000519114").json()
    assert body["identifiers"]["wfo_id"] == "wfo-0000519114"
    assert any(
        n["name"] == "Cimicifuga racemosa" and n["name_type"] == "synonym" for n in body["names"]
    )
    [indication] = body["indications"]
    assert indication["use_category"] == "well_established_use"
    [monograph] = body["monographs"]
    assert monograph["interactions_section_states_none_reported"] == ["well_established_use"]
    assert body["provenance"][0]["source_code"] == "wfo_ethcstwin"


@pytest.mark.parametrize(
    ("path", "status"), [("/api/v1/plants/wfo-0000000001", 404), ("/api/v1/plants/not-a-wfo", 422)]
)
def test_plant_detail_errors(api: TestClient, path: str, status: int) -> None:
    response = api.get(path)
    assert response.status_code == status
    assert "error" in response.json()


def test_drugs_search_detail_and_class(api: TestClient) -> None:
    found = api.get("/api/v1/drugs", params={"q": "warf"}).json()
    assert [d["name"] for d in found["items"]] == ["warfarin"]
    detail = api.get("/api/v1/drugs/11289").json()
    assert detail["atc_classes"][0]["code"] == "B01AA"
    assert detail["provenance"][0]["source_code"] == "rxnav"
    cls = api.get("/api/v1/drug-classes/B01AA").json()
    assert cls["drug_class"]["level"] == 4 and [d["name"] for d in cls["drugs"]] == ["warfarin"]
    assert api.get("/api/v1/drugs/999999").status_code == 404
    assert api.get("/api/v1/drug-classes/b01aa").status_code == 422


def test_drug_resolve_from_database_and_without_remote(api: TestClient) -> None:
    local = api.post(
        "/api/v1/drugs/resolve", json={"name": "Warfarin", "allow_remote": False}
    ).json()
    assert (local["status"], local["resolved_via"], local["drug"]["rxcui"]) == (
        "resolved",
        "database",
        "11289",
    )
    missing = api.post(
        "/api/v1/drugs/resolve", json={"name": "Coumadin", "allow_remote": False}
    ).json()
    assert missing["status"] == "not_found"


def test_evidence_filters_and_type_is_not_quality(api: TestClient) -> None:
    body = api.get(
        "/api/v1/evidence", params={"wfo_id": "wfo-0000728093", "source": "pubmed"}
    ).json()
    [item] = body["items"]
    etype = item["evidence_type"]
    assert etype["code"] == "RCT" and etype["basis"] == "nlm_publication_type"
    assert etype["quality_assessed"] is False and "not a quality rating" in etype["note"]
    ema = api.get(
        "/api/v1/evidence", params={"herb": "Hyperici herba", "source": "ema_hmpc"}
    ).json()
    assert ema["total"] == 2 and all(
        i["evidence_type"]["basis"] == "source_document" for i in ema["items"]
    )
    by_type = api.get("/api/v1/evidence", params={"evidence_type": ["RCT", "SR"]}).json()
    assert {i["evidence_type"]["code"] for i in by_type["items"]} == {"RCT"}
    searched = api.get("/api/v1/evidence", params={"q": "serotonin"}).json()
    assert {i["external_id"] for i in searched["items"]} == {
        "set-sert#drug_interactions",
        "set-li#warnings",
    }


def test_evidence_detail_and_errors(api: TestClient) -> None:
    listed = api.get("/api/v1/evidence", params={"source": "nccih"}).json()["items"][0]
    detail = api.get(f"/api/v1/evidence/{listed['id']}").json()
    assert detail["content"][0]["text"].startswith("There is conflicting evidence")
    assert detail["provenance"] and detail["herbs"] == ["Hyperici herba"]
    assert api.get("/api/v1/evidence/00000000-0000-0000-0000-000000000000").status_code == 404
    assert api.get("/api/v1/evidence", params={"herb": "Nonexistent herba"}).status_code == 404
    assert api.get("/api/v1/evidence", params={"evidence_type": "QUALITY5"}).status_code == 422
    assert api.get("/api/v1/evidence", params={"limit": 101}).status_code == 422


def test_sources_and_coverage(api: TestClient) -> None:
    sources = {s["code"]: s for s in api.get("/api/v1/sources").json()}
    assert sources["ema_hmpc"]["licence_status"] in {"verified", "catalogue", "to_verify"}
    coverage = {
        row["herb"]["pharmaceutical_name"]: row for row in api.get("/api/v1/coverage").json()
    }
    assert coverage["Crataegi folium cum flore"]["taxa"] == 2
    sjw = coverage["Hyperici herba"]
    assert sjw["monograph"] == "EMA/HMPC/7695/2021" and sjw["fact_sheet"] is True
    assert sjw["pubmed_by_type"] == {"RCT": 1}
    assert "not a quality rating" in sjw["type_note"]


def test_sources_expose_recorded_licence_metadata_without_inventing_any(api: TestClient) -> None:
    sources = {s["code"]: s for s in api.get("/api/v1/sources").json()}
    ema = sources["ema_hmpc"]
    for field in (
        "licence_url",
        "attribution",
        "access_method",
        "latest_retrieved_at",
        "latest_source_version",
    ):
        assert field in ema
    # Unrecorded metadata stays null (clients show it as "not recorded", never as permission).
    assert all(s["licence_url"] is None for s in sources.values())
    assert all(s["attribution"] is None for s in sources.values())


def test_plant_coverage_covers_every_taxon_and_matches_plant_detail(api: TestClient) -> None:
    index = api.get("/api/v1/plants", params={"limit": 100}).json()
    coverage = api.get("/api/v1/coverage/plants").json()
    assert coverage["total"] == index["total"] == len(coverage["items"])
    assert {row["wfo_id"] for row in coverage["items"]} == {t["wfo_id"] for t in index["items"]}

    for row in coverage["items"]:
        assert row["taxonomic_status"] == "accepted"
        detail = api.get(f"/api/v1/plants/{row['wfo_id']}").json()
        counts = detail["counts"]
        assert row["literature_clinical_items"] == counts.get("evidence_literature_clinical", 0)
        assert row["literature_interaction_items"] == counts.get(
            "evidence_literature_interaction", 0
        )
        assert row["fact_sheet_items"] == counts.get("evidence_fact_sheet", 0)
        assert row["drug_label_mentions"] == counts.get("evidence_label_mention", 0)
        assert row["monograph_documents"] == len(detail["monographs"])
        assert row["active_interaction_statements"] == counts["active_interaction_statements"]


def test_plant_coverage_keeps_product_labels_and_supplementary_sources_apart(
    api: TestClient,
) -> None:
    row = next(
        r
        for r in api.get("/api/v1/coverage/plants").json()["items"]
        if r["wfo_id"] == "wfo-0000728093"
    )
    # Product labels are a separate count; supplementary mappings carry only resolved/candidate.
    assert isinstance(row["dsld_products"], int)
    assert set(row["supplementary_sources"].values()) <= {"resolved", "candidate"}
    assert set(row["supplementary_sources"]) <= {"ddid", "supp_ai", "livertox"}


def test_openapi_documents_every_endpoint(api: TestClient) -> None:
    paths = api.get("/api/openapi.json").json()["paths"]
    for path in (
        "/api/v1/plants",
        "/api/v1/plants/{wfo_id}",
        "/api/v1/interactions/check",
        "/api/v1/evidence",
        "/api/v1/coverage",
        "/api/v1/coverage/plants",
    ):
        assert path in paths
    assert "409" in paths["/api/v1/interactions/check"]["post"]["responses"]


def _fixture(name: str) -> httpx.Response:
    import json
    from pathlib import Path

    import httpx

    path = Path(__file__).parents[1] / "fixtures" / "captured" / name
    return httpx.Response(200, json=json.loads(path.read_text(encoding="utf-8")))


def test_drug_resolve_brand_name_via_captured_rxnav(api: TestClient) -> None:
    """Remote path on CAPTURED RxNav responses: brand 'Coumadin' (BN 202421) → ingredient warfarin."""
    import respx

    rx = "https://rxnav.nlm.nih.gov/REST"
    with respx.mock(assert_all_called=False) as router:
        router.get(f"{rx}/rxcui.json", params={"name": "Coumadin"}).mock(
            return_value=_fixture("rxnav_rxcui_name_coumadin.json")
        )
        router.get(f"{rx}/rxcui/202421/properties.json").mock(
            return_value=_fixture("rxnav_properties_202421.json")
        )
        router.get(url__regex=rf"{rx}/rxcui/202421/related\.json\?tty=IN\+MIN$").mock(
            return_value=_fixture("rxnav_related_202421.json")
        )
        router.get(f"{rx}/rxclass/class/byRxcui.json", params={"rxcui": "11289"}).mock(
            return_value=_fixture("rxnav_atc_11289.json")
        )
        body = api.post("/api/v1/drugs/resolve", json={"name": "Coumadin"}).json()
    assert (body["status"], body["resolved_via"]) == ("resolved", "rxnav")
    assert (body["drug"]["rxcui"], body["drug"]["name"]) == ("11289", "warfarin")


def test_drug_resolve_reports_unreachable_rxnav(api: TestClient) -> None:
    import httpx
    import respx

    with respx.mock(assert_all_called=False) as router:
        router.route(host="rxnav.nlm.nih.gov").mock(side_effect=httpx.ConnectError("down"))
        body = api.post("/api/v1/drugs/resolve", json={"name": "ibuprofen"}).json()
    assert body["status"] == "lookup_failed"
