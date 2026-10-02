"""M0, the RP evaluation on real chats (PHASE-11 step 2): does the packet a real request gets hold what its scene
needs, and keep out what it must not? Read-only; point it at a restored backup (PHASE-11 Q1).

The cases are the owner's chats and stay outside the repository; the report prints numbers only.

    cd apps/sidecar
    uv run python ../../tools/eval_rp.py DIR --db postgresql://…/copy [--extractor KEY] [--summarizer KEY] [--canon KEY]
        [--policy P] [--budget N] [--projection KEY [--embed-url URL]] [--no-vectors] [--json]
        [--given-name-join [--show-joins]]

DIR/cases.json:

    [{"name": "goal-1", "category": "goal", "trace": "<a recorded request of the chat>",
      "query": "<optional: a probe in place of the request's user message>",
      "gold": ["<a phrase the packet must hold>", ["<a phrase>", "<or another wording of it>"]],
      "forbidden": ["<a phrase it must not hold: stale, irrelevant, kept from the one asking>"]}]

A case passes when the model has every gold phrase (any wording of it) and the packet holds no forbidden one; phrases
match case- and space-insensitively. The model has a phrase when the packet holds it or the messages the request's
prompt already held do (the recorded `in_context` window): memory leaves those out on purpose (D3), so a gold answer
there is not missing. The report counts both. A forbidden phrase is what must not be presented as current: the
earlier version a packet-v5 line names ("; before, turn N: …", ADR 0038) does not count against it. Categories are free text; PHASE-11 uses state, past, promise, goal, question,
threat, debt, relationship, address, secret, why and irrelevant. The request is compiled again as of its own
time (ADR 0027 replay); `--extractor` names a newer extractor generation, and the request is then compiled as
of now with that generation's facts, as `eval_secrets.py build` does; `--policy` and `--budget` replace the
request's own (a request recorded before the default reserve rose to 800 carries 600); `--canon` names a canon
generation whose facts the request reads, as of now (ADR 0047): a request recorded before canon facts reads the chat's
canon in force, one recorded since keeps the canon it recorded (ADR 0027), so its read may have none. A request whose chat was
edited before its position since cannot be replayed and is counted as skipped.

Vectors (PHASE-15 Q6). By default each request searches the embedding projection it recorded, with the settings'
embedder. `--projection` names another one, for a copy embedded again since (a request's own projection may have
been partial): the query is embedded with that projection's model, at its recorded endpoint when that is this
machine, else at `--embed-url`, which must then be given. The embedder is warmed with one query first (a local model
loads in seconds, a request waits 300 ms), and every replay gets `--embed-timeout-ms` (5,000) for its query. Each case
reports whether vector search ran; the table counts them, and when vectors were asked for and a case ran without
them, the tool says so and exits with status 2: a lexical-only number is never passed off as one with vectors.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from nmos_sidecar import audit, runtime, vectors
from nmos_sidecar.config import Settings
from nmos_sidecar.facts import memory_view
from nmos_sidecar.llm import Embedder
from nmos_sidecar.retrieval import RecallOptions, query_prefix


def norm(text: str) -> str:
    return " ".join(text.casefold().split())


BEFORE = re.compile(r"; before, turn -?\d+: [^<]*")  # packet-v5: what a standing fact replaced, and how it started
STORY = re.compile(r"<Story>.*?</Story>", re.S)  # summaries tell the past (packet-v8, ADR 0043)


def score(case: dict[str, Any], text: str, prompt: str = "") -> dict[str, Any]:
    """How a packet's text answers one case: gold phrases the model has (in the packet, or in the prompt's own
    messages: `prompt`), forbidden ones placed as current, pass."""
    held, in_prompt, packet, current, window = [], 0, norm(text), norm(BEFORE.sub("", STORY.sub("", text))), norm(prompt)
    for phrase in case.get("gold") or []:
        wordings = [norm(w) for w in ([phrase] if isinstance(phrase, str) else phrase) if w.strip()]
        if any(w in packet for w in wordings):
            held.append(True)
        elif window and any(w in window for w in wordings):
            held.append(True)
            in_prompt += 1
        else:
            held.append(False)
    placed = [norm(p) in current for p in case.get("forbidden") or [] if p.strip()]
    # a case needs memory when one of its gold phrases is in no wording in the prompt's own messages
    needs = any(not any(norm(w) in window for w in ([g] if isinstance(g, str) else g) if w.strip())
                for g in case.get("gold") or [])
    return {"gold": len(held), "held": sum(held), "in_prompt": in_prompt, "forbidden": len(placed),
            "placed": sum(placed), "passed": all(held) and not any(placed), "needs_memory": needs}


WINDOW = ("SELECT sr.content FROM retrieval_trace t JOIN active_membership am ON am.commit_id = {commit}"
          " JOIN source_revision sr ON sr.id = am.source_revision_id JOIN source_object so ON so.id = sr.source_object_id"
          " WHERE t.id = %s AND so.host_logical_id = ANY(SELECT jsonb_array_elements_text(t.in_context))"
          " AND am.position {upto} t.upto_position ORDER BY am.position")


def prompt_window(conn: psycopg.Connection, trace: UUID, probe: bool = False) -> str:
    """The text of the messages the request's prompt already held (its `in_context` ids). Membership is kept for the
    head commit only, so once the chat moved on, the request's own commit has none: then the same messages are read at
    the conversation's head (PHASE-18 step 2; an empty window scored answers the prompt held as memory's). A `probe`
    takes the place of the request's own message, so that message is not part of the window."""
    upto = "<" if probe else "<="
    rows = conn.execute(WINDOW.format(commit="t.commit_id", upto=upto), (trace,)).fetchall()
    if not rows:
        rows = conn.execute(WINDOW.format(
            commit="(SELECT c.head_commit_id FROM conversation c WHERE c.id = t.conversation_id)", upto=upto),
            (trace,)).fetchall()
    return "\n".join(r["content"] or "" for r in rows)


