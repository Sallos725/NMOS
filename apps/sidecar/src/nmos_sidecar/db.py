"""Connection pool."""

from __future__ import annotations

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


def make_pool(database_url: str) -> ConnectionPool:
    return ConnectionPool(
        database_url,
        min_size=1,
        max_size=8,
        kwargs={"row_factory": dict_row, "autocommit": False},
        open=True,
    )
