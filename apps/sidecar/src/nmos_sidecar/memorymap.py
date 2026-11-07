"""The memory map (PHASE-55): a chat's memory by where it came from, who is tied to whom, what happened when, and how much
an event record holds.

Pure: it shapes the dictionary `facts.memory_view` returns (participants resolved by `inspector.with_participants`);
nothing else is read and nothing is written. `views.memory_map` draws it.
"""

from __future__ import annotations

import math
from typing import Any

from .entities import norm
from .extraction import name_parts
from .facts import STANDING, excluded_ids
from .inspector import pairs

SOURCES = ("setting", "over", "story", "owner")
# Q4: one edge per pair of characters carries these, both directions; `addresses` only in its detail.
TIES = ("relationship", "role_toward", "feels_toward")
CAPS = {"character": 24, "group": 8, "place": 8}  # Q7: in the drawing; the lines list everyone
EVENT_LINES = 200  # Q7: event lines drawn, the earliest left out and counted
# Q2: concentric rings. Room per node along a ring, and between two rings, in the drawing's units (pixels).
ARC = 96
GAP = 120


def source(f: dict[str, Any]) -> str:
    """Where a current fact came from, by its history's canon marks (PHASE-32's rule for "Only from the setting"):
    the owner's correction, the setting's only (every step canon), the story's over the setting's (the current version
    the story's, an earlier one canon) or the story's only."""
    if f.get("owner"):
        return "owner"
    history = f.get("history") or [f]
    if f.get("canon") and all(h.get("canon") for h in history):
        return "setting"
    return "over" if any(h.get("canon") for h in history) else "story"


def _said(x: dict[str, Any]) -> tuple[Any, ...]:
    """What a statement says, as `notes.changes` compares it: its value, else its object (a pair's history holds both
    directions, so the other end is not compared)."""
    return norm(x.get("value") or x.get("object")), x.get("polarity")


def changed(f: dict[str, Any]) -> bool:
    """Whether a story value replaced a canon one that said something else (what PHASE-52 lists as changed)."""
    return not f.get("canon") and any(h.get("canon") and h.get("outcome") in ("superseded", "ended")
                                       and _said(h) != _said(f) for h in f.get("history") or ())


def mark(facts: list[dict[str, Any]]) -> str:
    """An edge's mark (Q4): "changed" when a story value replaced a canon one, "setting" when every step of all its
    facts is canon, else "story"."""
    if any(changed(f) for f in facts):
        return "changed"
    return "setting" if all(source(f) == "setting" for f in facts) else "story"


def sources(view: dict[str, Any], last_turn: int | None) -> dict[str, Any]:
    """Section 1: per predicate, every current fact by where it came from; and the story's current facts (not the
    setting's, not the owner's) per turn of the chat. Counted as the 2026-11-02 prototype counted them, so the same chat
    gives the owner the same numbers (step 5)."""
    by: dict[str, dict[str, int]] = {}
    for f in view["facts"]:
        row = by.setdefault(f["predicate"], dict.fromkeys(SOURCES, 0))
        row[source(f)] += 1
    rows = sorted(({"predicate": p, **c} for p, c in by.items()), key=lambda r: (-sum(r[s] for s in SOURCES),
                                                                                  r["predicate"]))
    total = {s: sum(r[s] for r in rows) for s in SOURCES}
    told = total["over"] + total["story"]
    turns = (last_turn + 1) if isinstance(last_turn, int) and last_turn >= 0 else 0
    return {"rows": rows, "total": total, "facts": sum(total.values()), "told": told, "turns": turns,
            "per_turn": round(told / turns, 1) if turns else None}


def _key(e: dict[str, Any] | None, kind: str, name: Any) -> str:
    """A node's key: the entity's id, or the name as written when it names no entity."""
    return str(e["id"]) if e and e.get("id") else f"text:{kind}:{norm(name)}"


