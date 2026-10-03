"""Independent synthetic role/alias probes. Dry-run by default; no DB or host writes.

Each case has fixed, authored earlier roles, not the output of a sequential worker.
Gold expectations never enter the prompt. --execute makes one call per case/run,
stopping on the first failure without retries. Use a fresh output directory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any
from uuid import UUID

from nmos_sidecar import extraction as X, facts
from nmos_sidecar.entities import resolve
from nmos_sidecar.llm import ChatModel
from nmos_sidecar.packet import estimate_tokens
from nmos_sidecar.predicates import registry_prompt

CONVERSATION = UUID("01900000-0000-7000-8000-000000000128")
DEFAULT_CASES = Path(__file__).parent / "scenarios" / "glass-garden.json"


def save(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_cases(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or data.get("provenance") != "authored-synthetic":
        raise ValueError("expected schema_version=1 and provenance=authored-synthetic")
    cases = data.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("cases must be a nonempty list")
    seen: set[str] = set()
    for case in cases:
        identifier = case["id"]
        if not isinstance(identifier, str) or not re.fullmatch(r"[a-z0-9-]+", identifier) or identifier in seen:
            raise ValueError("case ids must be unique safe filenames")
        seen.add(identifier)
        if not isinstance(case["target"], str) or not 0 < len(case["target"]) <= X.TARGET_CHARS:
            raise ValueError(f"{identifier}: target must fit the production prompt")
        if not isinstance(case["context"], list) or any(
                not isinstance(text, str) or not 0 < len(text) <= X.CONTEXT_CHARS for text in case["context"]):
            raise ValueError(f"{identifier}: invalid context")
        roles = case["roles"]
        if not isinstance(roles, list) or len(roles) > X.OPEN_ROLES:
            raise ValueError(f"{identifier}: invalid roles")
        pairs = set()
        for role in roles:
            if any(not isinstance(role.get(k), str) or not role[k].strip() for k in ("by", "to", "role")):
                raise ValueError(f"{identifier}: invalid role fields")
            pair = (role["by"], role["to"])
            if pair in pairs or type(role.get("turn")) is not int or not 0 <= role["turn"] < len(case["context"]):
                raise ValueError(f"{identifier}: roles must be distinct earlier pairs")
            pairs.add(pair)
        if not set(case["expected_ended"]) <= {f"R{i}" for i in range(1, len(roles) + 1)}:
            raise ValueError(f"{identifier}: unknown expected role")
        for key in ("expected_aliases", "forbidden_aliases"):
            for pair in case[key]:
                if (not isinstance(pair, list) or len(pair) != 2 or pair[0] == pair[1]
                        or any(not isinstance(name, str) or not name.strip() for name in pair)):
                    raise ValueError(f"{identifier}: invalid alias pair")
        if not roles and not case["expected_aliases"] and not case["forbidden_aliases"]:
            raise ValueError(f"{identifier}: no acceptance check")
    return data


def prompt(case: dict[str, Any], compiler: str) -> str:
    context = [{"turn": i, "metadata": {"role": "char", "name": "Narrator"}, "content": text}
               for i, text in enumerate(case["context"])]
    ctx = {"context": context, "target": {"turn": len(context)},
           "members": [{"metadata": {"role": "char", "name": "Narrator"}, "content": case["target"]}]}
    return X.build_prompt(ctx, roles=case["roles"] if compiler in X.ROLES else [], compiler=compiler)


def grade(case: dict[str, Any], parsed: dict[str, Any], compiler: str) -> dict[str, Any]:
    if not isinstance(parsed.get("assertions"), list):
        raise ValueError("model reply has no assertions list")
    items = [a for a in parsed["assertions"] if not (isinstance(a, dict) and a.get("predicate") in X.DERIVED)]
    if compiler in X.ROLES:
        items = X.ended_roles(parsed, items, case["roles"], case["target"])
    rows = X.normalize(items, case["target"], shown=case["target"], apart=compiler in X.PARTS_APART)
    valid = [a | {"id": f"measured-{i}", "turn": len(case["context"]), "position": len(case["context"])}
             for i, a in enumerate(rows) if a["status"] == "valid"]
    actual = [a for a in valid if a["modality"] == "actual" and a["source"] == "narration"]
    seeds = [{"id": f"seed-{i}", "turn": r["turn"], "position": r["turn"],
              "subject": r["by"], "subject_type": "character", "object": r["to"], "object_type": "character",
              "predicate": "role_toward", "value": r["role"], "polarity": "positive", "modality": "actual",
              "source": "narration", "status": "valid"} for i, r in enumerate(case["roles"])]
    # The product gives the resolver claims too; it decides which self-alias claims may join names.
    resolution = resolve(CONVERSATION, [*seeds, *valid])
    checks = []
    for i, seed in enumerate(seeds, 1):
        history = [seed, *(a for a in actual if a["predicate"] == "role_toward"
                          and facts.version_key(a, resolution) == facts.version_key(seed, resolution))]
        held = any(a["polarity"] == "positive" for a in facts._versions(history, resolution))
        expected = f"R{i}" not in case["expected_ended"]
        checks.append({"check": f"R{i} held", "expected": expected, "actual": held, "passed": held == expected})
    allowed_endings = {(facts.version_key(seed, resolution), facts.relation(seed, resolution))
                       for i, seed in enumerate(seeds, 1)
                       if f"R{i}" in case["expected_ended"]}
    unexpected = [a for a in actual if a["predicate"] == "role_toward" and a["polarity"] == "negative"
                  and (facts.version_key(a, resolution), facts.relation(a, resolution)) not in allowed_endings]
    checks.append({"check": "no unexpected role endings", "passed": not unexpected, "rows": unexpected})
    for key, expected in (("expected_aliases", True), ("forbidden_aliases", False)):
        for left, right in case[key]:
            joined = resolution.key("character", left) == resolution.key("character", right)
            checks.append({"check": f"{left} = {right}", "expected": expected, "actual": joined,
                           "passed": joined == expected})
    allowed_aliases = {frozenset(pair) for pair in case["expected_aliases"]}
    unexpected_aliases = [a for _, _, a in resolution.alias_rows
                         if frozenset((a["subject"], a["value"])) not in allowed_aliases]
    checks.append({"check": "no unexpected aliases", "passed": not unexpected_aliases, "rows": unexpected_aliases})
    return {"passed": all(c["passed"] for c in checks), "checks": checks, "assertions": rows,
            "roles_ended": parsed.get("roles_ended")}


def run(args: argparse.Namespace) -> int:
    if not 1 <= args.runs <= 20:
        raise ValueError("runs must be between 1 and 20")
    data = load_cases(args.cases)
    system = X.PROMPTS[args.compiler].format(registry=registry_prompt())
    prompts = [(c, prompt(c, args.compiler)) for c in data["cases"]]
    manifest = {"title": data["title"], "mode": "execute" if args.execute else "dry-run",
                "method": "fixed authored roles; no DB, live host, sequential worker or backfill",
                "compiler": args.compiler, "model": args.model, "url": args.url,
                "planned_calls": len(prompts) * args.runs, "runs": args.runs, "retries": 0,
                "estimated_input_tokens": sum(estimate_tokens(system + user) for _, user in prompts) * args.runs,
                "cases_sha256": sha(args.cases.read_text(encoding="utf-8")), "system_sha256": sha(system),
                "extraction_sha256": hashlib.sha256(Path(X.__file__).read_bytes()).hexdigest(),
                "tool_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    if args.execute and (not args.url or not args.model):
        raise ValueError("--execute requires --url and --model")
    args.out.mkdir(parents=True, exist_ok=False)
    save(args.out / "manifest.json", manifest)
    save(args.out / "cases.json", data)
    save(args.out / "prompts.json", {c["id"]: user for c, user in prompts})
    (args.out / "system.txt").write_text(system, encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False), flush=True)
    if not args.execute:
        return 0
    model = ChatModel(args.url, args.model, api_key=os.environ.get("NMOS_EVAL_API_KEY", ""), timeout_s=300)
    summary: dict[str, Any] = {"planned": manifest["planned_calls"], "completed": 0, "passed": 0, "errors": 0,
                               "input_tokens": 0, "output_tokens": 0, "usage_missing": 0, "retries": 0}
    with (args.out / "calls.jsonl").open("x", encoding="utf-8") as journal:
        def event(value: dict[str, Any]) -> None:
            journal.write(json.dumps(value, ensure_ascii=False) + "\n")
            journal.flush()
            os.fsync(journal.fileno())

        for case, user in prompts:
            for repeat in range(1, args.runs + 1):
                name = f"{case['id']}-{repeat}"
                event({"event": "start", "call": name, "prompt_sha256": sha(user)})
                try:
                    parsed, raw, usage = model.complete_metered(system, user)
                    save(args.out / f"{name}-raw.json", {"parsed": parsed, "raw": raw, "usage": usage})
                    result = grade(case, parsed, args.compiler)
                    save(args.out / f"{name}.json", result)
                except Exception as exc:
                    # Do not write provider response bodies or credentials from exception messages.
                    event({"event": "error", "call": name, "error_type": type(exc).__name__})
                    summary["errors"] += 1
                    save(args.out / "summary.json", summary)
                    print(f"Stopped at {name}: {type(exc).__name__}; no retry.", flush=True)
                    return 1
                summary["completed"] += 1
                summary["passed"] += int(result["passed"])
                for field in ("input", "output"):
                    summary[f"{field}_tokens"] += (usage or {}).get(field, 0)
                summary["usage_missing"] += int(not usage or "input" not in usage or "output" not in usage)
                event({"event": "finish", "call": name, "passed": result["passed"], "usage": usage})
                save(args.out / "summary.json", summary)
                print(json.dumps({"call": name, "passed": result["passed"]}), flush=True)
                if not result["passed"]:
                    return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--out", type=Path, required=True, help="a new directory; existing output is never overwritten")
    parser.add_argument("--compiler", choices=("extract-v15", "extract-v16"), default="extract-v16")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--execute", action="store_true", help="actually call the model; omit for a cost estimate")
    parser.add_argument("--url")
    parser.add_argument("--model")
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
