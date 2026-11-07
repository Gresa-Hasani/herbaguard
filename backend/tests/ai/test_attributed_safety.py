"""Attributed-safety exception to the critical ``safety_claim`` rule (approved 2026-11-07).

Source sentences are the real NCCIH fact-sheet wording stored in HerbaGuard (2026-11-06). The default
is rejection; only source-attributed reporting that keeps every material qualifier is allowed.
"""

from __future__ import annotations

import pytest

from herbaguard.ai.context import ContextItem, EvidenceContext
from herbaguard.ai.validation import Paragraph, attributed_safety_issue, validate

VALERIAN = "Research suggests that valerian is generally safe for short-term use by most adults."
LICORICE = "Licorice root is generally considered safe as a food ingredient."
ECHINACEA = "It's likely safe for most adults to consume products with extracts of E. purpurea."
COHOSH = ("It's uncertain whether black cohosh is safe for women who have had hormone-sensitive conditions "
          "such as breast or uterine cancer.")  # fmt: skip


def context(source: str, pair: str | None = None) -> EvidenceContext:
    items = [ContextItem("S1", "excerpt", "direct_evidence", source, source_code="nccih")]
    if pair:
        items.insert(0, ContextItem("C1", "classification", "deterministic_classification",
                                    f"Pair: {pair}\nClass D — No interaction evidence found"))  # fmt: skip
    return EvidenceContext(items)


def check(answer: str, source: str, pair: str | None = None):  # type: ignore[no-untyped-def]
    result = validate([Paragraph(answer, ("S1",))], [], False, context(source, pair),
                      expected_classes={"D"} if pair else set())  # fmt: skip
    return {i.rule: i for i in result.issues}


ALLOWED = [
    ("NCCIH notes that research suggests valerian is generally safe for short-term use by most adults.", VALERIAN),
    ("According to NCCIH, licorice root is generally considered safe as a food ingredient.", LICORICE),
    ("The NCCIH fact sheet states that it is likely safe for most adults to consume extracts of E. purpurea.", ECHINACEA),
]  # fmt: skip


@pytest.mark.parametrize(("answer", "source"), ALLOWED)
def test_attributed_statement_with_all_qualifiers_is_allowed(answer: str, source: str) -> None:
    issues = check(answer, source)
    assert "safety_claim" not in issues and "attributed_safety_statement" in issues
    assert (
        issues["attributed_safety_statement"].severity == "warning"
    )  # recorded for audit, not blocking


@pytest.mark.parametrize(
    ("answer", "source", "reason"),
    [
        # not attributed: an independent HerbaGuard assurance
        (
            "Valerian is generally safe for short-term use by most adults.",
            VALERIAN,
            "not attributed",
        ),
        # qualifier omission: duration and population dropped
        (
            "NCCIH notes that research suggests valerian is generally safe.",
            VALERIAN,
            "qualifiers missing",
        ),
        # uncertainty dropped ("research suggests")
        (
            "NCCIH states that valerian is generally safe for short-term use by most adults.",
            VALERIAN,
            "qualifiers missing",
        ),
        # use/route dropped ("as a food ingredient")
        (
            "According to NCCIH, licorice root is generally considered safe.",
            LICORICE,
            "qualifiers missing",
        ),
        # upgraded certainty: "likely safe" reported as "safe"
        (
            "The NCCIH fact sheet states that echinacea is safe for most adults.",
            ECHINACEA,
            "same certainty",
        ),
        ("NCCIH states that echinacea is completely safe for most adults.", ECHINACEA, "stronger"),
        # incorrect attribution: the cited source does not say it
        (
            "According to NCCIH, ginkgo is generally safe for short-term use by most adults.",
            LICORICE,
            "qualifiers missing",
        ),
        # incorrect attribution with every qualifier kept: the herb is swapped
        (
            "According to NCCIH, ginkgo is generally considered safe as a food ingredient.",
            LICORICE,
            "the cited source is not about this subject",
        ),
        # certainty differs from the source: "generally considered" vs a bare "safe"
        (
            "According to NCCIH, licorice root is safe as a food ingredient.",
            LICORICE,
            "same certainty",
        ),
        # combination with a medicine
        (
            "NCCIH notes that licorice root is generally considered safe as a food ingredient, so it can be "
            "taken with digoxin.",
            LICORICE,
            "advice",
        ),
        (
            "According to NCCIH, licorice root is generally considered safe as a food ingredient together "
            "with medicines.",
            LICORICE,
            "combination",
        ),
        # particular patient / advice
        (
            "According to NCCIH, valerian is generally safe for you for short-term use by most adults, research "
            "suggests.",
            VALERIAN,
            "addressed to a person",
        ),
        # absence of risk and 'safe to take'
        ("NCCIH states there is no risk in using valerian.", VALERIAN, "absence-of-risk"),
        (
            "According to NCCIH, valerian is safe to take for most adults.",
            VALERIAN,
            "absence-of-risk",
        ),
    ],
)
def test_everything_else_stays_critical(answer: str, source: str, reason: str) -> None:
    issues = check(answer, source)
    assert issues["safety_claim"].severity == "critical"
    assert reason in issues["safety_claim"].message


def test_combination_with_the_asked_drug_is_rejected() -> None:
    answer = "According to NCCIH, licorice root is generally considered safe as a food ingredient and digoxin."
    issues = check(answer, LICORICE, pair="Licorice root + digoxin")
    assert "combination" in issues["safety_claim"].message


def test_negated_safety_wording_is_unchanged() -> None:
    issues = check(
        "It's uncertain whether black cohosh is safe for women after breast cancer.", COHOSH
    )
    assert "safety_claim" not in issues and "attributed_safety_statement" not in issues


def test_hedged_unattributed_wording_is_now_caught() -> None:
    """'likely/possibly safe' was not matched before this change; unattributed it is rejected."""
    assert "safety_claim" in check("Echinacea is likely safe for most adults.", ECHINACEA)


def test_rejected_combination_absence_of_evidence_claim() -> None:
    issues = check("The combination is safe because no interaction was reported.", VALERIAN)
    assert issues["safety_claim"].severity == "critical"


def test_helper_rejects_when_no_source_is_cited() -> None:
    assert attributed_safety_issue("NCCIH states valerian is generally safe for short-term use by most adults.",
                                   [], set()) is not None  # fmt: skip
