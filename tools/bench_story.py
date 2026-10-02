"""Retrieve at 10,000 messages with extraction and summaries on (PHASE-12 step 7): the request path as it runs with a
model configured. Every turn has a fact and a few are secrets; where the code has summaries (Phase 12), every due
window has a scene summary and there is a story so far, so each request reads them, checks them against the secrets
and picks the scene the message is about. Run it in two checkouts to compare: in one without summaries the same
requests run without them. Uses `bench_scale.py`'s chat and requests. With BENCH_REPAIRS=N (Phase 13) the chat
has N live owner repairs (ADR 0044) when the requests run: a found out for each secret, the rest retractions and
corrections of the facts current then. With BENCH_CANON=N (Phase 14) the chat has a canon of N lorebook entries, the
card and the persona, synced as the plugin does, with the canon generation's facts stored (ADR 0047); each request
names that canon and holds a quarter of the entries, the card and the persona in its prompt.

    cd apps/sidecar && uv run python ../../tools/bench_story.py 10000
    cd apps/sidecar && BENCH_SUMMARIES=0 uv run python ../../tools/bench_story.py 10000  # summaries off
    cd apps/sidecar && BENCH_REPAIRS=100 uv run python ../../tools/bench_story.py 10000  # with 100 repairs
    cd apps/sidecar && BENCH_CANON=200 uv run python ../../tools/bench_story.py 10000  # with a 200-entry lorebook
    cd apps/sidecar && BENCH_BUDGET=4000 uv run python ../../tools/bench_story.py 10000  # another memory budget
    cd apps/sidecar && NMOS_PACKET_POLICY=packet-v8 uv run python ../../tools/bench_story.py 10000  # another policy
    cd apps/sidecar && BENCH_RECALL=wide BENCH_BUDGET=8000 uv run python ../../tools/bench_story.py 10000

With BENCH_FIRST=1 (Phase 21) every question starts with "처음에", the first cue (ADR 0056).

With BENCH_NAMES=1 (Phase 24) the story's 40 characters are named as people are: 20 three-syllable Hangul names and
20 romanized ones, and every question starts with one of them as the user would write it, a given name or the Hangul
spelling of a romanized name (ADR 0058).

With BENCH_RECALL=wide (Phase 15) every message has a vector near the query's (a stub embedder answers at once) and
each request asks for the scenes of a place with no previous reply, so recall has more excerpts and facts to offer than
any budget takes: a larger budget's recall is the largest. The default questions match the chat's repeated sentence,
whose excerpts all say the same thing, and there is no embedder.

With BENCH_EMBED_MS=N (ADR 0061) the wide embedder answers after N ms, as a remote or busy embedder does (K34): with N
near or above `NMOS_EMBED_TIMEOUT_MS` (300), the result also says how many of the 15 requests had vectors. With
BENCH_PREFETCH=1 each request's user message is its question, as the plugin sends it, so the sync that delivers the
message starts its embedding (ADR 0061 item 7) and the retrieve that follows takes it.
"""

from __future__ import annotations

import gc
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
from psycopg.types.json import Jsonb

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bench_scale import ADMIN_URL, DIM, PLACES, QUERIES, SENTENCE, build_chat, p, post, sync  # noqa: E402
from nmos_sidecar import generations  # noqa: E402
from nmos_sidecar.api import create_app  # noqa: E402
from nmos_sidecar.config import Settings  # noqa: E402
from nmos_sidecar.ids import uuid7  # noqa: E402
from nmos_sidecar.llm import LLMError  # noqa: E402
from nmos_sidecar.migrate import apply_migrations  # noqa: E402
from nmos_sidecar.vectors import projection, vector_literal  # noqa: E402

try:
    from nmos_sidecar import summaries
except ImportError:  # before Phase 12
    summaries = None
try:
    from nmos_sidecar import repairs
    from nmos_sidecar.facts import memory_view, version_key
except ImportError:  # before Phase 13
    repairs = None
try:
    from nmos_sidecar import canon, canonfacts
except ImportError:  # before Phase 14
    canon = None

SECRETS = 6  # about what the owner's longest chat keeps
BUDGET = int(os.environ.get("BENCH_BUDGET", "2000"))  # 2,000: Phase 12's default; Phase 15 compares 4,000 and 8,000
# BENCH_NAMES=1 (Phase 24): 20 Hangul names and 20 romanized ones, each given name used once
_FAMILY = "김이박최정강조윤장임"
_ROMAN = {"김": "Kim", "이": "Lee", "박": "Park", "최": "Choi", "정": "Jung", "강": "Kang", "조": "Cho", "윤": "Yoon",
          "장": "Jang", "임": "Lim"}
