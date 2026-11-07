"""Rules ported from the earlier Evidence Assistant on ``main`` (tests/ai/test_assistant_rules.py).

That assistant was replaced by the Phase 5 AI layer when the branches were merged. Its screening
cases, its fabricated-reference check and its extra safety phrasings are kept here, adapted to the
Phase 5 validator. Passage wording is real source text (EMA/HMPC/7695/2021 §4.5; NCCIH St. John's
wort fact sheet), as in the original tests.
"""

from __future__ import annotations

import pytest

from herbaguard.ai.context import ContextItem, EvidenceContext
from herbaguard.ai.guardrails import QuestionKind, screen
from herbaguard.ai.validation import Paragraph, limitation_safety_claims, validate

EMA_45 = (
    "Hyperici herba preparations induce the activity of CYP3A4, CYP2B6, CYP2C9, CYP2C19 and "
    "P-glycoprotein. Concomitant use with coumarin-type anticoagulants, cyclosporine is "
    "contraindicated (see section 4.3. 'Contraindications'). The efficacy of hormonal "
    "contraceptives may be reduced."
)
NCCIH = (
    "St. John's wort can weaken the effects of many medicines, including birth control pills. "
    "Combining St. John's wort with certain antidepressants may lead to serotonin syndrome."
)

# --------------------------------------------------------------------------- screening (main's cases)


@pytest.mark.parametrize(
    ("question", "kind"),
    [
        ("Can I take St John's wort with my contraceptive pill?", QuestionKind.EVIDENCE),
        ("How much valerian should I take to sleep?", QuestionKind.DOSING),
        ("What is the right dose of St John's wort for me?", QuestionKind.DOSING),
        ("What does the monograph say about posology?", QuestionKind.EVIDENCE),
        ("My son swallowed a whole bottle of senna tablets", QuestionKind.EMERGENCY),
        ("I took echinacea and now my throat is swelling", QuestionKind.EMERGENCY),
        ("I think I overdosed on ginkgo", QuestionKind.EMERGENCY),
        ("Can ginkgo lower the seizure threshold?", QuestionKind.EVIDENCE),
        ("Does hawthorn cause chest pain in studies?", QuestionKind.EVIDENCE),
        ("St John's wort and emergency contraception", QuestionKind.EVIDENCE),
        # a medicine-combination question is not a dosing request (main's fix, 3861b91)
        ("Can I take ginseng with my blood pressure tablets?", QuestionKind.EVIDENCE),
        ("Can I take 600 mg of St John's wort?", QuestionKind.DOSING),
        ("Should I take two capsules of valerian?", QuestionKind.DOSING),
        ("Should I double my dose of ginkgo?", QuestionKind.DOSING),
        ("???", QuestionKind.EMPTY),
    ],
)
def test_screening(question: str, kind: QuestionKind) -> None:
    assert screen(question).kind is kind


# --------------------------------------------------------------------------- fabricated references


def _context() -> EvidenceContext:
    return EvidenceContext([
        ContextItem("S1", "statement", "direct_evidence", EMA_45, source_code="ema_hmpc",
                    url="https://www.ema.europa.eu/en/documents/herbal-monograph/hyperici-herba.pdf"),
        ContextItem("E1", "excerpt", "direct_evidence", NCCIH, source_code="pubmed",
                    external_id="PMID:15671185", title="Review, doi 10.1016/j.example.2005.01.001"),
    ])  # fmt: skip


def _rules(text: str, cites: tuple[str, ...] = ("S1",)) -> list[str]:
    result = validate([Paragraph(text, cites)], [], False, _context(), expected_classes=set())
    return [f"{i.rule}: {i.message}" for i in result.issues]


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("See PMID 12345678 for details on induction of CYP3A4.", "PMID 12345678"),
        ("More at https://example.com/sjw about CYP3A4 induction.", "URL https://example.com/sjw"),
        ("A review (doi 10.1000/fake.123) reports CYP3A4 induction.", "DOI 10.1000/fake.123"),
    ],
)
def test_references_not_in_the_context_remove_the_paragraph(text: str, kind: str) -> None:
    issues = _rules(text)
    assert any(i.startswith("unsupported_reference") and kind in i for i in issues), issues


def test_references_present_in_the_context_are_accepted() -> None:
    text = ("The monograph (https://www.ema.europa.eu/en/documents/herbal-monograph/hyperici-herba.pdf) "
            "states that the preparations induce CYP3A4; see also PMID 15671185.")  # fmt: skip
    assert not any(i.startswith("unsupported_reference") for i in _rules(text, ("S1", "E1")))


# --------------------------------------------------------------------------- safety phrasings


@pytest.mark.parametrize(
    "text",
    [
        "There is no interaction between St John's wort and sertraline.",
        "There is no danger in combining them.",
        "This combination is safe to take.",
    ],
)
def test_added_safety_phrasings_are_critical(text: str) -> None:
    assert any(i.startswith("safety_claim") for i in _rules(text))


@pytest.mark.parametrize(
    "text",
    [
        "The sources do not say whether it is safe to take.",
        "No interaction found does not mean it is safe to combine.",
        "The absence of a report does not mean there is no interaction.",
    ],
)
def test_negated_safety_wording_is_not_a_claim(text: str) -> None:
    assert not any(i.startswith("safety_claim") for i in _rules(text))
    assert limitation_safety_claims(text) == []
