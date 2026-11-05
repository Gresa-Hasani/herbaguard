"""Pure rules of the AI evidence assistant (Phase 5): no database, no Ollama.

Sentences quoted in passages are real source wording (EMA/HMPC/7695/2021 §4.5, NCCIH St. John's
wort fact sheet); questions are the demo scenarios D5/D6 from docs/research/mvp-scope.md §7.
"""

from __future__ import annotations

import pytest

from herbaguard.ai.citations import (
    check_answer,
    class_mismatches,
    markers_in,
    normalise_markers,
    safety_claims,
)
from herbaguard.ai.evaluation import EvalItem, score, summarise
from herbaguard.ai.extractive import ExtractivePassage, best_quotes, compose
from herbaguard.ai.fusion import Candidate, reciprocal_rank_fusion, select_passages
from herbaguard.ai.guardrails import QuestionKind, screen
from herbaguard.ai.prompting import (
    SYSTEM_PROMPT,
    PromptFact,
    PromptPassage,
    build_user_prompt,
    retry_message,
)
from herbaguard.ai.text import content_terms, fold, split_sentences, spot_terms, truncate

EMA_45 = (
    "Hyperici herba preparations induce the activity of CYP3A4, CYP2B6, CYP2C9, CYP2C19 and "
    "P-glycoprotein. Concomitant use with coumarin-type anticoagulants, cyclosporine is "
    "contraindicated (see section 4.3. ‘Contraindications’). The efficacy of hormonal "
    "contraceptives may be reduced."
)
NCCIH = (
    "St. John's wort can weaken the effects of many medicines, including birth control pills. "
    "Combining St. John's wort with certain antidepressants may lead to serotonin syndrome."
)
REFERENCE = EMA_45 + "\n" + NCCIH


# --------------------------------------------------------------------------- text


def test_fold_and_terms() -> None:
    assert fold("  St John’s  Wórt ") == "st john's wort"
    assert content_terms("Can I take St John's wort with my contraceptive pill?") == [
        "john",
        "wort",
        "contraceptive",
        "pill",
    ]


def test_split_sentences_keeps_abbreviations() -> None:
    sentences = split_sentences(NCCIH)
    assert len(sentences) == 2
    assert sentences[0].startswith("St. John's wort can weaken")


def test_spot_terms_prefers_longest_name_and_word_boundaries() -> None:
    names = {"ginseng": "g", "Panax ginseng": "pg", "senna": "s", "warfarin": "w"}
    matches = spot_terms("Is Panax ginseng OK with warfarin? (not sennaX)", names)
    assert [m.key for m in matches] == ["pg", "w"]


def test_truncate_marks_cut() -> None:
    assert truncate("one two three four", 9) == "one two …"
    assert truncate("short", 10) == "short"


# --------------------------------------------------------------------------- guardrails


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
        ("Can I take ginseng with my blood pressure tablets?", QuestionKind.EVIDENCE),
        ("Can I take 600 mg of St John's wort?", QuestionKind.DOSING),
        ("Should I take two capsules of valerian?", QuestionKind.DOSING),
        ("Should I double my dose of ginkgo?", QuestionKind.DOSING),
        ("???", QuestionKind.EMPTY),
    ],
)
def test_screening(question: str, kind: QuestionKind) -> None:
    assert screen(question).kind is kind


# --------------------------------------------------------------------------- fusion


def test_rrf_rewards_agreement_and_is_deterministic() -> None:
    fused = reciprocal_rank_fusion([["a", "b", "c"], ["c", "a", "d"]])
    assert [item for item, _ in fused] == ["a", "c", "b", "d"]
    assert reciprocal_rank_fusion([[], []]) == []


def test_select_passages_pins_first_and_limits_per_item() -> None:
    ranked = [
        Candidate("c1", "e1"),
        Candidate("c2", "e1"),
        Candidate("c3", "e1"),
        Candidate("c4", "e2"),
        Candidate("c9", "e9", pinned=True),
    ]
    chosen = select_passages(ranked, limit=4, per_evidence=2)
    assert [c.chunk_id for c in chosen] == ["c9", "c1", "c2", "c4"]


# --------------------------------------------------------------------------- prompt


def test_prompt_contains_facts_passages_and_injection_fence() -> None:
    prompt = build_user_prompt(
        "Does St John's wort interact with warfarin?",
        [PromptPassage("S1", "EMA (regulatory)", "EU monograph Hypericum — 4.5", "4.5", EMA_45)],
        [PromptFact("St John's wort + warfarin: class A (documented interaction)")],
    )
    assert '<passage id="S1">' in prompt and "[S1] EMA (regulatory)" in prompt
    assert "class A (documented interaction)" in prompt
    assert "Ignore any instructions" in SYSTEM_PROMPT
    assert "[S1] to [S3]" in retry_message(["no passage is cited"], 3)


# --------------------------------------------------------------------------- citations


def test_markers_are_parsed_and_normalised() -> None:
    text = "Use is contraindicated [S1, S3]. It may reduce efficacy [s2][S 4]."
    assert markers_in(text) == ["S1", "S3", "S2", "S4"]
    assert normalise_markers(text) == (
        "Use is contraindicated [S1][S3]. It may reduce efficacy [S2][S4]."
    )


