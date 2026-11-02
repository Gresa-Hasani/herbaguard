"""Mechanism-path rules (docs/api/mechanism-paths.md) and their effect on classification."""

from __future__ import annotations

from herbaguard.domain.enums import EvidenceType, InteractionClass, StatementType
from herbaguard.domain.interactions import Finding, MechanismPath, Statement, classify
from herbaguard.domain.mechanisms import (
    MECHANISM_CAVEAT,
    AssessedPath,
    DrugRole,
    HerbEffect,
    assess_paths,
    describe,
)


def herb(
    target: str = "CYP3A4",
    *,
    effect: str = "induces",
    potency: str | None = None,
    evidence: str = "REG",
    kind: str = "herbal_substance",
    label: str = "Hyperici herba",
    source: str = "ema_hmpc",
) -> HerbEffect:
    return HerbEffect(f"h-{target}-{effect}-{evidence}-{kind}", target, effect, potency, evidence,
                      source, kind, label, "Use category: well-established use")  # fmt: skip


def drug(
    target: str = "CYP3A", role: str = "sensitive_substrate", source: str = "fda_cyp_table"
) -> DrugRole:
    return DrugRole(f"d-{target}-{role}", target, role, None, source)


def only(paths: list[AssessedPath]) -> AssessedPath:
    assert len(paths) == 1
    return paths[0]


def test_cyp3a4_herb_effect_matches_fda_cyp3a_substrate() -> None:
    path = only(assess_paths([herb("CYP3A4")], [drug("CYP3A")]))
    assert path.qualifies
    assert path.target_symbols == "CYP3A4 / CYP3A"
    assert "Hyperici herba induces CYP3A4 [ema_hmpc]" in describe(path)
    assert "sensitive substrate of CYP3A [fda_cyp_table]" in describe(path)


def test_different_enzymes_do_not_match() -> None:
    assert assess_paths([herb("CYP2C9")], [drug("CYP2D6")]) == []
    assert assess_paths([herb("CYP2C9")], [drug("CYP2C19")]) == []


def test_transporter_substrate_qualifies() -> None:
    assert only(assess_paths([herb("ABCB1")], [drug("ABCB1", "substrate")])).qualifies


def test_moderately_sensitive_substrate_qualifies() -> None:
    path = only(assess_paths([herb("CYP2C9")], [drug("CYP2C9", "moderately_sensitive_substrate")]))
    assert path.qualifies


def test_drug_that_is_itself_an_inhibitor_is_context_only() -> None:
    path = only(assess_paths([herb("CYP3A4")], [drug("CYP3A", "inhibitor")]))
    assert not path.qualifies
    assert "not a substrate" in path.reasons_not_qualifying[0]


def test_constituent_effect_is_context_only() -> None:
    effect = herb("ABCG2", effect="inhibits", evidence="GOV", kind="constituent", label="curcumin",
                  source="fda_cyp_table")  # fmt: skip
    path = only(assess_paths([effect], [drug("ABCG2", "substrate")]))
    assert not path.qualifies
    assert "constituent curcumin" in path.reasons_not_qualifying[0]


def test_in_vitro_effect_is_context_only() -> None:
    path = only(assess_paths([herb(evidence="INVITRO")], [drug()]))
    assert not path.qualifies
    assert "INVITRO" in path.reasons_not_qualifying[0]


def test_weak_effect_is_context_only() -> None:
    path = only(assess_paths([herb("CYP2C9", effect="inhibits", potency="weak")], [drug("CYP2C9")]))
    assert not path.qualifies


def test_drug_role_from_unlisted_source_is_context_only() -> None:
    assert not only(assess_paths([herb()], [drug(source="somewhere_else")])).qualifies


def test_qualifying_paths_come_first() -> None:
    paths = assess_paths([herb("CYP3A4", evidence="INVITRO"), herb("CYP3A4")], [drug()])
    assert [p.qualifies for p in paths] == [True, False]


# --------------------------------------------------------------------------- with classify


def mechanism() -> MechanismPath:
    path = only(assess_paths([herb()], [drug()]))
    return MechanismPath("CYP3A4 / CYP3A", "induces", "sensitive_substrate", "ema_hmpc + fda_cyp_table",
                         description=describe(path))  # fmt: skip


def run(
    statements: list[Statement], mechanisms: list[MechanismPath], none: list[str] | None = None
):  # type: ignore[no-untyped-def]
    return classify(herb_resolved=True, drug_resolved=True, herb_has_sources=True,
                    statements=statements, mechanisms=mechanisms, herb_level_none_reported=none or [])  # fmt: skip


def documented() -> Statement:
    return Statement("s1", "ema_hmpc", EvidenceType.REGULATORY, StatementType.INTERACTION, "drug",
                     None, None, "is contraindicated", "well_established_use")  # fmt: skip


def test_mechanism_only_gives_b_with_caveat() -> None:
    result = run([], [mechanism()])
    assert result.interaction_class is InteractionClass.POTENTIAL
    assert result.finding is Finding.POTENTIAL_INTERACTION
    assert result.reasons[0].startswith("Hyperici herba induces CYP3A4")
    assert MECHANISM_CAVEAT in result.caveats


def test_documented_statement_still_wins_over_mechanism() -> None:
    result = run([documented()], [mechanism()])
    assert result.interaction_class is InteractionClass.DOCUMENTED


def test_mechanism_against_none_reported_shows_disagreement() -> None:
    result = run(
        [], [mechanism()], ['EMA/HMPC/X §4.5 (well established use, 2018-01-01): "None reported"']
    )
    assert result.interaction_class is InteractionClass.POTENTIAL
    assert any(c.startswith("Sources differ") for c in result.caveats)


def test_no_mechanism_and_no_statement_stays_no_evidence() -> None:
    assert run([], []).interaction_class is InteractionClass.NO_EVIDENCE_FOUND
