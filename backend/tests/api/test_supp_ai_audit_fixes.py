"""Regression tests for the P2 SUPP.AI audit (docs/data/supp-ai-p2-audit-2026-11-07.md).

1. SUPP.AI mentions never displace other evidence (no reserved slot; ranked last).
2. Negation is pair-specific and clause-aware; warnings are not negations.
3. Animal, in-vitro and conflicting mentions cannot back patient or clinical claims.
4. SUPP.AI alone can establish neither a confirmed interaction nor "no interaction".

Sentences are synthetic paraphrases of the audited real patterns (SUPP.AI text is not redistributable).
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from herbaguard.ai import service
from herbaguard.ai.context import (
    RESERVED_SLOTS,
    ContextItem,
    EvidenceContext,
    assemble,
    mention_item,
)
from herbaguard.ai.mentions import pair_negation, study_type, tagged_span
from herbaguard.ai.providers.base import GenerationRequest
from herbaguard.ai.providers.mock import ScriptedProvider
from herbaguard.ai.providers.registry import GenerationChain
from herbaguard.ai.service import MAX_MENTIONS_PER_PAIR, MENTION_PRIORITY
from herbaguard.ai.validation import Paragraph, mention_issue, validate
from herbaguard.api.routes.ai import get_embedding_provider, get_generation_chain
from herbaguard.core.config import LLMProviderName, Settings
from herbaguard.ingestion.context import run_ingestion
from herbaguard.ingestion.loaders import ensure_sources
from herbaguard.ingestion.pipelines import ddid, supp_ai
from herbaguard.models import Target
from tests.api.test_supp_ai_context import extended_fixture

FIXTURES = Path(__file__).parents[1] / "fixtures"


# --------------------------------------------------------------------------- 1. context slots


def _statement(text: str, priority: int = 5, source: str = "openfda_label") -> ContextItem:
    return ContextItem(label="", kind="statement", role="direct_evidence", text=text, source_code=source,
                       priority=priority)  # fmt: skip


def _observation(n: int) -> ContextItem:
    return ContextItem(label="", kind="observation", role="experimental_evidence", text=f"DDID record {n}: human study.",
                       source_code="ddid", priority=24 + n)  # fmt: skip


def _mentions(n: int = MAX_MENTIONS_PER_PAIR, size: int = 600) -> list[ContextItem]:
    return [mention_item(text=f"SUPP.AI machine-extracted mention {i}: " + "x" * size, study_type="human",
                         negation_cue=None, external_id=None, url=None, title=None, location="l", provenance=[],
                         priority=MENTION_PRIORITY + i) for i in range(n)]  # fmt: skip


def _chosen(items: list[ContextItem], **kw: Any) -> list[str]:
    context = assemble(items, max_tokens=kw.get("max_tokens", 2600), max_items=8)
    return [f"{i.kind}:{i.text}" for i in context.items]


CLASSIFICATION = ContextItem(label="", kind="classification", role="deterministic_classification", text="Class A",
                             priority=0)  # fmt: skip


def test_supp_ai_has_no_reserved_slot_and_ranks_after_all_other_evidence() -> None:
    assert "mention" not in RESERVED_SLOTS
    assert RESERVED_SLOTS == {"observation": 2, "hepatotoxicity": 2}  # DDID and LiverTox unchanged
    assert MENTION_PRIORITY > 40  # after statements, mechanisms, excerpts, DDID, LiverTox and facts


def test_sjw_cyclosporine_keeps_the_fda_statement_and_ddid_records() -> None:
    """Audit case: the FDA label statement 'reports of a serious drug interaction' was displaced."""
    base = [CLASSIFICATION,
            *(_statement(f"Decisive label statement {i} for cyclosporine.") for i in range(4)),
            _statement("St. John's Wort: there have been reports of a serious drug interaction with cyclosporine."),
            _observation(0), _observation(1), _observation(2), _observation(3),
            ContextItem(label="", kind="excerpt", role="direct_evidence", text="Retrieved excerpt.", source_code="pubmed",
                        priority=21)]  # fmt: skip
    without = _chosen(list(base))
    with_ = _chosen([*base, *_mentions()])
    assert [x for x in with_ if not x.startswith("mention:")] == without
    assert any("serious drug interaction" in x for x in with_)
    assert sum(x.startswith("observation:") for x in with_) == 2  # the reserved DDID slots
    assert not any(x.startswith("mention:") for x in with_)  # no room left: mentions are left out


def test_sjw_warfarin_keeps_decisive_statements_and_the_mechanism_path() -> None:
    """Audit case: a decisive statement and the 'induces CYP2C9' mechanism path were displaced."""
    base = [CLASSIFICATION,
            *(_statement(f"Warfarin label statement {i}.") for i in range(5)),
            ContextItem(label="", kind="mechanism", role="graph_context", text="Hyperici herba induces CYP2C9.",
                        source_code="ema_hmpc", priority=10),
            _observation(0), _observation(1)]  # fmt: skip
    without = _chosen(list(base))
    with_ = _chosen([*base, *_mentions()])
    assert [x for x in with_ if not x.startswith("mention:")] == without
    assert (
        any("induces CYP2C9" in x for x in with_)
        and sum(x.startswith("statement:") for x in with_) == 5
    )


def test_mentions_only_fill_free_room_and_never_consume_needed_tokens() -> None:
    base = [CLASSIFICATION, _statement("Short decisive statement."), _observation(0)]
    with_ = _chosen([*base, *_mentions()])
    assert [x for x in with_ if not x.startswith("mention:")] == _chosen(list(base))
    assert (
        sum(x.startswith("mention:") for x in with_) == MAX_MENTIONS_PER_PAIR
    )  # free room is used
    # a tight token budget: the large mentions do not fit, nothing else is affected
    tight = [CLASSIFICATION, *(_statement("y" * 1500 + str(i)) for i in range(5))]
    assert [
        x for x in _chosen([*tight, *_mentions()], max_tokens=2600) if not x.startswith("mention:")
    ] == _chosen(list(tight), max_tokens=2600)


def answer(paragraphs: list[tuple[str, list[str]]]) -> str:
    return json.dumps({"paragraphs": [{"text": t, "citations": c} for t, c in paragraphs],
                       "limitations": [], "insufficient_evidence": False})  # fmt: skip


def _prompt(api: TestClient, question: str) -> str:
    seen: list[str] = []

    def reply(request: GenerationRequest) -> str:
        seen.append(request.messages[0].content)
        return answer([("HerbaGuard gives class A for this pair.", ["C1"])])

    chain = GenerationChain(
        (LLMProviderName.OLLAMA,), (ScriptedProvider(reply, name="ollama", model="qwen3:4b"),)
    )
    api.app.dependency_overrides[get_generation_chain] = lambda: chain  # type: ignore[attr-defined]
    api.app.dependency_overrides[get_embedding_provider] = lambda: None  # type: ignore[attr-defined]
    response = api.post(
        "/api/v1/ai/ask", json={"question": question, "allow_remote_drug_lookup": False}
    )
    assert response.status_code == 200, response.text
    return seen[0]


def _non_mention_blocks(prompt: str) -> list[str]:
    blocks = re.findall(r"<(?:evidence|fact|classification) id=\"[A-Z]\d+\".*?</(?:evidence|fact|classification)>",
                        prompt, re.S)  # fmt: skip
    # leave out SUPP.AI's own items (U# mentions and the SUPP.AI fact)
    return [b for b in blocks if 'source="supp_ai"' not in b.split(">", 1)[0]]


@pytest.mark.db
@pytest.mark.parametrize("question", [
    "Does St John's wort interact with warfarin?",
    "Does St John's wort interact with sertraline?",
])  # fmt: skip
def test_adding_supp_ai_never_changes_any_other_context_item(
    api: TestClient, db_session: Session, seeded: dict[str, object], tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch, question: str,
) -> None:  # fmt: skip
    ensure_sources(db_session)
    db_session.add(Target(id=uuid.uuid4(), symbol="CYP2C9", name="Cytochrome P450 2C9", target_type="enzyme",
                          uniprot_accession="P11712"))  # fmt: skip
    db_session.flush()
    extended_fixture(tmp_path / "supp_ai")
    for source, run, folder in (
        ("ddid", ddid.run, FIXTURES / "ddid"),
        ("supp_ai", supp_ai.run, tmp_path / "supp_ai"),
    ):
        with run_ingestion(db_session, source, Settings(_env_file=None)) as ctx:  # type: ignore[call-arg]
            run(ctx, folder)
    with_mentions = _prompt(api, question)
    real = service._supplementary_mentions
    monkeypatch.setattr(service, "_supplementary_mentions", lambda *a, **k: [])
    without = _prompt(api, question)
    monkeypatch.setattr(service, "_supplementary_mentions", real)
    assert _non_mention_blocks(with_mentions) == _non_mention_blocks(without)
    if "warfarin" in question:
        assert re.search(r'<evidence id="X\d+"', with_mentions)  # DDID present
        assert re.search(r'<evidence id="U\d+"', with_mentions)  # and SUPP.AI fills free room


# --------------------------------------------------------------------------- 2. negation

SJW, CSA = ["St John's wort", "Hypericum perforatum"], ["cyclosporine", "ciclosporin"]


@pytest.mark.parametrize(("sentence", "herb", "drug", "negated", "elsewhere"), [
    # mixed-drug sentences: the negation is about other drugs
    ("St John's wort decreased the blood levels of ciclosporin, midazolam and tacrolimus, but did not alter the "
     "kinetics of carbamazepine and pravastatin.", SJW, CSA, None, "did not"),
    ("St John's wort decreased the blood levels of ciclosporin, midazolam and tacrolimus, but did not alter the "
     "kinetics of carbamazepine and pravastatin.", SJW, ["carbamazepine"], "did not", None),
    ("St John's wort increased the clearance of S-warfarin, whereas ginkgo and ginger did not affect warfarin "
     "kinetics in healthy subjects.", SJW, ["warfarin", "S-warfarin"], None, "did not"),
    ("St John's wort increased the clearance of S-warfarin, whereas ginkgo and ginger did not affect warfarin "
     "kinetics in healthy subjects.", ["ginger"], ["warfarin"], "did not", None),
    ("SJW increased midazolam clearance but failed to alter bosentan exposure.", ["SJW"], ["midazolam"], None,
     "failed to"),
    ("Garlic lowered saquinavir exposure, but not ritonavir exposure, in volunteers.", ["garlic"], ["saquinavir"],
     None, "not"),
    ("Garlic lowered saquinavir exposure, but not ritonavir exposure, in volunteers.", ["garlic"], ["ritonavir"],
     "not", None),
    ("Verapamil, but not nifedipine, increased the effect of garlic on atrial tissue.", ["garlic"], ["verapamil"],
     None, "not"),
    ("Verapamil, but not nifedipine, increased the effect of garlic on atrial tissue.", ["garlic"], ["nifedipine"],
     "not", None),
    ("St John's wort may lower the INR with warfarin; nicotine is not known to alter warfarin's effect.", SJW,
     ["warfarin"], None, None),
    # genuine no-effect statements about the pair are kept
    ("St John's wort did not alter digoxin pharmacokinetics.", SJW, ["digoxin"], "did not", None),
    ("Garlic reduced docetaxel clearance, although the difference did not reach significance.", ["garlic"],
     ["docetaxel"], "did not", None),
    ("No interaction between St John's wort and ciclosporin was observed.", SJW, CSA, "No", None),
    # one substance on its own, study limits and emphasis are not negations of the pair
    ("Ginger alone did not change olanzapine-induced weight gain.", ["ginger"], ["olanzapine"], None, "did not"),
    ("The interaction between senna and digoxin has not been studied.", ["senna"], ["digoxin"], None, None),
    ("These garlic and ritonavir results should not be extrapolated to steady state.", ["garlic"], ["ritonavir"],
     None, None),
    ("Licorice not only reduced methotrexate toxicity but also its clearance.", ["licorice"], ["methotrexate"], None,
     None),
])  # fmt: skip
def test_pair_specific_negation(sentence: str, herb: list[str], drug: list[str], negated: str | None,
                                elsewhere: str | None) -> None:  # fmt: skip
    result = pair_negation(sentence, herb, drug)
    assert (result.negated, result.elsewhere) == (negated, elsewhere)
    assert result.warning is None


@pytest.mark.parametrize(("sentence", "warning"), [
    ("Use of St John's wort with bupropion is not recommended.", "is not recommended"),
    ("Coadministration of etravirine with St John's wort is currently not recommended.", "is currently not recommended"),
    ("St John's wort should not be given to patients treated with simvastatin.", "should not be given"),
    ("Irinotecan and St John's wort cannot be given safely in combination without loss of efficacy.",
     "cannot be given safely"),
    ("Garlic and ginkgo should not be used together with warfarin.", "should not be used"),
])  # fmt: skip
def test_warnings_are_not_negations(sentence: str, warning: str) -> None:
    result = pair_negation(sentence, ["St John's wort", "garlic", "irinotecan"],
                           ["bupropion", "etravirine", "simvastatin", "irinotecan", "warfarin"])  # fmt: skip
    assert result.warning == warning and result.negated is None


def test_mention_item_labels_pair_negation_warning_and_other_negation() -> None:
    def item(**kw: Any) -> ContextItem:
        return mention_item(text="m", study_type="human", external_id=None, url=None, title=None, location="l",
                            provenance=[], priority=60, **kw)  # fmt: skip

    negated = item(negation_cue="did not")
    assert any(
        q.startswith("negation applies to this herb-drug pair ('did not')")
        for q in negated.qualifiers
    )
    warning = item(negation_cue=None, warning_cue="not recommended")
    assert any("neither a confirmed interaction nor evidence that there is no interaction" in q
               for q in warning.qualifiers)  # fmt: skip
    assert not any(q.startswith("negation applies") for q in warning.qualifiers)
    other = item(negation_cue=None, other_negation_cue="did not")
    assert any("does not appear to apply to this herb-drug pair" in q for q in other.qualifiers)
    # a positive claim from a mention whose negation concerns other drugs is not removed
    assert mention_issue("One machine-extracted mention reports that St John's wort increased S-warfarin clearance.",
                         [other]) is None  # fmt: skip
    assert mention_issue("It increases levels.", [negated])[0] == "negated_mention_as_positive"  # type: ignore[index]


def test_misaligned_spans_are_not_used() -> None:
    sentence = "Coadministration of garlic nonsignificantly decreased the AUC."
    assert tagged_span(sentence, {"span": [20, 26]}) == "garlic"
    assert tagged_span(sentence, {"span": [23, 29]}) is None  # 'lic no': cuts words
    assert tagged_span(sentence, {"span": [19, 22]}) is None  # leading space
    assert tagged_span(sentence, {"span": [0]}) is None


# --------------------------------------------------------------------------- 3. study types


@pytest.mark.parametrize(("paper", "sentence", "expected"), [
    ({"clinical_study": True, "human_study": True, "title": "Interaction in healthy volunteers"}, None, "clinical"),
    ({"clinical_study": True, "human_study": False, "animal_study": True,
      "title": "Time-course effects of St John's wort on cyclosporine in dogs"}, None, "conflicting"),
    ({"human_study": True, "title": "Transwell-grown HepG2 cell monolayers as a permeability model"}, None, "in_vitro"),
    ({"human_study": True, "title": "Hyperforin and docetaxel metabolism by human hepatocyte cultures"}, None,
     "in_vitro"),
    ({"clinical_study": True, "human_study": True, "title": "A review"}, "In human liver microsomes the extract "
     "inhibited CYP3A4.", "in_vitro"),
    ({"human_study": True, "title": "Herb interactions"}, "Ginger decreased cyclosporine levels in rats.",
     "animal_wording"),
    ({"human_study": False, "animal_study": False, "title": "Garlic and atorvastatin in dyslipidaemic rats"}, None,
     "animal_wording"),
    ({"human_study": True, "animal_study": True, "title": "Effects in rats and in patients"}, None, "animal_and_human"),
    ({"animal_study": True, "title": "A rat study"}, None, "animal"),
])  # fmt: skip
def test_study_type_downgrades(paper: dict[str, Any], sentence: str | None, expected: str) -> None:
    assert study_type(paper, sentence) == expected


def _u(label: str, kind: str, sentence: str) -> ContextItem:
    item = mention_item(text=f'SUPP.AI machine-extracted mention: "{sentence}"', study_type=kind, negation_cue=None,
                        external_id=None, url=None, title=None, location="l", provenance=[], priority=60)  # fmt: skip
    item.label = label
    return item


DOG = _u(
    "U1",
    "conflicting",
    "Repeated St John's wort administration affects cyclosporine pharmacokinetics in dogs.",
)
CELLS = _u(
    "U2", "in_vitro", "Hyperforin increased docetaxel metabolism in human hepatocyte cultures."
)
RAT = _u("U3", "animal", "Ginger decreased the oral bioavailability of cyclosporine in rats.")
CLINICAL = _u(
    "U4", "clinical", "St John's wort decreased cyclosporine levels in renal transplant patients."
)
LABEL = ContextItem(label="S1", kind="statement", role="direct_evidence", source_code="openfda_label",
                    text="St. John's Wort: there have been reports of a serious drug interaction with cyclosporine.")  # fmt: skip
CONTEXT = EvidenceContext([ContextItem(label="C1", kind="classification", role="deterministic_classification",
                                       text="Class A"), LABEL, DOG, CELLS, RAT, CLINICAL])  # fmt: skip


def _rules(text: str, cites: tuple[str, ...]) -> set[str]:
    return {
        i.rule
        for i in validate(
            [Paragraph(text, cites)], [], False, CONTEXT, expected_classes={"A"}
        ).issues
    }


@pytest.mark.parametrize(("text", "cites"), [
    ("A clinical study found that repeated St John's wort administration affects cyclosporine pharmacokinetics.",
     ("U1",)),
    ("In a clinical trial, St John's wort affected the pharmacokinetics of cyclosporine.", ("U1",)),
    ("A clinical study in patients showed that St John's wort affects cyclosporine pharmacokinetics.", ("U1",)),
    ("In patients, hyperforin increases docetaxel metabolism.", ("U2",)),
    ("Human data show that hyperforin increases docetaxel metabolism.", ("U2",)),
    ("Ginger decreases the oral bioavailability of cyclosporine in humans.", ("U3",)),
    # one valid label statement plus a non-human mention cannot carry a patient claim
    ("In patients, St John's wort affects cyclosporine pharmacokinetics, with reports of a serious drug "
     "interaction.", ("S1", "U1")),
    ("Patients taking cyclosporine had increased docetaxel metabolism with hyperforin.", ("S1", "U2")),
])  # fmt: skip
def test_nonhuman_mentions_cannot_back_patient_claims(text: str, cites: tuple[str, ...]) -> None:
    assert "mention_nonhuman_as_clinical" in _rules(text, cites)


@pytest.mark.parametrize(("text", "cites"), [
    ("In a dog study, repeated St John's wort administration affected cyclosporine pharmacokinetics; this is not "
     "human evidence.", ("U1",)),
    ("In human hepatocyte cultures (in vitro), hyperforin increased docetaxel metabolism.", ("U2",)),
    ("In patients, there have been reports of a serious drug interaction; a rat study found ginger decreased "
     "cyclosporine bioavailability.", ("S1", "U3")),
    ("In renal transplant patients, St John's wort decreased cyclosporine levels, according to one "
     "machine-extracted mention.", ("U4",)),
])  # fmt: skip
def test_correctly_described_mentions_are_accepted(text: str, cites: tuple[str, ...]) -> None:
    assert "mention_nonhuman_as_clinical" not in _rules(text, cites)


# --------------------------------------------------------------------------- 4. no-interaction conclusions

SUPP_FACT = ContextItem(label="F1", kind="fact", role="catalogue", source_code="supp_ai",
                        text="SUPP.AI holds no eligible machine-extracted mention for Ginger with cyclosporine.")  # fmt: skip


@pytest.mark.parametrize("text", [
    "SUPP.AI found no interaction between ginger and cyclosporine.",
    "According to the SUPP.AI mentions, ginger does not interact with cyclosporine.",
    "Ginger doesn't interact with cyclosporine.",
    "The machine-extracted mentions show no clinically relevant interaction.",
    "Based on SUPP.AI, the combination is unlikely to interact.",
    "There is no evidence of an interaction in SUPP.AI.",
    "Ginger and cyclosporine can be safely combined, according to SUPP.AI.",
    "Ginkgo and ginger did not affect warfarin pharmacokinetics, so there is no interaction.",
    "SUPP.AI reports no risk for this combination.",
])  # fmt: skip
@pytest.mark.parametrize("cited", ["mention", "supp_ai_fact"])
def test_supp_ai_alone_cannot_establish_no_interaction(text: str, cited: str) -> None:
    items = [RAT] if cited == "mention" else [SUPP_FACT]
    issue = mention_issue(text, items)
    assert issue is not None and issue[:2] == ("supp_ai_absence_as_no_interaction", "critical")


@pytest.mark.parametrize("text", [
    "SUPP.AI holds no eligible mention for this pair; this does not show that no interaction exists.",
    "The absence of a SUPP.AI mention does not mean there is no interaction.",
    "One machine-extracted SUPP.AI mention reports that St John's wort did not alter digoxin pharmacokinetics.",
    "This is not a confirmed interaction.",
])  # fmt: skip
def test_accurate_absence_wording_is_accepted(text: str) -> None:
    issue = mention_issue(text, [RAT])
    assert issue is None or issue[0] != "supp_ai_absence_as_no_interaction"


def test_supp_ai_alone_cannot_confirm_an_interaction() -> None:
    assert mention_issue(
        "St John's wort interacts with cyclosporine; this is confirmed.", [CLINICAL]
    )[0] == (  # type: ignore[index]
        "supp_ai_mention_as_confirmed"
    )
    assert "supp_ai_mention_as_confirmed" in _rules("This is a confirmed interaction.", ("U4",))
    # with a label statement the paragraph is no longer SUPP.AI-only; the statement carries it
    assert mention_issue("St John's wort interacts with cyclosporine.", [LABEL, CLINICAL]) is None


def test_validate_rejects_no_interaction_from_supp_ai_only() -> None:
    rules = _rules("SUPP.AI found no interaction between ginger and cyclosporine.", ("U3",))
    assert "supp_ai_absence_as_no_interaction" in rules