LOCAL = re.compile(r"^https?://(127\.0\.0\.1|localhost|\[::1\])(:\d+)?(/|$)")


def options(conn: psycopg.Connection, use_vectors: bool, projection: str | None = None,
            embed_url: str | None = None) -> RecallOptions:
    """The embedder a replay searches with: the settings' active projection, or `projection` (its model; its recorded
    endpoint only when local, so a copy of another machine's database never calls that machine's endpoint)."""
    cur = runtime.effective(Settings(), runtime.stored(conn))
    if not use_vectors:
        return RecallOptions(query_prefix=query_prefix(cur.embed_model, cur.embed_query_instruction))
    if projection:
        row = conn.execute("SELECT model, endpoint FROM projection_generation WHERE key = %s AND kind = 'embed'",
                           (projection,)).fetchone()
        if row is None:
            raise SystemExit(f"no embedding projection {projection} in this database")
        url = embed_url or (row["endpoint"] if LOCAL.match(row["endpoint"]) else None)
        if not url:
            raise SystemExit(f"{projection} was embedded at another machine's endpoint: give --embed-url")
        return RecallOptions(embedder=Embedder(url, row["model"], ""), embed_projection=projection,
                             query_prefix=query_prefix(row["model"], cur.embed_query_instruction))
    pj = vectors.projection(cur)
    emb = Embedder(cur.embed_url, cur.embed_model, cur.embed_api_key) if pj else None
    return RecallOptions(embedder=emb, embed_projection=pj.key if pj else "",
                         query_prefix=query_prefix(cur.embed_model, cur.embed_query_instruction))


def warm(opts: RecallOptions) -> None:
    """Load the embedding model before the first replay (a cold local model takes seconds, PHASE-15 Q6)."""
    if opts.embedder is not None:
        opts.embedder.embed([opts.query_prefix + "warm-up"], 120)


