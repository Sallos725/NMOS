"""Check the Phase 8 scope audit against the recorded runs and print the counts PHASE-8 cites.

Standard library only. The audit (`fixtures/model/phase8/scope-audit.json`) holds one entry per valid
`event`, `destroyed`, `goal`, `knows` and `fulfilled` assertion of the recorded real-model runs, with
the other people its value involves (a manual review). This script fails when an entry no longer
matches its run file, when an assertion is missing or listed twice, or when a derived field disagrees
with the audit's rules.

    python3 tools/check_phase8_scope_audit.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "fixtures/model/phase8/scope-audit.json"
RUNS = ("fixtures/model/phase5", "fixtures/model/phase6", "fixtures/model/phase7")
PREDICATES = ("event", "destroyed", "goal", "knows", "fulfilled")
PHASE8 = ("event", "destroyed", "goal", "knows")
PERSONA = "{{user}}"
FIELDS = ("predicate", "subject", "object", "value", "modality")


def route(a: dict) -> str:
    if a.get("source") == "character_claim" and a["modality"] in ("actual", "unknown"):
        return "claim"
    return "fact" if a["modality"] == "actual" else "not_in_packet"


def exclusion(e: dict) -> str | None:
    if not e["participants"]:
        return e["exclusion"] if e["exclusion"] in ("no other person in value", "participant is subject or object") \
            else "no other person in value"
    if e["predicate"] not in PHASE8:
        return "thread resolution (ADR 0019)"
    if e["route"] == "not_in_packet":
        return "modality keeps it out of the packet"
    if all(p["name"] == PERSONA for p in e["participants"]):
        return "persona only (never a mention)"
    return None


def check() -> tuple[list[str], dict]:
    audit = json.loads(AUDIT.read_text())
    problems: list[str] = []
    seen: set[tuple] = set()
    lines: dict[str, list[str]] = {}
    for e in audit["entries"]:
        key = (e["source"], e["line"], e["index"])
        if key in seen:
            problems.append(f"duplicate entry {key}")
        seen.add(key)
        path = ROOT / e["source"]
        if not path.exists():
            problems.append(f"missing run file {e['source']}")
            continue
        rows = lines.setdefault(e["source"], path.read_text().splitlines())
        try:
            record = json.loads(rows[e["line"] - 1])
            a = record["assertions"][e["index"]]
        except (IndexError, KeyError, ValueError):
            problems.append(f"stale reference {key}")
            continue
        if record["scene"] != e["scene"] or record["run"] != e["run"] or record["variant"] != e["variant"]:
            problems.append(f"{key}: scene, run or variant differs from the run file")
        if any(a.get(f) != e[f] for f in FIELDS) or a.get("source") != e["source_class"] or a.get("status") != "valid":
            problems.append(f"{key}: assertion fields differ from the run file")
        if route(a) != e["route"]:
            problems.append(f"{key}: route {e['route']} should be {route(a)}")
        for p in e["participants"]:
            if p["name"] in (e["subject"], e["object"]) or p["type"] not in ("character", "group"):
                problems.append(f"{key}: participant {p} is the subject/object or has a bad type")
            elif p["name"] != PERSONA and p["name"] not in (e["value"] or "") and p["kind"] != "possessor":
                problems.append(f"{key}: participant {p['name']} does not occur in the value")
        if e["value_only"] != bool(e["participants"]):
            problems.append(f"{key}: value_only disagrees with participants")
        want = exclusion(e)
        if e["usable"] != (want is None) or (want is not None and e["exclusion"] != want):
            problems.append(f"{key}: usable/exclusion should be {want is None}/{want}")
    for directory in RUNS:  # completeness: every candidate assertion is in the audit
        for path in sorted((ROOT / directory).glob("*/runs.jsonl")):
            source = str(path.relative_to(ROOT))
            for n, line in enumerate(path.read_text().splitlines(), 1):
                for i, a in enumerate(json.loads(line).get("assertions") or []):
                    if a.get("status") == "valid" and a["predicate"] in PREDICATES and (source, n, i) not in seen:
                        problems.append(f"not in the audit: {(source, n, i)}")
    return problems, audit


def counts(audit: dict) -> dict:
    per: dict[str, Counter] = defaultdict(Counter)
    scenes: dict[str, set] = defaultdict(set)
    for e in audit["entries"]:
        c = per[e["predicate"]]
        c["valid"] += 1
        c["names_another_person"] += e["value_only"]
        c["usable"] += e["usable"]
        if e["usable"]:
            c[f"usable_{e['route']}"] += 1
            scenes[e["predicate"]].add(e["scene"])
        elif e["exclusion"] not in (None, "no other person in value", "participant is subject or object"):
            c[f"excluded: {e['exclusion']}"] += 1
    return {p: {**dict(per[p]), "usable_scenes": len(scenes[p])} for p in PREDICATES}


if __name__ == "__main__":
    problems, audit = check()
    for p in problems:
        print(f"scope audit: {p}")
    table = counts(audit)
    print(json.dumps(table, ensure_ascii=False, indent=1))
    usable = sum(t.get("usable", 0) for t in table.values())
    scenes = {e["scene"] for e in audit["entries"] if e["usable"]}
    print(f"usable: {usable} assertions in {len(scenes)} scenes")
    sys.exit(1 if problems else 0)
