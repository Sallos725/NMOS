"""What an owner's join, split or undo would change in a chat's memory (PHASE-20, ADR 0055).

Pure: the difference of two memory views of the same head (`facts.memory_view`), the chat as it is and as it would
be. Nothing here reads or writes the database; the caller builds both views, the second with `what_if`.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .entities import norm
from .facts import fact_text, version_key

Names = list[tuple[str, str]]  # (entity type, name) of the two names an action is about


def _fact(f: dict[str, Any]) -> dict[str, Any]:
    return {"id": f["id"], "turn": f.get("turn"), "predicate": f["predicate"], "subject": f.get("subject"),
            "object": f.get("object"), "value": f.get("value"), "text": fact_text(f)}


def _same_value(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return (norm(a.get("object")), norm(a.get("value")), a.get("polarity")) == (
        norm(b.get("object")), norm(b.get("value")), b.get("polarity"))


def _entity(e: dict[str, Any] | None) -> dict[str, Any] | None:
    return {k: e[k] for k in ("id", "type", "name", "names", "persona")} if e else None


def _facts(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    """Current facts that stop or start being current, each with the fact that takes or gave up its version."""
    rb, ra = before["resolution"], after["resolution"]
    was = {f["id"]: f for f in before["facts"]}
    now = {f["id"]: f for f in after["facts"]}
    after_by_key: dict[tuple, dict[str, Any]] = {}
    for g in after["facts"]:
        after_by_key.setdefault(version_key(g, ra), g)
    before_by_key: dict[tuple, dict[str, Any]] = {}
    for f in before["facts"]:
        before_by_key.setdefault(version_key(f, rb), f)
    lines = []
    for fid, f in was.items():
        if fid in now:
            continue
        by = after_by_key.get(version_key(f, ra))
        if by is None:
            lines.append({"kind": "fact_ended", "fact": _fact(f)})
        else:
            lines.append({"kind": "fact_merged" if _same_value(f, by) else "fact_replaced", "fact": _fact(f),
                          "by": _fact(by)})
    for fid, g in now.items():
        if fid in was:
            continue
        instead = before_by_key.get(version_key(g, rb))
        lines.append({"kind": "fact_back", "fact": _fact(g), **({"instead_of": _fact(instead)} if instead else {})})
    return sorted(lines, key=lambda x: (x["fact"]["turn"] or 0, x["fact"]["id"]))


def _selves(view: dict[str, Any], r: Any) -> tuple[dict[int, dict[str, Any]], dict[int, dict[str, Any]]]:
    """Relationships and threads of `view` whose two sides are one entity under `r`."""
    rels = {f["id"]: f for f in view["facts"] if f["predicate"] == "relationship" and f.get("object")
            and r.key(f.get("subject_type"), f["subject"]) == r.key(f.get("object_type"), f["object"])}
    threads = {t["id"]: t for t in view["threads"]
               if t.get("to") and r.key("character", t["by"]) == r.key("character", t["to"])}
    return rels, threads


def _self_relations(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    """A relationship, promise or thread whose two sides become one entity (PHASE-20 Q6: shown, kept), or stop
    being one (an undo or a split)."""
    rels_b, threads_b = _selves(before, before["resolution"])
    rels_a, threads_a = _selves(after, after["resolution"])
    return ([{"kind": "self_relation", "fact": _fact(f)} for i, f in rels_a.items() if i not in rels_b]
            + [{"kind": "self_relation_gone", "fact": _fact(f)} for i, f in rels_b.items() if i not in rels_a]
            + [{"kind": "self_thread", "thread": _thread(t)} for i, t in threads_a.items() if i not in threads_b]
            + [{"kind": "self_thread_gone", "thread": _thread(t)} for i, t in threads_b.items() if i not in threads_a])


def _thread(t: dict[str, Any]) -> dict[str, Any]:
    return {k: t.get(k) for k in ("id", "kind", "by", "to", "text", "turn", "status")}


def _threads(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    was = {t["id"]: t for t in before["threads"]}
    now = {t["id"]: t for t in after["threads"]}
    lines = []
    for tid, t in was.items():
        if tid not in now:
            lines.append({"kind": "thread_merged", "thread": _thread(t)})  # now a restatement of another thread
        elif now[tid]["status"] != t["status"]:
            lines.append({"kind": "thread_status", "thread": _thread(t), "status": now[tid]["status"]})
    lines += [{"kind": "thread_back", "thread": _thread(t)} for tid, t in now.items() if tid not in was]
    return lines


def _secret(s: dict[str, Any]) -> dict[str, Any]:
    return {k: s.get(k) for k in ("id", "text", "turn", "holders", "kept_from", "open")}


def _secrets(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    """Secrets whose keepers or open ends change, and those kept from someone who holds them (Q1)."""
    rb, ra = before["resolution"], after["resolution"]

    def kept_from_holder(s: dict[str, Any] | None, r: Any) -> bool:
        if s is None:
            return False
        keys = lambda names: {r.key("character", n) for n in names or () if n}  # noqa: E731
        return bool(keys(s.get("open")) & (keys(s.get("holders")) | keys([s.get("subject")])))

    def names(s: dict[str, Any]) -> list[list[str]]:
        return [sorted(map(norm, s.get(k) or [])) for k in ("holders", "kept_from", "open")]

    was = {s["id"]: s for s in before["secrets"]}
    lines = []
    for s in after["secrets"]:
        old = was.get(s["id"])
        if old is None:
            lines.append({"kind": "secret_back", "secret": _secret(s)})
            continue
        new, gone = kept_from_holder(s, ra), kept_from_holder(old, rb)
        if names(old) != names(s) or new != gone:
            lines.append({"kind": "secret", "secret": _secret(s), "before": _secret(old),
                          "kept_from_holder": new and not gone, "kept_from_holder_gone": gone and not new})
    kept = {x["id"] for x in after["secrets"]}
    lines += [{"kind": "secret_merged", "secret": _secret(s)} for sid, s in was.items() if sid not in kept]
    return lines


def _repairs(before: dict[str, Any], after: dict[str, Any], exclude: set[str]) -> list[dict[str, Any]]:
    """The owner's repairs in force whose match changes (ADR 0044): one that applies now and would match nothing,
    or the other way round, or another item."""
    was = {str(x["id"]): x for x in before["repairs"]}
    lines = []
    for x in after["repairs"]:
        rid = str(x["id"])
        if rid in exclude or rid not in was:
            continue
        if str(was[rid].get("applied")) != str(x.get("applied")):
            lines.append({"kind": "repair", "repair": {"id": rid, "kind": x["kind"], "target": x.get("target")},
                          "before": was[rid].get("applied"), "after": x.get("applied")})
    return lines


def _conflicts(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    """Disputed whereabouts (ADR 0017), canon conflicts and statements a lock holds off (ADR 0047) that appear or go."""
    def keyed(v: dict[str, Any]) -> dict[tuple, dict[str, Any]]:
        return {(c["kind"], c["fact"], (c.get("against") or {}).get("id")): c for c in v["conflicts"]}
    was, now = keyed(before), keyed(after)
    brief = lambda c: {k: c.get(k) for k in ("kind", "fact", "turn", "text")}  # noqa: E731
    return ([{"kind": "conflict_new", "conflict": brief(c)} for k, c in now.items() if k not in was]
            + [{"kind": "conflict_gone", "conflict": brief(c)} for k, c in was.items() if k not in now])


def _canon_aliases(r: Any, names: Names) -> dict[tuple[str, str], dict[str, Any]]:
    out = {}
    for t, n in names:
        for x in (r.entity(t, n) or {}).get("aliases", ()):
            if x.get("canon"):
                out.setdefault((norm(x["name"]), norm(x["other"])), x)
    return out


def _entities(before: dict[str, Any], after: dict[str, Any], names: Names) -> tuple[list, list, list]:
    rb, ra = before["resolution"], after["resolution"]
    b = {e["id"]: _entity(e) for t, n in names if (e := rb.entity(t, n))}
    a = {e["id"]: _entity(e) for t, n in names if (e := ra.entity(t, n))}
    lines = []
    if any(e["persona"] for e in a.values()) and not all(e["persona"] for e in b.values()):
        lines.append({"kind": "persona"})
    elif any(e["persona"] for e in b.values()) and not all(e["persona"] for e in a.values()):
        lines.append({"kind": "persona_gone"})
    was, now = _canon_aliases(rb, names), _canon_aliases(ra, names)
    lines += [{"kind": "canon_alias", "name": x["name"], "other": x["other"]} for k, x in now.items() if k not in was]
    lines += [{"kind": "canon_alias_gone", "name": x["name"], "other": x["other"]} for k, x in was.items() if k not in now]
    return list(b.values()), list(a.values()), lines


def diff(before: dict[str, Any], after: dict[str, Any], names: Names, exclude_repairs: set[str] = frozenset()) -> dict[str, Any]:
    """What changes from `before` to `after` (PHASE-20 Q1), for the action about `names`. `exclude_repairs`: the
    action's own repair (a split), which is not a change to report."""
    ents_before, ents_after, lines = _entities(before, after, names)
    lines += _facts(before, after) + _self_relations(before, after) + _threads(before, after)
    lines += _secrets(before, after) + _repairs(before, after, set(exclude_repairs)) + _conflicts(before, after)
    joined = {e["id"] for e in ents_before} != {e["id"] for e in ents_after}
    counts: dict[str, int] = {}
    for x in lines:
        counts[x["kind"]] = counts.get(x["kind"], 0) + 1
    return {"changes": joined or bool(lines), "before": ents_before, "after": ents_after, "lines": lines,
            "counts": counts}


def fingerprint(preview: dict[str, Any], state: dict[str, Any]) -> str:
    """What a preview read (Q4): the head, the owner links and repairs in force, the generations, and the difference
    itself, with the turns an undo would re-extract. An action whose fingerprint differs from the preview's was
    previewed on other memory."""
    shown = {k: preview.get(k) for k in ("before", "after", "lines", "reextract")}
    body = json.dumps({"state": state, "preview": shown},
                      sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(body.encode()).hexdigest()[:32]