_HANGUL_GIVEN = ["민준", "서윤", "하진", "지우", "도윤", "수아", "은비", "태오", "하람", "이안", "서진", "예준", "지안", "시우",
                 "하윤", "유나", "준서", "다은", "건우", "소율"]
_LATIN_GIVEN = [("지호", "Ji-ho"), ("예린", "Ye-rin"), ("현우", "Hyun-woo"), ("채원", "Chae-won"), ("우진", "Woo-jin"),
                ("나연", "Na-yeon"), ("승민", "Seung-min"), ("가은", "Ga-eun"), ("도현", "Do-hyun"), ("수빈", "Su-bin"),
                ("재원", "Jae-won"), ("하은", "Ha-eun"), ("민서", "Min-seo"), ("지훈", "Ji-hoon"), ("서연", "Seo-yeon"),
                ("태민", "Tae-min"), ("유진", "Yu-jin"), ("성훈", "Sung-hoon"), ("아린", "A-rin"), ("동현", "Dong-hyun")]


def person(n: int) -> str:
    """Character n of 40 (n < 20: a Hangul name, else a romanized one), or 인물n without BENCH_NAMES."""
    if os.environ.get("BENCH_NAMES") != "1":
        return f"인물{n}"
    fam = _FAMILY[n % 10]
    return f"{fam}{_HANGUL_GIVEN[n]}" if n < 20 else f"{_ROMAN[fam]} {_LATIN_GIVEN[n - 20][1]}"


