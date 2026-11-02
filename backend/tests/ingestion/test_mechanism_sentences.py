"""Target recognition and EMA mechanism-sentence rules (pure, no database)."""

from __future__ import annotations

import pytest

from herbaguard.domain.enums import ModulationEffect
from herbaguard.ingestion.normalize.mechanisms import Outcome, extract_mechanisms, subject_patterns
from herbaguard.ingestion.normalize.targets import find_targets

SJW = subject_patterns(["Hyperici herba"], ["hypericum", "St John's wort"])

# Real sentence: EU herbal monograph on Hypericum perforatum L., herba (EMA/HMPC/7695/2021), 4.5.
SJW_45 = (
    "Hyperici herba preparations induce the activity of CYP3A4, CYP2B6, CYP2C9, CYP2C19 and "
    "P-glycoprotein."
)


def symbols(text: str, *, prefix: bool = True) -> list[str]:
    return [s for m in find_targets(text, cyp_prefix_required=prefix) for s in m.symbols]


def test_target_table() -> None:
    assert symbols(SJW_45) == ["CYP3A4", "CYP2B6", "CYP2C9", "CYP2C19", "ABCB1"]
    assert symbols("OATP1B transporters", prefix=False) == ["SLCO1B1", "SLCO1B3"]
    assert symbols("OCT2; MATE1; MATE2-K", prefix=False) == ["SLC22A2", "SLC47A1", "SLC47A2"]
    # FDA cells: bare isoforms, and a footnote number glued to a token when <sup> is lost
    assert symbols("1A220; 3A moderate inhibitor", prefix=False) == ["CYP1A2", "CYP3A"]
    # free text requires the CYP prefix: "3A" alone is not an enzyme in a sentence
    assert symbols("Table 3A shows results") == []


def test_real_sjw_sentence_gives_induction_of_five_targets() -> None:
    result = extract_mechanisms(SJW_45, SJW)
    assert result.outcome is Outcome.EXTRACTED
    (statement,) = result.statements
    assert statement.effect is ModulationEffect.INDUCES
    assert statement.targets == ("CYP3A4", "CYP2B6", "CYP2C9", "CYP2C19", "ABCB1")
    assert statement.target_labels[-1] == "P-glycoprotein"
    assert statement.sentence == SJW_45
    assert statement.study_context is None


@pytest.mark.parametrize(
    ("sentence", "outcome"),
    [
        # names an enzyme but states no effect of the herb (real EMA wording)
        ("Concomitant use with imatinib and other cytostatic agents metabolised by CYP3A4 is contraindicated.",
         Outcome.NO_MECHANISM),
        # "inhibitors" is a noun about other drugs
        ("Concomitant use with CYP3A4 inhibitors should be avoided.", Outcome.NO_MECHANISM),
        # relative clause about other medicines
        ("Medicinal products that inhibit CYP3A4 may increase plasma levels.", Outcome.OTHER_DRUGS),
        # negation
        ("Hyperici herba extract does not inhibit CYP2D6.", Outcome.NEGATED),
        # subject is not the herb
        ("In vitro, it inhibits CYP2C9.", Outcome.SUBJECT_UNCLEAR),
    ],
)  # fmt: skip
def test_sentences_that_never_produce_an_effect(sentence: str, outcome: Outcome) -> None:
    result = extract_mechanisms(sentence, SJW)
    assert result.outcome is outcome
    assert result.statements == []


def test_noun_form_and_two_effects_in_one_sentence() -> None:
    text = "Hypericum extract is a potent inducer of CYP3A4 and inhibits CYP2C19."
    result = extract_mechanisms(text, SJW)
    assert [(s.effect, s.targets) for s in result.statements] == [
        (ModulationEffect.INDUCES, ("CYP3A4",)),
        (ModulationEffect.INHIBITS, ("CYP2C19",)),
    ]


def test_in_vitro_findings_are_flagged() -> None:
    result = extract_mechanisms("In vitro, Hyperici herba extracts inhibited CYP2C9.", SJW)
    (statement,) = result.statements
    assert statement.study_context == "in_vitro"
