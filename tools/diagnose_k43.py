"""Read-only K43 stage capture, or inspect a saved capture. Never calls a model.

Run with the sidecar environment. A frozen query vector must name the exact
projection and prefixed query; without it, explicitly request lexical-only.
Captures contain private story text: keep them outside the repository.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from copy import deepcopy
from dataclasses import asdict, replace
import json
import math
import os
from pathlib import Path
from typing import Any
from unittest.mock import patch
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from nmos_sidecar import audit, retrieval

GOLD = "북해 조류 일지"


class FrozenEmbedder:
    def __init__(self, payload: dict[str, Any], trace: dict[str, Any]):
        expected = (trace.get("recall_options") or {}).get("query_prefix", "") + trace["query"]
        if payload.get("projection") != trace.get("embed_projection") or payload.get("text") != expected:
            raise ValueError("frozen vector must match the trace's projection and exact prefixed query")
        vector = payload.get("vector")
        if not isinstance(vector, list) or not vector or any(
                isinstance(x, bool) or not isinstance(x, (float, int)) or not math.isfinite(x) for x in vector):
            raise ValueError("vector must be a nonempty finite numeric list")
        self.text, self.vector = expected, vector

    def embed(self, texts: list[str], **kwargs: Any) -> list[list[float]]:
        if texts != [self.text]:
            raise ValueError("unexpected query: refusing to substitute another embedding")
        return [self.vector]


def capture(conn: Any, trace_id: UUID, vector: dict[str, Any] | None = None,
            lexical_only: bool = False, gold: str = GOLD) -> dict[str, Any]:
    trace = audit._trace(conn, trace_id)
    if trace is None:
        raise ValueError("trace not found")
    if vector is None and not lexical_only:
        raise ValueError("provide a frozen vector or explicitly choose --lexical-only")
    if vector is not None and lexical_only:
        raise ValueError("frozen vector and lexical-only are mutually exclusive")
    options = retrieval.RecallOptions()
    if vector is not None:
        options = replace(options, embedder=FrozenEmbedder(vector, trace),
                          embed_projection=trace["embed_projection"])
    stages: dict[str, Any] = {"fact_rank_calls": []}

    def observe(module: Any, name: str, key: str):
        original = getattr(module, name)

        def wrapped(*args: Any, **kwargs: Any):
            result = original(*args, **kwargs)
            if name == "memory_view":
                stages[key] = deepcopy({k: result[k] for k in ("assertions", "facts", "claims", "items", "other")})
            elif name == "relevant_facts":
                # `limit` is the fifth positional argument at both call sites (retrieval.gather); a keyword call would
                # need this changed.
                all_args = list(args)
                all_args[4] = len(args[0])
                stages[key].append({"input": deepcopy(args[0]), "output": deepcopy(result),
                                    "ranked_all": deepcopy(original(*all_args, **kwargs)),
                                    "limit": args[4], "options": deepcopy(kwargs)})
            elif name == "gather":
                stages[key] = asdict(result)
                stages["effective_options"] = asdict(args[5])
                stages["effective_options"].pop("embedder", None)
            elif name == "compile_gathered":
                stages[key] = asdict(result)
            else:
                stages[key] = deepcopy(result)
            return result
        return patch.object(module, name, wrapped)

    with ExitStack() as stack:
        for module, name, key in (
                (retrieval, "_lexical", "lexical"), (retrieval, "_keyword_lexical", "keyword"),
                (retrieval, "vector_candidates", "vector"), (retrieval, "memory_view", "view"),
                (retrieval, "relevant_facts", "fact_rank_calls"), (audit, "gather", "gathered"),
                (audit, "compile_gathered", "compiled")):
            stack.enter_context(observe(module, name, key))
        result = audit.replay(conn, trace_id, options)
        if result and result.get("status") == "changed" and trace.get("query"):
            # A harness probe is sent and deleted again, so its own position reads as changed: replay it as the probe
            # (`query`), which needs only the story before it intact (audit.replay, PHASE-18 step 2). The replay then
            # notes "query replaced" and is not compared with the recorded ledger (`reproduced` absent).
            result = audit.replay(conn, trace_id, options, query=trace["query"])
    if result and result.get("status") == "ok":
        stages["gold_sources"] = conn.execute(
            "SELECT sr.id, am.position, am.turn, so.host_logical_id, sr.lifecycle, sr.metadata,"
            " rt.clean_content AS clean FROM active_membership am"
            " JOIN source_revision sr ON sr.id = am.source_revision_id"
            " JOIN source_object so ON so.id = sr.source_object_id"
            " LEFT JOIN revision_text rt ON rt.source_revision_id = sr.id AND rt.normalizer = %s"
            " WHERE am.commit_id = %s AND am.position <= %s AND strpos(rt.clean_content, %s) > 0",
            (retrieval.NORMALIZER_VERSION, trace["head_commit_id"], trace["upto_position"], gold)).fetchall()
        stages["stored_assertions"] = conn.execute(
            "SELECT a.id, a.subject, a.predicate, a.object, a.value, a.status, a.polarity, a.modality, a.source,"
            " e.extractor_key, e.window_hash, e.discarded_at, e.created_at, am.position, am.turn, am.turn_hash"
            " FROM active_membership am JOIN extraction e ON e.source_revision_id = am.source_revision_id"
            " JOIN assertion a ON a.extraction_id = e.id"
            " WHERE am.commit_id = %s AND am.position <= %s"
            " AND strpos(concat_ws(' ', a.subject, a.object, a.value), %s) > 0",
            (trace["head_commit_id"], trace["upto_position"], gold)).fetchall()
    return {"schema": 1, "mode": "lexical-only" if lexical_only else "frozen-vector",
            "trace": trace, "stages": stages, "replay": result}


def contains(row: dict[str, Any], gold: str) -> bool:
    # Names in value text count too; an object-only check previously misdiagnosed NMO-24.
    return any(gold in str(row.get(k) or "") for k in ("subject", "object", "value", "text", "content"))


def report(snapshot: dict[str, Any], gold: str = GOLD) -> dict[str, Any]:
    replay = snapshot.get("replay") or {}
    if replay.get("status") != "ok":
        return {"status": replay.get("status", "missing"), "diagnosis": "no valid replay; no stage conclusion"}
    stages = snapshot["stages"]
    view = stages.get("view", {})
    g = stages.get("gathered", {})
    sources = {str(c["id"]) for route in (stages.get("lexical", [[], "off"])[0],
                                        stages.get("keyword", [[], "off"])[0], stages.get("vector", []))
               for c in route if gold in c.get("clean", "")}
    sources |= {str(c["id"]) for c in stages.get("gold_sources", []) if gold in (c.get("clean") or "")}
    candidates = g.get("candidates", [])
    excluded = {str(c["id"]) for c in g.get("excluded", [])}
    eligible = [c for c in candidates if str(c["id"]) not in excluded]
    excerpts = {str(e["revision_id"]): e for e in g.get("ranked", [])}
    ledger = replay.get("lines", [])
    paths = []
    for rid in sorted(sources):
        candidate = next((c for c in candidates if str(c["id"]) == rid), None)
        offered = excerpts.get(rid)
        entry = next((e for e in ledger if str((e.get("ref") or {}).get("revision")) == rid), None)
        rank = next((i + 1 for i, c in enumerate(eligible) if str(c["id"]) == rid), None)
        in_route = any(str(c["id"]) == rid for route in (stages.get("lexical", [[], "off"])[0],
                       stages.get("keyword", [[], "off"])[0], stages.get("vector", [])) for c in route)
        if not in_route:
            loss = "absent from route outputs (inspect source eligibility, bars, broad/timeout and candidate caps)"
        elif candidate is None:
            loss = "fusion abstention"
        elif rid in excluded:
            loss = "already in host context"
        elif rank and rank > stages["effective_options"]["top_k"]:
            loss = "excerpt top_k"
        elif offered is None:
            loss = "withheld before fitter (inspect mode/keyword secrecy counters)"
        elif gold not in offered["text"]:
            loss = "excerpt span/anchor/growth"
        elif entry is None:
            loss = "offered without ledger entry: inspect capture"
        elif not entry["placed"]:
            loss = "fitter: " + entry["why"]
        elif entry.get("form"):
            loss = "placed shortened excerpt; inspect exact packet text (ledger text is capped at 400 chars)"
        else:
            loss = "gold reached packet"
        paths.append({"revision": rid, "eligible_rank": rank, "stage": loss, "candidate": candidate,
                      "excerpt": offered, "ledger": entry})
    return {"status": "ok", "mode": snapshot["mode"], "reproduced": replay.get("reproduced"),
            "notes": replay.get("notes", []),
            "original_packet_gold_in_recorded_ledger": any(contains(e, gold) and e.get("placed")
                                                          for e in snapshot["trace"].get("lines") or []),
            "packet_gold": gold in replay.get("text", ""),
            "stored_assertions": stages.get("stored_assertions", []),
            "served_assertions": [a for a in view.get("assertions", []) if contains(a, gold)],
            "folded_facts": [a for a in view.get("facts", []) if contains(a, gold)],
            "history": [h for f in view.get("facts", []) for h in f.get("history", []) if contains(h, gold)],
            "fact_ranking": [{"input": [a for a in c["input"] if contains(a, gold)],
                              "output": [a for a in c["output"] if contains(a, gold)],
                              "ranked_all": [a for a in c.get("ranked_all", []) if contains(a, gold)],
                              "limit": c["limit"]} for c in stages.get("fact_rank_calls", [])],
            "offered_fact_lines": [a for a in g.get("lead", []) + g.get("facts", [])
                                   + [a for _, lines in g.get("cast_lines", []) for a in lines] if contains(a, gold)],
            "gold_ledger": [e for e in ledger if contains(e, gold)], "passage_paths": paths,
            "unobserved": "No source absent from every route can be classified using route output alone. "
                          "A lexical-only replay cannot establish the original vector/ranking outcome. "
                          "Gold in a possession is not proof of lending; inspect the actual lending passage."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", type=UUID)
    parser.add_argument("--vector", type=Path)
    parser.add_argument("--lexical-only", action="store_true")
    parser.add_argument("--snapshot", type=Path, help="inspect an existing capture without DB or models")
    parser.add_argument("--output", type=Path, required=True, help="private JSON capture outside the repository")
    parser.add_argument("--gold", default=GOLD)
    args = parser.parse_args()
    if args.snapshot:
        snapshot = json.loads(args.snapshot.read_text())
    else:
        if args.trace is None:
            parser.error("--trace is required for DB capture")
        vector = json.loads(args.vector.read_text()) if args.vector else None
        # DB enforces read-only, including nested savepoints used by lexical recall.
        with psycopg.connect(os.environ["NMOS_DIAG_DATABASE_URL"], row_factory=dict_row) as conn:
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            snapshot = capture(conn, args.trace, vector, args.lexical_only, args.gold)
    snapshot["report"] = report(snapshot, args.gold)
    with args.output.open("x", encoding="utf-8") as dest:
        json.dump(snapshot, dest, ensure_ascii=False, indent=2, default=str)
        dest.write("\n")
    print(json.dumps({"status": snapshot["report"]["status"], "mode": snapshot.get("mode"),
                      "output": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