def called(n: int) -> str:
    """How a question calls character n: the given name, or the Hangul spelling of the romanized name."""
    return _HANGUL_GIVEN[n] if n < 20 else f"{_FAMILY[n % 10]}{_LATIN_GIVEN[n - 20][0]}"


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
            [(i, a["rid"], person(a["turn"] % 40), PLACES[a["turn"] % len(PLACES)],
              *(("limited", [person(a["turn"] % 40)], [person((a["turn"] + 1) % 40)]) if n < SECRETS
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


def add_repairs(db: psycopg.Connection, conv, head, key: str, count: int) -> int:
    """`count` owner repairs as the panel makes them (repairs.plan, then a row): a found out for each secret, then three
    retractions to one correction (its object, at its own turn) of a fact current at that point."""
    last = db.execute("SELECT max(turn) AS t FROM active_membership WHERE commit_id = %s", (head,)).fetchone()["t"]
    made = 0

    def add(kind: str, item: str, view: dict, **kw) -> None:
        nonlocal made
        target, value = repairs.plan(kind, item, view, last, None, kw.get("character"), None, kw.get("new_object"),
                                     None, None, None, version_key)
        db.execute("INSERT INTO owner_repair (id, conversation_id, kind, target, value) VALUES (%s, %s, %s, %s, %s)",
                   (uuid7(), conv, kind, Jsonb(target), Jsonb(value)))
        made += 1

    view = memory_view(db, head, key)
    for s in view["secrets"]:
        if made < count and s["open"]:
            add("secret_found_out", str(s["id"]), view, character=s["open"][0])
    while made < count:
        view = memory_view(db, head, key)
        f = next((f for f in view["facts"] if f["predicate"] == "located_in" and not f.get("owner")
                  and not f.get("hidden_from")), None)
        if f is None:
            break
        if made % 4:  # a correction ends what can be repaired of that subject: the owner's version is current
            add("fact_retract", str(f["id"]), view)
        else:
            add("fact_correct", str(f["id"]), view,
                new_object=next(x for x in PLACES if x != f.get("object")))
    return made


CARD = "하나는 항구 마을의 등대지기 딸로, 오래된 편지를 모으며 도서관에서 일한다. " * 40  # ≈ 1,800 characters
PERSONA = "카이토는 바다를 건너온 우편배달부로, 하나에게 편지를 전한다. " * 30  # ≈ 1,000 characters
LORE = "{name}은(는) 항구 마을 사람으로, {place}에서 일하며 {other}과(와) 오랜 친구 사이다. "  # × 12 ≈ 600 characters


def add_canon(client: TestClient, db: psycopg.Connection, chat, count: int) -> dict:
    """The chat's canon as the plugin syncs it (ADR 0045): the card, the persona and `count` lorebook entries, each
    keyed by its subject's name and an alias; then five canon facts per text of the canon generation, as its reads
    store them (ADR 0047). Returns the manifest id and the keys a prompt holds."""
    texts = {"card:name": "하나", "card:desc": CARD, "persona": PERSONA}
    meta: dict[str, dict] = {"card:name": {"field": "name"}, "card:desc": {"field": "desc"}, "persona": {"name": "카이토"}}
    for i in range(count):
        texts[f"lore:e{i}"] = LORE.format(name=f"인물{i}" if i < 40 else f"장소{i}", place=PLACES[i % len(PLACES)],
                                          other=f"인물{(i + 1) % 40}") * 12
        meta[f"lore:e{i}"] = {"scope": "character", "mode": "normal", "always_active": i % 4 == 0,
                              "keys": [f"인물{i}" if i < 40 else f"장소{i}", f"별칭{i}"]}
    entries = [{"key": k, "hash": canon.content_hash(t), "metadata": meta[k]} for k, t in texts.items()]
    out, _ = post(client, "/v1/sync/canon", {"chat_id": chat.id, "entries": entries,
                                             "contents": {canon.content_hash(t): t for t in texts.values()}})
    assert out["applied"], out
    key = generations.active(db, "canon")
    db.execute("UPDATE job SET status = 'obsolete' WHERE status = 'queued'")  # the reads are stored below instead
    revs = db.execute("SELECT so.host_logical_id AS hlid, sr.id AS rid, length(sr.content) AS chars FROM source_object so"
                      " JOIN source_revision sr ON sr.source_object_id = so.id WHERE so.source_kind = 'canon'"
                      " AND so.host_logical_id <> 'canon:card:name'").fetchall()
    ids = [uuid7() for _ in revs]
    with db.cursor() as cur:
        cur.executemany(
            "INSERT INTO extraction (id, source_revision_id, window_hash, compiler_version, extractor_key, model, raw,"
            " coverage, members) VALUES (%s, %s, 'canon:0:plain', %s, %s, 'bench', '{}', %s, %s)",
            [(i, r["rid"], canonfacts.VERSION, key, Jsonb({"chars": r["chars"], "part": 0, "parts": 1,
                                                          "part_chars": r["chars"], "unread_chars": 0}), [r["rid"]])
             for i, r in zip(ids, revs)])
        facts = []
        for n, (i, r) in enumerate(zip(ids, revs)):  # as sample 2's: about five facts a text, each text about its own
            who = f"인물{n}" if n < 40 else f"장소{n}"  # subject; the first 40 are the story's characters
            if n < 40:
                facts += [(i, r["rid"], who, "character", "identity", None, None, f"항구 마을의 {PLACES[n % len(PLACES)]} 일꾼"),
                          (i, r["rid"], who, "character", "has_trait", None, None, "편지를 아낀다"),
                          (i, r["rid"], who, "character", "has_trait", None, None, "바다를 무서워한다"),
                          (i, r["rid"], who, "character", "member_of", "등대 모임", "group", None),
                          (i, r["rid"], who, "character", "relationship", f"인물{(n + 1) % 40}", "character", "오랜 친구")]
            else:
                facts += [(i, r["rid"], who, "place", "world_fact", None, None, text)
                          for text in ("항구 북쪽에 있다", "밤에는 문을 닫는다", "오래된 편지가 보관되어 있다",
                                       "등대에서 보인다", "마을 사람들이 자주 찾는다")]
        cur.executemany("INSERT INTO assertion (extraction_id, source_revision_id, subject, subject_type, predicate,"
                        " object, object_type, value, status) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'valid')", facts)
    held = ["card:desc", "persona"] + [k for k, m in meta.items() if m.get("always_active")]
    return {"manifest": out["manifest_id"], "held": held, "texts": len(revs), "facts": len(facts)}


class Near:
    """BENCH_RECALL=wide: a query embedder that answers at once with the vector every message is near (`add_vectors`),
    so vector search has more relevant candidates than any budget takes, as on a long real chat."""

    def __init__(self, delay_ms: int = 0) -> None:
        self.base: list[float] = [random.Random(11).gauss(0, 1) for _ in range(DIM)]
        self.delay_ms = delay_ms  # BENCH_EMBED_MS: a slow embedder, answering after this long

    def embed(self, texts: list[str], timeout_s: float) -> list[list[float]]:
        if self.delay_ms:
            if self.delay_ms / 1000 > timeout_s:  # what httpx would do: the call times out before the answer
                time.sleep(timeout_s)
                raise LLMError(f"embedding request failed: ReadTimeout after {timeout_s:.3f}s")
            time.sleep(self.delay_ms / 1000)
        return [self.base for _ in texts]


def add_vectors(db: psycopg.Connection, key: str, base: list[float]) -> int:
    """One vector per revision under the active projection, each the shared base plus noise (cosine ≈ 0.78 to it)."""
    rnd = random.Random(7)
    rows = db.execute("SELECT id FROM source_revision").fetchall()
    with db.cursor() as cur:
        cur.executemany(
            "INSERT INTO revision_embedding (source_revision_id, projection, model, chunk, dim, text_start, text_end,"
            " embedding) VALUES (%s, %s, 'bench', 0, %s, 0, 10, %s::vector)",
            [(r["id"], key, DIM, vector_literal([b + rnd.gauss(0, 0.8) for b in base])) for r in rows])
    db.execute("ANALYZE revision_embedding")
    return len(rows)


def bench(n: int) -> dict:
    name = f"nmos_bench_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{name}"')
    url = ADMIN_URL.rpartition("/")[0] + f"/{name}"
    result: dict = {"messages": n, "summaries": summaries is not None and os.environ.get("BENCH_SUMMARIES") != "0"}
    off = {"summaries": False} if os.environ.get("BENCH_SUMMARIES") == "0" else {}  # the same code with them off
    wide = os.environ.get("BENCH_RECALL") == "wide"
    embed = {"embed_url": "http://bench/v1", "embed_model": "bench"} if wide else {}
    settings = Settings(database_url=url, llm_url="http://bench/v1", llm_model="bench", **off, **embed)  # no worker runs
    near = Near(int(os.environ.get("BENCH_EMBED_MS", "0"))) if wide else None
    try:
        apply_migrations(url)
        chat = build_chat(n)
        with psycopg.connect(url, row_factory=dict_row, autocommit=True) as db:
            lore = int(os.environ.get("BENCH_CANON", "0")) if canon is not None else 0
            with TestClient(create_app(settings)) as client:
                sync(client, chat)
                held = add_canon(client, db, chat, lore) if lore else None
            head = db.execute("SELECT head_commit_id FROM conversation").fetchone()["head_commit_id"]
            conv = db.execute("SELECT id FROM conversation").fetchone()["id"]
            db.execute("UPDATE job SET status = 'obsolete' WHERE status = 'queued'")  # no worker in this run
            result["facts"] = add_facts(db, head, generations.active(db, "extract"))
            if wide:
                result["vectors"] = add_vectors(db, projection(settings).key, near.base)
            if result["summaries"]:
                result["scenes"] = add_summaries(db, conv, head, generations.active(db, "summarize"))
            wanted = int(os.environ.get("BENCH_REPAIRS", "0"))
            if wanted and repairs is not None:
                result["repairs"] = add_repairs(db, conv, head, generations.active(db, "extract"), wanted)
            if held:
                result["canon"] = {"lore": lore, "texts": held["texts"], "facts": held["facts"],
                                   "held": len(held["held"])}
            extra = {"canon_manifest_id": held["manifest"], "canon_held": held["held"]} if held else {}
            db.execute("ANALYZE")
            with TestClient(create_app(settings, embedder=near)) as client:
                # The harness holds the 10,000-message chat in this process; a full collection during a request
                # would scan it too, which the sidecar alone never does. Its objects are frozen out of collection.
                gc.collect()
                gc.freeze()
                retrieves, story, sizes, vectors_on = [], 0, [], 0
                for i in range(15):
                    chat.reply(SENTENCE * 20 + f"새 장면 {i}.")
                    q = f"{PLACES[i % len(PLACES)]} 장면" if wide else QUERIES[i % len(QUERIES)]
                    q = f"처음에 {q}" if os.environ.get("BENCH_FIRST") == "1" else q  # Phase 21: every message asks how it started
                    q = f"{called(i * 3 % 40)}, {q}" if os.environ.get("BENCH_NAMES") == "1" else q  # Phase 24
                    # ADR 0061 item 7: the user's message is the question, as the plugin sends it; else another message
                    chat.user(q if os.environ.get("BENCH_PREFETCH") == "1" else f"새 대사 {i}: {PLACES[i % len(PLACES)]}에 다시 가자.")
                    sync(client, chat)
                    out, ms = post(client, "/v1/retrieve", {"chat_id": chat.id, "query": q,
                                                             "previous_ai": "" if wide else SENTENCE,
                                                             "in_context_ids": [m["chatId"] for m in chat.messages[-40:]],
                                                             "budget_tokens": BUDGET, **extra})
                    retrieves.append(ms)
                    vectors_on += out.get("vectors") == "on"
                    story += "<Story>" in out["packet"]["text"]
                    sizes.append((out["packet"]["token_estimate"], out["packet"]["excerpt_count"]))
            result["retrieve_ms"] = {"p50": p(retrieves, 0.5), "p95": p(retrieves, 0.95)}
            result["packets_with_story"] = story
            if near is not None:
                result["vectors_on"] = vectors_on  # of 15 requests (K34, ADR 0061)
            result["budget"], result["policy"] = BUDGET, settings.packet_policy or "default"
            result["packet_tokens_mean"] = round(sum(t for t, _ in sizes) / len(sizes))
            result["excerpts_mean"] = round(sum(e for _, e in sizes) / len(sizes), 1)
            if held:  # the requests read the canon's names and facts (ADR 0046, 0047)
                result["canon"]["requests_read"] = db.execute(
                    "SELECT count(*) AS n FROM retrieval_trace WHERE recall_options->>'canon_facts' = %s",
                    (held["manifest"],)).fetchone()["n"]
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
