"""Sampled-turn comparison of extractor prompts (docs/phases/PHASE-19.md, step 4): extract chosen turns of an evaluation
copy with the sidecar's own prompt, several runs, and score them.

`run` extracts each chosen turn of a copy exactly as the turn worker would (`extraction.load_context`, the hints of
one existing generation of the copy so every prompt sees the same, `build_prompt`, `normalize`) and writes one JSON
file per turn. The code measured is the `nmos_sidecar` on `PYTHONPATH`: this checkout for its own generation, another
checkout for another (today's prompt from `main`, say). Every valid row also records whether its quote is found in its
target turn (`quote_in_turn`, the evidence check of extract-v14, ADR 0054), so a generation without the check can be
scored as if it had it. `--dry` makes no call and prints the calls and an estimate of their input tokens.

`score` compares labels: rows, the evidence check, input and output tokens, `addresses` and `relationship` rows, and,
with `--ledger` (a fact ledger of a synthetic chat: `must_appear_in_turn`, `subject`, `statement`, `kind`), how many
ledger facts some row finds (one of the fact's characters named, its object or value overlapping the statement's
character trigrams by at least 0.5): a recall measure with no precision check.

The chats, ledgers and results stay outside the repository; the tool prints counts only.

    cd apps/sidecar && NMOS_EVAL_API_KEY=… uv run python ../../tools/eval_extract_sample.py run ~/eval/out \\
        --db postgresql://nmos:nmos@127.0.0.1:5436/copy --hints extract-… --label v14 --runs 3 \\
        --ledger ~/eval/ledger.json --url https://ollama.com/v1 --model gemma4:31b
    PYTHONPATH=/path/to/main/apps/sidecar/src uv run python ../../tools/eval_extract_sample.py run … --label v13
    uv run python ../../tools/eval_extract_sample.py score ~/eval/out --labels v13,v14 --ledger ~/eval/ledger.json
"""

from __future__ import annotations

import argparse
import json
import os
import statistics as st
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

from nmos_sidecar import extraction as X
from nmos_sidecar.llm import ChatModel, LLMError, metered
from nmos_sidecar.packet import estimate_tokens
from nmos_sidecar.predicates import registry_prompt
from nmos_sidecar.threads import similarity

QUOTE_MIN = X.EVIDENCE_MIN  # the reveal test (PHASE-10), applied to every quote since extract-v14
QUOTE_MIN_CHARS = getattr(X, "EVIDENCE_MIN_CHARS", 12)  # a checkout from before extract-v14 has no floor of its own


def conversation_of(conn: psycopg.Connection, given: str | None) -> str:
    """The chat to sample: the one given, or the copy's only chat with turns (a copy often holds several)."""
    if given:
        return given
    chats = [r["id"] for r in conn.execute("""
        SELECT DISTINCT c.id FROM conversation c JOIN active_membership am ON am.commit_id = c.head_commit_id
        WHERE am.turn_hash IS NOT NULL""").fetchall()]
    if len(chats) != 1:
        raise SystemExit(f"this database holds {len(chats)} chats with turns: give --conversation")
    return str(chats[0])


def anchors(conn: psycopg.Connection, conversation: str) -> list[dict[str, Any]]:
    """One anchor per turn of that chat's head, in turn order."""
    return conn.execute("""
        SELECT DISTINCT ON (am.turn) am.source_revision_id AS id, am.turn_hash, am.turn
        FROM conversation c JOIN active_membership am ON am.commit_id = c.head_commit_id
        WHERE c.id = %s AND am.turn IS NOT NULL AND am.turn_hash IS NOT NULL
        ORDER BY am.turn, am.position""", (conversation,)).fetchall()


def ledger_turns(path: Path) -> set[int]:
    """The turns a ledger says a fact must appear in (1-based chat turns → NMOS's 0-based turns)."""
    return {x["must_appear_in_turn"] - 1 for x in json.loads(path.read_text(encoding="utf-8"))
            if x.get("must_appear_in_turn") is not None}


