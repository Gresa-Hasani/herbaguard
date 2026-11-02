"""Structured logging setup based on structlog.

Standard-library loggers (uvicorn, sqlalchemy, alembic) are routed through the same
renderer so that production logs are one JSON object per line.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

from herbaguard.core.config import LogFormat, Settings


def configure_logging(settings: Settings) -> None:
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
    ]

    renderer: Any
    if settings.effective_log_format is LogFormat.JSON:
        renderer = structlog.processors.JSONRenderer()
        shared_processors.append(structlog.processors.format_exc_info)
    else:
        # Plain tracebacks: the default "rich" formatter prints local variables, which could
        # expose user input (e.g. medication names) in logs.
        renderer = structlog.dev.ConsoleRenderer(exception_formatter=structlog.dev.plain_traceback)

    structlog.configure(
        processors=[*shared_processors, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, renderer],
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(settings.log_level)

    # Uvicorn installs its own handlers; let records propagate to the root handler instead.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True

    # Uvicorn's access log records full URLs including query strings, which may contain
    # medication names typed by users. RequestContextMiddleware logs method, path and status
    # only, so the access log is silenced.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    logger: structlog.stdlib.BoundLogger = structlog.stdlib.get_logger(name)
    return logger
