"""Sidecar cost of large chats (#12): cold sync, warm append, edits, lexical/vector recall, fact reads, storage.

Drives the real FastAPI app (in-process TestClient: request parsing and validation included, network
excluded) against the compose PostgreSQL, one throwaway database per size. Pair with the plugin
side: `node adapters/pocketrisu-plugin/scripts/bench-manifest.mjs`.

    cd apps/sidecar && uv run python ../../tools/bench_scale.py 1000,5000,10000,25000
"""

from __future__ import annotations

import json
import os
import random
import sys
import time
import uuid
from pathlib import Path

import psycopg
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "sidecar" / "tests"))
from simchat import SimChat  # noqa: E402

from nmos_sidecar import generations  # noqa: E402
from nmos_sidecar.api import create_app  # noqa: E402
from nmos_sidecar.config import Settings  # noqa: E402
from nmos_sidecar.facts import fact_versions  # noqa: E402
from nmos_sidecar.ids import uuid7  # noqa: E402
from nmos_sidecar.migrate import apply_migrations  # noqa: E402
from nmos_sidecar.vectors import vector_candidates, vector_literal  # noqa: E402

ADMIN_URL = os.environ.get("NMOS_TEST_ADMIN_URL", "postgresql://nmos:nmos@127.0.0.1:5436/postgres")
BODY_CHUNK = 250  # plugin core.ts
DIM = 1024  # qwen3-embedding:0.6b
SENTENCE = '하나는 창가에 앉아 등대 쪽을 바라보았다. "오늘은 바람이 차네." '
PLACES = ["등대", "도서관", "항구", "시계탑", "지하실", "온실", "기차역", "성당"]
QUERIES = ["등대 지하에 숨긴 열쇠 어디 있었지?", "도서관에서 무슨 일이 있었더라", "기차역 약속 기억나?",
           "은빛 회중시계", "오늘은 바람이 차네", "우리가 처음 만난 곳", "성당 종소리", "그 편지 누가 보냈어?"]


def build_chat(n: int) -> SimChat:
    rnd = random.Random(n)
    chat = SimChat()
    for i in range(n):
        if i % 2 == 0:
            chat.user(f"대사 {i}: {rnd.choice(PLACES)}에 가 볼까?")
        else:
            place = rnd.choice(PLACES)
            chat.reply(SENTENCE * 28 + f"{place}에서 {i}번째 장면이 이어졌다.\n<status>HP {i % 100}</status>")
    return chat


def post(client: TestClient, path: str, body: dict) -> tuple[dict, float]:
    t = time.perf_counter()
    res = client.post(path, json=body)
    ms = (time.perf_counter() - t) * 1000
    assert res.status_code == 200, res.text[:300]
    return res.json(), ms


def sync(client: TestClient, chat: SimChat) -> dict[str, float]:
    """The plugin flow; harness-side hashing happens before the clock starts."""
    manifest = chat.manifest()
    out, reconcile_ms = post(client, "/v1/sync/reconcile", manifest)
    timings = {"reconcile": reconcile_ms, "bodies": 0.0, "chunks": 0}
    if out["status"] == "needs_bodies":
        bodies = chat.bodies(out["needed_bodies"])
        for i in range(0, len(bodies), BODY_CHUNK):
            last = i + BODY_CHUNK >= len(bodies)
            res, ms = post(client, "/v1/sync/bodies", {"chat_id": chat.id, "bodies": bodies[i:i + BODY_CHUNK],
                                                       "then_reconcile": manifest if last else None})
            timings["bodies"] += ms
            timings["chunks"] += 1
            assert res["ok"]
            if last:
                out = res["reconcile"]
    assert out["status"] in ("applied", "noop"), out
    timings["total"] = timings["reconcile"] + timings["bodies"]
    return timings


def p(xs: list[float], q: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))]


def sizes(conn: psycopg.Connection) -> dict[str, float]:
    out = {"database_mb": conn.execute("SELECT pg_database_size(current_database()) AS b").fetchone()["b"] / 2**20}
    for table in ("source_revision", "revision_text", "active_membership", "worldline_commit", "host_observation",
                  "revision_embedding", "extraction", "assertion"):
        out[f"{table}_mb"] = conn.execute("SELECT pg_total_relation_size(%s) AS b", (table,)).fetchone()["b"] / 2**20
    out["host_observation_rows"] = conn.execute("SELECT count(*) AS n FROM host_observation").fetchone()["n"]
    return out


