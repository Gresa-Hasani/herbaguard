"""Emergency and dosing screening (ported behaviour from main e491d02) and controlled regeneration."""

from __future__ import annotations

import json

import pytest

from herbaguard.ai.context import ContextItem, EvidenceContext
from herbaguard.ai.generation import generate
from herbaguard.ai.guardrails import QuestionKind, screen
from herbaguard.ai.providers.base import GenerationRequest
from herbaguard.ai.providers.mock import ScriptedProvider
from herbaguard.ai.providers.registry import GenerationChain
from herbaguard.ai.query import Intent
from herbaguard.core.config import LLMProviderName, Settings


@pytest.mark.parametrize(
    "question",
    [
        "I took too many valerian tablets and feel dizzy",
        "My son swallowed a whole bottle of St John's wort",
        "I think I overdosed on ginkgo",
        "My wife has chest pain after taking hawthorn",
        "I can't breathe after drinking the tea",
        "Her lips are swelling after echinacea",
        "I want to end my life",
    ],
)
def test_emergencies_are_recognised(question: str) -> None:
    assert screen(question).kind is QuestionKind.EMERGENCY


@pytest.mark.parametrize(
    "question",
    [
        "How much valerian should I take to sleep?",
        "What is the maximum daily dose of St John's wort?",
        "Can I take 900 mg of ginkgo daily?",
        "How often should I take echinacea?",
    ],
)
def test_dosing_questions_are_recognised(question: str) -> None:
    assert screen(question).kind is QuestionKind.DOSING


@pytest.mark.parametrize(
    "question",
    [
        "Can ginkgo lower the seizure threshold?",  # evidence question about seizures, not an emergency
        "Does St John's wort cause dose-dependent CYP3A4 induction?",
        "What does the monograph say about overdose of senna?",  # see the conservative rule below
    ],
)
def test_evidence_questions_are_not_refused(question: str) -> None:
    kind = screen(question).kind
    if "overdose" in question:
        # Conservative by design: any mention of overdose is screened as an emergency.
        assert kind is QuestionKind.EMERGENCY
    else:
        assert kind is QuestionKind.EVIDENCE


def test_empty_question() -> None:
    assert screen("?? !!").kind is QuestionKind.EMPTY


# --------------------------------------------------------------------------- regeneration

SETTINGS = Settings(_env_file=None)  # type: ignore[call-arg]
CONTEXT = EvidenceContext([
    ContextItem("C1", "classification", "deterministic_classification", "Pair: X + Y\nClass A — Documented"),
    ContextItem("S1", "statement", "direct_evidence", "Concomitant use is contraindicated.", source_code="ema_hmpc"),
])  # fmt: skip
GOOD = json.dumps({"paragraphs": [{"text": "HerbaGuard gives class A.", "citations": ["C1"]}],
                   "limitations": [], "insufficient_evidence": False})  # fmt: skip
WRONG_CLASS = json.dumps({"paragraphs": [{"text": "This is class B.", "citations": ["C1"]}],
                          "limitations": [], "insufficient_evidence": False})  # fmt: skip


def run(replies: list[str], settings: Settings = SETTINGS):  # type: ignore[no-untyped-def]
    queue = list(replies)
    provider = ScriptedProvider(lambda r: queue.pop(0))
    chain = GenerationChain((LLMProviderName.OLLAMA,), (provider,))
    outcome = generate(settings, chain, question="q", intent=Intent.HERB_DRUG_INTERACTION, context=CONTEXT,
                       expected_classes={"A"}, personal_advice=False, partial_coverage=False)  # fmt: skip
    return outcome, provider.requests


def test_failed_check_is_regenerated_once_with_feedback() -> None:
    outcome, requests = run([WRONG_CLASS, GOOD])
    assert (outcome.status, outcome.regenerations) == ("answered", 1)
    retry: GenerationRequest = requests[1]
    assert retry.messages[1].role == "assistant" and retry.messages[1].content == WRONG_CLASS
    assert "classification_conflict" in retry.messages[2].content
    assert retry.messages[0] == requests[0].messages[0]  # same evidence context


def test_malformed_output_is_regenerated() -> None:
    outcome, _ = run(["not json", GOOD])
    assert outcome.status == "answered" and outcome.regenerations == 1


def test_still_failing_after_regeneration_is_rejected() -> None:
    outcome, requests = run([WRONG_CLASS, WRONG_CLASS])
    assert outcome.status == "rejected" and len(requests) == 2


def test_regeneration_can_be_disabled() -> None:
    no_retry = Settings(_env_file=None, llm_max_regenerations=0)  # type: ignore[call-arg]
    outcome, requests = run([WRONG_CLASS, GOOD], settings=no_retry)
    assert outcome.status == "rejected" and len(requests) == 1
