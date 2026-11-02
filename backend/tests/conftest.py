"""Shared fixtures.

Database tests (marker ``db``) run against a dedicated ``<name>_test`` database that is
created and migrated per test session, so development data is never touched. They are
skipped when no PostgreSQL server is reachable.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from herbaguard.api.routes.health import get_database_check
from herbaguard.core.config import Environment, Settings, get_settings
from herbaguard.main import create_app

BACKEND_DIR = __import__("pathlib").Path(__file__).resolve().parents[1]


@pytest.fixture
def settings() -> Settings:
    return Settings(environment=Environment.TEST, log_level="WARNING")


@pytest.fixture
def make_client(settings: Settings) -> Callable[..., TestClient]:
    def _make(database_ok: bool = True) -> TestClient:
        app = create_app(settings)

        def fake_check() -> bool:
            if not database_ok:
                raise OSError("connection refused")
            return True

        app.dependency_overrides[get_database_check] = lambda: fake_check
        app.dependency_overrides[get_settings] = lambda: settings
        return TestClient(app, raise_server_exceptions=False)

    return _make


@pytest.fixture
def client(make_client: Callable[..., TestClient]) -> TestClient:
    return make_client()


# --------------------------------------------------------------------------- database


def _test_database_url() -> str:
    url = make_url(get_settings().sqlalchemy_url)
    return url.set(database=f"{url.database}_test").render_as_string(hide_password=False)


def _admin_conninfo(url: str) -> str:
    parsed = make_url(url)
    return (
        f"host={parsed.host} port={parsed.port} user={parsed.username} "
        f"password={parsed.password} dbname=postgres connect_timeout=3"
    )


@pytest.fixture(scope="session")
def migrated_engine() -> Iterator[Engine]:
    url = _test_database_url()
    database = make_url(url).database
    try:
        admin = psycopg.connect(_admin_conninfo(url), autocommit=True)
    except psycopg.OperationalError as exc:
        pytest.skip(f"PostgreSQL not reachable: {exc}")

    with admin:
        admin.execute(f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)')
        admin.execute(f'CREATE DATABASE "{database}"')

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")

    engine = create_engine(url)
    try:
        yield engine
    finally:
        engine.dispose()
        with psycopg.connect(_admin_conninfo(url), autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)')


@pytest.fixture
def alembic_config() -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", _test_database_url())
    return config


@pytest.fixture
def db_session(migrated_engine: Engine) -> Iterator[Session]:
    """A session whose changes are rolled back after each test."""
    connection = migrated_engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection, join_transaction_mode="create_savepoint")()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
