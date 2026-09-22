"""Integration fixtures: a throwaway database on the compose Postgres (NMOS_TEST_ADMIN_URL)."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

from nmos_sidecar.api import create_app
from nmos_sidecar.config import Settings
from nmos_sidecar.migrate import apply_migrations

ADMIN_URL = os.environ.get("NMOS_TEST_ADMIN_URL", "postgresql://nmos:nmos@127.0.0.1:5436/postgres")
TOKEN = "test-token"


def _db_url(name: str) -> str:
    base, _, _ = ADMIN_URL.rpartition("/")
    return f"{base}/{name}"


@pytest.fixture
def database_url() -> Iterator[str]:
    name = f"nmos_test_{uuid.uuid4().hex[:12]}"
    try:
        admin = psycopg.connect(ADMIN_URL, autocommit=True)
    except psycopg.OperationalError as exc:  # pragma: no cover
        pytest.skip(f"Postgres not reachable at {ADMIN_URL}: {exc}")
    with admin:
        admin.execute(f'CREATE DATABASE "{name}"')
    url = _db_url(name)
    try:
        yield url
    finally:
        with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


@pytest.fixture
def database_url_factory() -> Iterator:
    """Create any number of migrated throwaway databases; all dropped afterwards."""
    names: list[str] = []

    def make() -> str:
        name = f"nmos_test_{uuid.uuid4().hex[:12]}"
        with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
            admin.execute(f'CREATE DATABASE "{name}"')
        names.append(name)
        apply_migrations(_db_url(name))
        return _db_url(name)

    yield make
    with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
        for name in names:
            admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


@pytest.fixture
def migrated(database_url: str) -> str:
    apply_migrations(database_url)
    return database_url


def make_client(url: str, **overrides) -> TestClient:
    settings = Settings(database_url=url, auth_token=TOKEN, cors_origins=("http://localhost:6101",), **overrides)
    client = TestClient(create_app(settings))
    client.headers["Authorization"] = f"Bearer {TOKEN}"
    return client


@pytest.fixture
def client(migrated: str) -> Iterator[TestClient]:
    with make_client(migrated) as c:
        yield c


@pytest.fixture
def db(migrated: str) -> Iterator[psycopg.Connection]:
    with psycopg.connect(migrated, row_factory=dict_row, autocommit=True) as conn:
        yield conn
