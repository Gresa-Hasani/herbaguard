"""Interaction check end-to-end (API → service → rules → seeded database).

Covers every finding, including negative and insufficient-evidence scenarios.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.db

Check = Callable[..., dict[str, Any]]


def result_for(response: dict[str, Any], drug: str) -> dict[str, Any]:
    return next(r for r in response["results"] if r["drug"]["query"] == drug)


def test_documented_interaction_via_atc_class_with_full_provenance(check: Check) -> None:
    r = result_for(check("St John's wort", ["warfarin"]), "warfarin")
    c = r["classification"]
    assert (c["interaction_class"], c["finding"]) == ("A", "documented_interaction")
    assert c["severity_wordings"] == ["is contraindicated"]
    assert "no machine learning or LLM" in c["method"]
    [statement] = r["decisive_statements"]
    assert statement["role"] == "decisive"
    assert statement["matched_via"] == "class" and statement["drug_class"]["code"] == "B01AA"
    assert statement["excerpt"].startswith("Concomitant use with coumarin-type anticoagulants")
    assert statement["evidence"]["external_id"] == "EMA/HMPC/7695/2021#4.5#WEU"
    prov = statement["provenance"][0]
    assert prov["source_code"] == "ema_hmpc" and prov["retrieved_url"] and prov["retrieved_at"]
    assert prov["excerpt"] == statement["excerpt"]


def test_partial_class_statement_is_potential_not_documented(check: Check) -> None:
    c = result_for(check("St John's wort", ["docetaxel"]), "docetaxel")["classification"]
    assert (c["interaction_class"], c["finding"]) == ("B", "potential_interaction")


def test_unclassified_label_mention_is_context_only(check: Check) -> None:
    r = result_for(check("St John's wort", ["isotretinoin"]), "isotretinoin")
    c = r["classification"]
    assert (c["interaction_class"], c["finding"]) == ("C", "mentioned_without_interaction_wording")
    assert "not a confirmed interaction" in c["explanation"]
    [statement] = r["decisive_statements"]
    assert statement["statement_type"] == "unclassified"
    assert "context only" in statement["statement_type_note"]


def test_uncertain_evidence(check: Check) -> None:
    c = result_for(check("St John's wort", ["digoxin"]), "digoxin")["classification"]
    assert (c["interaction_class"], c["finding"]) == ("C", "uncertain_evidence")


def test_superseded_statement_is_ignored_and_empty_result_is_not_safe(check: Check) -> None:
    r = result_for(check("St John's wort", ["metformin"]), "metformin")
    c = r["classification"]
    assert (c["interaction_class"], c["finding"]) == ("D", "no_evidence_found")
    assert r["decisive_statements"] == [] and r["context_statements"] == []
    assert "does not mean the combination is safe" in c["explanation"]
    assert any("not evidence that a combination is safe" in cav for cav in c["caveats"])
    assert "safe" not in {k.lower() for k in c}  # no "safe" field anywhere


def test_herb_level_none_reported(check: Check) -> None:
    r = result_for(check("Black cohosh", ["warfarin"]), "warfarin")
    c = r["classification"]
    assert (c["interaction_class"], c["finding"]) == ("D", "no_interaction_reported")
    assert (
        'EMA/HMPC/48745/2017 §4.5 (well established use, 2018-03-27): "None reported"'
        in c["reasons"][0]
    )
    assert "not for this drug specifically" in c["reasons"][0]


def test_unknown_drug_without_remote_lookup_is_insufficient(check: Check) -> None:
    r = result_for(check("St John's wort", ["notadrugxyz"]), "notadrugxyz")
    assert r["drug"]["status"] == "not_found"
    assert (r["classification"]["interaction_class"], r["classification"]["finding"]) == (
        "E",
        "insufficient_information",
    )


def test_unknown_herb_gives_insufficient_for_every_drug(check: Check) -> None:
    response = check("Unobtainium officinale", ["warfarin", "sertraline"])
    assert response["herb"]["status"] == "not_found"
    assert {r["classification"]["finding"] for r in response["results"]} == {
        "insufficient_information"
    }


def test_ambiguous_herb_name_returns_409_with_candidates(check: Check) -> None:
    error = check("ginseng", ["warfarin"], status=409)["error"]
    assert error["code"] == "ambiguous_entity"
    names = {c["pharmaceutical_name"] for c in error["details"]["candidates"]}
    assert names == {"Ginseng radix", "Eleutherococci radix"}


def test_synonym_resolves_to_accepted_herb_with_note(check: Check) -> None:
    response = check("Cimicifuga racemosa", ["warfarin"])
    herb = response["herb"]
    assert (
        herb["status"] == "resolved"
        and herb["herb"]["pharmaceutical_name"] == "Cimicifugae rhizoma"
    )
    assert herb["matched_name"]["name_type"] == "synonym"
    assert "accepted name is Actaea racemosa" in herb["note"]


def test_sources_searched_and_literature_are_reported(check: Check) -> None:
    r = result_for(check("St John's wort", ["warfarin"]), "warfarin")
    searched = {s["source_code"]: s for s in r["sources_searched"]}
    assert searched["ema_hmpc"]["used_for_classification"] is True
    assert "244 distinct generic names" in searched["openfda_label"]["description"]
    assert searched["pubmed"]["used_for_classification"] is False
    assert r["related_literature"]["used_for_classification"] is False
    assert "not quality" in r["related_literature"]["note"]


def test_multiple_drugs_and_duplicates(check: Check) -> None:
    response = check("St John's wort", ["warfarin", "sertraline", "warfarin"])
    assert [r["drug"]["query"] for r in response["results"]] == ["warfarin", "sertraline"]
    sertraline = result_for(response, "sertraline")["classification"]
    assert sertraline["finding"] == "documented_interaction"
    assert response["disclaimer"].startswith("HerbaGuard provides information")


@pytest.mark.parametrize(
    "body",
    [
        {"herb": "", "drugs": ["warfarin"]},
        {"herb": "St John's wort", "drugs": []},
        {"herb": "St John's wort", "drugs": [""]},
        {"herb": "St John's wort", "drugs": ["x"] * 21},
        {"herb": "x" * 201, "drugs": ["warfarin"]},
    ],
)
def test_validation_errors_use_the_envelope(api: TestClient, body: dict[str, Any]) -> None:
    response = api.post("/api/v1/interactions/check", json=body)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_herb_interaction_overview_groups_and_filters(api: TestClient) -> None:
    groups = api.get("/api/v1/plants/wfo-0000728093/interactions").json()
    targets = {g["target"] for g in groups}
    assert {"Vitamin K antagonists", "isotretinoin", "sertraline", "digoxin"} <= targets
    assert "metformin" not in targets  # superseded
    only_unclassified = api.get(
        "/api/v1/plants/wfo-0000728093/interactions", params={"statement_type": "unclassified"}
    ).json()
    assert {s["statement_type"] for g in only_unclassified for s in g["statements"]} == {
        "unclassified"
    }
    assert api.get("/api/v1/plants/wfo-0000000001/interactions").status_code == 404


def test_label_sentence_not_naming_drug_outside_interaction_section_is_not_confirmed(
    check: Check,
) -> None:
    r = result_for(check("St John's wort", ["lithium carbonate"]), "lithium carbonate")
    c = r["classification"]
    assert (c["interaction_class"], c["finding"]) == ("C", "label_subject_not_confirmed")
    [statement] = r["decisive_statements"]
    assert statement["subject_check"] == "not_verified"
    assert "context only" in statement["subject_check_note"]


def test_label_sentence_in_interaction_section_stays_documented(check: Check) -> None:
    r = result_for(check("St John's wort", ["pexidartinib"]), "pexidartinib")
    assert r["classification"]["finding"] == "documented_interaction"
    assert r["decisive_statements"][0]["subject_check"] == "interaction_section"


def test_label_sentence_naming_drug_is_confirmed(check: Check) -> None:
    r = result_for(check("St John's wort", ["sertraline"]), "sertraline")
    assert r["decisive_statements"][0]["subject_check"] == "named_in_sentence"
