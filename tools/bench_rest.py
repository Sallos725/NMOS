"""The rest's cost on large chats (PHASE-34 Q8 e): `/v1/retrieve` under `packet-v13` and `packet-v14` on the same
synthetic chat as a conversation goes on (each request reads the chat's last traces and the replies after them), and
`overuse.recent` alone. The bar: the reads add at most 30 ms at p95 at 10,000 messages.

    cd apps/sidecar && uv run python ../../tools/bench_rest.py 1000,10000
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
from bench_scale import ADMIN_URL, PLACES, SENTENCE, QUERIES, build_chat, p, post, sync  # noqa: E402

from nmos_sidecar import overuse  # noqa: E402
from nmos_sidecar.api import create_app  # noqa: E402
from nmos_sidecar.config import Settings  # noqa: E402
from nmos_sidecar.migrate import apply_migrations  # noqa: E402

TURNS = 30


def bench(n: int) -> dict:
    name = f"nmos_bench_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{name}"')
    url = ADMIN_URL.rpartition("/")[0] + f"/{name}"
    out: dict = {"messages": n}
    try:
        apply_migrations(url)
        chat = build_chat(n)
        with TestClient(create_app(Settings(database_url=url, packet_policy="packet-v13"))) as v13, \
                TestClient(create_app(Settings(database_url=url, packet_policy="packet-v14"))) as v14, \
                psycopg.connect(url, row_factory=dict_row, autocommit=True) as db:
            sync(v13, chat)
            db.execute("ANALYZE")
            ms: dict[str, list[float]] = {"packet-v13": [], "packet-v14": []}
            reads: list[float] = []
            conv, head = None, None
            for i in range(TURNS):
                chat.reply(SENTENCE * 20 + f"새 장면 {i}.")
                chat.user(f"새 대사 {i}: {PLACES[i % len(PLACES)]}에 다시 가자.")
                sync(v13, chat)
                q = QUERIES[i % len(QUERIES)]
                for pol, client in (("packet-v13", v13), ("packet-v14", v14)):
                    _, t = post(client, "/v1/retrieve", {"chat_id": chat.id, "query": q, "previous_ai": SENTENCE,
                                                         "in_context_ids": [m["chatId"] for m in chat.messages[-40:]],
                                                         "budget_tokens": 4000})
                    ms[pol].append(t)
                if conv is None:
                    row = db.execute("SELECT id, head_commit_id FROM conversation").fetchone()
                    conv = row["id"]
                head = db.execute("SELECT head_commit_id FROM conversation WHERE id = %s", (conv,)).fetchone()[
                    "head_commit_id"]
                t0 = time.perf_counter()
                overuse.recent(db, conv, head, n=3)
                reads.append((time.perf_counter() - t0) * 1000)
            out["retrieve_ms"] = {k: {"p50": round(p(v, 0.5), 1), "p95": round(p(v, 0.95), 1)} for k, v in ms.items()}
            out["recent_read_ms"] = {"p50": round(p(reads, 0.5), 1), "p95": round(p(reads, 0.95), 1)}
            out["v14_over_v13_p95"] = round(p(ms["packet-v14"], 0.95) - p(ms["packet-v13"], 0.95), 1)
    finally:
        with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    return out


def main() -> None:
    for n in [int(x) for x in (sys.argv[1] if len(sys.argv) > 1 else "1000,10000").split(",")]:
        print(json.dumps(bench(n), ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
