"""``herbaguard`` command-line interface for the data pipeline."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import typer
from sqlalchemy import text

from herbaguard import __version__
from herbaguard.core.config import get_settings
from herbaguard.core.db import get_session_factory
from herbaguard.core.logging import configure_logging
from herbaguard.ingestion.context import IngestionContext, run_ingestion
from herbaguard.ingestion.sources import SOURCES

app = typer.Typer(help="HerbaGuard data pipeline.", no_args_is_help=True)
ingest_app = typer.Typer(
    help="Run ingestion pipelines (order: sources, taxonomy, ema, nccih, labels, pubmed, mechanisms)."
)
app.add_typer(ingest_app, name="ingest")

from herbaguard.ai.cli import ai_app  # noqa: E402 - registered after the ingest group

app.add_typer(ai_app, name="ai")

HerbOption = Annotated[
    list[str] | None, typer.Option("--herb", help="Limit to curated herb key(s).")
]


@app.command()
def version() -> None:
    """Print the HerbaGuard version."""
    typer.echo(__version__)


@app.command("sources")
def list_sources() -> None:
    """List registered data sources and their licence status."""
    for source in SOURCES:
        official = "official" if source.is_official else "wrapper"
        typer.echo(
            f"{source.priority}  {source.code:<18} {official:<8} licence={source.licence_status.value:<9} {source.name}"
        )


def _run(
    source_code: str, pipeline: Callable[[IngestionContext], None], parameters: dict[str, object]
) -> None:
    settings = get_settings()
    configure_logging(settings)
    session = get_session_factory()()
    started = time.perf_counter()
    try:
        from herbaguard.ingestion.loaders import ensure_sources

        ensure_sources(session)
        session.commit()
        with run_ingestion(session, source_code, settings, parameters=parameters) as ctx:
            pipeline(ctx)
            stats = dict(ctx.stats)
            status_note = "with data-quality errors" if ctx.error_issues else "ok"
        typer.echo(
            f"[{source_code}] finished in {time.perf_counter() - started:.1f}s ({status_note})"
        )
        for key in sorted(stats):
            typer.echo(f"    {key}: {stats[key]}")
    finally:
        session.close()


@ingest_app.command("sources")
def ingest_sources() -> None:
    """Register/refresh the source table (licence metadata)."""
    session = get_session_factory()()
    try:
        from herbaguard.ingestion.loaders import ensure_sources

        n = ensure_sources(session)
        session.commit()
        typer.echo(f"{n} sources registered")
    finally:
        session.close()


@ingest_app.command("taxonomy")
def ingest_taxonomy(herb: HerbOption = None) -> None:
    from herbaguard.ingestion.pipelines import taxonomy

    _run("wfo_ethcstwin", lambda ctx: taxonomy.run(ctx, herb), {"herbs": herb})


@ingest_app.command("ema")
def ingest_ema(herb: HerbOption = None) -> None:
    from herbaguard.ingestion.pipelines import ema

    _run("ema_hmpc", lambda ctx: ema.run(ctx, herb), {"herbs": herb})


@ingest_app.command("nccih")
def ingest_nccih(herb: HerbOption = None) -> None:
    from herbaguard.ingestion.pipelines import nccih

    _run("nccih", lambda ctx: nccih.run(ctx, herb), {"herbs": herb})


@ingest_app.command("labels")
def ingest_labels(
    herb: HerbOption = None,
    max_pages: Annotated[
        int,
        typer.Option(
            help="Pages of 100 labels per herb (openFDA: 1,000 requests/day without key)."
        ),
    ] = 5,
) -> None:
    from herbaguard.ingestion.pipelines import labels

    _run(
        "openfda_label",
        lambda ctx: labels.run(ctx, herb, max_pages),
        {"herbs": herb, "max_pages": max_pages},
    )


@ingest_app.command("pubmed")
def ingest_pubmed(herb: HerbOption = None) -> None:
    from herbaguard.ingestion.pipelines import pubmed

    _run("pubmed", lambda ctx: pubmed.run(ctx, herb), {"herbs": herb})


@ingest_app.command("mechanisms")
def ingest_mechanisms(
    herb: HerbOption = None,
    fda_html_file: Annotated[
        Path | None,
        typer.Option(
            help="Saved copy of the FDA CYP/transporter page, if fda.gov refuses automated requests.",
            exists=True,
            dir_okay=False,
        ),
    ] = None,
) -> None:
    """Enzymes/transporters, herb effects from EU monographs (stored in the ema step) and drug
    roles from the FDA CYP/transporter table. Run after taxonomy and ema."""
    from herbaguard.ingestion.pipelines import mechanisms

    _run(
        "ema_hmpc", lambda ctx: mechanisms.run_ema(ctx, herb), {"step": "mechanisms", "herbs": herb}
    )
    _run(
        "fda_cyp_table",
        lambda ctx: mechanisms.run_fda(ctx, fda_html_file),
        {"html_file": fda_html_file.name if fda_html_file else None},
    )


@ingest_app.command("ddid")
def ingest_ddid(
    directory: Annotated[
        Path | None,
        typer.Option(
            help="Folder with the five DDID CSV files (default: <raw data dir>/ddid).",
            exists=True,
            file_okay=False,
        ),
    ] = None,
) -> None:
    """DDID experimental herb/food–drug records, herbs, drugs, natural products and TTD targets
    (local CSV files; nothing is downloaded). Run after taxonomy and labels/rxnav."""
    from herbaguard.ingestion.pipelines import ddid

    folder = directory or Path(get_settings().raw_data_dir) / "ddid"
    _run("ddid", lambda ctx: ddid.run(ctx, folder), {"directory": str(folder)})


DatasetFolder = Annotated[
    Path | None,
    typer.Option(help="Folder with the downloaded files (default: <raw data dir>/<source>).",
                 exists=True, file_okay=False),
]  # fmt: skip


@ingest_app.command("supp-ai")
def ingest_supp_ai(directory: DatasetFolder = None) -> None:
    """SUPP.AI supplement–drug interaction mentions for curated herbs (automatically extracted
    sentences; never confirmed interactions). Local files only. Run after taxonomy and labels/rxnav."""
    from herbaguard.ingestion.pipelines import supp_ai

    folder = directory or Path(get_settings().raw_data_dir) / "supp_ai"
    _run("supp_ai", lambda ctx: supp_ai.run(ctx, folder), {"directory": str(folder)})


@ingest_app.command("livertox")
def ingest_livertox(directory: DatasetFolder = None) -> None:
    """LiverTox hepatotoxicity chapters and agent master list (local files only). Run after
    taxonomy and labels/rxnav."""
    from herbaguard.ingestion.pipelines import livertox

    folder = directory or Path(get_settings().raw_data_dir) / "livertox"
    _run("livertox", lambda ctx: livertox.run(ctx, folder), {"directory": str(folder)})


@ingest_app.command("nih-dsld")
def ingest_nih_dsld(directory: DatasetFolder = None) -> None:
    """NIH DSLD product labels and ingredient composition for products that list a curated herb
    (local CSV files only). Run after taxonomy."""
    from herbaguard.ingestion.pipelines import nih_dsld

    folder = directory or Path(get_settings().raw_data_dir) / "nih_dsld"
    _run("nih_dsld", lambda ctx: nih_dsld.run(ctx, folder), {"directory": str(folder)})


@ingest_app.command("all")
def ingest_all(herb: HerbOption = None, max_pages: int = 5) -> None:
    """Run every pipeline in dependency order."""
    ingest_sources()
    ingest_taxonomy(herb)
    ingest_ema(herb)
    ingest_nccih(herb)
    ingest_labels(herb, max_pages)
    ingest_pubmed(herb)
    ingest_mechanisms(herb)


@app.command()
def validate() -> None:
    """Validate the ingested data; exits with code 1 if any check fails."""
    from herbaguard.ingestion.validate import run_all

    session = get_session_factory()()
    try:
        results = run_all(session)
    finally:
        session.close()
    symbols = {"pass": "PASS", "warn": "WARN", "fail": "FAIL"}
    for result in results:
        typer.echo(f"[{symbols[result.status]}] {result.name}: {result.detail}")
    if any(r.status == "fail" for r in results):
        raise typer.Exit(code=1)


@app.command()
def report() -> None:
    """Counts per table, latest run per source, and data-quality issues by rule."""
    session = get_session_factory()()
    try:
        typer.echo("== Table counts")
        for table in ("source", "ingestion_run", "source_record", "provenance", "data_quality_issue", "taxon", "taxon_name",
                      "herbal_substance", "drug", "drug_class", "drug_class_membership", "evidence_item", "chunk",
                      "herbal_substance_evidence", "indication", "interaction_assertion", "target",
                      "target_modulation", "drug_target_role", "constituent",
                      "herbal_substance_constituent"):  # fmt: skip
            count = session.execute(text(f"SELECT count(*) FROM {table}")).scalar()  # noqa: S608 - fixed names
            typer.echo(f"  {table:<28} {count}")
        typer.echo("== Latest run per source")
        rows = session.execute(text(
            "SELECT DISTINCT ON (source_code) source_code, status, started_at, finished_at FROM ingestion_run "
            "ORDER BY source_code, started_at DESC"
        )).all()  # fmt: skip
        for source, status, started, finished in rows:
            duration = (finished - started).total_seconds() if finished else None
            typer.echo(
                f"  {source:<16} {status:<10} {started:%Y-%m-%d %H:%M} {f'{duration:.0f}s' if duration else ''}"
            )
        typer.echo("== Data-quality issues (latest run per source)")
        rows = session.execute(text(
            "SELECT r.source_code, i.severity, i.rule, count(*) FROM data_quality_issue i JOIN ingestion_run r ON r.id=i.ingestion_run_id "
            "WHERE r.id IN (SELECT DISTINCT ON (source_code) id FROM ingestion_run ORDER BY source_code, started_at DESC) "
            "GROUP BY 1,2,3 ORDER BY 1,2,4 DESC"
        )).all()  # fmt: skip
        for source, severity, rule, count in rows:
            typer.echo(f"  {source:<16} {severity:<8} {rule:<48} {count}")
        typer.echo("== Interaction assertions by source and statement type")
        rows = session.execute(
            text(
                "SELECT source_code, statement_type, count(*) FROM interaction_assertion GROUP BY 1,2 ORDER BY 1,2"
            )
        ).all()
        for source, statement, count in rows:
            typer.echo(f"  {source:<16} {statement:<26} {count}")
        typer.echo("== Mechanism edges by source")
        rows = session.execute(
            text(
                "SELECT 'target_modulation', source_code, evidence_type, count(*) FROM target_modulation "
                "GROUP BY 2,3 UNION ALL SELECT 'drug_target_role', source_code, role, count(*) "
                "FROM drug_target_role GROUP BY 2,3 ORDER BY 1,2,3"
            )
        ).all()
        for table, source, kind, count in rows:
            typer.echo(f"  {table:<18} {source:<16} {kind:<32} {count}")
        typer.echo("== Evidence items by source and type")
        rows = session.execute(
            text(
                "SELECT source_code, evidence_type, count(*) FROM evidence_item GROUP BY 1,2 ORDER BY 1,2"
            )
        ).all()
        for source, etype, count in rows:
            typer.echo(f"  {source:<16} {etype:<8} {count}")
    finally:
        session.close()


@app.command("ema-report")
def ema_report() -> None:
    """Markdown table: per EMA monograph and required section, extraction completeness per use
    category and the PDFium cross-check result. Generated from the database."""
    from herbaguard.ingestion.parsers.ema_monograph import REQUIRED_SECTIONS

    session = get_session_factory()()
    try:
        rows = session.execute(
            text(
                "SELECT metadata->>'herb_key', external_id, document_date, metadata->'extraction' "
                "FROM evidence_item WHERE source_code='ema_hmpc' AND metadata ? 'extraction' "
                "ORDER BY metadata->>'herb_key'"
            )
        ).all()
        sections_present = session.execute(
            text(
                "SELECT metadata->>'herb_key', metadata->>'section', metadata->>'use_category', "
                "metadata->>'section_statement' FROM evidence_item WHERE source_code='ema_hmpc' "
                "AND metadata ? 'section'"
            )
        ).all()
    finally:
        session.close()
    statements = {(h, s, c): st for h, s, c, st in sections_present}
    header = (
        "| Herb | Document | Use categories | "
        + " | ".join(REQUIRED_SECTIONS)
        + " | Token coverage |"
    )
    typer.echo(header)
    typer.echo("|" + "---|" * (len(REQUIRED_SECTIONS) + 4))
    for herb, document, doc_date, extraction in rows:
        categories = extraction["use_categories"]
        checks = {(c["section"], c["use_category"]): c for c in extraction["crosscheck"]}
        cells = []
        for section in REQUIRED_SECTIONS:
            status = extraction["completeness"].get(section, "missing")
            parts = []
            for category in categories:
                check = checks.get((section, category))
                short = "WEU" if category.startswith("well") else "TU"
                verdict = check["status"] if check else "n/a"
                mark = {"verified": "✓", "both_empty": "∅", "mismatch": "✗"}.get(verdict, "?")
                none = (
                    " (none reported)"
                    if statements.get((herb, section, category)) == "none_reported"
                    else ""
                )
                parts.append(f"{short} {mark}{none}")
            cells.append(f"{status}: " + ", ".join(parts))
        short_categories = ", ".join("WEU" if c.startswith("well") else "TU" for c in categories)
        typer.echo(
            f"| {herb} | {document} ({doc_date}) | {short_categories} | "
            + " | ".join(cells)
            + f" | {extraction['document_token_coverage']:.4f} |"
        )


if __name__ == "__main__":
    app()
