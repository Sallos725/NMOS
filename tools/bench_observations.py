"""Host observation storage before and after compaction (ADR 0018) on a large chat.

Syncs a `bench_scale.py` chat, then N non-append actions (alternating reroll of the last reply and an
edit deep in the chat), each of which stores the whole manifest as its observation. Reports the
observations' size before and after `retention.compact_observations`, the pass time, and checks that
every observation rebuilds exactly.

    cd apps/sidecar && uv run python ../../tools/bench_observations.py 10000 20
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

from nmos_sidecar import retention  # noqa: E402
from nmos_sidecar.api import create_app  # noqa: E402
from nmos_sidecar.config import Settings  # noqa: E402
from nmos_sidecar.migrate import apply_migrations  # noqa: E402

SIZE = "SELECT count(*) AS n, sum(pg_column_size(raw_manifest)) AS bytes FROM host_observation"


def run(n: int, actions: int) -> dict:
    name = f"nmos_bench_{uuid.uuid4().hex[:10]}"
    with psycopg.connect(scale.ADMIN_URL, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{name}"')
    url = f"{scale.ADMIN_URL.rpartition('/')[0]}/{name}"
    try:
        apply_migrations(url)
        chat = scale.build_chat(n)
        with TestClient(create_app(Settings(database_url=url, auth_token=""))) as client:
            scale.sync(client, chat)
            for i in range(actions):
                if i % 2 == 0 and chat.messages[-1]["role"] == "char":
                    chat.reroll(f"다시 쓴 답장 {i}.")
                else:
                    chat.edit(len(chat.messages) // 3 + i, f"고친 문장 {i}.")
                scale.sync(client, chat)
        with psycopg.connect(url, row_factory=dict_row, autocommit=True) as db:
            before = db.execute(SIZE).fetchone()
            originals = {r["id"]: (r["raw_manifest"]["columns"], r["raw_manifest"]["entries"]) for r in db.execute(
                "SELECT id, raw_manifest FROM host_observation WHERE raw_manifest ? 'entries'").fetchall()}
            started = time.perf_counter()
            compacted = retention.compact_observations(db, limit=10_000)
            first = (time.perf_counter() - started) * 1000
            started = time.perf_counter()
            assert retention.compact_observations(db) == 0
            idle = (time.perf_counter() - started) * 1000
            after = db.execute(SIZE).fetchone()
            started = time.perf_counter()
            exact = all(retention.observed_rows(db, i) == rows for i, rows in originals.items())
            rebuild = (time.perf_counter() - started) * 1000 / max(1, len(originals))
            return {"messages": n, "full_observations": len(originals), "compacted": compacted,
                    "observations": before["n"], "bytes_before": before["bytes"], "bytes_after": after["bytes"],
                    "first_pass_ms": round(first), "idle_pass_ms": round(idle, 1),
                    "rebuild_ms_per_observation": round(rebuild, 1), "exact": exact}
    finally:
        with psycopg.connect(scale.ADMIN_URL, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


if __name__ == "__main__":
    sizes = sys.argv[1] if len(sys.argv) > 1 else "10000"
    actions = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    for size in sizes.split(","):
        print(json.dumps(run(int(size), actions)), flush=True)
