"""PHASE-38 step 5: a restore from the panel into a running install, at 10,000 messages.

A source install gets a synthetic chat of N messages (`bench_scale.build_chat`) and one extraction generation over
every turn (`bench_scale.add_generation`); its whole-install archive is exported. A target install, running, holds a
chat of its own. The archive goes through the panel's routes (8 MB chunks of base64, check, restore) while two threads
keep using the target: one syncs a new turn of one of its chats every 0.1 s (a write that draws ids), one recalls in
another of its chats every 0.2 s (a read that records the request). A recall in the chat whose sync waits waits with
it: the plugin recalls after the sync, in the same request. Reported: the archive's size, each phase's time, and every sync's and
recall's time while the restore ran. No model is called.

    cd apps/sidecar && uv run python ../../tools/bench_restore.py 10000
"""

from __future__ import annotations

import base64
import hashlib
import json
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

import psycopg
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bench_scale import ADMIN_URL, SimChat, add_generation, build_chat, p, sync  # noqa: E402

from nmos_sidecar import archive  # noqa: E402
from nmos_sidecar.api import create_app  # noqa: E402
from nmos_sidecar.config import Settings  # noqa: E402
from nmos_sidecar.migrate import apply_migrations  # noqa: E402


def database() -> str:
    name = f"nmos_bench_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{name}"')
    url = ADMIN_URL.rpartition("/")[0] + f"/{name}"
    apply_migrations(url)
    return url


def drop(url: str) -> None:
    with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
        admin.execute(f'DROP DATABASE IF EXISTS "{url.rpartition("/")[2]}" WITH (FORCE)')


def run(n: int) -> dict:
    source, target = database(), database()
    out: dict = {"messages": n}
    try:
        chat = build_chat(n)
        with TestClient(create_app(Settings(database_url=source))) as c, \
                psycopg.connect(source, row_factory=dict_row, autocommit=True) as db:
            sync(c, chat)
            head = db.execute("SELECT head_commit_id FROM conversation").fetchone()["head_commit_id"]
            add_generation(db, head, "bench-model", None)
            out["source_assertions"] = db.execute("SELECT count(*) AS n FROM assertion").fetchone()["n"]
        path = Path(tempfile.mkdtemp(prefix="nmos-bench-")) / f"all{archive.SUFFIX}"
        t0 = time.perf_counter()
        archive.export_file(source, str(path))
        out["export_s"] = round(time.perf_counter() - t0, 2)
        data = path.read_bytes()
        out["archive_mb"] = round(len(data) / 2**20, 2)

        own, other = SimChat(), SimChat()
        for chat_ in (own, other):
            chat_.user("Mina is in the tower.")
            chat_.reply("Noted.")
            chat_.user("Go on.")
        with TestClient(create_app(Settings(database_url=target))) as c:
            sync(c, own)
            sync(c, other)
            t0 = time.perf_counter()
            up = c.post("/v1/archive/uploads", json={"bytes": len(data)}).json()
            size = up["chunk_bytes"]
            for i in range(0, len(data), size):
                part = data[i:i + size]
                res = c.put(f"/v1/archive/uploads/{up['id']}/chunks/{i // size}",
                            json={"data": base64.b64encode(part).decode(), "sha256": hashlib.sha256(part).hexdigest()})
                assert res.status_code == 200, res.text
            out["upload_s"] = round(time.perf_counter() - t0, 2)
            out["chunks"] = -(-len(data) // size)

            def until(*states: str) -> dict:
                while True:
                    view = c.get(f"/v1/archive/uploads/{up['id']}").json()
                    if view["state"] in states:
                        return view
                    time.sleep(0.02)

            t0 = time.perf_counter()
            assert c.post(f"/v1/archive/uploads/{up['id']}/check").status_code == 202
            assert until("checked", "refused")["state"] == "checked"
            out["check_s"] = round(time.perf_counter() - t0, 2)

            stop = threading.Event()
            writes: list[tuple[float, float]] = []  # (start, ms)
            reads: list[tuple[float, float]] = []

            def writer() -> None:
                i = 0
                while not stop.is_set():
                    own.reply(f"Noted {i}.")
                    own.user(f"Turn {i}: Mina moved to the harbor.")
                    start = time.perf_counter()
                    sync(c, own)
                    writes.append((start, (time.perf_counter() - start) * 1000))
                    i += 1
                    time.sleep(0.1)

            def reader() -> None:
                ids = [m["chatId"] for m in other.messages[-2:]]
                while not stop.is_set():
                    start = time.perf_counter()
                    res = c.post("/v1/retrieve", json={"chat_id": other.id, "query": "where is Mina", "previous_ai": "",
                                                       "in_context_ids": ids, "budget_tokens": 600})
                    if res.status_code == 200:
                        reads.append((start, (time.perf_counter() - start) * 1000))
                    time.sleep(0.2)

            threads = [threading.Thread(target=writer), threading.Thread(target=reader)]
            for t in threads:
                t.start()
            time.sleep(1.0)  # a baseline before the restore
            t0 = time.perf_counter()
            assert c.post(f"/v1/archive/uploads/{up['id']}/restore").status_code == 202
            done = until("restored", "failed")
            t1 = time.perf_counter()
            time.sleep(1.0)
            stop.set()
            for t in threads:
                t.join()
            assert done["state"] == "restored", done
            out["restore_s"] = round(t1 - t0, 2)
            out["queued_jobs"] = done["result"].get("queued_jobs")
            during = lambda xs: [ms for start, ms in xs if t0 <= start <= t1]
            outside = lambda xs: [ms for start, ms in xs if start < t0 or start > t1]
            for name, xs in (("sync", writes), ("recall", reads)):
                d, o = during(xs), outside(xs)
                out[f"{name}_during"] = {"n": len(d), "p50_ms": round(p(d, 0.5)) if d else None,
                                         "max_ms": round(max(d)) if d else None}
                out[f"{name}_outside"] = {"n": len(o), "p50_ms": round(p(o, 0.5)) if o else None,
                                          "max_ms": round(max(o)) if o else None}
        with psycopg.connect(target) as conn:
            out["target_assertions"] = conn.execute("SELECT count(*) FROM assertion").fetchone()[0]
    finally:
        drop(source)
        drop(target)
    return out


def main() -> None:
    for n in (int(x) for x in (sys.argv[1] if len(sys.argv) > 1 else "10000").split(",")):
        print(json.dumps(run(n), ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
