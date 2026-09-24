"""Fact read with item assertions (Phase 6 facts tier, docs/phases/PHASE-6.md "Performance").

Syncs a `bench_scale.py` chat into a throwaway database, adds one stub extraction per turn with two
assertions (a character's place, and an item's holder, place or end cycling over 60 items), and times
`fact_versions` (run on every request with extraction on). Run it on two checkouts to compare folds:

    cd apps/sidecar && uv run python ../../tools/bench_facts.py 1000,5000,10000
    PYTHONPATH=/path/to/other/checkout/apps/sidecar/src uv run python ../../tools/bench_facts.py 10000
"""

from __future__ import annotations

import json
import sys
import time
import uuid
from pathlib import Path

import psycopg
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bench_scale as scale  # noqa: E402

import nmos_sidecar  # noqa: E402
from nmos_sidecar import generations  # noqa: E402
from nmos_sidecar.api import create_app  # noqa: E402
from nmos_sidecar.config import Settings  # noqa: E402
from nmos_sidecar.facts import fact_versions  # noqa: E402
from nmos_sidecar.ids import uuid7  # noqa: E402
from nmos_sidecar.migrate import apply_migrations  # noqa: E402

ITEMS = 60


def item_row(turn: int) -> tuple:
    """(subject, subject_type, predicate, object, object_type, value) for this turn's item assertion."""
    item = f"물건{turn % ITEMS}"
    kind = (turn // ITEMS) % 3
    if kind == 0:
        return (f"인물{turn % 40}", "character", "possesses", item, "item", None)
    if kind == 1:
        return (item, "item", "located_in", scale.PLACES[turn % len(scale.PLACES)], "place", None)
    return (item, "item", "destroyed", None, None, "부서짐")


def run(n: int) -> dict:
    name = f"nmos_bench_{uuid.uuid4().hex[:10]}"
    with psycopg.connect(scale.ADMIN_URL, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{name}"')
    url = f"{scale.ADMIN_URL.rpartition('/')[0]}/{name}"
    try:
        apply_migrations(url)
        with TestClient(create_app(Settings(database_url=url, auth_token=""))) as client:
            scale.sync(client, scale.build_chat(n))
        with psycopg.connect(url, row_factory=dict_row, autocommit=True) as db:
            head = db.execute("SELECT head_commit_id FROM conversation").fetchone()["head_commit_id"]
            gen = generations.make("extract", "http://bench/v1", "bench", compiler="bench")
            generations.activate(db, gen)
            anchors = db.execute("SELECT source_revision_id AS rid, turn_hash, turn FROM active_membership"
                                 " WHERE commit_id = %s AND turn_hash IS NOT NULL", (head,)).fetchall()
            ids = [uuid7() for _ in anchors]
            rows = []
            for i, a in zip(ids, anchors):
                rows.append((i, a["rid"], f"인물{a['turn'] % 40}", "character", "located_in",
                             scale.PLACES[a["turn"] % len(scale.PLACES)], "place", None))
                rows.append((i, a["rid"], *item_row(a["turn"])))
            with db.cursor() as cur:
                cur.executemany("INSERT INTO extraction (id, source_revision_id, window_hash, compiler_version,"
                                " extractor_key, model, raw) VALUES (%s, %s, %s, 'bench', %s, 'bench', '{}')",
                                [(i, a["rid"], a["turn_hash"], gen.key) for i, a in zip(ids, anchors)])
                cur.executemany("INSERT INTO assertion (extraction_id, source_revision_id, subject, subject_type,"
                                " predicate, object, object_type, value, status, knowledge)"
                                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'valid', 'unknown')", rows)
            db.execute("ANALYZE extraction")
            db.execute("ANALYZE assertion")
            ms = []
            for _ in range(15):
                started = time.perf_counter()
                facts = fact_versions(db, head, gen.key)
                ms.append((time.perf_counter() - started) * 1000)
            return {"messages": n, "assertions": len(rows), "facts": len(facts),
                    "fact_read_ms": {"p50": round(scale.p(ms, 0.5), 1), "p95": round(scale.p(ms, 0.95), 1)},
                    "code": str(Path(nmos_sidecar.__file__).resolve().parents[1])}
    finally:
        with psycopg.connect(scale.ADMIN_URL, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


if __name__ == "__main__":
    for size in (sys.argv[1] if len(sys.argv) > 1 else "1000,5000,10000").split(","):
        print(json.dumps(run(int(size)), ensure_ascii=False), flush=True)
