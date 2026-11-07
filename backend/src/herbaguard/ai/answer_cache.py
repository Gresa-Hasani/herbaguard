"""Validated-answer cache for the suggested Evidence Assistant questions.

Local CPU generation takes minutes, so the three suggested questions can be prepared ahead of time
with ``herbaguard ai prepare-answers``. The cache never replaces the pipeline and never decides
what is true:

* only the three exact suggested questions (after whitespace/apostrophe/case normalisation) are
  eligible; every other question follows the normal pipeline untouched;
* an answer is stored only when the normal pipeline produced it with a language model and it passed
  validation (status ``answered``); rejected, insufficient, extractive, fallback or failed
  generations are never stored;
* the cache is checked *after* retrieval and evidence assembly. An entry is served only when its
  fingerprint equals the fingerprint of what the pipeline would send to the model right now: the
  rendered evidence context, the citation and provenance payloads, the deterministic classification,
  the prompt texts, the validation code and the generator configuration. If any of these changed,
  the entry is ignored and the normal pipeline runs; if the new answer passes validation it replaces
  the entry.

This is the narrowest dependency the architecture offers: unrelated data changes do not invalidate
an answer, while anything that could change the model's input, its validation or what the reader
sees does.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from datetime import UTC, datetime, timedelta
from functools import cache
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from herbaguard.ai import context as ctx
from herbaguard.ai import mentions as mentions_module
from herbaguard.ai import validation as validation_module
from herbaguard.ai.generation import SYSTEM_PROMPT_VERSION, load_prompt, task_prompt
from herbaguard.ai.query import Intent
from herbaguard.api.schemas.ai import AskResponse, CacheInfo, PairClassification, RetrievalInfo
from herbaguard.core.config import Settings
from herbaguard.models import AnswerCache

# Bump when the stored payload layout or the cache semantics change.
CACHE_SCHEMA_VERSION = 1

# The exact questions offered under "Try asking" in the interface. They are the only questions the
# cache serves. Keep identical to frontend/src/pages/AssistantPage.tsx (a test enforces this).
SUGGESTED_QUESTIONS: tuple[str, ...] = (
    "What does the evidence say about St John’s wort and warfarin?",
    "Which sources support the use of ginger for nausea?",
    "What interactions are documented for ginkgo?",
)


# typographic apostrophes (U+2019, U+2018, U+02BC) -> ASCII apostrophe
_APOSTROPHES = {0x2019: "'", 0x2018: "'", 0x02BC: "'"}


def normalize_question(question: str) -> str:
    """Whitespace, case and apostrophe-style normalisation; nothing fuzzier than that."""
    text = unicodedata.normalize("NFC", question)
    text = text.translate(_APOSTROPHES)
    return " ".join(text.split()).casefold()


def question_id(question: str) -> str:
    return hashlib.sha256(normalize_question(question).encode("utf-8")).hexdigest()


_SUGGESTED_IDS = {question_id(q): q for q in SUGGESTED_QUESTIONS}


def suggested_question_id(question: str) -> str | None:
    """The cache id of ``question`` when it is one of the suggested questions, else ``None``."""
    qid = question_id(question)
    return qid if qid in _SUGGESTED_IDS else None


@cache
def validation_version() -> str:
    """Hash of the validation code. Any change to the rules invalidates every cached answer."""
    digest = hashlib.sha256()
    for module in (validation_module, mentions_module):
        digest.update(Path(str(module.__file__)).read_bytes())
    return digest.hexdigest()[:16]


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def compute_fingerprint(
    *,
    settings: Settings,
    chain_names: tuple[str, ...],
    qid: str,
    intent: Intent,
    expected: set[str],
    personal_advice: bool,
    partial: bool,
    context: ctx.EvidenceContext,
    citations: list[Any],
    classifications: list[PairClassification],
) -> str:
    prompt = task_prompt(intent, partial_coverage=partial)
    system = load_prompt("system", SYSTEM_PROMPT_VERSION)
    payload = {
        "schema": CACHE_SCHEMA_VERSION,
        "question": qid,
        "intent": intent.value,
        "expected_classes": sorted(expected),
        "personal_advice": personal_advice,
        "partial_coverage": partial,
        # exactly what the model would be given, plus what the reader would see next to the answer
        "rendered_context": ctx.render(context),
        "omitted": context.omitted,
        "excluded_for_licence": context.excluded_for_licence,
        "context_notes": context.notes,
        "citations": [c.model_dump(mode="json") for c in citations],
        "classification": [c.model_dump(mode="json") for c in classifications],
        "prompts": {p.ref: _sha(p.text) for p in (system, prompt)},
        "validation": validation_version(),
        "generator": {
            "chain": list(chain_names),
            "model": settings.llm_model,
            "temperature": settings.llm_temperature,
            "seed": settings.llm_seed,
            "max_output_tokens": settings.llm_max_output_tokens,
            "num_ctx": settings.ollama_num_ctx,
            "regenerations": settings.llm_max_regenerations,
            "context_items": settings.ai_context_max_items,
            "context_tokens": settings.ai_context_max_tokens,
        },
    }
    return _sha(json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str))


def lookup(
    session: Session, settings: Settings, qid: str, fingerprint: str, *, now: datetime | None = None
) -> tuple[AnswerCache, AskResponse] | None:
    """The stored answer for ``qid`` if (and only if) it is still valid; otherwise ``None``."""
    entry = session.scalar(select(AnswerCache).where(AnswerCache.question_id == qid))
    if entry is None:
        return None
    current = now or datetime.now(UTC)
    if (
        entry.validation_status != "passed"
        or entry.schema_version != CACHE_SCHEMA_VERSION
        or entry.validation_version != validation_version()
        or entry.fingerprint != fingerprint
        or entry.generated_at < current - timedelta(days=settings.ai_answer_cache_max_age_days)
    ):
        return None
    try:
        response = AskResponse.model_validate(entry.response)
    except ValueError:  # a payload that no longer fits the contract is never served
        return None
    if response.status != "answered" or not response.paragraphs or not response.citations:
        return None
    return entry, response


def servable_response(
    entry: AnswerCache, stored: AskResponse, *, question: str, retrieval: RetrievalInfo | None
) -> AskResponse:
    """The stored answer, returned through the normal response contract.

    Retrieval information is the current request's own. No language model ran, so the generation
    duration is zero and the original duration is reported in ``cache`` instead of being presented
    as this request's timing.
    """
    return stored.model_copy(
        update={
            "question": question,
            "retrieval": retrieval,
            "generation": stored.generation.model_copy(update={"duration_ms": 0}),
            "cache": CacheInfo(
                generated_at=entry.generated_at,
                original_generation_ms=entry.generation_ms,
            ),
        }
    )


def eligible_for_storage(response: AskResponse, *, mode: str, failed_attempts: int) -> bool:
    """Only a validated, model-generated, fully cited answer from the primary generator."""
    return (
        response.status == "answered"
        and mode == "model"
        and failed_attempts == 0
        and bool(response.paragraphs)
        and bool(response.citations)
        and response.cache is None
    )


def store(
    session: Session,
    *,
    qid: str,
    question: str,
    fingerprint: str,
    response: AskResponse,
    now: datetime | None = None,
) -> AnswerCache:
    """Insert or replace the entry for ``qid`` (one row per question)."""
    entry = session.scalar(select(AnswerCache).where(AnswerCache.question_id == qid))
    if entry is None:
        entry = AnswerCache(question_id=qid)
        session.add(entry)
    generation = response.generation
    entry.question_text = question
    entry.fingerprint = fingerprint
    entry.schema_version = CACHE_SCHEMA_VERSION
    entry.validation_version = validation_version()
    entry.validation_status = "passed"
    entry.provider = generation.provider
    entry.model = generation.model
    entry.prompts = list(generation.prompts)
    entry.generated_at = now or datetime.now(UTC)
    entry.generation_ms = generation.duration_ms
    entry.input_tokens = generation.input_tokens
    entry.output_tokens = generation.output_tokens
    entry.citation_labels = [c.label for c in response.citations]
    entry.response = response.model_dump(mode="json")
    session.flush()
    return entry


def stored_entries(session: Session) -> dict[str, AnswerCache]:
    """Stored rows keyed by question id (for the status command)."""
    return {e.question_id: e for e in session.scalars(select(AnswerCache))}
