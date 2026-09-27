"""Response-model tier for secrets (PHASE-10 step 7): does a response model keep a secret unsaid in front of the
character it is kept from, and does its holder still remember it, under each packet?

The cases are the owner's real chats and stay outside the repository: a case directory holds them, and every
report prints numbers only. Three steps, each resumable:

    cd apps/sidecar
    # 1. packets: each case's recorded request with the packet compiled again per condition (read-only)
    uv run python ../../tools/eval_secrets.py build DIR --db postgresql://…/copy [--extractor KEY]
    # 2. answers, one call per request; credentials only from the environment, never printed or written.
    #    An OpenAI-compatible endpoint (requests with `messages`):
    NMOS_EVAL_API_KEY=… uv run python ../../tools/eval_secrets.py run DIR --url https://…/v1/chat/completions \
        --model MODEL --max-calls N --max-cost USD
    #    Gemini on Vertex AI (requests with `contents`, as PocketRisu sends them), a service-account key:
    VERTEX_SA_JSON=/path/key.json uv run python ../../tools/eval_secrets.py run DIR --provider vertex \
        --model gemini-3.1-pro-preview --max-calls N --max-input-tokens T
    # 3. numbers: surface echo of each watched secret, and the reviewer's labels when DIR/labels.json exists
    uv run python ../../tools/eval_secrets.py report DIR

DIR/cases.json:

    [{"name": "D1", "request": "requests/4128.json",        # the host's request body, packet included
      "trace": "<the NMOS trace of that request>",            # or, for a request before the ledger (Phase 9):
      # "conversation": "<id>", "user_starts": "<the start of the request's user message>", "context": 10,
      # "query": "<the user message the request really sent, when it was replaced by a probe>",
      "watch": [{"id": "hug", "text": "<the secret's content>", "kept_from": "<name>"}],
      "conditions": ["packet-v2", "packet-v4", "packet-v4+strict"], "runs": 3}]

A condition is a packet policy, optionally with `+strict` or `+narrator=<name>` (ADR 0035), or `recorded` (the
packet as the request carried it). `build` replays the trace (ADR 0027) as of now when `--extractor` names a
newer extractor generation than the one recorded, else as of the request. Without a trace it gathers at the
user message on the conversation's head, with the `context` messages before it as the host's window. Echo is a surface measure: a reply
that reuses a watched secret's words either leaks it or recalls it, and only a reader can tell which; label
them in DIR/labels.json as {"<request name>": {"<watch id>": ["leak" | "slip" | "recall", …]}}: `leak`, a character it
is kept from is told or shown it; `slip`, a hint or a near miss (a holder blurting, "it's a secret"); `recall`, a
holder shows they know it (in words to another holder, thoughts or narration). An empty list is kept, not recalled.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import httpx

PACKET = re.compile(r"<NarrativeMemory\b.*?</NarrativeMemory>", re.S)
ECHO = 0.5  # share of a watched secret's spans a reply reuses to count as echoing it


def conditions(case: dict) -> list[str]:
    return case.get("conditions") or ["packet-v2", "packet-v4"]


def parse(cond: str) -> tuple[str, dict]:
    policy, *mods = cond.split("+")
    overrides: dict = {}
    for mod in mods:
        if mod == "strict":
            overrides["strict"] = True
        elif mod.startswith("narrator="):
            overrides["narrator"] = mod.split("=", 1)[1]
        else:
            raise SystemExit(f"unknown condition modifier: {mod}")
    return policy, overrides


def with_packet(body: dict, packet: str | None) -> dict:
    """The request with its NMOS packet replaced (or kept, for `recorded`): an OpenAI-style body
    (`messages`) or a Gemini one (`contents`, `systemInstruction`)."""
    out = json.loads(json.dumps(body))
    if "messages" in out:
        out["stream"] = False
        slots = [(m, "content") for m in out["messages"] if isinstance(m.get("content"), str)]
    else:
        parts = [p for c in out.get("contents", []) for p in c.get("parts", [])]
        parts += (out.get("systemInstruction") or {}).get("parts", [])
        slots = [(p, "text") for p in parts if isinstance(p.get("text"), str)]
    if packet is None:
        return out
    hits = [(holder, key) for holder, key in slots if PACKET.search(holder[key])]
    if len(hits) != 1:
        raise SystemExit(f"expected one NMOS packet in the request, found {len(hits)}")
    holder, key = hits[0]
    holder[key] = PACKET.sub(lambda _: packet, holder[key])
    return out


def build(args: argparse.Namespace) -> None:
    import psycopg
    from psycopg.rows import dict_row
    from nmos_sidecar import audit
    from nmos_sidecar.retrieval import RecallOptions

    root = Path(args.dir)
    cases = json.loads((root / "cases.json").read_text())
    (root / "requests").mkdir(exist_ok=True)
    (root / "packets").mkdir(exist_ok=True)
    manifest = []
    with psycopg.connect(args.db, row_factory=dict_row) as conn:
        conn.read_only = True
        for case in cases:
            body = json.loads((root / case["request"]).read_text())
            for cond in conditions(case):
                if cond == "recorded":
                    packet = None
                elif "trace" in case:
                    policy, overrides = parse(cond)
                    if args.extractor:
                        overrides["extractor_key"] = args.extractor
                    out = audit.replay(conn, UUID(case["trace"]), RecallOptions(), policy,
                                       known_at=datetime.now(timezone.utc) if args.extractor else None, **overrides)
                    if out is None or out.get("status") != "ok":
                        raise SystemExit(f"{case['name']}: replay {out and out.get('status')}")
                    packet = out["text"]
                else:
                    packet = at_message(conn, case, cond, args.extractor)
                    (root / "packets" / f"{case['name']}__{cond}.txt").write_text(packet)
                request = with_packet(body, packet)
                for run in range(1, case.get("runs", 3) + 1):
                    name = f"{case['name']}__{cond}__{run}"
                    (root / "requests" / f"{name}.json").write_text(json.dumps(request, ensure_ascii=False))
                    manifest.append({"name": name, "case": case["name"], "condition": cond, "run": run})
    (root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    print(f"{len(manifest)} requests in {len(cases)} cases")


def at_message(conn, case: dict, cond: str, extractor: str | None) -> str:
    """The packet for a user message on the conversation's head (a request recorded before the ledger)."""
    import dataclasses

    from nmos_sidecar.packet import clean_text, compile_lines
    from nmos_sidecar.retrieval import RecallOptions, gather

    policy, overrides = parse(cond)
    head = conn.execute("SELECT head_commit_id FROM conversation WHERE id = %s", (case["conversation"],)).fetchone()
    if head is None:
        raise SystemExit(f"{case['name']}: no conversation {case['conversation']}")
    msgs = conn.execute(
        "SELECT am.position, so.host_logical_id, sr.content, sr.metadata->>'role' AS role FROM active_membership am"
        " JOIN source_revision sr ON sr.id = am.source_revision_id JOIN source_object so ON so.id = sr.source_object_id"
        " WHERE am.commit_id = %s ORDER BY am.position", (head["head_commit_id"],)).fetchall()
    user = [m for m in msgs if m["role"] == "user" and m["content"].lstrip().startswith(case["user_starts"])]
    if len(user) != 1:
        raise SystemExit(f"{case['name']}: {len(user)} user messages start that way")
    p = user[0]["position"]
    previous = next((m for m in reversed(msgs) if m["position"] < p and m["role"] != "user"), None)
    window = {m["host_logical_id"] for m in msgs if p - case.get("context", 10) <= m["position"] <= p}
    options = dataclasses.replace(RecallOptions(), policy=policy, extractor_key=extractor, **overrides)
    g = gather(conn, head["head_commit_id"], clean_text(case.get("query") or user[0]["content"]),
               clean_text(previous["content"]) if previous else "", window, options, upto=p)
    budget = case.get("budget", 800)
    return compile_lines(g.ranked, budget, state=g.state, threads=g.threads, facts=g.facts, policy=policy,
                         lead=g.lead, note=g.note).text


