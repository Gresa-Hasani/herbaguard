"""Seeded test database for API tests.

SYNTHETIC SEED, modelled on real Phase 2 records: identifiers (WFO IDs, RxCUIs, ATC codes,
EMA document numbers) and quoted sentences are real; the selection of rows is reduced, and a few
rows exist only to exercise a rule path (marked "rule fixture" below):
- "Eleutherococci radix" (Siberian ginseng) is NOT a curated herb in the real data; it is added
  only to test ambiguous names.
- the uncertain-evidence statement for St John's wort + digoxin is a rule fixture.
- the superseded metformin statement is a rule fixture.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from herbaguard.core.config import Settings, get_settings
from herbaguard.core.db import get_session
from herbaguard.ingestion.loaders import ensure_sources
from herbaguard.main import create_app
from herbaguard.models import (
    Chunk,
    DataQualityIssue,
    Drug,
    DrugClass,
    DrugClassMembership,
    EvidenceItem,
    HerbalSubstance,
    HerbalSubstanceEvidence,
    Indication,
    IngestionRun,
    InteractionAssertion,
    InteractionAssertionEvidence,
    Provenance,
    SourceRecord,
    Taxon,
    TaxonName,
)

SJW_WFO = "wfo-0000728093"
BLACK_COHOSH_WFO = "wfo-0000519114"
HAWTHORN_WFOS = ("wfo-0001009785", "wfo-0000441236")
GINSENG_WFO = "wfo-0000263606"
ELEUTHERO_WFO = "wfo-0000948117"


class Seed:
    def __init__(self, session: Session) -> None:
        self.s = session
        ensure_sources(session)
        self.run = IngestionRun(
            id=uuid.uuid4(),
            source_code="ema_hmpc",
            status="succeeded",
            parameters={},
            statistics={},
        )
        session.add(self.run)
        session.flush()

    def record(
        self, source: str, native: str, url: str, version: str | None = None
    ) -> SourceRecord:
        rec = SourceRecord(
            id=uuid.uuid4(), source_code=source, ingestion_run_id=self.run.id, native_id=native, url=url,
            request_parameters={}, http_status=200, content_type="application/json",
            content_sha256=uuid.uuid4().hex + uuid.uuid4().hex, raw_path=None, payload=None,
            source_version=version, retrieved_at=datetime(2026, 11, 2, 12, 0, tzinfo=UTC),
        )  # fmt: skip
        self.s.add(rec)
        self.s.flush()
        return rec

    def prov(
        self,
        table: str,
        entity: object,
        record: SourceRecord,
        location: str,
        excerpt: str | None = None,
    ) -> None:
        self.s.add(
            Provenance(
                entity_table=table, entity_id=str(entity), source_record_id=record.id,
                extraction_method="test_seed", location=location, verbatim_excerpt=excerpt,
            )
        )  # fmt: skip

    def taxon(
        self, wfo: str, name: str, author: str, family: str, pharm: str, part: str, common: str
    ) -> HerbalSubstance:
        taxon = Taxon(
            id=uuid.uuid4(), wfo_id=wfo, scientific_name=name, authorship=author, family=family
        )
        self.s.add(taxon)
        self.s.flush()
        rec = self.record(
            "wfo_ethcstwin",
            f"names:{name}",
            f"https://wfo.ethcstwin.di.uoa.gr:65000/names/?full_name_no_authors={name}",
        )
        self.prov("taxon", taxon.id, rec, "wfo_id, scientific_name")
        for value, kind, lang in (
            (name, "accepted", "la"),
            (pharm, "pharmaceutical", "la"),
            (common, "common", "en"),
        ):
            self.s.add(TaxonName(taxon_id=taxon.id, name=value, normalized_name=value.lower().replace("’", "'"),
                                 name_type=kind, language=lang, source_code="herbaguard_curated"))  # fmt: skip
        substance = HerbalSubstance(id=uuid.uuid4(), taxon_id=taxon.id, plant_part=part, pharmaceutical_name=pharm,
                                    common_name_en=common, in_curated_scope=True)  # fmt: skip
        self.s.add(substance)
        self.s.flush()
        return substance

    def drug(self, rxcui: str, name: str, atc: str, atc_name: str) -> Drug:
        if self.s.get(DrugClass, atc) is None:
            self.s.add(
                DrugClass(code=atc, name=atc_name, level={1: 1, 3: 2, 4: 3, 5: 4, 7: 5}[len(atc)])
            )
        drug = Drug(id=uuid.uuid4(), rxcui=rxcui, name=name)
        self.s.add(drug)
        self.s.flush()
        self.s.add(DrugClassMembership(drug_id=drug.id, drug_class_code=atc, source_code="rxnav"))
        rec = self.record(
            "rxnav",
            f"properties:{rxcui}",
            f"https://rxnav.nlm.nih.gov/REST/rxcui/{rxcui}/properties.json",
        )
        self.prov("drug", drug.id, rec, f"rxcui={rxcui}")
        return drug

    def evidence(self, source: str, external: str, etype: str, title: str, text: str, substances: list[HerbalSubstance],
                 relation: str, metadata: dict[str, object] | None = None, doc_date: date | None = None) -> EvidenceItem:  # fmt: skip
        item = EvidenceItem(id=uuid.uuid4(), source_code=source, external_id=external, evidence_type=etype, title=title,
                            url=f"https://example.org/{external}", metadata_=metadata or {}, document_date=doc_date,
                            publication_year=doc_date.year if doc_date else None)  # fmt: skip
        self.s.add(item)
        self.s.flush()
        self.s.add(
            Chunk(evidence_item_id=item.id, ordinal=0, section=title[:100], text=text, metadata_={})
        )
        for substance in substances:
            self.s.add(
                HerbalSubstanceEvidence(
                    herbal_substance_id=substance.id, evidence_item_id=item.id, relation=relation
                )
            )
        rec = self.record(source, external, f"https://example.org/{external}", version=external)
        self.prov("evidence_item", item.id, rec, title)
        self.s.flush()
        return item

    def assertion(self, substance: HerbalSubstance, evidence: EvidenceItem, excerpt: str, *, drug: Drug | None = None,
                  cls: str | None = None, stype: str = "interaction", etype: str = "REG", section: str = "4.5",
                  use: str = "well_established_use", severity: str | None = None, conditions: str | None = None,
                  status: str = "active", subject: str | None = None) -> InteractionAssertion:  # fmt: skip
        a = InteractionAssertion(
            id=uuid.uuid4(), herbal_substance_id=substance.id, drug_id=drug.id if drug else None, drug_class_code=cls,
            object_label_verbatim=drug.name if drug else (cls or ""), subject_label_verbatim=subject,
            source_code=evidence.source_code, evidence_type=etype, source_section=section, use_category=use,
            severity_wording=severity, conditions=conditions, statement_type=stype, status=status,
        )  # fmt: skip
        self.s.add(a)
        self.s.flush()
        self.s.add(
            InteractionAssertionEvidence(
                interaction_assertion_id=a.id, evidence_item_id=evidence.id
            )
        )
        rec = self.record(evidence.source_code, f"assert:{a.id}", evidence.url or "")
        self.prov("interaction_assertion", a.id, rec, f"section {section}", excerpt)
        self.s.flush()
        return a


def build_seed(session: Session) -> dict[str, object]:
    seed = Seed(session)
    sjw = seed.taxon(
        SJW_WFO,
        "Hypericum perforatum",
        "L.",
        "Hypericaceae",
        "Hyperici herba",
        "herba",
        "St John's wort",
    )
    cohosh = seed.taxon(
        BLACK_COHOSH_WFO,
        "Actaea racemosa",
        "L.",
        "Ranunculaceae",
        "Cimicifugae rhizoma",
        "rhizoma",
        "Black cohosh",
    )
    session.add(TaxonName(taxon_id=cohosh.taxon_id, name="Cimicifuga racemosa", normalized_name="cimicifuga racemosa",
                          name_type="synonym", language="la", source_code="wcvp_ethcstwin"))  # fmt: skip
    haw1 = seed.taxon(
        HAWTHORN_WFOS[0],
        "Crataegus monogyna",
        "Jacq.",
        "Rosaceae",
        "Crataegi folium cum flore",
        "folium cum flore",
        "Hawthorn",
    )
    seed.taxon(
        HAWTHORN_WFOS[1],
        "Crataegus laevigata",
        "(Poir.) DC.",
        "Rosaceae",
        "Crataegi folium cum flore",
        "folium cum flore",
        "Hawthorn",
    )
    seed.taxon(
        GINSENG_WFO, "Panax ginseng", "C.A.Mey.", "Araliaceae", "Ginseng radix", "radix", "ginseng"
    )
    # Rule fixture: a second herb sharing the common name "ginseng" (not curated in real data).
    eleuthero = seed.taxon(ELEUTHERO_WFO, "Eleutherococcus senticosus", "(Rupr. & Maxim.) Maxim.", "Araliaceae",
                           "Eleutherococci radix", "radix", "Siberian ginseng")  # fmt: skip
    session.add(TaxonName(taxon_id=eleuthero.taxon_id, name="ginseng", normalized_name="ginseng", name_type="common",
                          language="en", source_code="gbif"))  # fmt: skip

    warfarin = seed.drug("11289", "warfarin", "B01AA", "Vitamin K antagonists")
    sertraline = seed.drug(
        "36437", "sertraline", "N06AB", "Selective serotonin reuptake inhibitors"
    )
    docetaxel = seed.drug("72962", "docetaxel", "L01CD", "Taxanes")
    session.add(DrugClass(code="L01", name="ANTINEOPLASTIC AGENTS", level=2))
    isotretinoin = seed.drug("6064", "isotretinoin", "D10BA", "Retinoids for treatment of acne")
    metformin = seed.drug("6809", "metformin", "A10BA", "Biguanides")
    digoxin = seed.drug("3407", "digoxin", "C01AA", "Digitalis glycosides")

    seed.evidence("ema_hmpc", "EMA/HMPC/7695/2021", "REG", "European Union herbal monograph on Hypericum perforatum L., herba",
                        "monograph", [sjw], "monograph", {"herb_key": "st_johns_wort", "ema_latin_name": "Hyperici herba",
                        "extraction": {"use_categories": ["traditional_use", "well_established_use"],
                                       "completeness": {"4.5": "complete"}, "crosscheck": []}}, date(2022, 11, 23))  # fmt: skip
    s45_text = (
        "Hyperici herba preparations induce the activity of CYP3A4, CYP2B6, CYP2C9, CYP2C19 and P-glycoprotein. "
        "Concomitant use with coumarin-type anticoagulants, cyclosporine is contraindicated (see section 4.3. ‘Contraindications’). "
        "Concomitant use with imatinib and other cytostatic agents metabolised by CYP3A4 is contraindicated."
    )
    s45 = seed.evidence("ema_hmpc", "EMA/HMPC/7695/2021#4.5#WEU", "REG", "EU monograph Hypericum — 4.5 Interactions (WEU)",
                        s45_text, [sjw], "monograph", {"herb_key": "st_johns_wort", "document": "EMA/HMPC/7695/2021",
                        "section": "4.5", "use_category": "well_established_use", "section_statement": None}, date(2022, 11, 23))  # fmt: skip
    seed.assertion(sjw, s45, "Concomitant use with coumarin-type anticoagulants, cyclosporine is contraindicated (see section 4.3. ‘Contraindications’).",
                   cls="B01AA", severity="is contraindicated")  # fmt: skip
    seed.assertion(sjw, s45, "Concomitant use with imatinib and other cytostatic agents metabolised by CYP3A4 is contraindicated.",
                   cls="L01", severity="is contraindicated",
                   conditions="Applies to part of the class only: 'other cytostatic agents metabolised by CYP3A4'")  # fmt: skip

    label_text = "Pregnancies have been reported by users of combined hormonal contraceptives who also used some form of St. John's Wort."
    label = seed.evidence("openfda_label", "set-iso#warnings", "REG", "FDA label: isotretinoin — warnings", label_text, [sjw], "label_mention",
                          {"set_id": "set-iso", "generic_name": "ISOTRETINOIN"})  # fmt: skip
    seed.assertion(
        sjw,
        label,
        label_text,
        drug=isotretinoin,
        stype="unclassified",
        section="warnings",
        use="not_applicable",
        subject="St. John's Wort",
    )

    sert_text = "Concomitant use of sertraline and other serotonergic drugs (including ... St. John's Wort) increases the risk of serotonin syndrome."
    sert = seed.evidence(
        "openfda_label",
        "set-sert#drug_interactions",
        "REG",
        "FDA label: sertraline",
        sert_text,
        [sjw],
        "label_mention",
    )
    seed.assertion(
        sjw,
        sert,
        sert_text,
        drug=sertraline,
        section="drug_interactions",
        use="not_applicable",
        subject="St. John's Wort",
    )

    lithium = seed.drug("6448", "lithium carbonate", "N05AN", "Lithium")
    pexidartinib = seed.drug("2183101", "pexidartinib", "L01EX", "Other protein kinase inhibitors")
    # Real label wording (lithium carbonate, warnings): the label drug is not named in the sentence.
    li_text = ("The risk is increased with concomitant use of other serotonergic drugs (including selective "
               "serotonin reuptake inhibitors, ... St. John's Wort).")  # fmt: skip
    li = seed.evidence("openfda_label", "set-li#warnings", "REG", "FDA label: lithium — warnings", li_text, [sjw], "label_mention",
                       {"generic_name": "LITHIUM CARBONATE"})  # fmt: skip
    seed.assertion(
        sjw,
        li,
        li_text,
        drug=lithium,
        section="warnings",
        use="not_applicable",
        subject="St. John's Wort",
    )
    # Real label wording (pexidartinib, drug_interactions): not named, but in the interaction section.
    px_text = "Management Avoid concomitant use of strong CYP3A inducers, including St John's wort."
    px = seed.evidence("openfda_label", "set-px#drug_interactions", "REG", "FDA label: TURALIO", px_text, [sjw], "label_mention",
                       {"generic_name": "PEXIDARTINIB", "brand_name": "TURALIO"})  # fmt: skip
    seed.assertion(
        sjw,
        px,
        px_text,
        drug=pexidartinib,
        section="drug_interactions",
        use="not_applicable",
        subject="St John's wort",
    )

    nccih_text = "There is conflicting evidence about whether St. John's wort interacts with digoxin."  # rule fixture
    sheet = seed.evidence("nccih", "st-johns-wort#safety", "GOV", "NCCIH: St. John's Wort — What Do We Know About Safety?",
                          nccih_text, [sjw], "fact_sheet", {"last_updated": "May 2025"})  # fmt: skip
    seed.assertion(
        sjw,
        sheet,
        nccih_text,
        drug=digoxin,
        stype="uncertain",
        etype="GOV",
        section="What Do We Know About Safety?",
        use="not_applicable",
    )
    seed.assertion(
        sjw, sheet, nccih_text, drug=metformin, status="superseded", etype="GOV"
    )  # rule fixture: must be ignored

    seed.evidence("pubmed", "40325522", "RCT", "A randomised trial of Hypericum and drug X", "abstract text", [sjw], "literature_interaction",
                  {"publication_types": ["Randomized Controlled Trial"]}, date(2025, 1, 1))  # fmt: skip

    cohosh_doc = seed.evidence("ema_hmpc", "EMA/HMPC/48745/2017", "REG", "EU monograph Cimicifuga racemosa", "monograph", [cohosh], "monograph",
                               {"herb_key": "black_cohosh", "ema_latin_name": "Cimicifugae rhizoma",
                                "extraction": {"use_categories": ["well_established_use"], "completeness": {"4.5": "complete"}, "crosscheck": []}},
                               date(2018, 3, 27))  # fmt: skip
    seed.evidence("ema_hmpc", "EMA/HMPC/48745/2017#4.5#WEU", "REG", "Black cohosh — 4.5 (WEU)", "None reported", [cohosh], "monograph",
                  {"herb_key": "black_cohosh", "document": "EMA/HMPC/48745/2017", "section": "4.5",
                   "use_category": "well_established_use", "section_statement": "none_reported"}, date(2018, 3, 27))  # fmt: skip
    session.add(Indication(herbal_substance_id=cohosh.id, evidence_item_id=cohosh_doc.id,
                           text="Herbal medicinal product for the relief of menopausal complaints.", use_category="well_established_use"))  # fmt: skip
    session.add(DataQualityIssue(ingestion_run_id=seed.run.id, rule="openfda_coverage", severity="info",
                                 message="st_johns_wort: 3000 labels fetched (cap 3000), 244 distinct generic names seen of 245.",
                                 context={"herb": "st_johns_wort"}))  # fmt: skip
    session.flush()
    return {
        "sjw": sjw,
        "cohosh": cohosh,
        "hawthorn": haw1,
        "warfarin": warfarin,
        "docetaxel": docetaxel,
    }


@pytest.fixture
def seeded(db_session: Session) -> dict[str, object]:
    return build_seed(db_session)


@pytest.fixture
def api(db_session: Session, seeded: dict[str, object], tmp_path: Path) -> TestClient:
    app = create_app(Settings(environment="test", log_level="WARNING"))  # type: ignore[arg-type]

    def session_override() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_session] = session_override
    # Remote lookups (if a test enables them) write raw snapshots to a temporary folder.
    app.dependency_overrides[get_settings] = lambda: Settings(
        environment="test", raw_data_dir=tmp_path / "raw"
    )  # type: ignore[arg-type]
    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture
def check(api: TestClient) -> Callable[..., dict[str, object]]:
    def _check(herb: str, drugs: list[str], status: int = 200) -> dict[str, object]:
        response = api.post(
            "/api/v1/interactions/check",
            json={"herb": herb, "drugs": drugs, "allow_remote_drug_lookup": False},
        )
        assert response.status_code == status, response.text
        result: dict[str, object] = response.json()
        return result

    return _check
