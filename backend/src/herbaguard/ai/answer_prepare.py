"""Prepare (or refresh) the validated answers for the suggested questions.

Each question goes through the normal ``ai.service.ask`` pipeline (retrieval, evidence assembly,
generation, validation); the service itself decides whether the result is eligible for the cache.
Nothing here writes an answer, bypasses validation or shortens the pipeline. Questions are processed
strictly one after another: the generator runs on a CPU-only machine.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session, sessionmaker

from herbaguard.ai import answer_cache
from herbaguard.ai import service as ai_service
from herbaguard.ai.embeddings import EmbeddingProvider
from herbaguard.ai.providers.registry import GenerationChain
from herbaguard.core.config import Settings
from herbaguard.core.errors import HerbaGuardError


@dataclass(frozen=True, slots=True)
class PrepareResult:
    question: str
    outcome: str  # generated | already_valid | not_cached | failed
    seconds: float
    detail: str


def prepare_answers(
    session_factory: Callable[[], Session] | sessionmaker[Session],
    settings: Settings,
    chain: GenerationChain,
    embeddings: EmbeddingProvider | None,
    *,
    refresh: bool = False,
    questions: Sequence[str] = answer_cache.SUGGESTED_QUESTIONS,
    on_start: Callable[[int, str], None] | None = None,
) -> list[PrepareResult]:
    """Run the pipeline for each question, one at a time, and report what was stored.

    ``refresh=False`` keeps an answer that is still valid (it is not regenerated);
    ``refresh=True`` regenerates and replaces it. A failure of one question does not stop the
    others, and a failed or non-validated generation leaves any earlier valid entry untouched.
    """
    results: list[PrepareResult] = []
    for index, question in enumerate(questions, start=1):
        if on_start is not None:
            on_start(index, question)
        started_at = datetime.now(UTC)
        started = time.perf_counter()
        session = session_factory()
        try:
            response = ai_service.ask(
                session,
                settings,
                question=question,
                allow_remote_drug_lookup=False,
                chain=chain,
                embeddings=embeddings,
                refresh_answer_cache=refresh,
            )
            qid = answer_cache.question_id(question)
            entry = answer_cache.stored_entries(session).get(qid)
            if response.cache is not None:
                outcome, detail = "already_valid", "a valid answer exists; not regenerated"
            elif entry is not None and entry.generated_at >= started_at:
                outcome = "generated"
                detail = (
                    f"validated and cached ({len(response.citations)} citations, "
                    f"{len(response.validation)} validation notes)"
                )
            else:
                outcome = "not_cached"
                detail = f"status={response.status}; nothing was cached"
            session.commit()
        except HerbaGuardError as exc:
            session.rollback()
            outcome, detail = "failed", f"{type(exc).__name__}: {exc}"
        finally:
            session.close()
        results.append(PrepareResult(question, outcome, time.perf_counter() - started, detail))
    return results
