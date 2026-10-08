"""PHASE-32 step 4: the Inspector's render time at 10,000 messages, before and after the timeline (and PHASE-39's
status lanes).

One throwaway database per fixture on the test PostgreSQL (`NMOS_TEST_ADMIN_URL`, default :5436), the app in-process
(`TestClient`: request parsing included, network excluded), no model called. Fixtures:

- `base`: `docs/perf/scale.md`'s chat (`bench_scale.build_chat`) synced, then one extraction generation over every
  turn (`bench_scale.add_generation`: one `located_in` per turn, 40 characters in turn).
- `bar`: the same chat with a one-line status bar at the end of every reply (values change every few turns) and a
  block rule that reads it (`Settings(parsers_file=...)`), for the status window's lanes.
- `heavy`: `base` plus one more character with one assertion on every turn across eight predicates (places, status,
  traits, goals, identity, relationships and feelings toward the 40 others, events): a heavier character page than
  the named setup gives.

Every page is asked for twice to warm up, then timed `--runs` times. Pages the installed code does not have
(`part=timeline`, `part=status`, `timeline=lazy`, `status=lazy`, `span=recent` before PHASE-32/39) are skipped,
since FastAPI would ignore the unknown query and time the plain page under the wrong name.

    cd apps/sidecar && uv run python ../../tools/bench_inspector.py --fixture base,bar,heavy 10000

For the "before" side, run the same file from a checkout of the code to compare (its `tools/` and `apps/sidecar`).
"""

from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import sys
import tempfile
import time
import uuid
from pathlib import Path

import psycopg
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bench_scale import ADMIN_URL, PLACES, add_generation, build_chat, sync  # noqa: E402

from nmos_sidecar import generations, inspector  # noqa: E402
from nmos_sidecar.api import create_app  # noqa: E402
from nmos_sidecar.config import Settings  # noqa: E402
from nmos_sidecar.facts import memory_view  # noqa: E402
from nmos_sidecar.migrate import apply_migrations  # noqa: E402

TIMELINE = hasattr(inspector, "character_timeline")  # PHASE-32
STATUS = hasattr(inspector, "conversation_status")  # PHASE-39
BAR_RULE = {"id": "bar", "kind": "block", "role": "char", "start": r"☆ \[", "end": r"\]\s*$", "separator": "|"}
HEAVY = "주인공"


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


def with_bar(chat) -> None:
    """A one-line status bar at the end of every reply: level, gold and items, changing every few turns."""
    j = 0
    for m in chat.messages:
        if m["role"] == "char":
            m["data"] += f"\n☆ [Level: {1 + j // 40} | Gold: {(j // 3) * 10} | Items: 물약 ×{(j // 5) % 7}]"
            j += 1


