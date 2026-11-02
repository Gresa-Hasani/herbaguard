"""``herbaguard`` command-line interface. Ingestion commands are added in Phase 2."""

from __future__ import annotations

import typer

from herbaguard import __version__
from herbaguard.ingestion.sources import SOURCES

app = typer.Typer(help="HerbaGuard data pipeline.", no_args_is_help=True)


@app.command()
def version() -> None:
    """Print the HerbaGuard version."""
    typer.echo(__version__)


@app.command("sources")
def list_sources() -> None:
    """List the data sources selected in the Phase 0 audit and their licence status."""
    for source in SOURCES:
        official = "official" if source.is_official else "wrapper"
        typer.echo(
            f"{source.priority}  {source.code:<16} {official:<8} "
            f"licence={source.licence_status.value:<9} {source.name}"
        )


if __name__ == "__main__":
    app()
