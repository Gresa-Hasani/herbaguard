"""Regression tests for the Phase 5 audit corrections (2026-11-07): effect direction, strength-of-
evidence claims, audit trail of rejected text, and reserved context slots for experimental records.
Texts are taken from the 2026-11-06 live evaluation (docs/ai/results/) and real source wording."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from herbaguard.ai.context import ContextItem, EvidenceContext, assemble, observation_item
from herbaguard.ai.evaluation import Question, generation_checks
from herbaguard.ai.validation import Paragraph, direction_issue, strength_issue, validate
from herbaguard.api.schemas.ai import ValidationIssueOut

# Real FDA rivaroxaban label wording and the Phase 4 graph description
RIVAROXABAN_LABEL = ("Avoid concomitant use of XARELTO with known combined P-gp and strong CYP3A inducers "
                     "(e.g., carbamazepine, phenytoin, rifampin, St. John's wort).")  # fmt: skip
SJW_INDUCES_PGP = (
    "Hyperici herba induces ABCB1 [ema_hmpc]; this drug is a substrate of ABCB1 [fda_cyp_table]."
)
NCCIH_GINKGO = "Ginkgo may increase the risk of bleeding in people who take anticoagulant drugs such as warfarin."
EMA_SJW = "Concomitant use with coumarin-type anticoagulants, cyclosporine, everolimus is contraindicated."
DDID_IMATINIB = ("DDID record: Hypericum perforatum with Imatinib. Species: Homo Sapiens. Result: imatinib "
                 "clearance increased by 43% and AUC decreased by 30%. DDID label: Negative.")  # fmt: skip


def item(
    label: str, text: str, kind: str = "statement", role: str = "direct_evidence"
) -> ContextItem:
    return ContextItem(label=label, kind=kind, role=role, text=text)  # type: ignore[arg-type]


def _human_record(label: str, text: str) -> ContextItem:
    record = observation_item(text=text, study_context="human", effect_label="Negative", evidence_item_id=None,
                              external_id=None, url=None, title=None, location="row 2", provenance=[],
                              plant_part_note=None, priority=24)  # fmt: skip
    record.label = label
    return record


CONTEXT = EvidenceContext([
    item("C1", "Pair: St John's wort + rivaroxaban\nClass A — Documented", "classification", "deterministic_classification"),
    item("S1", RIVAROXABAN_LABEL),
    item("M1", SJW_INDUCES_PGP, "mechanism", "graph_context"),
    item("S2", NCCIH_GINKGO),
    item("S3", EMA_SJW),
    _human_record("X1", DDID_IMATINIB),  # real record: human study (Homo Sapiens)
])  # fmt: skip


def run(text: str, cites: list[str]):  # type: ignore[no-untyped-def]
    return validate([Paragraph(text, tuple(cites))], [], False, CONTEXT, expected_classes={"A"})


def rules(result) -> list[str]:  # type: ignore[no-untyped-def]
    return [i.rule for i in result.issues]


# --------------------------------------------------------------------------- effect direction


def test_audit_case_reversed_bleeding_claim_is_removed() -> None:
    """2026-11-06 v2-sjw-rivaroxaban: the label says avoid *inducers*; the model wrote bleeding risk."""
    r = run("Regulatory documents state that St John's wort may increase the risk of bleeding when used "
            "with rivaroxaban.", ["S1", "M1"])  # fmt: skip
    assert "effect_direction_unsupported" in rules(r) and r.paragraphs == []
    assert "bleeding" in r.issues[0].message


@pytest.mark.parametrize(
    ("text", "cites", "ok"),
    [
        (
            "St John's wort may increase rivaroxaban exposure.",
            ["S1", "M1"],
            False,
        ),  # contradicts induction
        (
            "St John's wort may decrease rivaroxaban exposure through P-gp induction.",
            ["S1", "M1"],
            True,
        ),
        (
            "Ginkgo may increase the risk of bleeding with warfarin.",
            ["S2"],
            True,
        ),  # bleeding stated by source
        (
            "St John's wort reduces the effectiveness of cyclosporine.",
            ["S3"],
            False,
        ),  # source states no direction
        ("St John's wort increased imatinib clearance and lowered its exposure.", ["X1"], True),
        (
            "St John's wort increased imatinib exposure.",
            ["X1"],
            False,
        ),  # clearance up = exposure down
        (
            "The monograph states that concomitant use is contraindicated.",
            ["S3"],
            True,
        ),  # no direction claimed
    ],
)
def test_direction_must_match_cited_evidence(text: str, cites: list[str], ok: bool) -> None:
    assert ("effect_direction_unsupported" not in rules(run(text, cites))) is ok


def test_direction_helpers_directly() -> None:
    assert (
        direction_issue("This may increase exposure.", "Grapefruit juice inhibits CYP3A.") is None
    )
    assert (
        direction_issue("This may reduce exposure.", "Grapefruit juice inhibits CYP3A.") is not None
    )
    # a sentence without an increase/decrease claim is never flagged
    assert direction_issue("The label lists St John's wort among inducers.", "") is None


# --------------------------------------------------------------------------- strength claims


@pytest.mark.parametrize(
    ("text", "cites", "ok"),
    [
        (
            "This interaction is well-documented in clinical evidence.",
            ["S3"],
            False,
        ),  # audit case v1 sjw-warfarin
        (
            "These findings suggest a clinically significant interaction.",
            ["X1"],
            False,
        ),  # audit case v2 imatinib
        (
            "There are no confirmed clinical interactions between them.",
            ["S3"],
            True,
        ),  # negated: uncertainty
        ("Whether this is clinically significant has not been established.", ["S3"], True),
        (
            "The interaction is clinically significant according to the label.",
            ["S4"],
            True,
        ),  # stated by source
    ],
)
def test_strength_claims_need_an_affirmative_source(text: str, cites: list[str], ok: bool) -> None:
    context = EvidenceContext(
        [
            *CONTEXT.items,
            item("S4", "The interaction is clinically significant and requires monitoring."),
        ]
    )
    r = validate([Paragraph(text, tuple(cites))], [], False, context, expected_classes={"A"})
    assert ("unsupported_strength_claim" not in rules(r)) is ok


def test_negated_source_wording_does_not_support_an_affirmative_claim() -> None:
    assert (
        strength_issue("The effect is established.", "Efficacy has not been established.")
        is not None
    )
    assert (
        strength_issue("The effect is established.", "The effect is established in two trials.")
        is None
    )


# --------------------------------------------------------------------------- audit trail


def test_issues_carry_the_offending_text() -> None:
    r = validate([Paragraph("It is safe to combine them.", ("S3",)), Paragraph("Unsupported.", ())], [],
                 False, CONTEXT, expected_classes={"A"})  # fmt: skip
    texts = {i.rule: i.text for i in r.issues}
    assert (
        texts["safety_claim"] == "It is safe to combine them."
        and texts["uncited_paragraph"] == "Unsupported."
    )


def test_audit_text_is_not_exposed_by_the_api_schema() -> None:
    issue = ValidationIssueOut(
        rule="safety_claim", severity="critical", message="m", paragraph=0, text="secret"
    )
    assert (
        issue.text == "secret"
        and "text" not in issue.model_dump()
        and "secret" not in issue.model_dump_json()
    )


def test_evaluation_report_keeps_rejected_text_and_messages() -> None:
    issues = [ValidationIssueOut(rule="safety_claim", severity="critical", message="Claims safety: 'is safe'.",
                                 paragraph=0, text="Green tea is safe.")]  # fmt: skip
    response = SimpleNamespace(
        status="rejected_by_validation", paragraphs=[], citations=[], validation=issues, classification=[],
        answer=None, insufficient_evidence=False,
        generation=SimpleNamespace(mode="model", provider="ollama", model="m", duration_ms=1, input_tokens=1,
                                   output_tokens=1, regenerations=1),
    )  # fmt: skip
    row = generation_checks(response, set(), Question(id="q", category="c", question="?"))
    assert row["rejected_text"] == "Green tea is safe."
    assert row["validation_issues"][0]["message"] == "Claims safety: 'is safe'."


# --------------------------------------------------------------------------- reserved slots for DDID records


def _observation(context: str, n: int) -> ContextItem:
    return observation_item(text=f"DDID record {n} ({context})", study_context=context, effect_label="Possible",
                            evidence_item_id=None, external_id=None, url=None, title=None, location=f"row {n}",
                            provenance=[], plant_part_note=None, priority=24 + n)  # fmt: skip


def test_two_slots_are_reserved_for_experimental_records() -> None:
    """2026-11-06 audit: records were crowded out by retrieved passages under the 8-item limit."""
    excerpts = [ContextItem(label="", kind="excerpt", role="direct_evidence", text=f"passage {n}", priority=21 + n)
                for n in range(10)]  # fmt: skip
    observations = [_observation("human", 0), _observation("animal", 1), _observation("unknown", 2)]
    context = assemble(excerpts + observations, max_tokens=10_000, max_items=8)
    kinds = [i.kind for i in context.items]
    assert kinds.count("observation") == 2 and kinds.count("excerpt") == 6 and len(kinds) == 8
    assert [i.text for i in context.items if i.kind == "observation"] == [
        "DDID record 0 (human)",
        "DDID record 1 (animal)",
    ]
    animal = next(i for i in context.items if "animal" in i.text)
    assert any(
        "NOT human clinical evidence" in q for q in animal.qualifiers
    )  # species limitation kept


def test_reservation_is_unused_without_records_and_respects_licensing() -> None:
    excerpts = [ContextItem(label="", kind="excerpt", role="direct_evidence", text=f"passage {n}", priority=21 + n)
                for n in range(10)]  # fmt: skip
    assert len(assemble(excerpts, max_tokens=10_000, max_items=8).items) == 8
    guarded = assemble([*excerpts, _observation("human", 0)], max_tokens=10_000, max_items=8,
                       redistributable={"ddid": False}, cloud_only_redistributable=True)  # fmt: skip
    assert all(i.kind != "observation" for i in guarded.items) and guarded.excluded_for_licence >= 1
