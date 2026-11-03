"""Phase 4 mechanism pipeline against PostgreSQL.

* FDA run: replays the CAPTURED excerpt of the real FDA page (tests/fixtures/captured) through the
  ``--fda-html-file`` path, with RxNorm normalisation replaced by a fixed name → drug table
  (RxNav itself is covered by test_pipelines_db.py).
* EMA run: a stored monograph section 4.5 whose text is the REAL St John's wort sentence; the
  section row, chunk and PDF record are SYNTHETIC stand-ins for what the Phase 2 ema step stores.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from herbaguard.core.config import Settings
from herbaguard.ingestion.context import run_ingestion
from herbaguard.ingestion.drugs import DrugResolver, Ingredient
from herbaguard.ingestion.http import HttpClient
from herbaguard.ingestion.loaders import ensure_sources
from herbaguard.ingestion.pipelines import mechanisms
from herbaguard.models import (
    Chunk,
    Constituent,
    DataQualityIssue,
    Drug,
    DrugTargetRoleLink,
    EvidenceItem,
    HerbalSubstance,
    HerbalSubstanceConstituent,
    Provenance,
    SourceRecord,
    Target,
    TargetModulation,
    Taxon,
)

pytestmark = pytest.mark.db

FIXTURE = (
    Path(__file__).parents[1] / "fixtures" / "captured" / "fda_cyp_transporter_table_excerpt.html"
)
SJW_SENTENCE = (
    "Hyperici herba preparations induce the activity of CYP3A4, CYP2B6, CYP2C9, CYP2C19 and "
    "P-glycoprotein."
)
DRUGS = {"midazolam": "6960", "warfarin": "11289", "digoxin": "3407", "ketoconazole": "6135"}


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(raw_data_dir=tmp_path / "raw")


@pytest.fixture
def http(settings: Settings) -> Iterator[HttpClient]:
    client = HttpClient(settings, retry_wait_max=0.01, rate_limit=False)
    yield client
    client.close()


@pytest.fixture
def herbs(db_session: Session) -> dict[str, HerbalSubstance]:
    ensure_sources(db_session)
    out = {}
    for key, wfo, name, pharm, part in (
        ("st_johns_wort", "wfo-0000728093", "Hypericum perforatum", "Hyperici herba", "herba"),
        ("turmeric", "wfo-0000365771", "Curcuma longa", "Curcumae longae rhizoma", "rhizoma"),
    ):
        taxon = Taxon(id=uuid.uuid4(), wfo_id=wfo, scientific_name=name)
        db_session.add(taxon)
        db_session.flush()
        out[key] = HerbalSubstance(id=uuid.uuid4(), taxon_id=taxon.id, plant_part=part,
                                   pharmaceutical_name=pharm, in_curated_scope=True)  # fmt: skip
        db_session.add(out[key])
    db_session.flush()
    return out


@pytest.fixture
def fake_rxnorm(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    drugs = {}
    for name, rxcui in DRUGS.items():
        drug = Drug(id=uuid.uuid4(), rxcui=rxcui, name=name)
        db_session.add(drug)
        drugs[name] = Ingredient(drug.id, rxcui, name)
    db_session.flush()

    def by_name(self: DrugResolver, name: str) -> Ingredient | None:
        return drugs.get(name.lower())

    monkeypatch.setattr(DrugResolver, "by_name", by_name)


def _run_fda(session: Session, settings: Settings, http: HttpClient, html: Path) -> None:
    with run_ingestion(session, "fda_cyp_table", settings, http=http) as ctx:
        mechanisms.run_fda(ctx, html)


def _role(session: Session, drug: str, symbol: str) -> DrugTargetRoleLink:
    return session.scalars(
        select(DrugTargetRoleLink)
        .join(Drug, Drug.id == DrugTargetRoleLink.drug_id)
        .join(Target, Target.id == DrugTargetRoleLink.target_id)
        .where(Drug.name == drug, Target.symbol == symbol)
    ).one()


def test_fda_table_pipeline(
    db_session: Session, settings: Settings, http: HttpClient, herbs: dict[str, HerbalSubstance],
    fake_rxnorm: None,
) -> None:  # fmt: skip
    _run_fda(db_session, settings, http, FIXTURE)

    assert db_session.scalar(select(func.count()).select_from(Target)) == 18
    cyp3a4 = db_session.scalars(select(Target).where(Target.symbol == "CYP3A4")).one()
    assert cyp3a4.uniprot_accession == "P08684"

    item = db_session.scalars(
        select(EvidenceItem).where(EvidenceItem.source_code == "fda_cyp_table")
    ).one()
    assert (item.evidence_type, item.document_date.isoformat()) == ("GOV", "2026-05-29")  # type: ignore[union-attr]
    record = db_session.scalars(
        select(SourceRecord).where(SourceRecord.source_code == "fda_cyp_table")
    ).one()
    assert record.request_parameters["method"] == "saved_from_browser"
    assert record.source_version == "2026-05-29"

    midazolam = _role(db_session, "midazolam", "CYP3A")
    assert (midazolam.role, midazolam.potency, midazolam.evidence_item_id) == (
        "sensitive_substrate",
        None,
        item.id,
    )
    prov = db_session.scalars(
        select(Provenance).where(Provenance.entity_id == str(midazolam.id))
    ).one()
    assert prov.verbatim_excerpt == "midazolam | CYP SENS SUB: 3A sensitive substrate"
    assert "column 'CYP SENS SUB'" in (prov.location or "")
    warfarin = _role(db_session, "warfarin", "CYP2C9")
    assert (warfarin.role, warfarin.conditions) == (
        "moderately_sensitive_substrate",
        "FDA footnotes: [19] S-warfarin",
    )
    assert (_role(db_session, "ketoconazole", "CYP3A").role, _role(db_session, "ketoconazole", "CYP3A").potency) == (
        "inhibitor", "strong",
    )  # fmt: skip
    assert (
        _role(db_session, "ketoconazole", "ABCB1").potency is None
    )  # transporter inhibitors are not graded

    # St John's wort row → herb effect (GOV, strong), with FDA footnote 18 as condition
    sjw = db_session.scalars(
        select(TargetModulation).where(
            TargetModulation.herbal_substance_id == herbs["st_johns_wort"].id
        )
    ).one()
    assert (sjw.effect, sjw.potency, sjw.evidence_type, sjw.source_code) == (
        "induces",
        "strong",
        "GOV",
        "fda_cyp_table",
    )
    assert "preparation dependent" in (sjw.conditions or "")

    # curcumin row → constituent effect, linked to turmeric
    curcumin = db_session.scalars(select(Constituent)).one()
    assert curcumin.inchikey == "VFLDPWHFBUODDF-FCXRPNKRSA-N"
    link = db_session.scalars(select(HerbalSubstanceConstituent)).one()
    assert link.herbal_substance_id == herbs["turmeric"].id
    effect = db_session.scalars(
        select(TargetModulation).where(TargetModulation.constituent_id == curcumin.id)
    ).one()
    assert effect.effect == "inhibits"

    rules = {i.rule for i in db_session.scalars(select(DataQualityIssue))}
    assert {
        "fda_row_out_of_scope",
        "fda_row_skipped",
        "fda_cell_unparsed_text",
        "fda_page_saved_copy",
    } <= rules
    assert "fda_cell_no_target" not in rules


def test_fda_pipeline_is_idempotent_and_removes_stale_edges(
    db_session: Session, settings: Settings, http: HttpClient, herbs: dict[str, HerbalSubstance],
    fake_rxnorm: None, tmp_path: Path,
) -> None:  # fmt: skip
    _run_fda(db_session, settings, http, FIXTURE)
    first = db_session.scalar(select(func.count()).select_from(DrugTargetRoleLink))
    _run_fda(db_session, settings, http, FIXTURE)
    assert db_session.scalar(select(func.count()).select_from(DrugTargetRoleLink)) == first

    # A later page version without the midazolam row: its role and provenance disappear.
    html = FIXTURE.read_text(encoding="utf-8")
    start = html.index("<tr><td>midazolam</td>")
    changed = tmp_path / "fda_changed.html"
    changed.write_text(html[:start] + html[html.index("</tr>", start) + 5 :], encoding="utf-8")
    role_id = str(_role(db_session, "midazolam", "CYP3A").id)
    _run_fda(db_session, settings, http, changed)
    assert db_session.scalar(select(func.count()).select_from(DrugTargetRoleLink)) == first - 1  # type: ignore[operator]
    assert (
        db_session.scalar(
            select(func.count()).select_from(Provenance).where(Provenance.entity_id == role_id)
        )
        == 0
    )


def _ema_section(session: Session, substance: HerbalSubstance, text: str) -> EvidenceItem:
    item = EvidenceItem(
        id=uuid.uuid4(), source_code="ema_hmpc", external_id="EMA/HMPC/7695/2021#4.5#well_established_use",
        evidence_type="REG", title="4.5 Interactions", metadata_={
            "herb_key": "st_johns_wort", "section": "4.5", "use_category": "well_established_use"},
    )  # fmt: skip
    session.add(item)
    session.flush()
    session.add(Chunk(evidence_item_id=item.id, ordinal=0, section="4.5", text=text, metadata_={}))
    pdf = SourceRecord(
        id=uuid.uuid4(), source_code="ema_hmpc", native_id="monograph.pdf",
        url="https://www.ema.europa.eu/en/documents/herbal-monograph/x_en.pdf", request_parameters={},
        http_status=200, content_type="application/pdf", content_sha256="0" * 64,
        retrieved_at=datetime(2026, 11, 2, tzinfo=UTC),
    )  # fmt: skip
    session.add(pdf)
    session.flush()
    session.add(Provenance(entity_table="evidence_item", entity_id=str(item.id), source_record_id=pdf.id,
                           extraction_method="ema_pdf_section_v1"))  # fmt: skip
    session.flush()
    return item


def test_ema_mechanism_extraction(
    db_session: Session, settings: Settings, http: HttpClient, herbs: dict[str, HerbalSubstance]
) -> None:
    text = (
        "Daily dose of hyperforin > 1 mg:\n\n"
        f"{SJW_SENTENCE} Concomitant use with imatinib and other cytostatic agents metabolised by "
        "CYP3A4 is contraindicated.\n\nMedicinal products that inhibit CYP2D6 may be affected."
    )
    item = _ema_section(db_session, herbs["st_johns_wort"], text)
    for _ in range(2):  # idempotent
        with run_ingestion(db_session, "ema_hmpc", settings, http=http) as ctx:
            mechanisms.run_ema(ctx, ["st_johns_wort"])

    rows = db_session.execute(
        select(Target.symbol, TargetModulation)
        .join(Target, Target.id == TargetModulation.target_id)
        .where(TargetModulation.source_code == "ema_hmpc")
    ).all()
    assert sorted(symbol for symbol, _ in rows) == [
        "ABCB1",
        "CYP2B6",
        "CYP2C19",
        "CYP2C9",
        "CYP3A4",
    ]
    for _, modulation in rows:
        assert (modulation.effect, modulation.evidence_type, modulation.evidence_item_id) == (
            "induces",
            "REG",
            item.id,
        )
        assert (
            modulation.conditions
            == "Use category: well-established use; Daily dose of hyperforin > 1 mg"
        )
        prov = db_session.scalars(
            select(Provenance).where(Provenance.entity_id == str(modulation.id))
        ).one()
        assert prov.verbatim_excerpt == SJW_SENTENCE
        assert prov.source_record.content_type == "application/pdf"
    not_used = [
        i
        for i in db_session.scalars(select(DataQualityIssue))
        if i.rule == "ema_mechanism_sentence_not_used"
    ]
    outcomes = {i.message.split(":")[0] for i in not_used}
    # "Medicinal products that inhibit CYP2D6 ..." (other_drugs) and, since the Phase 4 audit,
    # "... cytostatic agents metabolised by CYP3A4 ..." (enzyme named, no effect verb)
    assert outcomes == {"other_drugs", "no_effect_verb"}


# --------------------------------------------------------------------------- Phase 4 audit additions


def test_fda_prodrug_alias_stores_role_for_the_name_people_use(
    db_session: Session, settings: Settings, http: HttpClient, herbs: dict[str, HerbalSubstance],
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    """FDA lists "dabigatran etexilate"; users enter "dabigatran" (another RxNorm ingredient)."""
    names = {**DRUGS, "dabigatran etexilate": "1037042", "dabigatran": "1546356"}
    drugs = {}
    for name, rxcui in names.items():
        drug = Drug(id=uuid.uuid4(), rxcui=rxcui, name=name)
        db_session.add(drug)
        drugs[name] = Ingredient(drug.id, rxcui, name)
    db_session.flush()
    monkeypatch.setattr(DrugResolver, "by_name", lambda self, name: drugs.get(name.lower()))

    _run_fda(db_session, settings, http, FIXTURE)

    prodrug = _role(db_session, "dabigatran etexilate", "ABCB1")
    active = _role(db_session, "dabigatran", "ABCB1")
    assert (prodrug.role, active.role) == ("substrate", "substrate")
    assert prodrug.conditions is None
    assert active.conditions is not None
    assert active.conditions.startswith("FDA lists dabigatran etexilate; applied to dabigatran")
    sources = {
        p.source_record.source_code
        for p in db_session.scalars(
            select(Provenance).where(Provenance.entity_id == str(active.id))
        )
    }
    assert sources == {"fda_cyp_table", "herbaguard_curated"}


def test_ema_hedged_effect_keeps_its_wording(
    db_session: Session, settings: Settings, http: HttpClient, herbs: dict[str, HerbalSubstance]
) -> None:
    _ema_section(
        db_session,
        herbs["st_johns_wort"],
        "Hyperici herba preparations may inhibit CYP2D6. Hyperici herba preparations might "
        "affect the activity of CYP1A2.",
    )
    with run_ingestion(db_session, "ema_hmpc", settings, http=http) as ctx:
        mechanisms.run_ema(ctx, ["st_johns_wort"])
    rows = db_session.execute(
        select(Target.symbol, TargetModulation.effect, TargetModulation.hedge_wording)
        .join(Target, Target.id == TargetModulation.target_id)
        .where(TargetModulation.source_code == "ema_hmpc")
    ).all()
    assert {tuple(r) for r in rows} == {("CYP2D6", "inhibits", "may")}
    logged = [
        i.context.get("sentence")
        for i in db_session.scalars(select(DataQualityIssue))
        if i.rule == "ema_mechanism_sentence_not_used"
    ]
    assert logged == ["Hyperici herba preparations might affect the activity of CYP1A2."]
