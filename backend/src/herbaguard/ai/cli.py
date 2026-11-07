"""``herbaguard ai …`` commands: indexing, index status and evaluation (Phase 5)."""

from __future__ import annotations

import time
from typing import Annotated, Any

import typer

from herbaguard.core.config import get_settings
from herbaguard.core.db import get_session_factory
from herbaguard.core.logging import configure_logging

ai_app = typer.Typer(help="AI layer: retrieval index, status and evaluation.", no_args_is_help=True)

SourceOption = Annotated[
    list[str] | None, typer.Option("--source", help="Limit to source code(s), e.g. ema_hmpc.")
]
ModelOption = Annotated[
    str | None,
    typer.Option("--model", help="Embedding model (default: HERBAGUARD_EMBEDDING_MODEL)."),
]


@ai_app.command("index")
def index(
    source: SourceOption = None,
    model: ModelOption = None,
    segments_only: Annotated[bool, typer.Option(help="Only (re)build segments.")] = False,
    limit: Annotated[int | None, typer.Option(help="Embed at most N pending segments.")] = None,
    query_prefix: Annotated[str | None, typer.Option(help="Override the query prefix.")] = None,
    document_prefix: Annotated[
        str | None, typer.Option(help="Override the document prefix.")
    ] = None,
) -> None:
    """Incrementally (re)build retrieval segments and embed new or stale ones."""
    from herbaguard.ai.embeddings import build_embeddings
    from herbaguard.ai.indexing.indexer import embed_pending, sync_segments
    from herbaguard.ingestion.context import run_ingestion
    from herbaguard.ingestion.loaders import ensure_sources

    settings = get_settings()
    if query_prefix is not None or document_prefix is not None:
        settings = settings.model_copy(
            update={
                k: v
                for k, v in (("embedding_query_prefix", query_prefix),
                             ("embedding_document_prefix", document_prefix))
                if v is not None
            }
        )  # fmt: skip
    configure_logging(settings)
    session = get_session_factory()()
    started = time.perf_counter()
    try:
        ensure_sources(session)
        session.commit()
        parameters = {"sources": source or "all", "model": model or settings.embedding_model,
                      "segments_only": segments_only}  # fmt: skip
        with run_ingestion(session, "herbaguard_ai_index", settings, parameters=parameters) as ctx:
            sync_segments(ctx, settings, sources=source)
            if not segments_only:
                provider = build_embeddings(settings, model=model)
                if provider is None:
                    typer.echo("Embedding provider is 'none': segments only.")
                else:
                    embed_pending(ctx, provider, settings, sources=source, limit=limit)
            stats = dict(ctx.stats)
        typer.echo(f"[ai index] finished in {time.perf_counter() - started:.1f}s")
        for key in sorted(stats):
            typer.echo(f"    {key}: {stats[key]}")
    finally:
        session.close()


@ai_app.command("status")
def status(model: ModelOption = None) -> None:
    """Index coverage for the configured (or given) embedding model."""
    from herbaguard.ai.embeddings import EmbeddingError, build_embeddings
    from herbaguard.ai.indexing.indexer import index_status

    settings = get_settings()
    session = get_session_factory()()
    try:
        provider = build_embeddings(settings, model=model)
        info = None
        if provider is not None:
            try:
                info = provider.info()
            except EmbeddingError as exc:
                typer.echo(f"Embedding model unavailable: {exc}")
        st = index_status(session, model=info.model if info else None,
                          version=info.version if info else None,
                          dimension=info.dimension if info else None)  # fmt: skip
        typer.echo(f"segments (current evidence): {st.segments}")
        typer.echo(
            f"evidence items indexed: {st.evidence_items_indexed} / {st.evidence_items_current}"
        )
        typer.echo(f"model: {st.model} version={st.model_version} dim={st.dimension}")
        typer.echo(f"embedded (current): {st.embedded}; missing or stale: {st.stale_or_missing}")
    finally:
        session.close()


DEFAULT_DATASET = "../data/evaluation/rag_baseline_v1.yaml"


def _refuse_existing_report(output: str | None, overwrite: bool) -> None:
    """Checked before any work starts, so an earlier (historical) report is never replaced by accident."""
    from pathlib import Path

    if output and Path(output).exists() and not overwrite:
        typer.echo(
            f"Refusing to overwrite existing report {output} (pass --overwrite to replace it).",
            err=True,
        )
        raise typer.Exit(code=2)