def add_heavy(db: psycopg.Connection, key: str) -> int:
    """One more assertion per turn, in that turn's extraction of the active generation, about one character."""
    rows = db.execute("SELECT x.id, x.source_revision_id AS rid, m.turn FROM extraction x JOIN active_membership m"
                      " ON m.source_revision_id = x.source_revision_id AND m.turn_hash = x.window_hash"
                      " JOIN conversation c ON c.head_commit_id = m.commit_id WHERE x.extractor_key = %s",
                      (key,)).fetchall()

    def one(t: int) -> tuple:
        other = f"인물{(t // 8) % 40}"
        return [  # (predicate, object, object_type, value) by turn % 8
            ("located_in", PLACES[(t // 8) % len(PLACES)], "place", None),
            ("has_status", None, None, f"상태{(t // 80) % 10}"),
            ("relationship", other, "character", f"관계{(t // 400) % 5}"),
            ("feels_toward", other, "character", f"감정{(t // 200) % 6}"),
            ("has_trait", None, None, f"특성{t // 200}"),
            ("event", None, None, f"사건 {t}"),
            ("goal", None, None, f"목표{t // 400}"),
            ("identity", None, None, f"직함{t // 1000}"),
        ][t % 8]

    with db.cursor() as cur:
        cur.executemany("INSERT INTO assertion (extraction_id, source_revision_id, subject, subject_type, predicate,"
                        " object, object_type, value, status, knowledge) VALUES (%s, %s, %s, 'character', %s, %s, %s,"
                        " %s, 'valid', 'unknown')",
                        [(r["id"], r["rid"], HEAVY, *one(r["turn"])) for r in rows])
    db.execute("ANALYZE assertion")
    return len(rows)


def stats(ms: list[float]) -> dict:
    xs = sorted(ms)
    return {"p50": round(statistics.median(xs)), "p95": round(xs[math.ceil(0.95 * len(xs)) - 1]),
            "max": round(xs[-1])}


def counts(html: str) -> dict:
    return {k: len(re.findall(rf'class="[^"]*\b{k}\b', html)) for k in ("tl-row", "tl-bar", "tl-dot", "tl-tick")}


def timed(client: TestClient, path: str, warmup: int, runs: int) -> dict:
    for _ in range(warmup):
        assert client.get(path).status_code == 200, path
    ms, body = [], b""
    for _ in range(runs):
        t = time.perf_counter()
        res = client.get(path)
        ms.append((time.perf_counter() - t) * 1000)
        assert res.status_code == 200, (path, res.text[:200])
        body = res.content
    html = res.json()["html"] if path.startswith("/v1/") else body.decode()
    return {**stats(ms), "kb": round(len(html.encode()) / 1024, 1), **counts(html)}


def pages(conv: str, chars: dict[str, str], status: bool) -> list[tuple[str, str]]:
    """(name, path) of every page this code has; `span=recent` only where the timeline is."""
    c = f"/inspector/c/{conv}"
    spans = ("", "recent") if TIMELINE else ("",)
    out = [(f"conversation browser span={s or 'all'}", c + (f"?span={s}" if s else "")) for s in spans]
    out.append(("conversation panel (old plugin)", f"/v1{c}"))
    if TIMELINE:
        out.append(("conversation panel timeline=lazy" + ("&status=lazy" if STATUS else ""),
                    f"/v1{c}?timeline=lazy" + ("&status=lazy" if STATUS else "")))
        out += [(f"conversation panel part=timeline span={s or 'all'}", f"/v1{c}?part=timeline" + (f"&span={s}" if s else ""))
                for s in spans]
    if STATUS and status:
        out += [(f"conversation panel part=status span={s or 'all'}", f"/v1{c}?part=status" + (f"&span={s}" if s else ""))
                for s in spans]
    for label, eid in chars.items():
        e = f"{c}/e/{eid}"
        out += [(f"character {label} browser span={s or 'all'}", e + (f"?span={s}" if s else "")) for s in spans]
        out.append((f"character {label} panel (old plugin)", f"/v1{e}"))
        if TIMELINE:
            out.append((f"character {label} panel timeline=lazy", f"/v1{e}?timeline=lazy"))
            out += [(f"character {label} panel part=timeline span={s or 'all'}",
                     f"/v1{e}?part=timeline" + (f"&span={s}" if s else "")) for s in spans]
    return out


def run(n: int, fixture: str, warmup: int, runs: int) -> dict:
    url = database()
    out: dict = {"messages": n, "fixture": fixture, "timeline": TIMELINE, "status_lanes": STATUS}
    rules = None
    try:
        chat = build_chat(n)
        settings = {"database_url": url}
        if fixture == "bar":
            with_bar(chat)
            rules = Path(tempfile.mkdtemp(prefix="nmos-bench-")) / "parsers.json"
            rules.write_text(json.dumps({"rules": [BAR_RULE]}, ensure_ascii=False), encoding="utf-8")
            settings["parsers_file"] = str(rules)
        with TestClient(create_app(Settings(**settings))) as c, \
                psycopg.connect(url, row_factory=dict_row, autocommit=True) as db:
            sync(c, chat)
            conv = db.execute("SELECT id, head_commit_id FROM conversation").fetchone()
            key = add_generation(db, conv["head_commit_id"], "bench-model", None)
            if fixture == "heavy":
                out["heavy_assertions"] = add_heavy(db, key)
            db.execute("ANALYZE")
            out["assertions"] = db.execute("SELECT count(*) AS n FROM assertion").fetchone()["n"]
            out["state_observations"] = db.execute("SELECT count(*) AS n FROM state_observation").fetchone()["n"]
            if fixture == "bar":
                assert out["state_observations"] > 0, "the bar rule read nothing"
            view = memory_view(db, conv["head_commit_id"], generations.active(db, "extract"))
        per = {e["id"]: 0 for e in view["entities"] if e["type"] == "character"}
        hist = {e["id"]: 0 for e in view["entities"] if e["type"] == "character"}
        for f in view["facts"]:
            for ref in (f.get("subject_entity"), f.get("object_entity")):
                if ref and ref.get("id") in per:
                    per[ref["id"]] += 1
                    hist[ref["id"]] += len(f.get("history") or [])
        ranked = sorted(per, key=lambda i: (per[i], hist[i]), reverse=True)
        out["characters"] = len(per)
        out["facts"] = len(view["facts"])
        chars = {"most": ranked[0], "typical": ranked[len(ranked) // 2]}
        out["picked"] = {k: {"facts": per[v], "history_entries": hist[v]} for k, v in chars.items()}
        # a new app, so it reads the generation as active (as the sidecar does at startup)
        with TestClient(create_app(Settings(**settings))) as c:
            out["pages"] = {name: timed(c, path, warmup, runs)
                            for name, path in pages(str(conv["id"]), chars, fixture == "bar")}
    finally:
        drop(url)
        if rules is not None:
            rules.unlink(missing_ok=True)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("messages", nargs="?", type=int, default=10000)
    ap.add_argument("--fixture", default="base,bar,heavy")
    ap.add_argument("--runs", type=int, default=20)
    ap.add_argument("--warmup", type=int, default=2)
    a = ap.parse_args()
    for fixture in a.fixture.split(","):
        started = time.perf_counter()
        print(json.dumps(run(a.messages, fixture, a.warmup, a.runs), ensure_ascii=False), flush=True)
        print(f"# {fixture}: {time.perf_counter() - started:.0f}s", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
