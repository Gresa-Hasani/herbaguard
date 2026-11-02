"""Mechanism layer end-to-end (API → service → rules → seeded database), Phase 4.

SYNTHETIC SEED on top of tests/api/conftest.py, modelled on real Phase 4 records:
- herb effects of St John's wort: the EMA monograph sentence (EMA/HMPC/7695/2021 §4.5, WEU) and the
  FDA table row "St. John's wort | CYP Strg IND: 3A strong inducer" (real wording);
- drug roles: real FDA table rows for midazolam, warfarin, digoxin, ketoconazole and rosuvastatin;
- curcumin → BCRP (FDA row "curcumin | TRNSP INH: BCRP inhibitor") linked to turmeric.
RxCUIs, WFO IDs and UniProt accessions are the real identifiers.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from herbaguard.models import (
    Constituent,
    Drug,
    DrugTargetRoleLink,
    EvidenceItem,
    HerbalSubstance,
    HerbalSubstanceConstituent,
    Target,
    TargetModulation,
)
from tests.api.conftest import SJW_WFO, Seed

pytestmark = pytest.mark.db

Check = Callable[..., dict[str, Any]]
TURMERIC_WFO = "wfo-0000365771"
SJW_SENTENCE = (
    "Hyperici herba preparations induce the activity of CYP3A4, CYP2B6, CYP2C9, CYP2C19 and "
    "P-glycoprotein."
)


def result_for(response: dict[str, Any], drug: str) -> dict[str, Any]:
    return next(r for r in response["results"] if r["drug"]["query"] == drug)


@pytest.fixture
def mech(db_session: Session, seeded: dict[str, object]) -> dict[str, object]:
    s = db_session
    seed = Seed(s)
    sjw = seeded["sjw"]
    assert isinstance(sjw, HerbalSubstance)
    targets: dict[str, Target] = {}
    for symbol, name, kind, accession in (
        ("CYP3A", "Cytochrome P450 3A (CYP3A4 and CYP3A5, as grouped by FDA)", "enzyme", None),
        ("CYP3A4", "Cytochrome P450 3A4", "enzyme", "P08684"),
        ("CYP2C9", "Cytochrome P450 2C9", "enzyme", "P11712"),
        ("ABCB1", "P-glycoprotein (P-gp, MDR1)", "transporter", "P08183"),
        ("ABCG2", "Breast cancer resistance protein (BCRP)", "transporter", "Q9UNQ0"),
    ):
        targets[symbol] = Target(id=uuid.uuid4(), symbol=symbol, name=name, target_type=kind,
                                 uniprot_accession=accession)  # fmt: skip
        s.add(targets[symbol])
    s.flush()
    for target in targets.values():
        seed.prov("target", target.id, seed.record("herbaguard_curated", "targets.yaml", "file://data/curated/targets.yaml"), target.symbol)  # fmt: skip

    s45 = s.scalars(
        select(EvidenceItem).where(EvidenceItem.external_id == "EMA/HMPC/7695/2021#4.5#WEU")
    ).one()
    fda = seed.evidence("fda_cyp_table", "fda-cyp-transporter-examples#table-1", "GOV",
                        "FDA: Examples of Drugs that Interact with CYP Enzymes and Transporter Systems — Table 1",
                        "[18] The effect of St. John's wort varies widely and is preparation dependent.", [], "monograph")  # fmt: skip
    fda_record = seed.record(
        "fda_cyp_table", "fda-page", "https://www.fda.gov/drugs/...", version="2026-05-29"
    )
    ema_record = seed.record(
        "ema_hmpc", "monograph.pdf", "https://www.ema.europa.eu/x.pdf", version="EMA/HMPC/7695/2021"
    )

    def effect(target: str, *, source: str, evidence: EvidenceItem, etype: str, potency: str | None,
               excerpt: str, substance: HerbalSubstance | None = None, constituent: Constituent | None = None) -> None:  # fmt: skip
        m = TargetModulation(
            id=uuid.uuid4(), herbal_substance_id=substance.id if substance else None,
            constituent_id=constituent.id if constituent else None, target_id=targets[target].id,
            effect="inhibits" if "inhibitor" in excerpt else "induces", evidence_type=etype,
            potency=potency, conditions="Use category: well-established use" if source == "ema_hmpc" else None,
            source_code=source, evidence_item_id=evidence.id,
        )  # fmt: skip
        s.add(m)
        s.flush()
        seed.prov(
            "target_modulation",
            m.id,
            ema_record if source == "ema_hmpc" else fda_record,
            "row",
            excerpt,
        )

    for symbol in ("CYP3A4", "CYP2C9", "ABCB1"):
        effect(
            symbol,
            source="ema_hmpc",
            evidence=s45,
            etype="REG",
            potency=None,
            excerpt=SJW_SENTENCE,
            substance=sjw,
        )
    effect("CYP3A", source="fda_cyp_table", evidence=fda, etype="GOV", potency="strong",
           excerpt="St. John's wort | CYP Strg IND: 3A strong inducer", substance=sjw)  # fmt: skip

    turmeric = seed.taxon(TURMERIC_WFO, "Curcuma longa", "L.", "Zingiberaceae", "Curcumae longae rhizoma",
                          "rhizoma", "Turmeric")  # fmt: skip
    curcumin = Constituent(
        id=uuid.uuid4(), inchikey="VFLDPWHFBUODDF-FCXRPNKRSA-N", name="curcumin", pubchem_cid=969516
    )
    s.add(curcumin)
    s.flush()
    s.add(HerbalSubstanceConstituent(herbal_substance_id=turmeric.id, constituent_id=curcumin.id,
                                     source_code="herbaguard_curated"))  # fmt: skip
    effect("ABCG2", source="fda_cyp_table", evidence=fda, etype="GOV", potency=None,
           excerpt="curcumin | TRNSP INH: BCRP inhibitor", constituent=curcumin)  # fmt: skip

    warfarin = seeded["warfarin"]
    assert isinstance(warfarin, Drug)
    digoxin = s.scalars(select(Drug).where(Drug.rxcui == "3407")).one()
    midazolam = seed.drug("6960", "midazolam", "N05CD", "Benzodiazepine derivatives")
    ketoconazole = seed.drug("6135", "ketoconazole", "J02AB", "Imidazole derivatives")
    rosuvastatin = seed.drug("301542", "rosuvastatin", "C10AA", "HMG CoA reductase inhibitors")
    for d, target, role, potency, conditions, excerpt in (
        (midazolam, "CYP3A", "sensitive_substrate", None, None, "midazolam | CYP SENS SUB: 3A sensitive substrate"),
        (warfarin, "CYP2C9", "moderately_sensitive_substrate", None, "FDA footnotes: [19] S-warfarin",
         "warfarin | CYP Mod SENS SUB: 2C9 moderate sensitive substrate"),
        (digoxin, "ABCB1", "substrate", None, None, "digoxin | TRNSP SUB: P-gp substrate"),
        (ketoconazole, "CYP3A", "inhibitor", "strong", None, "ketoconazole | CYP Strg INH: 3A strong inhibitor"),
        (rosuvastatin, "ABCG2", "substrate", None, None, "rosuvastatin | TRNSP SUB: BCRP; OATP1B1; OATP1B3 substrate"),
    ):  # fmt: skip
        r = DrugTargetRoleLink(id=uuid.uuid4(), drug_id=d.id, target_id=targets[target].id, role=role,
                               source_code="fda_cyp_table", potency=potency, conditions=conditions,
                               evidence_item_id=fda.id)  # fmt: skip
        s.add(r)
        s.flush()
        seed.prov("drug_target_role", r.id, fda_record, "Table 1", excerpt)
    s.flush()
    return {"turmeric": turmeric}


# --------------------------------------------------------------------------- interaction check


def test_mechanism_only_pair_is_potential_with_both_premises(mech: object, check: Check) -> None:
    r = result_for(check("St John's wort", ["midazolam"]), "midazolam")
    c = r["classification"]
    assert (c["interaction_class"], c["finding"]) == ("B", "potential_interaction")
    assert r["decisive_statements"] == []
    assert any(
        reason.startswith("Hyperici herba induces CYP3A4 [ema_hmpc]") for reason in c["reasons"]
    )
    assert any("Mechanism-based finding" in caveat for caveat in c["caveats"])
    qualifying = [p for p in r["mechanism_paths"] if p["qualifies_for_class_b"]]
    assert {p["herb_effect"]["source_code"] for p in qualifying} == {"ema_hmpc", "fda_cyp_table"}
    ema_path = next(p for p in qualifying if p["herb_effect"]["source_code"] == "ema_hmpc")
    assert ema_path["target_symbols"] == "CYP3A4 / CYP3A"
    assert ema_path["herb_effect"]["provenance"][0]["excerpt"] == SJW_SENTENCE
    assert ema_path["drug_role"]["role"] == "sensitive_substrate"
    assert ema_path["drug_role"]["provenance"][0]["source_code"] == "fda_cyp_table"
    fda_path = next(p for p in qualifying if p["herb_effect"]["source_code"] == "fda_cyp_table")
    assert fda_path["herb_effect"]["potency"] == "strong"
    assert fda_path["herb_effect"]["evidence_type"]["code"] == "GOV"


def test_documented_interaction_keeps_class_a_and_lists_mechanism(
    mech: object, check: Check
) -> None:
    r = result_for(check("St John's wort", ["warfarin"]), "warfarin")
    assert r["classification"]["interaction_class"] == "A"
    (path,) = r["mechanism_paths"]
    assert path["target_symbols"] == "CYP2C9"
    assert path["qualifies_for_class_b"] is True
    assert path["drug_role"]["conditions"] == "FDA footnotes: [19] S-warfarin"


def test_mechanism_path_ranks_above_uncertain_statement(mech: object, check: Check) -> None:
    # digoxin: NCCIH rule fixture says the evidence is conflicting (C), the P-gp path gives B.
    c = result_for(check("St John's wort", ["digoxin"]), "digoxin")["classification"]
    assert c["interaction_class"] == "B"


def test_drug_that_is_an_inhibitor_does_not_qualify(mech: object, check: Check) -> None:
    r = result_for(check("St John's wort", ["ketoconazole"]), "ketoconazole")
    assert r["classification"]["finding"] == "no_evidence_found"
    assert r["mechanism_paths"]
    assert not any(p["qualifies_for_class_b"] for p in r["mechanism_paths"])
    assert "not a substrate" in r["mechanism_paths"][0]["reasons_not_qualifying"][0]


def test_constituent_path_is_context_only(mech: object, check: Check) -> None:
    r = result_for(check("Turmeric", ["rosuvastatin"]), "rosuvastatin")
    assert r["classification"]["interaction_class"] == "E"  # no source covers turmeric in this seed
    (path,) = r["mechanism_paths"]
    assert path["herb_effect"]["subject_kind"] == "constituent"
    assert path["herb_effect"]["subject_label"] == "curcumin"
    assert path["qualifies_for_class_b"] is False


def test_fda_table_is_listed_as_searched(mech: object, check: Check) -> None:
    r = result_for(check("St John's wort", ["midazolam"]), "midazolam")
    searched = {s["source_code"]: s for s in r["sources_searched"]}
    assert searched["fda_cyp_table"]["used_for_classification"] is True
    assert "induces CYP3A4 [ema_hmpc]" in searched["fda_cyp_table"]["description"]


def test_no_mechanism_data_means_no_paths(check: Check) -> None:
    # Without the Phase 4 seed nothing changes for Phase 3 results.
    r = result_for(check("St John's wort", ["digoxin"]), "digoxin")
    assert r["mechanism_paths"] == []
    assert r["classification"]["interaction_class"] == "C"


# --------------------------------------------------------------------------- mechanism endpoints


def test_targets_list(mech: object, api: TestClient) -> None:
    targets = {t["symbol"]: t for t in api.get("/api/v1/targets").json()}
    assert targets["ABCB1"]["uniprot_accession"] == "P08183"
    assert targets["ABCB1"]["uniprot_url"].endswith("/P08183/entry")
    assert targets["CYP3A"]["uniprot_accession"] is None
    assert targets["CYP3A"]["drug_roles"] == 2 and targets["CYP3A"]["herb_effects"] == 1


def test_target_detail_with_role_filter(mech: object, api: TestClient) -> None:
    body = api.get("/api/v1/targets/cyp3a", params={"role": "sensitive_substrate"}).json()
    assert body["symbol"] == "CYP3A"
    assert [r["drug"]["name"] for r in body["drug_role_statements"]] == ["midazolam"]
    assert body["drug_roles_total"] == 1
    (effect,) = body["herb_effect_statements"]
    assert (effect["herb"], effect["effect"], effect["potency"]) == (
        "Hyperici herba",
        "induces",
        "strong",
    )
    assert effect["provenance"][0]["excerpt"].startswith("St. John's wort | CYP Strg IND")
    assert "examples" in body["note"]


def test_unknown_target_is_404(mech: object, api: TestClient) -> None:
    response = api.get("/api/v1/targets/CYP9Z9")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_herb_graph(mech: object, api: TestClient) -> None:
    body = api.get(f"/api/v1/plants/{SJW_WFO}/mechanisms").json()
    nodes = {n["id"]: n for n in body["nodes"]}
    assert {"herb:Hyperici herba", "target:CYP3A4", "target:CYP3A", "drug:6960"} <= set(nodes)
    kinds = {(e["source"], e["kind"], e["target"]) for e in body["edges"]}
    assert ("herb:Hyperici herba", "induces", "target:CYP3A4") in kinds
    assert ("drug:6960", "substrate_of", "target:CYP3A") in kinds
    # ketoconazole is an inhibitor, not a substrate: not drawn as a victim drug
    assert "drug:6135" not in nodes
    assert body["rules"].startswith("mechanism rules v1")


def test_herb_graph_with_constituent(mech: dict[str, object], api: TestClient) -> None:
    body = api.get(
        f"/api/v1/plants/{TURMERIC_WFO}/mechanisms", params={"include_drugs": False}
    ).json()
    kinds = {(e["source"], e["kind"], e["target"]) for e in body["edges"]}
    assert ("herb:Curcumae longae rhizoma", "contains", "constituent:curcumin") in kinds
    assert ("constituent:curcumin", "inhibits", "target:ABCG2") in kinds
    assert not any(n["kind"] == "drug" for n in body["nodes"])


def test_paths_endpoint(mech: object, api: TestClient) -> None:
    response = api.post(
        "/api/v1/mechanisms/paths", json={"herb": "St John's wort", "drug": "midazolam"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["qualifying_paths"] == 2
    assert body["drug"]["status"] == "resolved"
    assert "never used for classification" in body["note"]


def test_paths_endpoint_rejects_ambiguous_herb(mech: object, api: TestClient) -> None:
    response = api.post("/api/v1/mechanisms/paths", json={"herb": "ginseng", "drug": "midazolam"})
    assert response.status_code == 409
