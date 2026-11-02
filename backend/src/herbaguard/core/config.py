"""Application settings, loaded from environment variables (prefix ``HERBAGUARD_``)."""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import Field, PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class LogFormat(StrEnum):
    CONSOLE = "console"
    JSON = "json"


DISCLAIMER = (
    "HerbaGuard provides information from scientific and regulatory sources. "
    "It is not medical advice and does not replace your doctor or pharmacist. "
    "The absence of a reported interaction does not mean a combination is safe."
)


class Settings(BaseSettings):
    """Runtime configuration. Every field can be set via ``HERBAGUARD_<FIELD_NAME>``."""

    model_config = SettingsConfigDict(
        env_prefix="HERBAGUARD_",
        # The repository-root .env is found whether commands run from the root or from backend/.
        # Real environment variables always take precedence over both files.
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Environment = Environment.DEVELOPMENT
    log_level: str = "INFO"
    log_format: LogFormat | None = Field(
        default=None,
        description="Defaults to JSON in production and console otherwise.",
    )

    database_url: PostgresDsn = Field(
        # Port 5455 matches the docker-compose default host port.
        default=PostgresDsn("postgresql+psycopg://herbaguard:herbaguard@127.0.0.1:5455/herbaguard"),
    )
    db_pool_size: int = Field(default=5, ge=1, le=50)
    db_echo: bool = False

    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    # Directory for raw source snapshots (git-ignored). Used from Phase 2 on.
    raw_data_dir: Path = Path("../data/raw")

    # Polite identification for external APIs (NCBI, Wikidata and openFDA ask for it).
    # Wikimedia's robot policy rejects (HTTP 403) user agents without contact information.
    http_user_agent: str = "HerbaGuard/0.1 (+https://github.com/Gresa-Hasani/herbaguard; EthnoHack 2026 research prototype)"
    http_timeout_seconds: float = Field(default=30.0, gt=0)
    contact_email: str | None = None

    @field_validator("log_level")
    @classmethod
    def _normalise_log_level(cls, value: str) -> str:
        level = value.upper()
        if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            msg = f"Unsupported log level: {value}"
            raise ValueError(msg)
        return level

    @property
    def effective_log_format(self) -> LogFormat:
        if self.log_format is not None:
            return self.log_format
        return LogFormat.JSON if self.environment is Environment.PRODUCTION else LogFormat.CONSOLE

    @property
    def sqlalchemy_url(self) -> str:
        return str(self.database_url)


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings (cached). Tests may call ``get_settings.cache_clear()``."""
    return Settings()
