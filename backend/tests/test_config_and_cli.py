"""Settings validation, model metadata invariants and the CLI stub."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from herbaguard import __version__
from herbaguard.core.config import Environment, LogFormat, Settings
from herbaguard.ingestion.cli import app as cli_app
from herbaguard.ingestion.sources import SOURCES, get_source
from herbaguard.models import Base
from herbaguard.models.base import MAX_IDENTIFIER_LENGTH


def test_log_format_defaults_depend_on_environment() -> None:
    assert Settings(environment=Environment.DEVELOPMENT).effective_log_format is LogFormat.CONSOLE
    assert Settings(environment=Environment.PRODUCTION).effective_log_format is LogFormat.JSON
    explicit = Settings(environment=Environment.PRODUCTION, log_format=LogFormat.CONSOLE)
    assert explicit.effective_log_format is LogFormat.CONSOLE


def test_log_level_is_validated() -> None:
    assert Settings(log_level="debug").log_level == "DEBUG"
    with pytest.raises(ValidationError):
        Settings(log_level="verbose")


def test_database_url_must_be_postgres() -> None:
    with pytest.raises(ValidationError):
        Settings(database_url="mysql://user:pw@localhost/db")  # type: ignore[arg-type]


def test_settings_read_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERBAGUARD_ENVIRONMENT", "production")
    monkeypatch.setenv("HERBAGUARD_CORS_ORIGINS", '["https://example.org"]')
    settings = Settings()
    assert settings.environment is Environment.PRODUCTION
    assert settings.cors_origins == ["https://example.org"]


def test_all_constraint_and_index_names_fit_postgres_limit() -> None:
    names: list[str] = []
    for table in Base.metadata.tables.values():
        names.extend(str(c.name) for c in table.constraints if c.name)
        names.extend(str(i.name) for i in table.indexes if i.name)
    too_long = [name for name in names if len(name) > MAX_IDENTIFIER_LENGTH]
    assert too_long == []


def test_every_table_has_a_primary_key() -> None:
    assert all(table.primary_key.columns for table in Base.metadata.tables.values())


def test_source_registry_is_consistent() -> None:
    codes = [source.code for source in SOURCES]
    assert len(codes) == len(set(codes))
    assert get_source("ema_hmpc").priority == "P0"
    with pytest.raises(KeyError):
        get_source("drugbank")  # excluded in the Phase 0 audit (licence)


def test_cli_version_and_sources() -> None:
    runner = CliRunner()
    version = runner.invoke(cli_app, ["version"])
    assert version.exit_code == 0
    assert version.stdout.strip() == __version__

    sources = runner.invoke(cli_app, ["sources"])
    assert sources.exit_code == 0
    assert "ema_hmpc" in sources.stdout
    assert "wrapper" in sources.stdout  # the ETHCSTWIN source is marked as non-official
