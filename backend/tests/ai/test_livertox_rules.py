"""Deterministic LiverTox rules: likelihood scores are not classes, and LiverTox never shows safety."""

from __future__ import annotations

import pytest

from herbaguard.ai.context import LIVERTOX_QUALIFIERS, hepatotoxicity_item
from herbaguard.ai.service import _first_passage
from herbaguard.ai.validation import hepatotoxicity_issue

CHAPTER = "Likelihood score: E (unlikely cause of clinically apparent liver injury). Milk thistle has not been linked to clinically apparent liver injury."


@pytest.mark.parametrize("text", [
    "Milk thistle is LiverTox class E.",
    "LiverTox classifies milk thistle as E.",
    "Its likelihood score corresponds to class E.",
    "Valerian is class C in LiverTox.",
    "Valerian is class C according to LiverTox.",
])  # fmt: skip
def test_livertox_score_presented_as_a_class(text: str) -> None:
    issue = hepatotoxicity_issue(text, CHAPTER)
    assert issue is not None and issue[0] == "livertox_score_as_class"


@pytest.mark.parametrize("text", [
    "Milk thistle does not cause liver damage.",
    "There is no risk to the liver.",
    "Milk thistle is safe for the liver.",
    "Milk thistle is liver-safe.",
    "Garlic is not hepatotoxic.",
    "Ginger won't harm your liver.",
])  # fmt: skip
def test_liver_safety_overstatements(text: str) -> None:
    issue = hepatotoxicity_issue(text, CHAPTER)
    assert issue is not None and issue[0] == "hepatotoxicity_overstated"


@pytest.mark.parametrize("text", [
    "The LiverTox likelihood score is E (unlikely cause of clinically apparent liver injury).",
    "HerbaGuard gives class A for this pair; separately, LiverTox gives a likelihood score of E.",
    "Milk thistle has not been linked to clinically apparent liver injury.",
    "LiverTox reports cases of liver injury with green tea extract.",
])  # fmt: skip
def test_accurate_livertox_wording_is_accepted(text: str) -> None:
    assert hepatotoxicity_issue(text, CHAPTER) is None


def test_overstatement_quoted_verbatim_from_the_cited_text_is_accepted() -> None:
    cited = "In clinical trials the extract does not cause liver injury at usual doses."
    assert (
        hepatotoxicity_issue("In clinical trials the extract does not cause liver injury.", cited)
        is None
    )


def test_item_carries_the_livertox_label_and_qualifiers() -> None:
    item = hepatotoxicity_item(text="t", title="LiverTox: Milk thistle", location="loc", url="https://x", external_id="MilkThistle",
                               provenance=[], extra_qualifiers=["extra"], priority=22)  # fmt: skip
    assert (item.kind, item.role, item.source_code) == (
        "hepatotoxicity",
        "hepatotoxicity_evidence",
        "livertox",
    )
    assert item.qualifiers[: len(LIVERTOX_QUALIFIERS)] == list(LIVERTOX_QUALIFIERS) or all(
        q in item.qualifiers for q in LIVERTOX_QUALIFIERS
    )
    assert "extra" in item.qualifiers


def test_first_passage_keeps_whole_sentences() -> None:
    text = "One sentence here. " * 100
    passage, more = _first_passage(text, limit=60)
    assert more and passage.endswith(".") and len(passage) <= 60
    assert _first_passage("Short. Text.", limit=900) == ("Short. Text.", False)
    long_sentence = "x" * 2000 + "."
    assert _first_passage(long_sentence, limit=100) == (long_sentence, False)
