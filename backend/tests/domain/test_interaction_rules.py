"""Classification rules (pure). Statements are built in-test; source wording in comments refers
to real Phase 2 records (EMA/HMPC/7695/2021, NCCIH cranberry, openFDA labels)."""

from __future__ import annotations

import itertools

import pytest

from herbaguard.domain.enums import EvidenceType, InteractionClass, StatementType
from herbaguard.domain.interactions import (
    ALWAYS_CAVEAT,
    NOT_SAFETY_CAVEAT,
    PARTIAL_CLASS_MARKER,
    Finding,
    MechanismPath,
    Statement,
    classify,
)

_ids = itertools.count()


def stmt(
    statement_type: StatementType,
    *,
    evidence: EvidenceType = EvidenceType.REGULATORY,
    via: str = "drug",
    code: str | None = None,
    conditions: str | None = None,
    severity: str | None = None,
    source: str = "ema_hmpc",
) -> Statement:
    return Statement(
        id=f"s{next(_ids)}",
        source_code=source,
        evidence_type=evidence,
        statement_type=statement_type,
        matched_via=via,
        drug_class_code=code,
        conditions=conditions,
        severity_wording=severity,
        use_category="well_established_use",
    )


def run(statements: list[Statement], **kwargs: object) -> object:
    params: dict[str, object] = {
        "herb_resolved": True,
        "drug_resolved": True,
        "herb_has_sources": True,
    }
    params.update(kwargs)
    return classify(statements=statements, **params)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- A


def test_documented_interaction_from_explicit_drug_statement() -> None:
    s = stmt(StatementType.INTERACTION, severity="is contraindicated")
    result = run([s])
    assert result.interaction_class is InteractionClass.DOCUMENTED
    assert result.finding is Finding.DOCUMENTED_INTERACTION
    assert result.decisive_statement_ids == [s.id]
    assert result.severity_wordings == ["is contraindicated"]  # relayed, never computed


def test_documented_interaction_via_whole_class() -> None:
    # EMA St John's wort: "Concomitant use with coumarin-type anticoagulants ... is contraindicated"
    s = stmt(StatementType.INTERACTION, via="class", code="B01AA")
    result = run([s])
    assert result.finding is Finding.DOCUMENTED_INTERACTION
    assert "ATC B01AA" in " ".join(result.reasons)


def test_precaution_only_is_documented_precaution_not_interaction() -> None:
    # EMA ginkgo: "...do not indicate that there is an interaction ..., but adequate monitoring is advised"
    s = stmt(StatementType.PRECAUTION, severity="adequate monitoring is advised")
    result = run([s])
    assert result.interaction_class is InteractionClass.DOCUMENTED
    assert result.finding is Finding.DOCUMENTED_PRECAUTION


def test_interaction_outranks_precaution_and_precaution_becomes_context() -> None:
    interaction = stmt(StatementType.INTERACTION)
    precaution = stmt(StatementType.PRECAUTION)
    result = run([precaution, interaction])
    assert result.finding is Finding.DOCUMENTED_INTERACTION
    assert result.decisive_statement_ids == [interaction.id]
    assert precaution.id in result.context_statement_ids


def test_government_summary_counts_as_authoritative() -> None:
    result = run(
        [stmt(StatementType.INTERACTION, evidence=EvidenceType.GOVERNMENT_SUMMARY, source="nccih")]
    )
    assert result.finding is Finding.DOCUMENTED_INTERACTION


@pytest.mark.parametrize(
    "evidence", [EvidenceType.CASE_REPORT, EvidenceType.IN_VITRO, EvidenceType.SPONTANEOUS_REPORT]
)
def test_non_authoritative_evidence_never_documents(evidence: EvidenceType) -> None:
    result = run([stmt(StatementType.INTERACTION, evidence=evidence, source="pubmed")])
    assert result.interaction_class is not InteractionClass.DOCUMENTED


# --------------------------------------------------------------------------- unclassified = context only


def test_unclassified_label_mention_is_never_a_confirmed_interaction() -> None:
    # isotretinoin label: "Pregnancies have been reported by users of combined hormonal contraceptives
    # who also used some form of St. John's Wort."
    s = stmt(StatementType.UNCLASSIFIED, source="openfda_label")
    result = run([s])
    assert result.interaction_class is InteractionClass.SUSPECTED
    assert result.finding is Finding.MENTIONED_WITHOUT_INTERACTION_WORDING
    assert "context only" in result.explanation


def test_unclassified_next_to_documented_stays_context() -> None:
    mention = stmt(StatementType.UNCLASSIFIED, source="openfda_label")
    documented = stmt(StatementType.INTERACTION)
    result = run([mention, documented])
    assert result.decisive_statement_ids == [documented.id]
    assert mention.id in result.context_statement_ids


# --------------------------------------------------------------------------- B


def test_partial_class_statement_is_only_potential() -> None:
    s = stmt(
        StatementType.INTERACTION,
        via="class",
        code="L01",
        conditions=f"{PARTIAL_CLASS_MARKER}: 'other cytostatic agents metabolised by CYP3A4'",
    )
    result = run([s])
    assert result.interaction_class is InteractionClass.POTENTIAL
    assert result.finding is Finding.POTENTIAL_INTERACTION