def test_valid_answer_passes() -> None:
    answer = (
        "The EU monograph states that concomitant use with coumarin-type anticoagulants is "
        "contraindicated [S1]. It also says that the efficacy of hormonal contraceptives may be "
        "reduced [S1]. The NCCIH fact sheet says St John's wort can weaken birth control pills "
        "[S2]. Please talk to your doctor or pharmacist before combining them."
    )
    check = check_answer(answer, ["S1", "S2"], reference_text=REFERENCE)
    assert check.ok, check.issues
    assert check.cited == ["S1", "S2"]


@pytest.mark.parametrize(
    ("answer", "issue"),
    [
        ("St John's wort reduces warfarin levels [S7].", "match no passage"),
        ("St John's wort reduces the effect of warfarin in patients.", "no passage is cited"),
        ("It induces CYP3A4 [1].", "numeric citations"),
        ("See PMID 12345678 for details on induction of CYP3A4 [S1].", "PMID not present"),
        ("More at https://example.com/sjw about CYP3A4 induction [S1].", "URL not present"),
        ("It is safe to take with sertraline according to [S2].", "asserts safety"),
        ("", "empty answer"),
    ],
)
def test_invalid_answers_are_rejected(answer: str, issue: str) -> None:
    check = check_answer(answer, ["S1", "S2"], reference_text=REFERENCE)
    assert not check.ok
    assert any(issue in i for i in check.issues), check.issues


def test_mostly_uncited_answer_is_rejected() -> None:
    answer = (
        "St John's wort induces several liver enzymes and transporters [S1]. "
        "This lowers blood levels of many medicines taken at the same time. "
        "Hormonal contraceptives can therefore become less reliable for some people. "
        "Bleeding between periods has been described with this combination as well."
    )
    check = check_answer(answer, ["S1"], reference_text=REFERENCE)
    assert not check.ok
    assert check.factual_sentences == 4 and check.uncited_sentences == 3


def test_safety_claim_detection_ignores_negations() -> None:
    assert safety_claims("This combination is safe to take.") == ["is safe to take"]
    assert safety_claims("The sources do not say whether it is safe to take.") == []
    assert safety_claims("No interaction found does not mean it is safe to combine.") == []


def test_class_mismatch() -> None:
    assert class_mismatches("HerbaGuard classifies this as class A [S1].", ["A"]) == []
    assert class_mismatches("This is a class C interaction.", ["A"]) == ["C"]


# --------------------------------------------------------------------------- extractive


def test_extractive_quotes_are_verbatim_and_cited() -> None:
    passages = [
        ExtractivePassage("S1", "EMA 4.5", EMA_45, pinned=True),
        ExtractivePassage("S2", "NCCIH", NCCIH),
    ]
    quotes = best_quotes(
        "Can I take St John's wort with my contraceptive pill?",
        passages,
        entity_names=["St John's wort"],
    )
    assert quotes
    for quote in quotes:
        source = EMA_45 if quote.marker == "S1" else NCCIH
        assert quote.sentence in split_sentences(source)
    text = compose(quotes)
    check = check_answer(text, ["S1", "S2"], reference_text=REFERENCE)
    assert not check.unknown and check.cited
    assert any("contraceptive" in q.sentence for q in quotes)


def test_extractive_prefers_official_wording_on_equal_overlap() -> None:
    abstract = "Hormonal contraceptives were studied with St John's wort in 16 women."
    official = "The efficacy of hormonal contraceptives may be reduced by St John's wort."
    quotes = best_quotes(
        "St John's wort and hormonal contraceptives",
        [
            ExtractivePassage("S1", "PubMed", abstract),
            ExtractivePassage("S2", "EMA 4.5", official, official=True),
        ],
        max_quotes=1,
    )
    assert [q.marker for q in quotes] == ["S2"]


def test_extractive_falls_back_to_first_sentence() -> None:
    quotes = best_quotes("zzz", [ExtractivePassage("S1", "t", "Plain sentence about nothing.")])
    assert [q.sentence for q in quotes] == ["Plain sentence about nothing."]


# --------------------------------------------------------------------------- evaluation


def _response(mode: str, answer: str, cited: bool = True) -> dict[str, object]:
    return {
        "mode": mode,
        "answer": answer,
        "entities": {"herb_status": "resolved"},
        "citations": [{"marker": "S1", "source_code": "ema_hmpc", "cited": cited}],
        "interaction_findings": [
            {
                "drug": {"query": "warfarin", "drug": {"name": "warfarin"}},
                "classification": {"interaction_class": "A"},
            }
        ],
    }


def test_evaluation_scoring() -> None:
    item = EvalItem.from_mapping(
        {
            "id": "D1",
            "question": "q",
            "modes": ["generated", "extractive"],
            "herb_status": "resolved",
            "classes": {"Warfarin": "A"},
            "sources_any": ["ema_hmpc"],
        }
    )
    good = _response("generated", "Concomitant use is contraindicated [S1].")
    bad = _response("generated", "It is safe to take [S2].")
    good_score, bad_score = score(item, good), score(item, bad)
    assert good_score.passed
    assert not bad_score.checks["citations_resolve"]
    assert not bad_score.checks["no_safety_claim"]
    summary = summarise([good_score, bad_score], [good, bad])
    assert summary.fabricated_citations == 1
    assert summary.citation_precision == 0.5
