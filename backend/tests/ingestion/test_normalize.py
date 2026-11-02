"""Name normalisation, sentence splitting, statement cues, evidence typing (no I/O).

Example strings are copied from real sources (EMA inventory/monographs retrieved 2026-11-02 —
EMA permits reproduction with source acknowledgement; NCCIH is a U.S. government work).
"""

from __future__ import annotations

import pytest

from herbaguard.domain.enums import EvidenceType, StatementType
from herbaguard.ingestion.normalize.evidence_type import classify_pubmed
from herbaguard.ingestion.normalize.names import (
    canonical_binomial,
    clean_name,
    format_wfo_id,
    normalize_for_lookup,
    split_ema_botanical_names,
)
from herbaguard.ingestion.normalize.statements import (
    classify_statement,
    is_condition_header,
    split_sentences,
)

# --------------------------------------------------------------------------- names


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Hypericum perforatumL.", "Hypericum perforatum L."),  # EMA inventory export defect
        ("Zingiber officinaleRoscoe", "Zingiber officinale Roscoe"),
        ("Panax ginseng\xa0C.A.Mey.", "Panax ginseng C.A.Mey."),  # non-breaking space
        ("  Allium   sativumL. ", "Allium sativum L."),
    ],
)
def test_clean_name(raw: str, expected: str) -> None:
    assert clean_name(raw) == expected


def test_split_ema_botanical_names_expands_abbreviated_genus() -> None:
    raw = "Crataegus monogyna Jacq. (Lindm.);C. laevigata(Poir.) DC.;C. pentagyna Waldst. et Kit. ex Willd.;C. azarolusL."
    names = split_ema_botanical_names(raw)
    assert [canonical_binomial(n) for n in names] == [
        "Crataegus monogyna",
        "Crataegus laevigata",
        "Crataegus pentagyna",
        "Crataegus azarolus",
    ]


def test_split_ema_botanical_names_drops_synonym_note() -> None:
    names = split_ema_botanical_names(
        "Serenoa repens (W.Bartram) Small (syn. Sabal serrulata (Michx.) Schult.f.)"
    )
    assert names == ["Serenoa repens (W.Bartram) Small"]


def test_format_wfo_id() -> None:
    assert format_wfo_id(728093) == "wfo-0000728093"
    assert format_wfo_id("wfo-0000728093") == "wfo-0000728093"
    with pytest.raises(ValueError, match="Not a WFO identifier"):
        format_wfo_id("Hypericum")


def test_normalize_for_lookup_folds_case_accents_and_quotes() -> None:
    assert normalize_for_lookup("St. John’s  Wort") == "st. john's wort"


# --------------------------------------------------------------------------- sentences


def test_sentence_split_keeps_abbreviations_and_initials() -> None:
    text = (
        "Caution is advised if combining G. biloba and dabigatran. "
        "Concomitant use (e.g. with warfarin) is not recommended. Next sentence."
    )
    assert split_sentences(text) == [
        "Caution is advised if combining G. biloba and dabigatran.",
        "Concomitant use (e.g. with warfarin) is not recommended.",
        "Next sentence.",
    ]


def test_sentence_split_respects_paragraphs() -> None:
    assert split_sentences("First para\n\nSecond para.") == ["First para", "Second para."]


# --------------------------------------------------------------------------- statement cues


@pytest.mark.parametrize(
    ("sentence", "statement", "severity"),
    [
        (
            "Concomitant use with saquinavir/ritonavir is contraindicated because of the risks of decrease in plasma concentration.",
            StatementType.INTERACTION,
            "is contraindicated",
        ),
        (
            "Available studies with warfarin do not indicate that there is an interaction between warfarin and G. biloba "
            "products, but adequate monitoring is advised when starting.",
            StatementType.PRECAUTION,
            "adequate monitoring is advised",
        ),
        ("None reported.", StatementType.NO_INTERACTION_REPORTED, None),
        (
            "There is conflicting evidence about whether cranberry interacts with the anticoagulant (blood thinner) warfarin.",
            StatementType.UNCERTAIN,
            None,
        ),
        (
            "If you take warfarin or any other medicine, talk with your health care provider before using cranberry or "
            "other herbal products; some herbs and medicines interact in harmful ways.",
            StatementType.PRECAUTION,
            None,
        ),
        (
            "Green tea extract can reduce blood levels of the cholesterol-lowering drug atorvastatin.",
            StatementType.INTERACTION,
            None,
        ),
        (
            "Women using hormonal contraceptives should take additional contraceptive measures.",
            StatementType.UNCLASSIFIED,
            None,
        ),
    ],
)
def test_classify_statement(sentence: str, statement: StatementType, severity: str | None) -> None:
    cues = classify_statement(sentence)
    assert cues.statement_type is statement
    assert cues.severity_wording == severity
    if severity:
        assert severity in sentence  # always relayed verbatim


def test_list_item_inherits_cues_from_lead_in() -> None:
    lead_in = "For example, St. John’s wort can weaken the effects of many medicines, including crucially important medicines such as:"
    assert (
        classify_statement("Birth control pills", lead_in).statement_type
        is StatementType.INTERACTION
    )


def test_condition_headers() -> None:
    assert is_condition_header("Daily dose of hyperforin > 1 mg:")
    assert is_condition_header("Indications 1), 3) and 4)")
    assert not is_condition_header("Concomitant use with warfarin is contraindicated.")


# --------------------------------------------------------------------------- evidence type


@pytest.mark.parametrize(
    ("types", "mesh", "expected"),
    [
        (
            ["Journal Article", "Meta-Analysis", "Systematic Review"],
            ["Humans"],
            EvidenceType.SYSTEMATIC_REVIEW,
        ),
        (
            ["Randomized Controlled Trial", "Journal Article"],
            ["Humans"],
            EvidenceType.RANDOMISED_CONTROLLED_TRIAL,
        ),
        (["Clinical Trial, Phase I"], [], EvidenceType.CLINICAL_STUDY),
        (["Comparative Study", "Journal Article"], ["Animals", "Rats"], EvidenceType.ANIMAL),
        (["Comparative Study", "Journal Article"], ["Humans"], EvidenceType.CLINICAL_STUDY),
        (["Case Reports"], ["Humans"], EvidenceType.CASE_REPORT),
        (["Review", "Journal Article"], ["Humans"], EvidenceType.NARRATIVE_REVIEW),
        (["Journal Article"], ["Microsomes, Liver", "Humans"], EvidenceType.IN_VITRO),
        (["Letter"], [], EvidenceType.OTHER),
    ],
)
def test_classify_pubmed(types: list[str], mesh: list[str], expected: EvidenceType) -> None:
    assert classify_pubmed(types, mesh) is expected
