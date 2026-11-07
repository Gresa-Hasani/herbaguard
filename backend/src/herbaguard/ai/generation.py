"""Grounded answer generation.

* Prompts are versioned files in ``ai/prompts/`` (front matter: id, version, purpose); the system
  prompt is ``system`` + the task prompt chosen by intent.
* The configured provider is called with a JSON schema (structured output). The answer is parsed
  and validated (``validation.validate``). An incomplete (token-limited), unparseable or rejected
  answer is never returned as an answer.
* Fallback: only the provider configured in ``llm_fallback_provider`` is tried next, with the same
  context; the response names the provider that actually produced it and why the first one failed.
* Extractive mode (provider ``extractive``) composes a deterministic answer from the context items
  without a model. It is used only when configured (as provider or fallback) or when there is no
  citable evidence at all (then no model is called).
* Cloud licensing guard: a cloud provider receives source text only if
  ``ai_cloud_send_source_text`` is true, and then only items from sources registered as
  redistributable (applied during context assembly).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from functools import cache
from importlib import resources

from herbaguard.ai.context import EvidenceContext, render
from herbaguard.ai.providers.base import (
    GenerationRequest,
    LLMProvider,
    Message,
    ProviderError,
    ProviderErrorKind,
    Usage,
)
from herbaguard.ai.providers.registry import GenerationChain
from herbaguard.ai.query import Intent
from herbaguard.ai.validation import (
    ANSWER_SCHEMA,
    AnswerFormatError,
    Issue,
    Paragraph,
    ValidationResult,
    parse,
    validate,
)
from herbaguard.core.config import LLMProviderName, Settings


@dataclass(frozen=True, slots=True)
class Prompt:
    id: str
    version: int
    text: str

    @property
    def ref(self) -> str:
        return f"{self.id}_v{self.version}"


SYSTEM_PROMPT_VERSION = (
    5  # v2: 3a (DDID); v3: 3b (LiverTox); v4: 3c (SUPP.AI); v5: 3d (DSLD labels)
)


@cache
def load_prompt(name: str, version: int = 1) -> Prompt:
    raw = (
        resources.files("herbaguard.ai.prompts")
        .joinpath(f"{name}_v{version}.md")
        .read_text("utf-8")
    )
    _, front, body = raw.split("---", 2)
    meta = dict(line.split(":", 1) for line in front.strip().splitlines())
    return Prompt(meta["id"].strip(), int(meta["version"]), body.strip())


def task_prompt(intent: Intent, *, partial_coverage: bool) -> Prompt:
    if partial_coverage:
        return load_prompt("insufficient")
    if intent is Intent.HERB_DRUG_INTERACTION:
        return load_prompt("interaction")
    if intent is Intent.EVIDENCE_COMPARISON:
        return load_prompt("comparison")
    return load_prompt("general")


@dataclass(slots=True)
class GenerationOutcome:
    status: str  # "answered" | "rejected"
    mode: str  # "model" | "extractive"
    provider: str
    model: str | None
    validation: ValidationResult
    prompts: list[str]
    usage: Usage = field(default_factory=Usage)
    duration_ms: int = 0
    attempts: list[dict[str, str]] = field(default_factory=list)  # failed attempts (provider, kind)
    regenerations: int = 0  # extra requests to the same provider after a failed check


def build_request(
    settings: Settings,
    question: str,
    context: EvidenceContext,
    prompt: Prompt,
    *,
    personal_advice: bool,
) -> GenerationRequest:
    system = load_prompt("system", SYSTEM_PROMPT_VERSION).text + "\n\n" + prompt.text
    note = (
        "\nNOTE: The question asks for personal medical advice. Do not give it; explain only what the "
        "evidence says and that a doctor or pharmacist must decide."
        if personal_advice
        else ""
    )
    user = (
        f"QUESTION (from the reader; answer it only from the items below):\n{question.strip()}\n{note}\n"
        f"ITEMS:\n{render(context)}\n\nReturn the JSON answer now."
    )
    return GenerationRequest(
        system=system,
        messages=(Message("user", user),),
        json_schema=ANSWER_SCHEMA,
        temperature=settings.llm_temperature,
        max_output_tokens=settings.llm_max_output_tokens,
        seed=settings.llm_seed,
    )


def extractive_answer(context: EvidenceContext, *, reason: str | None = None) -> ValidationResult:
    """Deterministic answer from context items: classification(s), then up to three quoted items."""
    paragraphs: list[Paragraph] = []
    for item in context.items:
        if item.kind == "classification":
            first = item.text.splitlines()
            paragraphs.append(Paragraph(" ".join(first[:3]), (item.label,)))
    quoted = [
        i
        for i in context.items
        if i.kind in ("statement", "excerpt", "mechanism", "hepatotoxicity", "fact")
    ][:3]
    for item in quoted:
        source = item.title or item.source_code or "Source"
        kind = {
            "graph_context": "Relationship from the knowledge graph",
            "catalogue": "HerbaGuard catalogue",
            "hepatotoxicity_evidence": f"LiverTox hepatotoxicity record ({item.title or 'LiverTox'})",
        }.get(item.role, source)
        paragraphs.append(Paragraph(f'{kind}: "{item.text}"', (item.label,)))
    limitations = list(context.notes)
    if reason:
        limitations.insert(0, reason)
    limitations.append("This answer quotes stored evidence without a language model summary.")
    return ValidationResult(paragraphs, limitations, insufficient_evidence=not quoted)


def generate(
    settings: Settings,
    chain: GenerationChain,
    *,
    question: str,
    intent: Intent,
    context: EvidenceContext,
    expected_classes: set[str],
    personal_advice: bool,
    partial_coverage: bool,
) -> GenerationOutcome:
    prompt = task_prompt(intent, partial_coverage=partial_coverage)
    prompts = [load_prompt("system", SYSTEM_PROMPT_VERSION).ref, prompt.ref]
    attempts: list[dict[str, str]] = []
    started = time.perf_counter()

    for name, provider in zip(chain.names, chain.providers, strict=True):
        if provider is None:  # extractive mode, configured explicitly
            reason = None
            if attempts:
                reason = f"Generated without a language model because {attempts[-1]['provider']} failed ({attempts[-1]['kind']})."
            result = extractive_answer(context, reason=reason)
            return GenerationOutcome("answered", "extractive", LLMProviderName.EXTRACTIVE.value, None, result,
                                     prompts, duration_ms=_ms(started), attempts=attempts)  # fmt: skip
        outcome = _try_model(settings, provider, name, question, context, prompt, expected_classes,
                             personal_advice, prompts, started)  # fmt: skip
        if isinstance(outcome, GenerationOutcome):
            outcome.attempts = attempts
            if outcome.status == "answered" or name == chain.names[-1]:
                return outcome
            attempts.append({"provider": provider.name, "kind": "rejected_by_validation"})
            continue
        attempts.append({"provider": provider.name, "kind": outcome.kind.value})
        if name == chain.names[-1]:
            raise outcome
    msg = "No generator configured."  # pragma: no cover - chain always has a primary
    raise RuntimeError(msg)


def _try_model(
    settings: Settings,
    provider: LLMProvider,
    name: LLMProviderName,
    question: str,
    context: EvidenceContext,
    prompt: Prompt,
    expected_classes: set[str],
    personal_advice: bool,
    prompts: list[str],
    started: float,
) -> GenerationOutcome | ProviderError:
    if provider.is_cloud and not settings.ai_cloud_send_source_text:
        return ProviderError(provider.name, ProviderErrorKind.REFUSED,
                             "Sending source text to a cloud provider is disabled "
                             "(HERBAGUARD_AI_CLOUD_SEND_SOURCE_TEXT=false).")  # fmt: skip
    request = build_request(settings, question, context, prompt, personal_advice=personal_advice)
    _ = name
    problem: str | None = None
    last_text = ""
    outcome: GenerationOutcome | None = None
    for attempt in range(settings.llm_max_regenerations + 1):
        if attempt and problem:
            request = _regeneration_request(request, last_text, problem)
        try:
            result = provider.generate(request)
        except ProviderError as exc:
            return exc
        last_text = result.text
        if not result.complete:
            problem = "The answer was cut off by the output token limit; partial answers are not returned."
            outcome = None
            continue
        try:
            paragraphs, limitations, insufficient = parse(result.text)
        except AnswerFormatError as exc:
            problem = str(exc)
            outcome = None
            continue
        validation = validate(paragraphs, limitations + list(context.notes), insufficient, context,
                              expected_classes=expected_classes)  # fmt: skip
        status = "rejected" if validation.rejected else "answered"
        outcome = GenerationOutcome(status, "model", result.provider, result.model, validation, prompts,
                                    result.usage, _ms(started), regenerations=attempt)  # fmt: skip
        if status == "answered":
            return outcome
        problem = "; ".join(
            f"{i.rule}: {i.message}" for i in validation.issues if i.severity == "critical"
        )
    if outcome is not None:
        return outcome  # rejected after the allowed regenerations
    return ProviderError(
        provider.name, ProviderErrorKind.BAD_RESPONSE, problem or "Unusable answer."
    )


def _regeneration_request(
    request: GenerationRequest, previous: str, problem: str
) -> GenerationRequest:
    """Same system prompt and evidence; the previous output and its problems are added so the
    model can correct them. The evidence context is never changed between attempts."""
    feedback = (
        "Your previous answer was not accepted by HerbaGuard's checks: "
        f"{problem[:600]}. Return a corrected JSON answer that follows every rule, cites only the "
        "given ids and restates the classification exactly as given."
    )
    return GenerationRequest(
        system=request.system,
        messages=(*request.messages, Message("assistant", previous[:4000]), Message("user", feedback)),
        json_schema=request.json_schema, temperature=request.temperature,
        max_output_tokens=request.max_output_tokens, seed=request.seed,
        contains_source_text=request.contains_source_text,
    )  # fmt: skip


def _ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


__all__ = ["GenerationOutcome", "Issue", "extractive_answer", "generate", "load_prompt"]