def cost_of(resp: dict) -> float | None:
    for path in (("providerMetadata", "gateway", "cost"), ("usage", "cost"), ("cost",)):
        v = resp
        for k in path:
            v = v.get(k) if isinstance(v, dict) else None
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
    return None


def endpoint(args: argparse.Namespace):
    """(url, headers function): credentials from the environment only."""
    if args.provider == "vertex":
        path = os.environ.get("VERTEX_SA_JSON")
        if not path:
            raise SystemExit("set VERTEX_SA_JSON to a service-account key file first")
        from nmos_sidecar.vertex import access_token
        info = json.loads(Path(path).read_text())
        url = (f"https://aiplatform.googleapis.com/v1/projects/{info['project_id']}/locations/global/publishers/"
               f"google/models/{args.model}:generateContent")
        return url, lambda: {"Authorization": f"Bearer {access_token(info)}"}
    key = os.environ.get("NMOS_EVAL_API_KEY")
    if not key or not args.url:
        raise SystemExit("set NMOS_EVAL_API_KEY and --url first (the key is never printed or written)")
    return args.url, lambda: {"Authorization": f"Bearer {key}"}


def usage_of(resp: dict) -> tuple[int | None, int | None]:
    if "usageMetadata" in resp:  # Gemini
        u = resp["usageMetadata"]
        return u.get("promptTokenCount"), u.get("candidatesTokenCount")
    u = resp.get("usage") or {}
    return u.get("prompt_tokens"), u.get("completion_tokens")


