"""Cost of the worker's superseded-vector pruning pass (ADR 0015) on large chats.

Syncs a `bench_scale.py` chat into a throwaway database on the compose PostgreSQL, writes two chunks
per revision for two embedding projections (the older one superseded), then times the first pass
(deletes every superseded vector) and passes with nothing left to prune.

    cd apps/sidecar && uv run python ../../tools/bench_prune.py 1000,10000
"""

from __future__ import annotations

import random
import statistics
import sys
import time
import uuid
from pathlib import Path

import psycopg
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bench_scale as scale  # noqa: E402

from nmos_sidecar import generations, retention  # noqa: E402
from nmos_sidecar.api import create_app  # noqa: E402
from nmos_sidecar.config import Settings  # noqa: E402
from nmos_sidecar.migrate import apply_migrations  # noqa: E402
from nmos_sidecar.vectors import vector_literal  # noqa: E402

CHUNKS = 2


def run(n: int) -> None:
    name = f"nmos_bench_{uuid.uuid4().hex[:10]}"
    with psycopg.connect(scale.ADMIN_URL, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{name}"')
    url = f"{scale.ADMIN_URL.rpartition('/')[0]}/{name}"
    try:
        apply_migrations(url)
        with TestClient(create_app(Settings(database_url=url, auth_token=""))) as client:
            scale.sync(client, scale.build_chat(n))
        with psycopg.connect(url, row_factory=dict_row, autocommit=True) as conn:
            old = generations.make("embed", "http://old/v1", "m")
            new = generations.make("embed", "http://new/v1", "m")
            generations.activate(conn, old)
            generations.activate(conn, new)
            rids = [r["id"] for r in conn.execute(
                "SELECT source_revision_id AS id FROM revision_text WHERE clean_chars > 0").fetchall()]
            vec = vector_literal([random.random() for _ in range(scale.DIM)])
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO revision_embedding (source_revision_id, projection, model, chunk, dim, text_start,"
                    " text_end, embedding) VALUES (%s, %s, 'm', %s, %s, 0, 10, %s::vector)",
                    [(rid, key, chunk, scale.DIM, vec) for key in (old.key, new.key) for rid in rids
                     for chunk in range(CHUNKS)])
            conn.execute("ANALYZE")
            started = time.perf_counter()
            deleted = retention.prune_embeddings(conn)
            first = (time.perf_counter() - started) * 1000
            idle = []
            for _ in range(5):
                started = time.perf_counter()
                assert retention.prune_embeddings(conn) == 0
                idle.append((time.perf_counter() - started) * 1000)
            print(f"{n} messages: first pass {deleted} vectors in {first:.0f} ms;"
                  f" nothing to prune p50 {statistics.median(idle):.0f} ms, max {max(idle):.0f} ms")
    finally:
        with psycopg.connect(scale.ADMIN_URL, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


if __name__ == "__main__":
    for size in (sys.argv[1] if len(sys.argv) > 1 else "1000,10000").split(","):
        run(int(size))