def evaluate(conn: psycopg.Connection, cases: list[dict[str, Any]], opts: RecallOptions, policy: str | None = None,
             extractor: str | None = None, budget: int | None = None, summarizer: str | None = None,
             canon: str | None = None, projection: str | None = None,
             embed_timeout_ms: int | None = None, keywords: bool | None = None,
             anchor: str | None = None, given_name_join: bool | None = None) -> dict[str, Any]:
    """Every case's numbers, and a summary per category and overall. Read-only."""
    results: list[dict[str, Any]] = []
    overrides: dict[str, Any] = {"extractor_key": extractor} if extractor else {}
    if embed_timeout_ms is not None and opts.embedder is not None:  # a replay is not a timing test
        overrides["embed_timeout_ms"] = embed_timeout_ms
    if summarizer:  # summaries of this generation in <Story> (packet-v8, ADR 0043), as of now
        overrides["summarize_key"] = summarizer
    if canon:  # canon facts of this generation (ADR 0047), as of now
        overrides["canon_key"] = canon
    if keywords is not None:  # the keyword route on or off whatever the request recorded (ADR 0052)
        overrides["lexical_keywords"] = keywords
    if anchor:  # packet-v11's tie-break anchor (PHASE-27 Q1b, ADR 0063): "focus" (today's) or "keywords"
        overrides["excerpt_anchor"] = anchor
    if given_name_join is not None:  # a full name and its given name as one (PHASE-28 Q4), whatever the request recorded
        overrides["given_name_join"] = given_name_join
    known_at = datetime.now(timezone.utc) if extractor or summarizer or canon else None
    for case in cases:
        out = audit.replay(conn, UUID(case["trace"]), opts, policy, known_at=known_at, query=case.get("query"),
                           budget=budget, projection=projection, **overrides)
        row = {"name": case["name"], "category": case.get("category") or "other"}
        if out is None or out["status"] != "ok":
            results.append({**row, "status": "missing" if out is None else out["status"]})
            continue
        results.append({**row, "status": "ok", "tokens": out["tokens"], "policy": out["policy"],
                        "vectors": out.get("vectors") == "on", "lexical_found": out.get("lexical_found", 0) > 0,
                        "excerpt_chars": excerpt_lengths(out["text"]),
                        **score(case, out["text"], prompt_window(conn, UUID(case["trace"]), case.get("query") is not None))})
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in results:
        groups[r["category"]].append(r)
        groups["all"].append(r)
    summary = {}
    for name, rows in groups.items():
        ok = [r for r in rows if r["status"] == "ok"]
        memory = [r for r in ok if r["needs_memory"]]
        summary[name] = {"cases": len(rows), "skipped": len(rows) - len(ok), "passed": sum(r["passed"] for r in ok),
                         "memory_cases": len(memory), "memory_passed": sum(r["passed"] for r in memory),
                         "gold": sum(r["gold"] for r in ok), "held": sum(r["held"] for r in ok),
                         "in_prompt": sum(r["in_prompt"] for r in ok),
                         "forbidden": sum(r["forbidden"] for r in ok), "placed": sum(r["placed"] for r in ok),
                         "tokens_mean": round(sum(r["tokens"] for r in ok) / len(ok)) if ok else None,
                         "vectors": sum(r["vectors"] for r in ok),
                         "lexical_found": sum(r["lexical_found"] for r in ok),
                         "excerpt_median": _median([n for r in ok for n in r["excerpt_chars"]])}
    return {"cases": results, "summary": summary}


def given_joins(conn: psycopg.Connection, cases: list[dict[str, Any]], extractor: str | None = None
                ) -> dict[str, list[list[str]]]:
    """Every join `given_name_join` makes as of each case's request (PHASE-28 Q4, Q5 (b)), per trace: [full name, given
    name], normalized. Names of the owner's chats: printed to the terminal for the owner to check, never kept."""
    out: dict[str, list[list[str]]] = {}
    for trace in dict.fromkeys(case["trace"] for case in cases):
        t = audit._trace(conn, UUID(trace))
        if t is None or t.get("upto_position") is None:
            continue
        view = memory_view(conn, t["head_commit_id"], extractor or t["extractor_key"], t["upto_position"],
                           None if extractor else t["created_at"], given_joins=True)
        r = view["resolution"]
        if r is not None and r.given_joins:
            out[trace] = [[full[1], short[1]] for full, short in r.given_joins]
    return out


EXCERPT = re.compile(r"<Excerpt\b[^>]*>(.*?)</Excerpt>", re.S)


def excerpt_lengths(text: str) -> list[int]:
    """The length, in characters, of each raw excerpt a packet placed (PHASE-18 step 2)."""
    return [len(html.unescape(m)) for m in EXCERPT.findall(text)]


def _median(values: list[int]) -> float | None:
    return statistics.median(values) if values else None


