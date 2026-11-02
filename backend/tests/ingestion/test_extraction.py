"""Lexicon matching and candidate extraction on real source wording.

EMA text is quoted from EU herbal monographs (EMA/HMPC/7695/2021 Hypericum; EMA/HMPC/321097/2012
Ginkgo; EMA/HMPC/7685/2013 Allium) — reproduction authorised by EMA with source acknowledgement.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from herbaguard.domain.enums import StatementType
from herbaguard.ingestion.curation import load_herbs, load_lexicon
from herbaguard.ingestion.extraction import (
    ExtractionResult,
    extract_from_monograph_text,
    extract_from_sentence,
    none_reported,
)
from herbaguard.ingestion.normalize.lexicon import LexiconMatcher
from herbaguard.ingestion.normalize.statements import split_sentences
from herbaguard.ingestion.parsers.nccih_html import SAFETY_SECTION, parse_fact_sheet
from herbaguard.ingestion.pipelines.labels import mentioning_sentences

FIXTURES = Path(__file__).parents[1] / "fixtures" / "captured"


@pytest.fixture(scope="module")
def matcher() -> LexiconMatcher:
    return LexiconMatcher(load_lexicon())


def keys(result: ExtractionResult) -> list[str]:
    return [c.hit.key for c in result.candidates]


def test_curation_files_are_valid() -> None:
    herbs = load_herbs()
    assert len(herbs.herbs) == 16
    assert herbs.get("hawthorn").taxa[0] == "Crataegus monogyna"
    lexicon = load_lexicon()
    assert any(d.name == "warfarin" for d in lexicon.drugs)


def test_longest_match_wins(matcher: LexiconMatcher) -> None:
    hits = matcher.find("Concomitant use with coumarin-type anticoagulants is contraindicated.")
    assert [(h.kind, h.key) for h in hits] == [("class", "coumarin-type anticoagulants")]
    assert hits[0].atc == ("B01AA",)


def test_st_johns_wort_dose_condition_is_attached(matcher: LexiconMatcher) -> None:
    text = (
        "Indications 1), 3) and 4)\n\nDaily dose of hyperforin > 1 mg:\n\n"
        "Hyperici herba preparations induce the activity of CYP3A4, CYP2B6, CYP2C9, CYP2C19 and P-glycoprotein. "
        "Concomitant use with coumarin-type anticoagulants, cyclosporine is contraindicated (see section 4.3. ‘Contraindications’)."
    )
    result = extract_from_monograph_text(matcher, text)
    assert keys(result) == ["coumarin-type anticoagulants", "cyclosporine"]
    first = result.candidates[0]
    assert first.conditions == "Indications 1), 3) and 4); Daily dose of hyperforin > 1 mg"
    assert first.severity_wording == "is contraindicated"
    assert first.mechanism is not None and "induce the activity of CYP3A4" in first.mechanism


def test_partial_class_reference_is_recorded(matcher: LexiconMatcher) -> None:
    sentence = (
        "Concomitant use with imatinib and other cytostatic agents metabolised by CYP3A4, CYP2B6, CYP2C9, CYP2C19 "
        "or transported by P-glycoprotein is contraindicated."
    )
    result = ExtractionResult()
    extract_from_sentence(matcher, sentence, result=result)
    cytostatics = next(c for c in result.candidates if c.hit.kind == "class")
    assert cytostatics.conditions is not None
    assert cytostatics.conditions.startswith(
        "Applies to part of the class only: 'other cytostatic agents metabolised by CYP3A4"
    )


def test_descriptive_class_next_to_drug_is_not_generalised(matcher: LexiconMatcher) -> None:
    result = ExtractionResult()
    extract_from_sentence(matcher, "Warfarin, an anticoagulant (blood thinner)", result=result)
    assert keys(result) == ["warfarin"]
    assert result.descriptive_skipped == 2


def test_class_with_examples_is_kept(matcher: LexiconMatcher) -> None:
    result = ExtractionResult()
    extract_from_sentence(
        matcher,
        "If the medicinal product is taken concomitantly with anticoagulants (e.g. phenprocoumon and warfarin), "
        "their effect may be influenced.",
        result=result,
    )
    assert keys(result) == ["anticoagulants", "phenprocoumon", "warfarin"]


def test_same_drug_twice_in_sentence_yields_one_candidate(matcher: LexiconMatcher) -> None:
    result = ExtractionResult()
    extract_from_sentence(
        matcher,
        "Available studies with warfarin do not indicate that there is an interaction between warfarin and G. biloba "
        "products, but adequate monitoring is advised when starting.",
        result=result,
    )
    assert keys(result) == ["warfarin"]
    assert result.candidates[0].statement_type is StatementType.PRECAUTION


def test_unmapped_phrase_is_reported_not_mapped(matcher: LexiconMatcher) -> None:
    result = ExtractionResult()
    extract_from_sentence(
        matcher,
        "Caffeine containing preparations reduce actions of sedative substances and increase side effects caused by "
        "sympathomimetic drugs.",
        result=result,
    )
    assert keys(result) == ["hypnotics and sedatives"]
    assert [u[0] for u in result.unmapped] == ["sympathomimetic drugs"]


def test_section_43_relays_heading_as_severity(matcher: LexiconMatcher) -> None:
    result = extract_from_monograph_text(
        matcher, "Patients under saquinavir/ritonavir therapy (see also section 4.5 Interactions).",
        section_title="Contraindications", section_number="4.3",
    )  # fmt: skip
    assert {c.severity_wording for c in result.candidates} == {"Contraindications"}


def test_none_reported() -> None:
    assert none_reported("None reported")
    assert none_reported("None known.")
    assert not none_reported("None reported in clinical trials with warfarin.")


def test_nccih_list_items_use_lead_in(matcher: LexiconMatcher) -> None:
    """Captured NCCIH page: nested list items inherit their lead-in and stay verbatim."""
    sheet = parse_fact_sheet(
        (FIXTURES / "nccih_st-johns-wort_main.html").read_text(encoding="utf-8")
    )
    safety = sheet.section(SAFETY_SECTION)
    assert safety is not None
    result = ExtractionResult()
    for block in safety.blocks:
        for sentence in [block.text] if block.is_list_item else split_sentences(block.text):
            extract_from_sentence(
                matcher,
                sentence,
                context=block.lead_in if block.is_list_item else None,
                result=result,
            )
    by_key = {c.hit.key: c for c in result.candidates}
    assert by_key["hormonal contraceptives"].sentence == "Birth control pills"
    assert by_key["hormonal contraceptives"].statement_type is StatementType.INTERACTION
    assert "antiepileptics" in by_key and by_key["antiepileptics"].conditions.startswith(
        "Applies to part"
    )  # type: ignore[union-attr]
    assert "heart medications" in [u[0] for u in result.unmapped]
    for candidate in result.candidates:
        assert (
            candidate.sentence in safety.text.replace("\n\n", " ")
            or candidate.sentence in safety.text
        )


def test_label_sentences_exclude_other_plants() -> None:
    ginseng = load_herbs().get("ginseng")
    text = "Ginseng may decrease INR. Siberian ginseng increased digoxin levels. American ginseng affected warfarin."
    assert [s for s, _ in mentioning_sentences(text, ginseng)] == ["Ginseng may decrease INR."]


def test_label_sentence_from_captured_openfda_label() -> None:
    import json

    label = json.loads((FIXTURES / "openfda_label_sertraline.json").read_text())["results"][0]
    herb = load_herbs().get("st_johns_wort")
    found = mentioning_sentences(" ".join(label["drug_interactions"]), herb)
    assert found
    sentence, words = found[0]
    assert "John" in words and sentence in " ".join(label["drug_interactions"])


def test_label_sentence_chunks_keep_every_sentence_intact() -> None:
    """Regression: a label section naming several herbs must keep all sentences in its chunks."""
    from herbaguard.ingestion.pipelines.labels import sentence_chunks

    text = " ".join(f"Sentence number {i} mentions ginseng or St. John's wort." for i in range(80))
    chunks = sentence_chunks(text, max_chars=300)
    assert len(chunks) > 1
    assert all(len(c) <= 360 for c in chunks)
    assert " ".join(chunks) == text