def graph(view: dict[str, Any], scene: list[str] | tuple[str, ...] = ()) -> dict[str, Any]:
    """Section 2: characters, the groups they belong to and the places they are now, and the edges between them (Q4).
    An entity the owner left out (PHASE-47) is not drawn, only counted; the persona is drawn and marked."""
    ex = excluded_ids(view)
    ents = {str(e["id"]): e for e in view["entities"]}
    nodes: dict[str, dict[str, Any]] = {}

    def add(kind: str, key: str, name: Any) -> None:
        e = ents.get(key)
        nodes.setdefault(key, {"id": key, "kind": kind, "name": str((e or {}).get("name") or name or ""),
                               "entity": key if e else None, "persona": bool((e or {}).get("persona")),
                               "mentions": int((e or {}).get("mentions") or 0), "ties": 0, "scene": False})

    edges: list[dict[str, Any]] = []
    for p in pairs([f for f in view["facts"] if f["predicate"] in STANDING], ex):
        drawn = p["relationship"] + p["role"] + p["feels"]
        if not drawn:  # a form of address alone is not a tie (Q4)
            continue
        ends = [str(i) if str(i) in ents else f"text:character:{i}" for i in p["ids"]]
        for key, i in zip(ends, p["ids"]):
            add("character", key, p["names"][i])
        edges.append({"kind": "tie", "a": ends[0], "b": ends[1], "mark": mark(drawn), "facts": drawn,
                      "speech": p["speech"]})
    for pred, kind in (("member_of", "group"), ("located_in", "place")):
        for f in view["facts"]:
            if (f["predicate"] != pred or f.get("subject_type") != "character" or not f.get("object")
                    or f.get("polarity") == "negative"):
                continue
            s = _key(f.get("subject_entity"), "character", f["subject"])
            if s in ex:
                continue
            o = _key(f.get("object_entity"), kind, f["object"])
            add("character", s, (f.get("subject_entity") or {}).get("name") or f["subject"])
            add(kind, o, (f.get("object_entity") or {}).get("name") or f["object"])
            edges.append({"kind": kind, "a": s, "b": o, "mark": mark([f]), "facts": [f], "speech": []})
    for e in edges:
        nodes[e["a"]]["ties"] += 1
        nodes[e["b"]]["ties"] += 1
    keys = {norm(n): str(e["id"]) for e in view["entities"] if e.get("type") == "character"
            for n in [e.get("name"), *(e.get("names") or [])] if n}
    for name in scene:
        k = keys.get(norm(name))
        if k is not None and k not in ex:
            add("character", k, name)
            nodes[k]["scene"] = True
    for e in view["entities"]:  # the persona is always on the map, marked as "you"
        if e.get("persona") and str(e["id"]) not in ex:
            add("character", str(e["id"]), e.get("name"))
    idle = sum(1 for e in view["entities"] if e.get("type") == "character" and str(e["id"]) not in ex
               and str(e["id"]) not in nodes)
    return {"nodes": list(nodes.values()), "edges": edges, "excluded": len(ex), "idle": idle,
            "suspects": suspects(view)}


def owner_splits(view: dict[str, Any]) -> set[frozenset[str]]:
    """The pairs of entities the owner split (ADR 0044): never flagged as one person."""
    r = view.get("resolution")
    out: set[frozenset[str]] = set()
    for _, _, split in getattr(r, "splits", None) or ():
        a, b = (r.entity(split.get("entity_type"), split.get(k)) for k in ("name", "other"))
        if a and b:
            out.add(frozenset((str(a["id"]), str(b["id"]))))
    return out


def suspects(view: dict[str, Any]) -> list[dict[str, Any]]:
    """Q5: two characters that may be one person kept as two, when one's name is a part of the other's by
    `extraction.name_parts` (PHASE-54's rule) or its words are the other's first words. Never a pair the owner split,
    an entity left out, or the persona. Shown only; nothing is joined."""
    ex, split = excluded_ids(view), owner_splits(view)
    chars = [e for e in view["entities"] if e.get("type") == "character" and not e.get("persona")
             and str(e["id"]) not in ex]
    order = {str(e["id"]): i for i, e in enumerate(chars)}
    named: dict[str, list[dict[str, Any]]] = {}  # a name, as written apart, to the characters it is a name of
    for e in chars:
        for n in {norm(x) for x in [e.get("name"), *(e.get("names") or [])] if x}:
            named.setdefault(n, []).append(e)
    found: dict[frozenset[str], tuple[dict[str, Any], dict[str, Any]]] = {}
    for full in chars:
        for f in [x for x in [full.get("name"), *(full.get("names") or [])] if x]:
            words = norm(f).split()
            shorter = {norm(p) for p in name_parts(str(f))} | {" ".join(words[:k]) for k in range(1, len(words))}
            for short in (s for n in shorter for s in named.get(n, ())):
                pair = frozenset((str(full["id"]), str(short["id"])))
                if len(pair) == 2 and pair not in split:
                    found.setdefault(pair, (full, short))
    return [{"full": {"id": str(a["id"]), "name": a.get("name")}, "short": {"id": str(b["id"]), "name": b.get("name")}}
            for a, b in sorted(found.values(), key=lambda p: sorted((order[str(p[0]["id"])], order[str(p[1]["id"])])))]


def events(view: dict[str, Any]) -> list[dict[str, Any]]:
    """Section 3: the story's events (the setting's stay with the setting), in turn order, each with its subject, who
    else took part (the entity's name when resolved), its weight, its reason and its outcome."""
    out = []
    for f in view["facts"]:
        if f["predicate"] != "event" or f.get("canon") or f.get("polarity") == "negative":
            continue
        subject = f.get("subject_entity") or {}
        who = [str((p.get("entity") or {}).get("name") or p.get("name") or "")
               for p in f.get("participant_entities") or f.get("participants") or ()]
        out.append({"turn": f.get("turn"), "position": f["position"], "subject": subject.get("name") or f["subject"],
                    "subject_id": str(subject["id"]) if subject.get("id") else None,
                    "participants": [w for w in dict.fromkeys(who) if w], "salience": f.get("salience"),
                    "because": f.get("because"), "outcome": f.get("outcome"),
                    "text": str(f.get("value") or f.get("object") or ""), "generation": f.get("generation")})
    out.sort(key=lambda e: (e["turn"] if isinstance(e["turn"], int) else -1, e["position"]))
    return out


