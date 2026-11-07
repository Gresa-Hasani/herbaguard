"""Regression tests for the two validator defects found in the 2026-11-07 generation evaluation.

1. HerbaGuard's own class D/E disclaimer was rejected as "A limitation claims safety".
2. "St John's wort may increase the risk of bleeding with rivaroxaban" passed validation because the
   cited label mentions bleeding elsewhere, although the label lists St John's wort among inducers
   that lower rivaroxaban exposure.
"""

from __future__ import annotations

import pytest

from herbaguard.ai.context import ContextItem, EvidenceContext
from herbaguard.ai.validation import (
    Paragraph,
    limitation_safety_claims,
    risk_issue,
    validate,
)

# --------------------------------------------------------------------------- 1. limitation disclaimers

DISCLAIMER = "The absence of reported interactions does not mean the combination is safe."


def limitation_rules(limitation: str) -> list[str]:
    context = EvidenceContext(
        [ContextItem("S1", "statement", "direct_evidence", "No interaction is reported.")]
    )
    result = validate([Paragraph("No interaction is reported.", ("S1",))], [limitation], False, context,
                      expected_classes=set())  # fmt: skip
    return [i.message for i in result.issues if i.rule == "safety_claim"]


@pytest.mark.parametrize(
    "limitation",
    [
        DISCLAIMER,  # exact wording from the 2026-11-07 evaluation
        "The absence of reported interactions doesn’t mean that the combination is safe!",
        "The absence of reported interactions does not mean the combination is safe",  # no final stop
        "No interactions were reported; this does not mean the combination is safe.",
        "Note: the absence of reported interactions does not mean the combination is safe. Consult the sources.",
        "No interaction has been reported, but this does not establish safety.",
        "There is no evidence that the combination is safe.",
        "It is unclear whether the combination is safe.",
        "Use with rivaroxaban has not been shown to be safe.",
        "This does not mean that ginkgo is safe to take with warfarin.",
    ],
)
def test_disclaimers_that_deny_a_safety_conclusion_are_accepted(limitation: str) -> None:
    assert limitation_rules(limitation) == []


@pytest.mark.parametrize(
    "limitation",
    [
        "The combination is safe.",  # unattributed reassurance
        "You can safely take both.",  # personal reassurance
        "There are no safety concerns.",  # absence of risk
        "There is no risk in combining them.",
        "No interactions have been reported, so the combination is safe.",  # negation in another clause
        "No interaction means the combination is safe.",  # negation of the noun, not of the conclusion
        "No evidence of an interaction means it is safe.",
        "Ginkgo does not interact with warfarin, and the combination is generally safe.",
        "The absence of reported interactions does not mean much. The combination is safe.",  # next sentence
    ],
)
def test_safety_assertions_in_limitations_stay_critical(limitation: str) -> None:
    messages = limitation_rules(limitation)
    assert messages and messages[0].startswith("A limitation claims safety")


def test_limitation_helper_reports_the_asserted_wording() -> None:
    assert limitation_safety_claims("You can safely take both.") == ["can safely"]
    assert limitation_safety_claims(DISCLAIMER) == []


def test_personal_reassurance_in_an_answer_paragraph_is_rejected() -> None:
    """'safely' wording was not matched before; in an answer paragraph it is advice, never allowed."""
    context = EvidenceContext([ContextItem("S1", "statement", "direct_evidence", "No interaction is reported.",
                                           source_code="nccih")])  # fmt: skip
    result = validate([Paragraph("According to NCCIH, you can safely take both.", ("S1",))], [], False,
                      context, expected_classes=set())  # fmt: skip
    assert any(i.rule == "safety_claim" and i.severity == "critical" for i in result.issues)


# --------------------------------------------------------------------------- 2. risk direction

# Real rivaroxaban label structure: the bleeding warning and the inhibitor sentence are about the drug;
# only the inducer sentence names St John's wort.
RIVAROXABAN_LABEL = (
    "XARELTO increases the risk of bleeding and can cause serious or fatal bleeding. "
    "Avoid concomitant use of XARELTO with known combined P-gp and strong CYP3A inducers "
    "(e.g., carbamazepine, phenytoin, rifampin, St. John's wort). "
    "Concomitant use of combined P-gp and strong CYP3A inhibitors increases rivaroxaban exposure and may "
    "increase bleeding risk."
)
NCCIH_GINKGO = "Ginkgo may increase the risk of bleeding in people who take anticoagulant drugs such as warfarin."


