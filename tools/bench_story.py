"""Retrieve at 10,000 messages with extraction and summaries on (PHASE-12 step 7): the request path as it runs with a
model configured. Every turn has a fact and a few are secrets; where the code has summaries (Phase 12), every due
window has a scene summary and there is a story so far, so each request reads them, checks them against the secrets
and picks the scene the message is about. Run it in two checkouts to compare: in one without summaries the same
requests run without them. Uses `bench_scale.py`'s chat and requests.

    cd apps/sidecar && uv run python ../../tools/bench_story.py 10000
    cd apps/sidecar && BENCH_SUMMARIES=0 uv run python ../../tools/bench_story.py 10000  # summaries off
"""

from __future__ import annotations

import gc
import json
import os
import sys
import time
import uuid
from pathlib import Path

import psycopg
from fastapi.testclient import TestClient
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bench_scale import ADMIN_URL, PLACES, QUERIES, SENTENCE, build_chat, p, post, sync  # noqa: E402
from nmos_sidecar import generations  # noqa: E402
from nmos_sidecar.api import create_app  # noqa: E402
from nmos_sidecar.config import Settings  # noqa: E402
from nmos_sidecar.ids import uuid7  # noqa: E402
from nmos_sidecar.migrate import apply_migrations  # noqa: E402

try:
    from nmos_sidecar import summaries
except ImportError:  # before Phase 12
    summaries = None

SECRETS = 6  # about what the owner's longest chat keeps
BUDGET = 2000  # the default since Phase 12 step 5; the same in both checkouts
SCENE = "하나와 카이토는 등대 아래에서 만나 편지 이야기를 나누었다. " * 8  # ≈ 250 characters, as the owner's
STORY = "하나는 항구 마을에서 카이토를 만나 등대와 도서관을 오가며 오래된 약속을 되짚었다. " * 6  # ≈ 280 characters


def add_facts(db: psycopg.Connection, head, key: str) -> int:
    """One `located_in` per turn under the active extractor (as bench_scale's fact read), the first SECRETS of them
    kept from someone (PHASE-10)."""
    anchors = db.execute("SELECT source_revision_id AS rid, turn_hash, turn FROM active_membership"
                         " WHERE commit_id = %s AND turn_hash IS NOT NULL ORDER BY turn", (head,)).fetchall()
    ids = [uuid7() for _ in anchors]
    with db.cursor() as cur:
        cur.executemany("INSERT INTO extraction (id, source_revision_id, window_hash, compiler_version, extractor_key,"
                        " model, raw) VALUES (%s, %s, %s, 'bench', %s, 'bench', '{}')",
                        [(i, a["rid"], a["turn_hash"], key) for i, a in zip(ids, anchors)])
        cur.executemany(
            "INSERT INTO assertion (extraction_id, source_revision_id, subject, subject_type, predicate, object,"
            " object_type, status, knowledge, known_by, hidden_from) VALUES (%s, %s, %s, 'character', 'located_in',"
            " %s, 'place', 'valid', %s, %s, %s)",
            [(i, a["rid"], f"인물{a['turn'] % 40}", PLACES[a["turn"] % len(PLACES)],
              *(("limited", [f"인물{a['turn'] % 40}"], [f"인물{(a['turn'] + 1) % 40}"]) if n < SECRETS
                else ("unknown", None, None)))
             for n, (i, a) in enumerate(zip(ids, anchors))])
    db.execute("ANALYZE extraction")
    db.execute("ANALYZE assertion")
    return len(anchors)


def add_summaries(db: psycopg.Connection, conv, head, key: str) -> int:
    """A scene summary for every due window and the story so far of them, as the worker writes them."""
    ws = summaries.windows(db, head)
    ids = [uuid7() for _ in ws]
    listed = Jsonb({"secrets": [summaries.secret_key(s) for s in summaries.head_secrets(db, head)]})  # as prompted
    with db.cursor() as cur:
        cur.executemany(
            "INSERT INTO summary (id, conversation_id, generation, level, window_key, members, first_turn, last_turn,"
            " text, raw, coverage) VALUES (%s, %s, %s, 'scene', %s, %s, %s, %s, %s, '{}', %s)",
            [(i, conv, key, w.key, list(w.members), w.first_turn, w.last_turn,
              f"{SCENE}{PLACES[w.index % len(PLACES)]}에서 {w.index}번째 장면.", listed)
             for i, w in zip(ids, ws)])
    db.execute("INSERT INTO summary (id, conversation_id, generation, level, window_key, members, first_turn,"
               " last_turn, text, raw, coverage) VALUES (%s, %s, %s, 'story', %s, %s, 0, %s, %s, '{}', %s)",
               (uuid7(), conv, key, summaries.members_key(ids), ids, ws[-1].last_turn, STORY, listed))
    db.execute("ANALYZE summary")
    return len(ws)


def bench(n: int) -> dict:
    name = f"nmos_bench_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{name}"')
    url = ADMIN_URL.rpartition("/")[0] + f"/{name}"
    result: dict = {"messages": n, "summaries": summaries is not None and os.environ.get("BENCH_SUMMARIES") != "0"}
    off = {"summaries": False} if os.environ.get("BENCH_SUMMARIES") == "0" else {}  # the same code with them off
    settings = Settings(database_url=url, llm_url="http://bench/v1", llm_model="bench", **off)  # no worker runs
    try:
        apply_migrations(url)
        chat = build_chat(n)
        with psycopg.connect(url, row_factory=dict_row, autocommit=True) as db:
            with TestClient(create_app(settings)) as client:
                sync(client, chat)
            head = db.execute("SELECT head_commit_id FROM conversation").fetchone()["head_commit_id"]
            conv = db.execute("SELECT id FROM conversation").fetchone()["id"]
            db.execute("UPDATE job SET status = 'obsolete' WHERE status = 'queued'")  # no worker in this run
            result["facts"] = add_facts(db, head, generations.active(db, "extract"))
            if result["summaries"]:
                result["scenes"] = add_summaries(db, conv, head, generations.active(db, "summarize"))
            db.execute("ANALYZE")
            with TestClient(create_app(settings)) as client:
                # The harness holds the 10,000-message chat in this process; a full collection during a request
                # would scan it too, which the sidecar alone never does. Its objects are frozen out of collection.
                gc.collect()
                gc.freeze()
                retrieves, story = [], 0
                for i in range(15):
                    chat.reply(SENTENCE * 20 + f"새 장면 {i}.")
                    chat.user(f"새 대사 {i}: {PLACES[i % len(PLACES)]}에 다시 가자.")
                    sync(client, chat)
                    q = QUERIES[i % len(QUERIES)]
                    out, ms = post(client, "/v1/retrieve", {"chat_id": chat.id, "query": q, "previous_ai": SENTENCE,
                                                             "in_context_ids": [m["chatId"] for m in chat.messages[-40:]],
                                                             "budget_tokens": BUDGET})
                    retrieves.append(ms)
                    story += "<Story>" in out["packet"]["text"]
            result["retrieve_ms"] = {"p50": p(retrieves, 0.5), "p95": p(retrieves, 0.95)}
            result["packets_with_story"] = story
    finally:
        with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    return result


def main() -> None:
    for n in [int(x) for x in (sys.argv[1] if len(sys.argv) > 1 else "10000").split(",")]:
        started = time.perf_counter()
        print(json.dumps(bench(n), default=lambda x: round(x, 2) if isinstance(x, float) else str(x)), flush=True)
        print(f"# {n}: {time.perf_counter() - started:.0f}s", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