def _depth(evs: list[dict[str, Any]]) -> dict[str, int]:
    return {"events": len(evs), "participants": sum(1 for e in evs if e["participants"]),
            "because": sum(1 for e in evs if e["because"]), "outcome": sum(1 for e in evs if e["outcome"]),
            "major": sum(1 for e in evs if e["salience"] == "major"),
            "minor": sum(1 for e in evs if e["salience"] == "minor"),
            "none": sum(1 for e in evs if e["salience"] not in ("major", "minor"))}


def depth(evs: list[dict[str, Any]]) -> dict[str, Any]:
    """Section 4: how many of the story's events name someone else, a reason and an outcome, and their weights; the
    same per extractor generation (under details: generations record them differently)."""
    gens: dict[str, list[dict[str, Any]]] = {}
    for e in evs:
        gens.setdefault(str(e.get("generation") or "-"), []).append(e)
    return {**_depth(evs), "by_generation": {k: _depth(v) for k, v in sorted(gens.items())}}


def build(view: dict[str, Any], last_turn: int | None, scene: list[str] | tuple[str, ...] = ()) -> dict[str, Any]:
    """The four sections of the map, from one read of the chat's memory."""
    evs = events(view)
    return {"sources": sources(view, last_turn), "graph": graph(view, scene), "events": evs, "depth": depth(evs),
            "last": last_turn or 0}


# --- the drawing (Q2, Q6, Q7) -------------------------------------------------------------------------------------------

def neighbours(g: dict[str, Any], key: str) -> set[str]:
    return {e["b"] if e["a"] == key else e["a"] for e in g["edges"] if key in (e["a"], e["b"])}


def drawn(g: dict[str, Any], focus: str | None = None, everyone: bool = False) -> dict[str, Any]:
    """What the drawing holds: with `focus`, that person and their direct ties on one ring (Q6); else the scene's cast
    and the persona, then the characters by ties and mentions, up to the caps (Q7) unless `everyone`, then the groups and
    places by ties. Nodes in three rings: the middle, the other characters, groups and places. What is left out is
    counted."""
    by = {n["id"]: n for n in g["nodes"]}
    rank = lambda n: (not (n["scene"] or n["persona"]), -n["ties"], -n["mentions"], n["name"])  # noqa: E731
    if focus is not None and focus in by:
        near = sorted(neighbours(g, focus), key=lambda k: (by[k]["kind"] != "character", rank(by[k])))
        middle, inner, outer, left = [by[focus]], [by[k] for k in near], [], {}  # one ring: it fits a phone
    else:
        chars = sorted((n for n in g["nodes"] if n["kind"] == "character" and (n["ties"] or n["scene"] or n["persona"])),
                       key=rank)
        groups = sorted((n for n in g["nodes"] if n["kind"] == "group"), key=rank)
        places = sorted((n for n in g["nodes"] if n["kind"] == "place"), key=rank)
        left = {}
        if not everyone:
            left = {k: len(xs) - CAPS[k] for k, xs in (("character", chars), ("group", groups), ("place", places))
                    if len(xs) > CAPS[k]}
            chars, groups, places = chars[:CAPS["character"]], groups[:CAPS["group"]], places[:CAPS["place"]]
        middle = [n for n in chars if n["scene"] or n["persona"]] or chars[:1]
        inner = [n for n in chars if n not in middle]
        outer = groups + places
    keep = {n["id"] for n in middle + inner + outer}
    edges = [e for e in g["edges"] if e["a"] in keep and e["b"] in keep]
    if focus is not None:
        edges = [e for e in edges if focus in (e["a"], e["b"])]
    pos, radius = rings([n["id"] for n in middle], [n["id"] for n in inner], [n["id"] for n in outer])
    return {"nodes": [by[k] for k in pos], "edges": edges, "pos": pos, "radius": radius, "left": left,
            "suspects": [s for s in g["suspects"] if s["full"]["id"] in keep and s["short"]["id"] in keep]}


def rings(middle: list[str], inner: list[str], outer: list[str]) -> tuple[dict[str, tuple[float, float]], float]:
    """Positions on concentric rings (Q2), from the order alone, so the same memory always draws the same map: one node
    in the middle sits at the centre; each ring is wide enough for its nodes (ARC apart) and GAP outside the last. Each
    ring starts at the top, every other one half a step on, so lines between rings do not run through nodes."""
    pos: dict[str, tuple[float, float]] = {}
    radius = 0.0
    for i, ring in enumerate((middle, inner, outer)):
        if not ring:
            continue
        if not pos and len(ring) == 1:
            pos[ring[0]] = (0.0, 0.0)
            continue
        radius = max(radius + GAP if pos else ARC * 0.75, len(ring) * ARC / (2 * math.pi))
        offset = math.pi / len(ring) if i % 2 else 0.0
        for j, key in enumerate(ring):
            angle = -math.pi / 2 + offset + 2 * math.pi * j / len(ring)
            pos[key] = (round(radius * math.cos(angle), 1), round(radius * math.sin(angle), 1))
    return pos, radius