def run(args: argparse.Namespace) -> None:
    url, headers = endpoint(args)
    root = Path(args.dir)
    out, ledger = root / "responses", root / "ledger.csv"
    out.mkdir(exist_ok=True)
    spent, calls, sent = 0.0, 0, 0
    if ledger.exists():
        for row in csv.DictReader(ledger.open()):
            calls += 1
            spent += float(row["cost"] or 0)
            sent += int(row["prompt_tokens"] or 0)
    todo = [m for m in json.loads((root / "manifest.json").read_text()) if not (out / f"{m['name']}.json").exists()]
    with httpx.Client(timeout=900) as client:
        for m in todo:
            if calls >= args.max_calls:
                print(f"stop: {calls} calls reached --max-calls")
                break
            if spent >= args.max_cost:
                print(f"stop: reported spend ${spent:.2f} reached --max-cost")
                break
            if sent >= args.max_input_tokens:
                print(f"stop: {sent} prompt tokens sent reached --max-input-tokens")
                break
            body = json.loads((root / "requests" / f"{m['name']}.json").read_text())
            if "messages" in body:
                body["model"] = args.model
            for attempt in range(8):
                started = time.time()
                r = client.post(url, json=body, headers=headers())
                if r.status_code in (429, 500, 502, 503, 529) and attempt < 7:
                    wait = min(300, 20 * 2 ** attempt)
                    print(f"  {m['name']}: HTTP {r.status_code}, retry in {wait}s")
                    time.sleep(wait)
                    continue
                if r.status_code != 200:
                    raise SystemExit(f"{m['name']}: HTTP {r.status_code} {r.text[:300]!r}")
                break
            resp = r.json()
            (out / f"{m['name']}.json").write_text(json.dumps(resp, ensure_ascii=False))
            (prompt, completion), cost = usage_of(resp), cost_of(resp)
            spent += cost or 0
            sent += prompt or 0
            calls += 1
            new = not ledger.exists()
            with ledger.open("a", newline="") as f:
                w = csv.writer(f)
                if new:
                    w.writerow(["name", "model", "prompt_tokens", "completion_tokens", "cost", "seconds"])
                w.writerow([m["name"], args.model, prompt, completion,
                            "" if cost is None else f"{cost:.4f}", f"{time.time() - started:.0f}"])
            print(f"{m['name']}: in {prompt} out {completion} cost {'?' if cost is None else f'${cost:.3f}'} "
                  f"(calls {calls}, spent ${spent:.2f}, prompt tokens {sent})")


def reply_of(resp: dict) -> str:
    if "candidates" in resp:  # Gemini: the answer's parts, not its thoughts
        parts = ((resp["candidates"] or [{}])[0].get("content") or {}).get("parts") or []
        return "".join(p.get("text", "") for p in parts if not p.get("thought"))
    choice = (resp.get("choices") or [{}])[0]
    content = (choice.get("message") or {}).get("content") or ""
    return content if isinstance(content, str) else "".join(p.get("text", "") for p in content if isinstance(p, dict))


def report(args: argparse.Namespace) -> None:
    from nmos_sidecar.spans import reuse

    root = Path(args.dir)
    cases = {c["name"]: c for c in json.loads((root / "cases.json").read_text())}
    labels = json.loads((root / "labels.json").read_text()) if (root / "labels.json").exists() else {}
    rows: dict[str, dict[str, int]] = {}
    for m in json.loads((root / "manifest.json").read_text()):
        path = root / "responses" / f"{m['name']}.json"
        if not path.exists():
            continue
        reply = reply_of(json.loads(path.read_text()))
        row = rows.setdefault(m["condition"], {"replies": 0, "watched": 0, "echoed": 0, "leak": 0, "slip": 0,
                                               "recall": 0, "unlabeled": 0})
        row["replies"] += 1
        for w in cases[m["case"]].get("watch", []):
            row["watched"] += 1
            row["echoed"] += reuse(w["text"], reply) >= ECHO
            given = (labels.get(m["name"]) or {}).get(w["id"])
            if given is None:
                row["unlabeled"] += 1
            for label in ([given] if isinstance(given, str) else given or []):
                if label in ("leak", "slip", "recall"):
                    row[label] += 1
    keys = ["replies", "watched", "echoed", "leak", "slip", "recall", "unlabeled"]
    print("| condition | " + " | ".join(keys) + " |")
    print("|---|" + "---:|" * len(keys))
    for cond, row in rows.items():
        print(f"| {cond} | " + " | ".join(str(row[k]) for k in keys) + " |")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("dir")
    b.add_argument("--db", required=True, help="a database copy (opened read-only)")
    b.add_argument("--extractor", help="compile with this extractor generation's facts, as of now")
    r = sub.add_parser("run")
    r.add_argument("dir")
    r.add_argument("--provider", choices=("openai", "vertex"), default="openai")
    r.add_argument("--url", help="an OpenAI-compatible chat completions URL (provider openai)")
    r.add_argument("--model", required=True)
    r.add_argument("--max-calls", type=int, required=True, help="calls in DIR in all, across runs")
    r.add_argument("--max-cost", type=float, default=float("inf"),
                   help="stop once the endpoint reports this many USD (Vertex reports none)")
    r.add_argument("--max-input-tokens", type=int, default=10**12, help="stop once this many prompt tokens were sent")
    p = sub.add_parser("report")
    p.add_argument("dir")
    args = ap.parse_args()
    {"build": build, "run": run, "report": report}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
