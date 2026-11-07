"""Generation chain: structured output, validation, explicit fallback, licensing guard."""

from __future__ import annotations

import json

import pytest

from herbaguard.ai.context import ContextItem, EvidenceContext
from herbaguard.ai.generation import extractive_answer, generate, load_prompt
from herbaguard.ai.providers.base import GenerationRequest, ProviderError, ProviderErrorKind
from herbaguard.ai.providers.mock import ScriptedProvider
from herbaguard.ai.providers.registry import GenerationChain
from herbaguard.ai.query import Intent
from herbaguard.core.config import LLMProviderName, Settings

SETTINGS = Settings(_env_file=None)  # type: ignore[call-arg]
CONTEXT = EvidenceContext([
    ContextItem("C1", "classification", "deterministic_classification", "Pair: X + Y\nClass A — Documented\nExplanation: e"),
    ContextItem("S1", "statement", "direct_evidence", "Concomitant use is contraindicated.", source_code="ema_hmpc"),
])  # fmt: skip
GOOD = json.dumps({"paragraphs": [{"text": "HerbaGuard gives class A.", "citations": ["C1"]},
                                  {"text": "The monograph states that concomitant use is contraindicated.", "citations": ["S1"]}],
                   "limitations": [], "insufficient_evidence": False})  # fmt: skip


def chain(*providers: object) -> GenerationChain:
    names = (LLMProviderName.OLLAMA, LLMProviderName.EXTRACTIVE, LLMProviderName.OPENAI)[
        : len(providers)
    ]
    return GenerationChain(names, tuple(providers))  # type: ignore[arg-type]


def run(
    c: GenerationChain, settings: Settings = SETTINGS, intent: Intent = Intent.HERB_DRUG_INTERACTION
):  # type: ignore[no-untyped-def]
    return generate(settings, c, question="Does X interact with Y?", intent=intent, context=CONTEXT,
                    expected_classes={"A"}, personal_advice=False, partial_coverage=False)  # fmt: skip


def test_model_answer_with_schema_and_versioned_prompts() -> None:
    provider = ScriptedProvider(lambda r: GOOD)
    outcome = run(chain(provider))
    request = provider.requests[0]
    assert request.json_schema is not None and "paragraphs" in request.json_schema["properties"]
    assert request.system.startswith(load_prompt("system", 2).text[:40])
    assert 'id="S1"' in request.messages[0].content
    assert (outcome.status, outcome.mode, outcome.provider) == ("answered", "model", "mock")
    assert outcome.prompts == ["system_v4", "interaction_v1"]


def test_provider_failure_without_fallback_raises() -> None:
    failing = ScriptedProvider(
        lambda r: ProviderError("mock", ProviderErrorKind.UNAVAILABLE, "down")
    )
    with pytest.raises(ProviderError):
        run(chain(failing))


def test_explicit_fallback_records_the_failed_provider() -> None:
    failing = ScriptedProvider(
        lambda r: ProviderError("ollama", ProviderErrorKind.TIMEOUT, "slow"), name="ollama"
    )
    outcome = run(chain(failing, None))
    assert (outcome.mode, outcome.provider) == ("extractive", "extractive")
    assert outcome.attempts == [{"provider": "ollama", "kind": "timeout"}]
    assert "ollama failed (timeout)" in outcome.validation.limitations[0]


def test_truncated_or_malformed_output_is_never_returned() -> None:
    with pytest.raises(ProviderError, match="cut off"):
        run(chain(ScriptedProvider(lambda r: GOOD[:40], finish_reason="length")))
    with pytest.raises(ProviderError, match="valid JSON"):
        run(chain(ScriptedProvider(lambda r: "plain text")))


def test_rejected_answer_falls_back_when_configured() -> None:
    unsafe = json.dumps({"paragraphs": [{"text": "It is safe to combine them.", "citations": ["S1"]}],
                         "limitations": [], "insufficient_evidence": False})  # fmt: skip
    alone = run(chain(ScriptedProvider(lambda r: unsafe)))
    assert alone.status == "rejected"
    with_fallback = run(chain(ScriptedProvider(lambda r: unsafe, name="ollama"), None))
    assert with_fallback.mode == "extractive"
    assert with_fallback.attempts == [{"provider": "ollama", "kind": "rejected_by_validation"}]


def test_cloud_provider_gets_no_source_text_unless_allowed() -> None:
    cloud = ScriptedProvider(lambda r: GOOD, name="anthropic", is_cloud=True)
    with pytest.raises(ProviderError) as info:
        run(chain(cloud))
    assert info.value.kind is ProviderErrorKind.REFUSED and cloud.requests == []
    allowed = Settings(_env_file=None, ai_cloud_send_source_text=True)  # type: ignore[call-arg]
    assert run(chain(cloud), settings=allowed).status == "answered"


def test_task_prompt_by_intent() -> None:
    seen: list[GenerationRequest] = []
    provider = ScriptedProvider(lambda r: (seen.append(r), GOOD)[1])
    assert run(chain(provider), intent=Intent.EVIDENCE_COMPARISON).prompts[1] == "comparison_v1"
    assert run(chain(provider), intent=Intent.MECHANISM).prompts[1] == "general_v1"


def test_extractive_answer_quotes_verbatim_and_cites() -> None:
    result = extractive_answer(CONTEXT)
    assert [p.citations for p in result.paragraphs] == [("C1",), ("S1",)]
    assert '"Concomitant use is contraindicated."' in result.paragraphs[1].text