def test_partial_qualifier_on_drug_level_match_does_not_downgrade() -> None:
    s = stmt(StatementType.INTERACTION, via="drug", conditions=f"{PARTIAL_CLASS_MARKER}: 'x'")
    assert run([s]).finding is Finding.DOCUMENTED_INTERACTION


def test_mechanism_path_gives_potential() -> None:
    path = MechanismPath(
        target_symbol="CYP3A4", herb_effect="induces", drug_role="sensitive_substrate", source="FDA"
    )
    result = run([], mechanisms=[path])
    assert result.finding is Finding.POTENTIAL_INTERACTION
    assert "CYP3A4" in result.reasons[0]


# --------------------------------------------------------------------------- C


def test_uncertain_evidence() -> None:
    # NCCIH cranberry: "There is conflicting evidence about whether cranberry interacts with ... warfarin."
    result = run(
        [stmt(StatementType.UNCERTAIN, evidence=EvidenceType.GOVERNMENT_SUMMARY, source="nccih")]
    )
    assert result.interaction_class is InteractionClass.SUSPECTED
    assert result.finding is Finding.UNCERTAIN_EVIDENCE


def test_uncertain_outranks_unclassified_mention() -> None:
    result = run([stmt(StatementType.UNCLASSIFIED), stmt(StatementType.UNCERTAIN)])
    assert result.finding is Finding.UNCERTAIN_EVIDENCE


# --------------------------------------------------------------------------- D (never "safe")


def test_no_evidence_found_is_not_safe() -> None:
    result = run([])
    assert result.interaction_class is InteractionClass.NO_EVIDENCE_FOUND
    assert result.finding is Finding.NO_EVIDENCE_FOUND
    assert "does not mean the combination is safe" in result.explanation
    assert NOT_SAFETY_CAVEAT in result.caveats


def test_explicit_negative_statement() -> None:
    s = stmt(StatementType.NO_INTERACTION_REPORTED)
    result = run([s])
    assert result.finding is Finding.NO_INTERACTION_REPORTED
    assert "does not prove" in result.explanation


def test_herb_level_none_reported_section() -> None:
    where = 'EMA/HMPC/48745/2017 §4.5 (well-established use, 2018-03-27): "None reported"'
    result = run([], herb_level_none_reported=[where])
    assert result.finding is Finding.NO_INTERACTION_REPORTED
    assert where in result.reasons[0]
    assert "not for this drug specifically" in result.reasons[0]
    assert NOT_SAFETY_CAVEAT in result.caveats


def test_herb_level_none_reported_does_not_override_documented() -> None:
    result = run(
        [stmt(StatementType.INTERACTION, source="openfda_label")],
        herb_level_none_reported=["EMA §4.5"],
    )
    assert result.finding is Finding.DOCUMENTED_INTERACTION


# --------------------------------------------------------------------------- E


@pytest.mark.parametrize(
    ("herb", "drug", "word"),
    [(False, True, "herb"), (True, False, "drug"), (False, False, "herb and the drug")],
)
def test_unresolved_entities_are_insufficient(herb: bool, drug: bool, word: str) -> None:
    result = run([stmt(StatementType.INTERACTION)], herb_resolved=herb, drug_resolved=drug)
    assert result.interaction_class is InteractionClass.INSUFFICIENT_INFORMATION
    assert word in result.reasons[0]
    assert result.decisive_statement_ids == []


def test_no_sources_for_herb_is_insufficient_not_no_evidence() -> None:
    result = run([], herb_has_sources=False)
    assert result.finding is Finding.INSUFFICIENT_INFORMATION


def test_every_result_carries_the_medical_caveat() -> None:
    for statements in ([], [stmt(StatementType.INTERACTION)], [stmt(StatementType.UNCERTAIN)]):
        assert ALWAYS_CAVEAT in run(statements).caveats


def test_label_statement_with_unconfirmed_subject_is_context_only() -> None:
    # isotretinoin label (precautions): "...a possible interaction has been suggested with hormonal
    # contraceptives ..." — about St John's wort and contraceptives, not about isotretinoin.
    unconfirmed = Statement(
        id="u1", source_code="openfda_label", evidence_type=EvidenceType.REGULATORY,
        statement_type=StatementType.INTERACTION, matched_via="drug", drug_class_code=None,
        conditions=None, severity_wording=None, use_category="not_applicable", subject_verified=False,
    )  # fmt: skip
    result = run([unconfirmed])
    assert result.interaction_class is InteractionClass.SUSPECTED
    assert result.finding is Finding.LABEL_SUBJECT_NOT_CONFIRMED
    assert (
        run([unconfirmed, stmt(StatementType.UNCLASSIFIED)]).finding
        is Finding.LABEL_SUBJECT_NOT_CONFIRMED
    )
    assert (
        run([unconfirmed, stmt(StatementType.INTERACTION)]).finding
        is Finding.DOCUMENTED_INTERACTION
    )


def test_monograph_none_reported_is_shown_when_other_sources_differ() -> None:
    where = 'EMA/HMPC/48704/2014 §4.5 (traditional use, 2015-11-24): "None reported."'
    result = run(
        [stmt(StatementType.INTERACTION, source="openfda_label")], herb_level_none_reported=[where]
    )
    assert result.finding is Finding.DOCUMENTED_INTERACTION
    assert any(c.startswith("Sources differ:") and where in c for c in result.caveats)
