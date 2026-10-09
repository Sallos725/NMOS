"""The forensic path's cost on large chats (PHASE-33 Q4, Q10 e): `/v1/retrieve` under `packet-v12` and `packet-v13`
on the same synthetic chat, for questions with a speech cue (the forensic path under v13) and without one (the normal
path under both). The bar: forensic p95 at most 150 ms above normal p95 at 10,000 messages.

The chat is `bench_scale.py`'s: every reply holds a quoted line many times, the worst case for the quote route (each
candidate message offers dozens of quotes). In-process app, no embedder (the vector route is the same for both
policies), one throwaway database per size.

    cd apps/sidecar && uv run python ../../tools/bench_forensic.py 1000,5000,10000
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

import psycopg
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bench_scale import ADMIN_URL, PLACES, SENTENCE, build_chat, p, post, sync  # noqa: E402

from nmos_sidecar.api import create_app  # noqa: E402
from nmos_sidecar.config import Settings  # noqa: E402
from nmos_sidecar.migrate import apply_migrations  # noqa: E402

CUED = ["하나가 등대에서 뭐라고 했지?", "{turn}턴에 하나가 뭐라고 했어?", "처음 도서관 갔을 때 하나가 뭐라고 했지?",
        "'오늘은 바람이 차네'라고 누가 말했어?", "기차역에서 하나가 뭐라고 물었어?"]
PLAIN = ["등대 지하에 숨긴 열쇠 어디 있었지?", "도서관에서 무슨 일이 있었더라", "기차역 약속 기억나?",
         "은빛 회중시계", "성당 종소리"]
ROUNDS = 6


def bench(n: int) -> dict:
    name = f"nmos_bench_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{name}"')
    url = ADMIN_URL.rpartition("/")[0] + f"/{name}"
    out: dict = {"messages": n}
    try:
        apply_migrations(url)
        chat = build_chat(n)
        clients = {pol: TestClient(create_app(Settings(database_url=url, packet_policy=pol)))
                   for pol in ("packet-v12", "packet-v13")}
        with clients["packet-v12"] as v12, clients["packet-v13"] as v13, \
                psycopg.connect(url, row_factory=dict_row, autocommit=True) as db:
            sync(v12, chat)
            db.execute("ANALYZE")
            in_context = [m["chatId"] for m in chat.messages[-40:]]
            ms: dict[str, list[float]] = {}
            quote_ms: list[float] = []
            for r in range(ROUNDS):
                for kind, queries in (("cued", CUED), ("plain", PLAIN)):
                    for q in queries:
                        q = q.format(turn=(n // 4) + r)
                        for pol, client in (("packet-v12", v12), ("packet-v13", v13)):
                            res, t = post(client, "/v1/retrieve", {"chat_id": chat.id, "query": q,
                                                                   "previous_ai": SENTENCE,
                                                                   "in_context_ids": in_context, "budget_tokens": 4000})
                            ms.setdefault(f"{pol} {kind}", []).append(t)
                            if pol == "packet-v13" and kind == "cued":
                                trace = client.get(f"/v1/trace/{res['trace_id']}").json()
                                lat = trace.get("latency_ms") or {}
                                assert lat.get("path") == "forensic", (q, lat.get("path"))
                                quote_ms.append(float(lat.get("quote_route") or 0))
            out["retrieve_ms"] = {k: {"p50": round(p(v, 0.5), 1), "p95": round(p(v, 0.95), 1)} for k, v in ms.items()}
            out["quote_route_ms"] = {"p50": round(p(quote_ms, 0.5), 1), "p95": round(p(quote_ms, 0.95), 1)}
            out["forensic_over_normal_p95"] = round(p(ms["packet-v13 cued"], 0.95) - p(ms["packet-v12 cued"], 0.95), 1)
    finally:
        with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    return out


def main() -> None:
    sizes = [int(x) for x in (sys.argv[1] if len(sys.argv) > 1 else "1000,10000").split(",")]
    for n in sizes:
        print(json.dumps(bench(n), ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