@ai_app.command("evaluate-retrieval")
def evaluate_retrieval_cmd(
    dataset: Annotated[str, typer.Option(help="Evaluation dataset (YAML).")] = DEFAULT_DATASET,
    embedding_model: Annotated[
        list[str] | None,
        typer.Option("--embedding-model", help="Model(s) to compare (repeatable)."),
    ] = None,
    output: Annotated[str | None, typer.Option(help="Write the full JSON report here.")] = None,
    overwrite: Annotated[
        bool, typer.Option(help="Allow replacing an existing report file.")
    ] = False,
) -> None:
    """Keyword vs semantic vs hybrid retrieval on the evaluation set (no language model)."""
    _refuse_existing_report(output, overwrite)
    import json
    from datetime import UTC, datetime
    from pathlib import Path

    from herbaguard.ai.embeddings import build_embeddings
    from herbaguard.ai.evaluation import (
        corpus_snapshot,
        evaluate_retrieval,
        load_dataset,
        rxnav_reachable,
    )

    settings = get_settings()
    data = load_dataset(Path(dataset))
    session = get_session_factory()()
    runs = []
    try:
        rx = rxnav_reachable()
        if not rx:
            typer.echo(
                "RxNav unreachable: brand-name questions are reported as externally blocked."
            )
        runs.append(
            evaluate_retrieval(
                session, settings, data, mode="keyword", embeddings=None, rxnav_available=rx
            )
        )
        for model in embedding_model or [settings.embedding_model]:
            provider = build_embeddings(settings, model=model)
            for mode in ("semantic", "hybrid"):
                runs.append(
                    evaluate_retrieval(
                        session, settings, data, mode=mode, embeddings=provider, rxnav_available=rx
                    )
                )
        report = {
            "dataset": data.label,
            "generated_at": datetime.now(UTC).isoformat(),
            "corpus": corpus_snapshot(session),
            "retrieval_settings": {
                k: v
                for k, v in settings.model_dump().items()
                if k.startswith(("retrieval_", "segment_"))
            },
            "runs": runs,
        }
    finally:
        session.close()
    typer.echo(
        f"{'mode':<9} {'model':<18} {'hit@5':>6} {'recall@5':>8} {'recall@10':>9} {'prec@5':>6} {'mrr':>6} {'dup@10':>6} {'src@10':>6} {'p50 ms':>7}"
    )
    for run in runs:
        s = run["summary"]
        typer.echo(
            f"{run['mode']:<9} {run['embedding_model'] or '-'!s:<18} {s['hit@5']:>6.3f} {s['recall@5']:>8.3f} "
            f"{s['recall@10']:>9.3f} {s['precision@5']:>6.3f} {s['mrr']:>6.3f} {s['duplicate_rate@10']:>6.3f} "
            f"{s['sources@10']:>6.2f} {s['latency_ms_median']:>7}"
        )
    if output:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        typer.echo(f"Report written to {output}")


@ai_app.command("evaluate-generation")
def evaluate_generation_cmd(
    dataset: Annotated[str, typer.Option(help="Evaluation dataset (YAML).")] = DEFAULT_DATASET,
    question_id: Annotated[
        list[str] | None, typer.Option("--question", help="Only these question ids.")
    ] = None,
    output: Annotated[str | None, typer.Option(help="Write the full JSON report here.")] = None,
    overwrite: Annotated[
        bool, typer.Option(help="Allow replacing an existing report file.")
    ] = False,
) -> None:
    """Run questions through /ai/ask with the configured provider and record deterministic checks.
    Calls the configured model (local Ollama by default; a cloud provider only if configured)."""
    _refuse_existing_report(output, overwrite)
    import json
    from datetime import UTC, datetime
    from pathlib import Path

    from herbaguard.ai import service
    from herbaguard.ai.embeddings import build_embeddings
    from herbaguard.ai.evaluation import (
        generation_checks,
        load_dataset,
        rxnav_reachable,
        summarise_generation,
    )
    from herbaguard.ai.providers.registry import generation_chain
    from herbaguard.core.errors import AmbiguousEntityError, HerbaGuardError
    from herbaguard.services import interactions as interaction_service

    settings = get_settings()
    configure_logging(settings)
    data = load_dataset(Path(dataset))
    chain = generation_chain(settings)
    embeddings = build_embeddings(settings)
    session = get_session_factory()()
    rows: list[dict[str, Any]] = []
    try:
        rx = rxnav_reachable()
        for q in data.questions:
            if question_id and q.id not in question_id:
                continue
            if q.allow_remote_drug_lookup and not rx:
                rows.append(
                    {"id": q.id, "category": q.category, "status": "externally_blocked_rxnav"}
                )
                typer.echo(f"{q.id:<34} externally blocked (RxNav unreachable)", err=False)
                continue
            try:
                response = service.ask(session, settings, question=q.question,
                                       allow_remote_drug_lookup=q.allow_remote_drug_lookup,
                                       chain=chain, embeddings=embeddings)  # fmt: skip
            except AmbiguousEntityError as exc:
                rows.append({"id": q.id, "category": q.category, "status": "ambiguous_entity_409",
                             "ambiguity_handled": q.expect_ambiguous,
                             "candidates": len((exc.details or {}).get("candidates", []))})  # fmt: skip
                typer.echo(
                    f"{q.id:<34} 409 ambiguous ({'expected' if q.expect_ambiguous else 'UNEXPECTED'})"
                )
                continue
            except HerbaGuardError as exc:
                rows.append({"id": q.id, "category": q.category, "error": exc.message})
                typer.echo(f"{q.id:<34} ERROR {exc.message[:80]}")
                continue
            if q.expect_ambiguous:
                typer.echo(f"{q.id:<34} NOT flagged as ambiguous")
            expected = set()
            for c in response.classification:
                check = interaction_service.check(
                    session, settings, herb_query=c.herb, drug_queries=[c.drug], allow_remote=False
                )
                expected |= {r.classification.interaction_class.value for r in check.results}
            row = generation_checks(response, expected, q)
            rows.append(row)
            typer.echo(f"{q.id:<34} {row['status']:<24} mode={row['generation_mode']:<10} cites={row['citations']:<2} "
                       f"removed={row['removed_paragraphs']} critical={','.join(row['critical_issues']) or '-'} "
                       f"{row['latency_ms'] / 1000:.0f}s")  # fmt: skip
    finally:
        session.close()
    summary = summarise_generation(rows)
    typer.echo(json.dumps(summary, indent=2))
    if output:
        report = {"dataset": data.label, "generated_at": datetime.now(UTC).isoformat(),
                  "provider": settings.llm_provider.value, "model": settings.llm_model,
                  "summary": summary, "questions": rows}  # fmt: skip
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        typer.echo(f"Report written to {output}")
