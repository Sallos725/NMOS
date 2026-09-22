#!/usr/bin/env python3
"""Summarize Phase 0A spike observations into a Markdown evidence report.

Reads collector JSON files (default: fixtures/host/incoming), groups them by scenario label,
and for every `<ID>-before` / `<ID>-after` snapshot pair prints a manifest diff: which host
message ids were kept, removed, or added, and which tracked fields changed on kept ids.

This only restates what the files contain. It never invents observations.
Standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

TRACKED = ("role", "swipeId", "swipeCount", "disabled", "generationId", "isComment", "contentHash", "dataHash")
PAIR = re.compile(r"^(?P<id>.+?)-(?P<side>before|after)$")


def load(directory: Path) -> list[dict[str, Any]]:
    records = []
    for path in sorted(directory.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            data["_file"] = path.name
            records.append(data)
    records.sort(key=lambda r: (str(r.get("timestamp", "")), r["_file"]))
    return records


def short(value: Any, n: int = 10) -> str:
    return "∅" if value is None else str(value)[:n]


def diff_manifests(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    b_msgs = before.get("messages", [])
    a_msgs = after.get("messages", [])
    b_ids = {m.get("chatId"): m for m in b_msgs}
    a_ids = {m.get("chatId"): m for m in a_msgs}
    changed = []
    for chat_id, bm in b_ids.items():
        am = a_ids.get(chat_id)
        if am is None:
            continue
        fields = {f: (bm.get(f), am.get(f)) for f in TRACKED if bm.get(f) != am.get(f)}
        if bm.get("position") != am.get("position"):
            fields["position"] = (bm.get("position"), am.get("position"))
        if fields:
            changed.append((chat_id, fields))
    return {
        "chatIdBefore": before.get("chatId"),
        "chatIdAfter": after.get("chatId"),
        "countBefore": len(b_msgs),
        "countAfter": len(a_msgs),
        "removed": [(m.get("position"), m.get("chatId"), m.get("role")) for m in b_msgs if m.get("chatId") not in a_ids],
        "added": [(m.get("position"), m.get("chatId"), m.get("role")) for m in a_msgs if m.get("chatId") not in b_ids],
        "kept": sum(1 for c in b_ids if c in a_ids),
        "changed": changed,
        "hashMethods": (before.get("hashMethod"), after.get("hashMethod")),
    }


def report(records: list[dict[str, Any]]) -> str:
    by_scenario: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in records:
        by_scenario[str(r.get("scenario", "unlabeled"))].append(r)

    out = ["# NMOS Phase 0A spike report", "", f"Observation files: {len(records)}", ""]
    envs = {json.dumps(r.get("environment"), sort_keys=True) for r in records if r.get("environment")}
    for env in sorted(envs):
        out.append(f"- environment: `{env}`")
    out.append("")

    for scenario in sorted(by_scenario):
        items = by_scenario[scenario]
        out += [f"## {scenario}", ""]
        for r in items:
            kind = r.get("kind")
            if kind == "beforeRequest":
                lu = r.get("latestUserInput") or {}
                p = r.get("prompt") or {}
                out.append(
                    f"- beforeRequest seq={r.get('seq')} mode=`{r.get('mode')}` "
                    f"actionCount={r.get('callCountForActionKey')} formatedCount={r.get('callCountForFormatedHash')} "
                    f"formatedHash={short(p.get('formatedHash'))} msgs={p.get('messageCount')} "
                    f"~tok={p.get('approximateTokens')} lastRole={r.get('formattedLastRole')} "
                    f"hostTail={short((r.get('hostLastMessage') or {}).get('role'))} "
                    f"userExact={lu.get('promptLastUserExactMatch')} dtPrev={r.get('msSincePreviousCall')}ms "
                    f"getChat={round((r.get('timings') or {}).get('getChatElapsedMs') or 0, 2)}ms "
                    f"`{r['_file']}`"
                )
            elif kind == "output":
                m = r.get("message") or {}
                out.append(
                    f"- output idx={r.get('messageIndex')} tail={r.get('messageIsTail')} chatId={m.get('chatId')} "
                    f"generationId={m.get('generationId')} swipe={m.get('swipeId')}/{m.get('swipeCount')} "
                    f"`{r['_file']}`"
                )
            elif kind == "snapshot":
                mt = r.get("metrics") or {}
                out.append(
                    f"- snapshot msgs={mt.get('messageCount')} bytes={mt.get('serializedBytes')} "
                    f"getChat={round(mt.get('getChatElapsedMs') or 0, 2)}ms "
                    f"hash={round(mt.get('manifestHashElapsedMs') or 0, 2)}ms ({mt.get('hashMethod')}) "
                    f"`{r['_file']}`"
                )
                for m in (r.get("manifest") or {}).get("messages", []):
                    for marker in m.get("specialComments", []):
                        out.append(f"  - marker at position {m.get('position')}: `{marker}`")
            elif kind == "hashBenchmark":
                out.append(
                    f"- hashBenchmark msgs={r.get('messageCount')} bytes={r.get('payloadBytes')} "
                    f"subtle={r.get('subtleMs')}ms fallback={r.get('fallbackMs')}ms agree={r.get('resultsAgree')} "
                    f"`{r['_file']}`"
                )
            else:
                out.append(f"- {kind} `{r['_file']}`")
        out.append("")

    pairs: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for r in records:
        if r.get("kind") != "snapshot":
            continue
        match = PAIR.match(str(r.get("scenario", "")))
        if match:
            pairs[match["id"]][match["side"]] = r  # latest snapshot per side wins

    out += ["# Before/after manifest diffs", ""]
    for sid in sorted(pairs):
        sides = pairs[sid]
        if "before" not in sides or "after" not in sides:
            out += [f"## {sid}", "", "- incomplete pair", ""]
            continue
        d = diff_manifests(sides["before"].get("manifest") or {}, sides["after"].get("manifest") or {})
        out += [
            f"## {sid}",
            "",
            f"- files: `{sides['before']['_file']}` → `{sides['after']['_file']}`",
            f"- host chat id: {d['chatIdBefore']} → {d['chatIdAfter']}",
            f"- messages: {d['countBefore']} → {d['countAfter']} (kept ids {d['kept']})",
            f"- removed ids: {d['removed'] or 'none'}",
            f"- added ids: {d['added'] or 'none'}",
        ]
        if d["changed"]:
            out.append("- changed on kept ids:")
            for chat_id, fields in d["changed"]:
                pretty = ", ".join(f"{k}: {short(v[0], 12)}→{short(v[1], 12)}" for k, v in fields.items())
                out.append(f"  - `{chat_id}`: {pretty}")
        else:
            out.append("- changed on kept ids: none")
        out.append("")
    return "\n".join(out) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", nargs="?", default="fixtures/host/incoming")
    parser.add_argument("--output", help="Write Markdown here instead of stdout")
    args = parser.parse_args()
    text = report(load(Path(args.directory)))
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"wrote {args.output}")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
