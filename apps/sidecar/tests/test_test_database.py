"""An unavailable test database must fail CI while local DB-free runs may skip it."""

import psycopg
import pytest

import conftest


@pytest.mark.parametrize("required", [False, True])
def test_unreachable_database_fails_only_when_required(monkeypatch, required):
    def unreachable(*args, **kwargs):
        raise psycopg.OperationalError("test server unavailable")

    monkeypatch.setattr(conftest, "REQUIRE_DB", required)
    monkeypatch.setattr(conftest.psycopg, "connect", unreachable)
    expected = pytest.fail.Exception if required else pytest.skip.Exception
    with pytest.raises(expected, match="test server unavailable"):
        conftest.connect_admin()