def table(report: dict[str, Any]) -> str:
    """The summary as a markdown table: numbers only, no phrase of any case."""
    rows = ["| Category | cases | passed | needing memory: passed | gold held | of it in the prompt | forbidden placed"
            " | skipped | mean tokens | with vectors | lexical found | excerpt median chars |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for name, s in sorted(report["summary"].items(), key=lambda kv: (kv[0] == "all", kv[0])):
        rows.append(f"| {name} | {s['cases']} | {s['passed']} | {s['memory_passed']}/{s['memory_cases']}"
                    f" | {s['held']}/{s['gold']} | {s['in_prompt']} | {s['placed']}/{s['forbidden']} | {s['skipped']}"
                    f" | {s['tokens_mean'] if s['tokens_mean'] is not None else '—'}"
                    f" | {s['vectors']}/{s['cases'] - s['skipped']} | {s['lexical_found']}/{s['cases'] - s['skipped']}"
                    f" | {s['excerpt_median'] if s['excerpt_median'] is not None else '—'} |")
    return "\n".join(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("dir", type=Path, help="the case directory (outside the repository)")
    ap.add_argument("--db", default=os.environ.get("NMOS_DATABASE_URL", Settings().database_url))
    ap.add_argument("--extractor", help="a newer extractor generation's key: compile as of now with its facts")
    ap.add_argument("--summarizer", help="a summarize generation's key: <Story> from its summaries as of now")
    ap.add_argument("--canon", help="a canon generation's key: its facts, as of now (a request recorded since canon"
                    " facts keeps the canon it recorded)")
    ap.add_argument("--policy", help="a packet policy in place of each request's own")
    ap.add_argument("--budget", type=int, help="a memory budget (tokens) in place of each request's own")
    ap.add_argument("--no-vectors", action="store_true")
    ap.add_argument("--projection", help="search this embedding projection's vectors in place of each request's own")
    ap.add_argument("--embed-url", help="the embedding endpoint for --projection (needed when it was not this machine's)")
    ap.add_argument("--embed-timeout-ms", type=int, default=5000, help="each replay's query embedding timeout")
    ap.add_argument("--anchor", choices=("focus", "keywords"),
                    help="packet-v11's excerpt tie-break anchor (Phase 27 Q1b): the question with the previous reply,"
                         " or the question's keywords alone")
    ap.add_argument("--keywords", choices=("on", "off"),
                    help="the keyword route (ADR 0052) in place of what each request recorded (before it: off)")
    ap.add_argument("--given-name-join", action="store_true",
                    help="read a full name and its given name as one character (Phase 28 Q4) in every request")
    ap.add_argument("--show-joins", action="store_true",
                    help="print to stderr every join --given-name-join makes, per request, for the owner to check"
                         " (names of the chat: keep them out of the repository)")
    ap.add_argument("--json", action="store_true", help="per-case numbers as JSON (names and counts only)")
    args = ap.parse_args()
    cases = json.loads((args.dir / "cases.json").read_text(encoding="utf-8"))
    with psycopg.connect(args.db, row_factory=dict_row, autocommit=True,
                         options="-c default_transaction_read_only=on") as conn:
        opts = options(conn, not args.no_vectors, args.projection, args.embed_url)
        warm(opts)
        report = evaluate(conn, cases, opts, args.policy, args.extractor, args.budget, args.summarizer, args.canon,
                          args.projection, args.embed_timeout_ms,
                          None if args.keywords is None else args.keywords == "on", anchor=args.anchor,
                          given_name_join=True if args.given_name_join else None)
        joins = given_joins(conn, cases, args.extractor) if args.show_joins else {}
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        if args.no_vectors:  # asked for explicitly: production recalls mostly without vectors (K34, PHASE-18 Q5)
            print("Vectors off (--no-vectors): lexical recall only.\n")
        print(table(report))
    for trace, pairs in joins.items():
        print(f"given-name joins as of {trace}: " + "; ".join(" = ".join(p) for p in pairs), file=sys.stderr)
    if args.show_joins:
        print(f"given-name joins: {sum(len(p) for p in joins.values())} over {len(joins)} request(s)", file=sys.stderr)
    lexical = [r["name"] for r in report["cases"] if r["status"] == "ok" and not r["vectors"]]
    if not args.no_vectors and lexical:
        print(f"vectors did not run for {len(lexical)} case(s): {', '.join(lexical)}", file=sys.stderr)
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
