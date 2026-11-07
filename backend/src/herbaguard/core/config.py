"""Application settings, loaded from environment variables (prefix ``HERBAGUARD_``)."""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import Field, PostgresDsn, SecretStr, field_validator, model_validator
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


class LLMProviderName(StrEnum):
    """Answer generators. ``extractive`` composes answers from stored excerpts without a model."""

    OLLAMA = "ollama"
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    EXTRACTIVE = "extractive"


class EmbeddingProviderName(StrEnum):
    OLLAMA = "ollama"
    NONE = "none"  # keyword retrieval only


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

    # ----------------------------------------------------------------- Phase 5: AI layer
    # Generation. The provider is chosen by configuration only; HerbaGuard never switches
    # provider on its own. A fallback is used only when configured explicitly.
    llm_provider: LLMProviderName = LLMProviderName.OLLAMA
    llm_model: str = "qwen3:4b"  # used by the Ollama provider
    llm_fallback_provider: LLMProviderName | None = None
    llm_timeout_seconds: float = Field(default=240.0, gt=0)
    llm_temperature: float = Field(default=0.0, ge=0, le=2)
    llm_seed: int = 42
    llm_max_output_tokens: int = Field(default=900, ge=64, le=8192)
    # Controlled regeneration: if the answer is malformed or fails validation, the same provider is
    # asked again (once by default) with the list of problems; then the fallback chain applies.
    llm_max_regenerations: int = Field(default=1, ge=0, le=3)
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_num_ctx: int = Field(default=8192, ge=2048)
    # How long Ollama keeps the model in memory after a request. Ollama's own default is 5 minutes;
    # after that the next question pays the full model load (measured ~100 s on the CPU-only
    # development machine). It does not change what is generated.
    ollama_keep_alive: str = "30m"
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str | None = None  # no default: the model is chosen by the operator
    anthropic_base_url: str = "https://api.anthropic.com"
    openai_api_key: SecretStr | None = None
    openai_model: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    # Licensing guard: source text is sent to a cloud provider only if this is true AND the
    # evidence comes from a source registered as redistributable (source.redistributable).
    ai_cloud_send_source_text: bool = False

    # Embeddings (independent of the generation provider).
    embedding_provider: EmbeddingProviderName = EmbeddingProviderName.OLLAMA
    embedding_model: str = (
        "nomic-embed-text"  # chosen by the Phase 5 benchmark (docs/ai/embedding-models.md)
    )
    embedding_batch_size: int = Field(default=16, ge=1, le=256)
    embedding_timeout_seconds: float = Field(default=120.0, gt=0)
    # Prefixes some models need (e.g. nomic-embed-text: "search_query: ", "search_document: ").
    embedding_query_prefix: str = ""
    embedding_document_prefix: str = ""

    # Segmentation (retrieval units cut from stored chunks; see docs/ai/hybrid-retrieval.md).
    segment_strategy: str = "sentence_window"
    segment_max_chars: int = Field(default=1200, ge=200, le=8000)
    segment_overlap_sentences: int = Field(default=1, ge=0, le=5)
    # Per-source overrides, e.g. {"pubmed": "whole_chunk"} / {"openfda_label": 1500}. New sources
    # use the defaults above without any code change.
    segment_strategy_by_source: dict[str, str] = Field(default_factory=dict)
    segment_max_chars_by_source: dict[str, int] = Field(default_factory=dict)

    # Retrieval (benchmarkable configuration, not scientific assumptions).
    retrieval_keyword_top_k: int = Field(default=40, ge=1, le=500)
    retrieval_vector_top_k: int = Field(default=40, ge=1, le=500)
    retrieval_top_k: int = Field(default=10, ge=1, le=100)
    retrieval_rrf_k: int = Field(default=60, ge=1)
    retrieval_keyword_weight: float = Field(default=1.0, ge=0)
    retrieval_vector_weight: float = Field(default=1.0, ge=0)
    retrieval_min_similarity: float = Field(default=0.0, ge=-1, le=1)
    retrieval_max_per_evidence_item: int = Field(default=2, ge=1, le=20)
    # Optional multiplicative preference per source code, e.g. {"ema_hmpc": 1.2}. Empty = neutral.
    retrieval_source_weights: dict[str, float] = Field(default_factory=dict)

    # Context assembly and request limits.
    ai_question_max_chars: int = Field(default=1000, ge=10, le=10000)
    ai_context_max_tokens: int = Field(default=2600, ge=500, le=100000)
    ai_context_max_items: int = Field(default=8, ge=1, le=50)
    ai_max_concurrent_requests: int = Field(default=2, ge=1, le=64)
    # Validated-answer cache for the suggested questions (see ai/answer_cache.py). A cached answer is
    # served only while its fingerprint still matches the current evidence, prompts and validation.
    ai_answer_cache_enabled: bool = True
    ai_answer_cache_max_age_days: int = Field(default=30, ge=1, le=365)
    # Questions in which no herb, drug, enzyme, transporter or constituent is recognised: retrieved
    # passages are used only if their semantic similarity reaches this value (keyword-only matches
    # are not used), so unrelated text is not presented as an answer. Benchmarkable.
    ai_unscoped_min_similarity: float = Field(default=0.6, ge=-1, le=1)

    @field_validator(
        "llm_fallback_provider", "anthropic_api_key", "anthropic_model", "openai_api_key",
        "openai_model", mode="before",
    )  # fmt: skip
    @classmethod
    def _empty_is_unset(cls, value: object) -> object:
        """``HERBAGUARD_X=`` (empty, as Docker Compose passes unset variables) means "not set"."""
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def _distinct_fallback(self) -> Settings:
        if (
            self.llm_fallback_provider is not None
            and self.llm_fallback_provider == self.llm_provider
        ):
            msg = "llm_fallback_provider must differ from llm_provider"
            raise ValueError(msg)
        return self

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
