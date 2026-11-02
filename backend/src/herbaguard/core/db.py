"""Database engine and session management (SQLAlchemy 2, synchronous psycopg 3 driver).

A synchronous driver keeps ingestion scripts, Alembic and the API on one code path.
FastAPI runs sync dependencies in a thread pool, which is sufficient for this workload.
"""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from herbaguard.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    return create_engine(
        settings.sqlalchemy_url,
        pool_size=settings.db_pool_size,
        pool_pre_ping=True,
        echo=settings.db_echo,
    )


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False, autoflush=False)


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one session per request, rolled back on error."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def check_database(engine: Engine | None = None) -> bool:
    """Return True if the database answers a trivial query."""
    engine = engine or get_engine()
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return True
