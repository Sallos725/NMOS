"""Entity identity at read time (Phase 5, ADR 0012, D26). Pure: no database, no model.

A mention is (entity type, normalized name). Within one conversation the same type and name is one
entity, the persona names are one entity, and names are linked only by actual `also_called` assertions
that the story narrates, or that a character says about their own name (a self-introduction, owner
decision 2026-09-24; extraction already required both names in the turn, so an alias lives exactly as
long as that turn is active). A name linked to names that are otherwise unconnected (a
nickname shared by two people) is ambiguous: its mentions keep their text key and link to nobody.
Transliteration or similarity never links names. Nothing is stored: a resolver change is a new
`RESOLVER_VERSION`, and the next read is the rebuild.

Since `resolve-v2` (Phase 8, ADR 0021) an assertion's typed participants are mentions too, read in a
second pass after every subject, object and alias name. They never link names, and they rank below
every `resolve-v1` name source: an entity that `resolve-v1` knows keeps the representative spelling,
name order and grouping it had, so extraction hints do not change because of participants. A
participant never named as a subject or object is an entity of its own.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from uuid import UUID, uuid5

RESOLVER_VERSION = "resolve-v2"
USER_NAMES = {"{{user}}", "{user}", "user", "유저"}
PERSONA = "{{user}}"
_NS = UUID("6c0c7e55-2f8e-4d0a-9d3b-5a4e1f0b7c21")  # NMOS entity namespace (arbitrary, fixed)

Node = tuple[str, str]  # (type, normalized name)


def norm(name: str | None) -> str:
    return " ".join(str(name or "").casefold().split())


def node(entity_type: str | None, name: str | None) -> Node:
    n = norm(name)
    if entity_type == "character" and n in USER_NAMES:
        n = PERSONA
    return (entity_type or "?", n)


def participant_mentions(row: dict[str, Any]) -> Iterable[tuple[Node, str]]:
    """Typed participants (PHASE-8), as stored: a list of {"name", "type"} or NULL."""
    for p in row.get("participants") or ():
        if isinstance(p, dict) and p.get("name"):
            yield node(p.get("type"), p["name"]), p["name"]


def mentions(row: dict[str, Any]) -> Iterable[tuple[Node, str]]:
    yield node(row.get("subject_type"), row.get("subject")), row.get("subject") or ""
    if row.get("object"):
        yield node(row.get("object_type"), row.get("object")), row["object"]


class Resolution:
    def __init__(self, conversation: UUID, rows: list[dict[str, Any]]):
        self.conversation = conversation
        first: dict[Node, tuple[int, str]] = {}  # node → (order, spelling) of its first mention on the head
        counts: dict[Node, int] = {}
        edges: dict[Node, set[Node]] = {}
        self.alias_rows: list[tuple[Node, Node, dict[str, Any]]] = []
        for row in rows:
            for n, spelling in mentions(row):
                first.setdefault(n, (len(first), spelling))
                counts[n] = counts.get(n, 0) + 1
            if (row["predicate"] == "also_called" and row.get("modality", "actual") == "actual"
                    and norm(row.get("value")) and _own_alias(row)):
                a, b = node(row.get("subject_type"), row.get("subject")), node(row.get("subject_type"), row["value"])
                if a != b:
                    first.setdefault(b, (len(first), row["value"]))
                    edges.setdefault(a, set()).add(b)
                    edges.setdefault(b, set()).add(a)
                    self.alias_rows.append((a, b, row))
        for row in rows:  # second pass: participants rank below every resolve-v1 name source
            for n, spelling in participant_mentions(row):
                first.setdefault(n, (len(first), spelling))
                counts[n] = counts.get(n, 0) + 1
        self.ambiguous = {n for n in edges if _splits(n, edges)}
        parent: dict[Node, Node] = {n: n for n in first}

        def find(n: Node) -> Node:
            while parent[n] != n:
                parent[n] = parent[parent[n]]
                n = parent[n]
            return n

        for a, nbrs in edges.items():
            for b in nbrs:
                if a not in self.ambiguous and b not in self.ambiguous:
                    ra, rb = find(a), find(b)
                    if ra != rb:
                        parent[max(ra, rb, key=lambda r: first[r])] = min(ra, rb, key=lambda r: first[r])
        self._root = {n: find(n) for n in first if n not in self.ambiguous}
        self._edges = edges
        self._first = first
        self._counts = counts
        self._entities: dict[Node, dict[str, Any]] = {}
        for n, root in sorted(self._root.items(), key=lambda kv: first[kv[0]]):
            e = self._entities.get(root)
            if e is None:
                e = self._entities[root] = {
                    "id": str(uuid5(_NS, f"{conversation}:{RESOLVER_VERSION}:{root[0]}:{root[1]}")),
                    "type": root[0], "name": first[root][1], "names": [], "mentions": 0, "aliases": []}
            e["names"].append(first[n][1])
            e["mentions"] += counts.get(n, 0)
        for a, b, row in self.alias_rows:
            if a in self._root and b in self._root:
                self._entities[self._root[a]]["aliases"].append(
                    {"name": row["subject"], "other": row["value"], "turn": row.get("turn")})

    # --- lookups --------------------------------------------------------------------------------

    def status(self, entity_type: str | None, name: str | None) -> str:
        n = node(entity_type, name)
        return "ambiguous" if n in self.ambiguous else ("resolved" if n in self._root else "unresolved")

    def entity(self, entity_type: str | None, name: str | None) -> dict[str, Any] | None:
        # Every fact read asks for the same few names thousands of times: memoize by spelling.
        cache = self.__dict__.setdefault("_entity_cache", {})
        k = (entity_type, name)
        if k not in cache:
            root = self._root.get(node(entity_type, name))
            cache[k] = self._entities.get(root) if root else None
        return cache[k]

    def key(self, entity_type: str | None, name: str | None) -> str:
        """The version-key part for a mention: the entity id, or the normalized text when ambiguous
        or unknown to the resolver (ADR 0012, items 3 and 7)."""
        e = self.entity(entity_type, name)
        return e["id"] if e else "text:" + norm(name)

    def candidates(self, entity_type: str | None, name: str | None) -> list[str]:
        n = node(entity_type, name)
        out = []
        for other in sorted(self._edges.get(n, ()), key=lambda o: self._first[o]):
            e = self._entities.get(self._root.get(other)) if other in self._root else None
            if e and e["name"] not in out:
                out.append(e["name"])
        return out

    def entities(self) -> list[dict[str, Any]]:
        out = list(self._entities.values())
        out.sort(key=lambda e: -e["mentions"])
        return out

    def ambiguous_mentions(self) -> list[dict[str, Any]]:
        return [{"type": n[0], "name": self._first[n][1], "candidates": self.candidates(*n)}
                for n in sorted(self.ambiguous, key=lambda n: self._first[n])]


def _own_alias(row: dict[str, Any]) -> bool:
    """Narration may name anyone; a character's words link only the speaker's own names."""
    if row.get("source") != "character_claim":
        return True
    speaker = row.get("asserted_by")
    return bool(speaker) and node(row.get("subject_type"), row.get("subject")) == node("character", speaker)


def _splits(n: Node, edges: dict[Node, set[Node]]) -> bool:
    """Whether `n` joins alias neighbours that are not otherwise connected: then it names more than one
    entity and must not merge them."""
    nbrs = list(edges.get(n, ()))
    if len(nbrs) < 2:
        return False
    seen = {nbrs[0]}
    stack = [nbrs[0]]
    while stack:
        cur = stack.pop()
        for nxt in edges.get(cur, ()):
            if nxt != n and nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return any(m not in seen for m in nbrs[1:])


def resolve(conversation: UUID, rows: list[dict[str, Any]]) -> Resolution:
    """Entities of one conversation's active assertions (rows in position order)."""
    return Resolution(conversation, rows)
