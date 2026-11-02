"""PHASE-55 step 5: the memory map's render time at 10,000 messages, beside the memory document and the hub.

`bench_inspector`'s fixtures (`base`, `heavy`) on the test PostgreSQL (`NMOS_TEST_ADMIN_URL`, default :5436), one
throwaway database each, the app in-process (`TestClient`), no model called. Every page is asked for twice to warm up,
then timed `--runs` times: p50 / p95 / max in ms and the HTML's size in KB.

    cd apps/sidecar && uv run python ../../tools/bench_map.py --fixture base,heavy 10000
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import psycopg
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bench_inspector import HEAVY, add_heavy, database, drop, timed  # noqa: E402
from bench_scale import add_generation, build_chat, sync  # noqa: E402

from nmos_sidecar.api import create_app  # noqa: E402
from nmos_sidecar.config import Settings  # noqa: E402


def pages(conv: str, focus: str | None) -> list[tuple[str, str]]:
    v = f"/views/c/{conv}"
    out = [("hub panel (old plugin)", f"/v1/views/hub?conversation={conv}"),
           ("hub panel map=1", f"/v1/views/hub?conversation={conv}&map=1"),
           ("memory panel (old plugin)", f"/v1{v}/memory"),
           ("memory panel map=1", f"/v1{v}/memory?map=1"),
           ("map panel", f"/v1{v}/map"),
           ("map browser", f"{v}/map"),
           ("map browser all=1", f"{v}/map?all=1")]
    if focus:
        out += [("map panel focus", f"/v1{v}/map?focus={focus}"), ("map browser focus", f"{v}/map?focus={focus}")]
    return out


def run(n: int, fixture: str, warmup: int, runs: int) -> dict:
    url = database()
    out: dict = {"messages": n, "fixture": fixture}
    try:
        chat = build_chat(n)
        settings = {"database_url": url}
        with TestClient(create_app(Settings(**settings))) as c, \
                psycopg.connect(url, row_factory=dict_row, autocommit=True) as db:
            sync(c, chat)
            conv = db.execute("SELECT id, head_commit_id FROM conversation").fetchone()
            key = add_generation(db, conv["head_commit_id"], "bench-model", None)
            if fixture == "heavy":
                out["heavy_assertions"] = add_heavy(db, key)
            db.execute("ANALYZE")
            out["assertions"] = db.execute("SELECT count(*) AS n FROM assertion").fetchone()["n"]
        # a new app, so it reads the generation as active (as the sidecar does at startup)
        with TestClient(create_app(Settings(**settings))) as c:
            cid = str(conv["id"])
            focus = next((e["id"] for e in c.get(f"/v1/conversations/{cid}/entities").json()
                          if e["name"] == (HEAVY if fixture == "heavy" else "인물0")), None)
            out["pages"] = {name: timed(c, path, warmup, runs) for name, path in pages(cid, focus)}
            for k in out["pages"].values():  # the timeline's counts mean nothing here
                for x in ("tl-row", "tl-bar", "tl-dot", "tl-tick"):
                    k.pop(x, None)
    finally:
        drop(url)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("messages", nargs="?", type=int, default=10000)
    ap.add_argument("--fixture", default="base,heavy")
    ap.add_argument("--runs", type=int, default=20)
    ap.add_argument("--warmup", type=int, default=2)
    a = ap.parse_args()
    for fixture in a.fixture.split(","):
        started = time.perf_counter()
        print(json.dumps(run(a.messages, fixture, a.warmup, a.runs), ensure_ascii=False), flush=True)
        print(f"# {fixture}: {time.perf_counter() - started:.0f}s", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