def bench(n: int) -> dict:
    name = f"nmos_bench_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{name}"')
    url = ADMIN_URL.rpartition("/")[0] + f"/{name}"
    result: dict = {"messages": n}
    try:
        apply_migrations(url)
        chat = build_chat(n)
        with TestClient(create_app(Settings(database_url=url))) as client, \
                psycopg.connect(url, row_factory=dict_row, autocommit=True) as db:
            result["manifest_bytes"] = len(json.dumps(chat.manifest(), ensure_ascii=False).encode())
            result["cold"] = sync(client, chat)
            db.execute("ANALYZE")  # steady state: autovacuum analyzes a long-lived chat's tables
            obs_before = sizes(db)

            appends = []
            retrieves = []
            for i in range(15):  # one generation: last reply is now followed by a new user turn
                chat.reply(SENTENCE * 20 + f"새 장면 {i}.")
                chat.user(f"새 대사 {i}: {PLACES[i % len(PLACES)]}에 다시 가자.")
                appends.append(sync(client, chat)["total"])
                q = QUERIES[i % len(QUERIES)]
                _, ms = post(client, "/v1/retrieve", {"chat_id": chat.id, "query": q, "previous_ai": SENTENCE,
                                                       "in_context_ids": [m["chatId"] for m in chat.messages[-40:]],
                                                       "budget_tokens": 600})
                retrieves.append(ms)
            obs_after = sizes(db)
            result["append_ms"] = {"p50": p(appends, 0.5), "p95": p(appends, 0.95)}
            result["retrieve_lexical_ms"] = {"p50": p(retrieves, 0.5), "p95": p(retrieves, 0.95),
                                             "by_query": {q: round(min(ms for i, ms in enumerate(retrieves)
                                                                        if QUERIES[i % len(QUERIES)] == q))
                                                          for q in QUERIES}}
            result["host_observation_per_append_kb"] = (
                (obs_after["host_observation_mb"] - obs_before["host_observation_mb"]) * 1024 / 15)

            head_edits, deep_edits = [], []
            for i in range(5):
                chat.edit(len(chat.messages) - 3, f"고친 문장 {i}.")
                head_edits.append(sync(client, chat)["total"])
                chat.edit(len(chat.messages) // 10, f"과거를 고친 문장 {i}.")
                deep_edits.append(sync(client, chat)["total"])
            result["edit_head_ms"] = {"p50": p(head_edits, 0.5), "max": max(head_edits)}
            result["edit_deep_ms"] = {"p50": p(deep_edits, 0.5), "max": max(deep_edits)}

            # Exact pgvector search: one DIM-dim vector per revision under one projection (real corpora
            # have up to MAX_CHUNKS per long revision, so this is a lower bound).
            gen = generations.make("embed", "http://bench/v1", "bench", dim=DIM)
            generations.activate(db, gen)
            rnd = random.Random(7)
            rows = db.execute("SELECT id FROM source_revision").fetchall()
            with db.cursor() as cur:
                cur.executemany(
                    "INSERT INTO revision_embedding (source_revision_id, projection, model, chunk, dim, text_start,"
                    " text_end, embedding) VALUES (%s, %s, 'bench', 0, %s, 0, 10, %s::vector)",
                    [(r["id"], gen.key, DIM, vector_literal([rnd.gauss(0, 1) for _ in range(DIM)])) for r in rows],
                )
            db.execute("ANALYZE revision_embedding")
            head = db.execute("SELECT head_commit_id FROM conversation").fetchone()["head_commit_id"]
            vec = []
            for _ in range(15):
                q = [rnd.gauss(0, 1) for _ in range(DIM)]
                t = time.perf_counter()
                vector_candidates(db, head, q, gen.key, -1, 50)
                vec.append((time.perf_counter() - t) * 1000)
            result["vector_search_ms"] = {"p50": p(vec, 0.5), "p95": p(vec, 0.95)}
            result["fact_read_ms"] = bench_facts(db, head)
            result["sizes"] = sizes(db)
    finally:
        with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    return result


def add_generation(db: psycopg.Connection, head, model: str, turns: int | None) -> str:
    """Stub extractions for the latest `turns` turns of the head (all when None): one `located_in`
    assertion per turn, about what a chat with extraction on accumulates."""
    gen = generations.make("extract", "http://bench/v1", model, compiler="bench")
    generations.activate(db, gen)
    anchors = db.execute("SELECT source_revision_id AS rid, turn_hash, turn FROM active_membership"
                         " WHERE commit_id = %s AND turn_hash IS NOT NULL ORDER BY turn DESC LIMIT %s",
                         (head, turns)).fetchall()
    ids = [uuid7() for _ in anchors]
    with db.cursor() as cur:
        cur.executemany("INSERT INTO extraction (id, source_revision_id, window_hash, compiler_version, extractor_key,"
                        " model, raw) VALUES (%s, %s, %s, 'bench', %s, %s, '{}')",
                        [(i, a["rid"], a["turn_hash"], gen.key, model) for i, a in zip(ids, anchors)])
        cur.executemany("INSERT INTO assertion (extraction_id, source_revision_id, subject, subject_type, predicate,"
                        " object, object_type, status, knowledge) VALUES (%s, %s, %s, 'character', 'located_in', %s,"
                        " 'place', 'valid', 'unknown')",
                        [(i, a["rid"], f"인물{a['turn'] % 40}", PLACES[a["turn"] % len(PLACES)])
                         for i, a in zip(ids, anchors)])
    db.execute("ANALYZE extraction")
    db.execute("ANALYZE assertion")
    return gen.key


def bench_facts(db: psycopg.Connection, head) -> dict:
    """Fact read (`fact_versions`, per request): one generation covering every turn, then a newer one
    covering only the recent window while the older serves the rest (ADR 0014)."""
    def timed(key: str) -> dict:
        ms = []
        for _ in range(15):
            t = time.perf_counter()
            fact_versions(db, head, key)
            ms.append((time.perf_counter() - t) * 1000)
        return {"first": ms[0], "p50": p(ms, 0.5), "p95": p(ms, 0.95), "max": max(ms)}

    one = timed(add_generation(db, head, "bench-a", None))
    two = timed(add_generation(db, head, "bench-b", 100))
    return {"one_generation": one, "two_generations": two}


def main() -> None:
    for n in [int(x) for x in (sys.argv[1] if len(sys.argv) > 1 else "1000,5000,10000,25000").split(",")]:
        started = time.perf_counter()
        print(json.dumps(bench(n), default=lambda x: round(x, 2) if isinstance(x, float) else str(x)), flush=True)
        print(f"# {n}: {time.perf_counter() - started:.0f}s", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