def run(pair: str, text: str, items: list[ContextItem]) -> list[str]:
    context = EvidenceContext([
        ContextItem("C1", "classification", "deterministic_classification", f"Pair: {pair}\nClass A — Documented"),
        *items,
    ])  # fmt: skip
    cites = tuple(i.label for i in items)
    result = validate([Paragraph(text, cites)], [], False, context, expected_classes={"A"})
    return [
        f"{i.rule}: {i.message}" for i in result.issues if i.rule == "effect_direction_unsupported"
    ]


LABEL = ContextItem(
    "S1", "statement", "direct_evidence", RIVAROXABAN_LABEL, source_code="openfda_label"
)
GINKGO_SHEET = ContextItem("S2", "statement", "direct_evidence", NCCIH_GINKGO, source_code="nccih")
SJW = "St John's wort + rivaroxaban"


def test_evaluation_case_bleeding_claim_from_an_unrelated_label_sentence_is_removed() -> None:
    """2026-11-07 v2-sjw-rivaroxaban-unknown-species: passed before because the label mentions bleeding."""
    issues = run(SJW, "The regulatory document states that St John's wort may increase the risk of bleeding "
                      "when used with rivaroxaban.", [LABEL])  # fmt: skip
    assert issues and "higher risk of bleeding" in issues[0]


@pytest.mark.parametrize(
    ("pair", "text", "items", "kept"),
    [
        # exposure: the herb's own sentence says inducer -> lower exposure; the inhibitor sentence is unrelated
        (
            SJW,
            "St John's wort may increase the plasma concentration of rivaroxaban.",
            [LABEL],
            False,
        ),
        (
            SJW,
            "St John's wort may decrease rivaroxaban exposure because it is listed among CYP3A inducers.",
            [LABEL],
            True,
        ),
        # a statement about the drug alone may use the drug's own label text
        (SJW, "Rivaroxaban increases the risk of bleeding.", [LABEL], True),
        # unspecified subject in a herb-drug answer is checked against statements about the herb
        (SJW, "It may increase the risk of bleeding.", [LABEL], False),
        # lower exposure does not imply lower risk, and a mechanism never supports a risk claim
        (
            SJW,
            "Because St John's wort lowers rivaroxaban exposure, it may reduce the risk of bleeding.",
            [LABEL],
            False,
        ),
        (
            SJW,
            "St John's wort lowers rivaroxaban exposure, which may increase the risk of stroke.",
            [LABEL],
            False,
        ),
        # pharmacological effect follows the cited exposure direction
        (
            SJW,
            "St John's wort may reduce the effectiveness of rivaroxaban as a CYP3A inducer.",
            [LABEL],
            True,
        ),
        (
            SJW,
            "St John's wort may enhance the anticoagulant effect of rivaroxaban.",
            [LABEL],
            False,
        ),
        # a separate, directly stated bleeding mechanism is preserved
        (
            "Ginkgo + rivaroxaban",
            "Ginkgo may increase the risk of bleeding when taken with rivaroxaban.",
            [GINKGO_SHEET, LABEL],
            True,
        ),
    ],
)
def test_direction_and_risk_claims_need_matching_statements_about_the_herb(
    pair: str, text: str, items: list[ContextItem], kept: bool
) -> None:
    assert (run(pair, text, items) == []) is kept


def test_a_direct_risk_statement_supports_a_risk_claim() -> None:
    record = ContextItem("S3", "statement", "direct_evidence", "St John's wort decreases rivaroxaban exposure "
                         "and may increase the risk of thrombotic events.", source_code="ema_hmpc")  # fmt: skip
    text = (
        "St John's wort may decrease rivaroxaban exposure and may increase the risk of thrombosis."
    )
    assert run(SJW, text, [record]) == []


@pytest.mark.parametrize(
    ("claim", "evidence", "ok"),
    [
        ("Ginkgo may increase the risk of bleeding.", NCCIH_GINKGO, True),
        (
            "Ginkgo may increase the risk of bleeding.",
            "Ginkgo did not increase the risk of bleeding.",
            False,
        ),
        ("Ginkgo may lower the risk of bleeding.", NCCIH_GINKGO, False),  # direction reversed
        (
            "Ginkgo may increase the risk of liver toxicity.",
            NCCIH_GINKGO,
            False,
        ),  # different outcome
        (
            "Bleeding risk may be increased with ginkgo.",
            NCCIH_GINKGO,
            True,
        ),  # direction after the noun
        ("The label mentions bleeding.", "", True),  # no risk-direction claim
    ],
)
def test_risk_helper(claim: str, evidence: str, ok: bool) -> None:
    assert (risk_issue(claim, evidence) is None) is ok