def chosen(conn: psycopg.Connection, args: argparse.Namespace) -> list[dict[str, Any]]:
    rows = anchors(conn, conversation_of(conn, args.conversation))
    if args.ledger:
        wanted = ledger_turns(args.ledger)
        rows = [a for a in rows if a["turn"] in wanted]
    elif args.sample:
        rows = rows[:: max(1, len(rows) // args.sample)][: args.sample]
    return rows


def in_turn(quote: str | None, text: str) -> bool | None:
    if not quote or len(quote) < QUOTE_MIN_CHARS:
        return None
    return similarity(quote, text) >= QUOTE_MIN


def prompts(args: argparse.Namespace) -> list[dict[str, Any]]:
    out = []
    with psycopg.connect(args.db, row_factory=dict_row, autocommit=True,
                         options="-c default_transaction_read_only=on") as conn:
        spec = conn.execute("SELECT spec FROM projection_generation WHERE key = %s", (args.hints,)).fetchone()
        if spec is None:
            raise SystemExit(f"no generation {args.hints} in this database")
        for a in chosen(conn, args):
            ctx = X.load_context(conn, a["id"], a["turn_hash"], args.turns, args.hints)
            if ctx is None or sum(len(r["content"]) for r in ctx["members"]) < X.MIN_CONTENT_CHARS:
                continue
            earlier = X.earlier_assertions(conn, ctx, args.hints)
            hints = X.entity_hints(conn, ctx, args.hints, spec["spec"].get("hints", 0), earlier)
            secrets = X.secret_hints(ctx, earlier)
            user = X.build_prompt(ctx, hints, X.promise_hints(ctx, earlier), secrets, X.thread_hints(ctx, earlier))
            out.append({"turn": a["turn"], "user": user, "hints": hints, "secrets": secrets,
                        "text": "\n".join(r["content"] for r in ctx["members"]),
                        # what the model saw of the target turn (extract-v14's `shown_target`)
                        "shown": "\n".join(r["content"][:X.TARGET_CHARS] for r in ctx["members"])})
    return out


def run(args: argparse.Namespace) -> None:
    system = X.SYSTEM_PROMPT.format(registry=registry_prompt())
    checks = hasattr(X, "shown_target")  # extract-v14 or later: normalize parks a quote not in the turn
    todo = []
    for p in prompts(args):
        for n in range(1, args.runs + 1):
            path = args.out / args.label / str(n) / f"{args.name}-{p['turn']}.json"
            if not path.exists():
                todo.append((path, p))
    tokens = sum(estimate_tokens(system + p["user"]) for _, p in todo)
    print(f"{args.label} ({X.COMPILER_VERSION}): {len(todo)} calls, about {tokens / 1e6:.2f}M input tokens (estimate)",
          flush=True)
    if args.dry or not todo:
        return
    key = os.environ.get("NMOS_EVAL_API_KEY", "")
    model = ChatModel(args.url, args.model, key, timeout_s=300)

    def one(job: tuple[Path, dict[str, Any]]) -> str:
        path, p = job
        for attempt in range(6):
            try:
                t0 = time.monotonic()
                parsed, raw, usage = metered(model.complete_metered, system, p["user"])
                items = parsed.get("assertions")
                if not isinstance(items, list):
                    raise LLMError("model reply has no `assertions` list")
                items = [x for x in items if not (isinstance(x, dict) and x.get("predicate") in X.DERIVED)]
                items += X.revealed(parsed, p["secrets"], p["text"])
                rows = (X.normalize(items, p["text"], p["hints"], p["shown"]) if checks
                        else X.normalize(items, p["text"], p["hints"]))
                for r in rows:
                    r["quote_in_turn"] = in_turn(r.get("evidence"), p["shown"])
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps({"turn": p["turn"], "compiler": X.COMPILER_VERSION, "usage": usage,
                                            "secs": round(time.monotonic() - t0, 1), "assertions": rows,
                                            "reveals": len(parsed.get("secrets") or [])},
                                           ensure_ascii=False, default=str), encoding="utf-8")
                return "ok"
            except LLMError as exc:
                print(f"  {path.stem} attempt {attempt + 1}: {str(exc)[:80]}", flush=True)
                time.sleep(30 * (attempt + 1) if "429" in str(exc) else 5)
        return "failed"

    with ThreadPoolExecutor(args.workers) as pool:
        results = list(pool.map(one, todo))
    print(args.label, dict(Counter(results)))


def grams(s: str) -> set[str]:
    s = f"  {(s or '').lower()} "
    return {s[i: i + 3] for i in range(len(s) - 2)}


def hit(a: dict[str, Any], item: dict[str, Any], persona: str) -> bool:
    """One of the fact's characters named in the row, and its object or value overlapping the fact's statement."""
    u = lambda x: str(x or "").replace("{{user}}", persona)  # noqa: E731
    where = " ".join([u(a.get("subject")), u(a.get("object")), u(a.get("value")),
                      u(json.dumps(a.get("participants") or [], ensure_ascii=False))])
    who = [] if item["subject"] == "early-detail" else [n for n in item["subject"].replace("->", "-").split("-") if n]
    if who and not any(n in where or n[-2:] in where for n in who):
        return False
    stmt = grams(item["statement"])
    for value in (a.get("object"), a.get("value")):
        g = grams(u(value))
        if len(g) >= 4 and len(g & stmt) / min(len(g), len(stmt)) >= 0.5:
            return True
    return False


def score(args: argparse.Namespace) -> None:
    gold: dict[int, list[dict[str, Any]]] = {}
    if args.ledger:
        for x in json.loads(args.ledger.read_text(encoding="utf-8")):
            if x.get("must_appear_in_turn") is not None:
                gold.setdefault(x["must_appear_in_turn"] - 1, []).append(x)
    print("| label | run | turns | valid rows | quote < 12 | not in the turn | share | ledger facts: any row | valid, checked |"
          " … lost to the check | addresses / relationship | input tokens (sum) | output (median) |")
    print("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for label in args.labels.split(","):
        for run_dir in sorted((args.out / label).iterdir()):
            files = sorted(run_dir.glob(f"{args.name}-*.json"))
            if not files:
                continue
            c: Counter[str] = Counter()
            kinds: Counter[str] = Counter()
            usage = []
            for f in files:
                r = json.loads(f.read_text(encoding="utf-8"))
                usage.append(r.get("usage") or {})
                valid = [a for a in r["assertions"] if a["status"] == "valid"
                         or (a["status"] == "pending" and (a.get("reason") or "").startswith("evidence not in the turn"))]
                kept = [a for a in valid if a.get("quote_in_turn") is not False]
                c["valid"] += len(valid)
                c["short"] += sum(1 for a in valid if a.get("evidence") and len(a["evidence"]) < QUOTE_MIN_CHARS)
                c["out"] += len(valid) - len(kept)
                c["pairs"] += sum(1 for a in kept if a["predicate"] in ("addresses", "relationship"))
                for item in gold.get(r["turn"], []):
                    found = any(hit(a, item, args.persona) for a in r["assertions"])
                    found_kept = any(hit(a, item, args.persona) for a in kept)
                    c["gold"] += 1
                    c["found"] += found
                    c["kept"] += found_kept
                    c["lost"] += any(hit(a, item, args.persona) for a in valid) and not found_kept
                    kinds[item["kind"]] += found_kept
            share = 100 * c["out"] / max(1, c["valid"])
            tokens_in = sum(u.get("input", 0) for u in usage)
            out_median = st.median(u.get("output", 0) for u in usage)
            print(f"| {label} | {run_dir.name} | {len(files)} | {c['valid']} | {c['short']} | {c['out']} | {share:.1f} % |"
                  f" {c['found']}/{c['gold']} | {c['kept']}/{c['gold']} | {c['lost']} | {c['pairs']} |"
                  f" {tokens_in / 1e3:.0f}k | {out_median:.0f} |")
            if kinds:
                print(f"|  | ledger kinds found (valid, checked): {dict(sorted(kinds.items()))} | | | | | | | | | | | |")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="extract the chosen turns")
    r.add_argument("out", type=Path, help="the results directory (outside the repository)")
    r.add_argument("--db", required=True, help="an evaluation copy (read-only connection)")
    r.add_argument("--hints", required=True, help="the copy's generation whose earlier facts give every prompt's hints")
    r.add_argument("--label", required=True, help="the name of what is measured, e.g. v13 or v14")
    r.add_argument("--conversation", help="the chat to sample (required when the copy holds several)")
    r.add_argument("--name", default="chat", help="the copy's name in the result files")
    r.add_argument("--ledger", type=Path, help="choose the turns a fact ledger names")
    r.add_argument("--sample", type=int, help="else this many turns, evenly spaced")
    r.add_argument("--turns", type=int, default=3, help="context turns (the worker's NMOS_EXTRACT_TURNS)")
    r.add_argument("--runs", type=int, default=3)
    r.add_argument("--workers", type=int, default=2)
    r.add_argument("--url", default="https://ollama.com/v1")
    r.add_argument("--model", default="gemma4:31b")
    r.add_argument("--dry", action="store_true", help="no call: print the calls and an input-token estimate")
    s = sub.add_parser("score", help="compare labels")
    s.add_argument("out", type=Path)
    s.add_argument("--labels", required=True, help="comma-separated")
    s.add_argument("--name", default="chat")
    s.add_argument("--ledger", type=Path)
    s.add_argument("--persona", default="", help="the name `{{user}}` stands for in the ledger's chat")
    args = ap.parse_args()
    run(args) if args.cmd == "run" else score(args)
    sys.exit(0)


if __name__ == "__main__":
    main()
