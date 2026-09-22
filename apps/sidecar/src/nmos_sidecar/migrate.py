"""Apply numbered SQL migrations in order; refuse if an applied file was edited."""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

import psycopg

from .config import Settings


def migrations_dir() -> Path:
    env = os.environ.get("NMOS_MIGRATIONS_DIR")
    return Path(env) if env else Path(__file__).resolve().parents[4] / "migrations"


def apply_migrations(database_url: str, directory: Path | None = None) -> list[str]:
    directory = directory or migrations_dir()
    files = sorted(p for p in directory.glob("[0-9][0-9][0-9][0-9]_*.sql"))
    applied_now: list[str] = []
    with psycopg.connect(database_url, autocommit=True) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            " version text PRIMARY KEY, checksum text NOT NULL, applied_at timestamptz NOT NULL DEFAULT now())"
        )
        conn.execute("SELECT pg_advisory_lock(727001)")
        try:
            applied = dict(conn.execute("SELECT version, checksum FROM schema_migrations").fetchall())
            for path in files:
                sql = path.read_text(encoding="utf-8")
                checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
                if path.name in applied:
                    if applied[path.name] != checksum:
                        raise RuntimeError(f"applied migration {path.name} was modified; add a new migration instead")
                    continue
                with conn.transaction():
                    conn.execute(sql)
                    conn.execute("INSERT INTO schema_migrations (version, checksum) VALUES (%s, %s)", (path.name, checksum))
                applied_now.append(path.name)
        finally:
            conn.execute("SELECT pg_advisory_unlock(727001)")
    return applied_now


def main() -> None:
    applied = apply_migrations(Settings().database_url)
    print("applied:", ", ".join(applied) if applied else "nothing (up to date)")
    sys.exit(0)


if __name__ == "__main__":
    main()
