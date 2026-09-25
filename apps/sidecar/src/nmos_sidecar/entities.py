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

Since `resolve-v3` (ADR 0023) the persona's name as the host reports it for the conversation (e.g.
"유우마") is a persona name like `{{user}}`, for characters only. The extractor writes the persona either
way, so without it one person was two entities.

Since `resolve-v4` (ADR 0025) the owner's links (`entity_link`) join two names of one type whenever both
are mentioned on the head. The owner outranks the story's aliases: a name the owner links is never
ambiguous, and when the story's aliases made it ambiguous, only the owner's link joins it. An entity is
named after its first mentioned name that is not the description of an unnamed character ("?…",
`extract-v9`, ADR 0024), so a revealed character takes its name even if the description came first.
"""

from __future__ import annotations

from collections.abc import Iterable
from functools import lru_cache
from typing import Any
from uuid import UUID, uuid5

RESOLVER_VERSION = "resolve-v4"
USER_NAMES = {"{{user}}", "{user}", "user", "유저"}
PERSONA = "{{user}}"
UNNAMED = "?"  # the extractor names a character shown without a name by a description starting with it (ADR 0024)
_NS = UUID("6c0c7e55-2f8e-4d0a-9d3b-5a4e1f0b7c21")  # NMOS entity namespace (arbitrary, fixed)

Node = tuple[str, str]  # (type, normalized name)


def norm(name: str | None) -> str:
    return " ".join(str(name or "").casefold().split())


@lru_cache(maxsize=8192)
def node(entity_type: str | None, name: str | None, persona: frozenset[str] = frozenset()) -> Node:
    """(type, normalized name). `persona`: the conversation's normalized persona names beyond `USER_NAMES`.
    Pure; cached because every fact read asks for the same few names."""
    n = norm(name)
    if entity_type == "character" and (n in USER_NAMES or n in persona):
        n = PERSONA
    return (entity_type or "?", n)


def mentions(row: dict[str, Any], persona: frozenset[str] = frozenset()) -> Iterable[tuple[Node, str]]:
    yield node(row.get("subject_type"), row.get("subject"), persona), row.get("subject") or ""
    if row.get("object"):
        yield node(row.get("object_type"), row.get("object"), persona), row["object"]


class Resolution:
    def __init__(self, conversation: UUID, rows: list[dict[str, Any]], persona: Iterable[str] = (),
                 links: Iterable[dict[str, Any]] = ()):
        self.conversation = conversation
        self.persona = frozenset(n for n in map(norm, persona) if n)
        first: dict[Node, tuple[int, str]] = {}  # node → (order, spelling) of its first mention on the head
        counts: dict[Node, int] = {}
        edges: dict[Node, set[Node]] = {}
        self.alias_rows: list[tuple[Node, Node, dict[str, Any]]] = []
        hosted: dict[str, str] = {}  # the host's persona names as the story spells them (a node keeps one spelling)
        for row in rows:
            for n, spelling in mentions(row, self.persona):
                first.setdefault(n, (len(first), spelling))
                counts[n] = counts.get(n, 0) + 1
                if n[0] == "character" and norm(spelling) in self.persona:
                    hosted.setdefault(norm(spelling), spelling)
            if (row["predicate"] == "also_called" and row.get("modality", "actual") == "actual"
                    and norm(row.get("value")) and _own_alias(row, self.persona)):
                a, b = self.node(row.get("subject_type"), row.get("subject")), self.node(row.get("subject_type"), row["value"])
                if a != b:
                    first.setdefault(b, (len(first), row["value"]))
                    edges.setdefault(a, set()).add(b)
                    edges.setdefault(b, set()).add(a)
                    self.alias_rows.append((a, b, row))
        for row in rows:  # second pass: participants rank below every resolve-v1 name source
            for p in row.get("participants") or ():  # stored by predicates.participants(): typed, named
                n = self.node(p["type"], p["name"])
                first.setdefault(n, (len(first), p.get("name")))
                counts[n] = counts.get(n, 0) + 1
                if n[0] == "character" and norm(p["name"]) in self.persona:
                    hosted.setdefault(norm(p["name"]), p["name"])
        # The owner's links between names the head mentions (ADR 0025); the others wait for a mention.
        self.links: list[tuple[Node, Node, dict[str, Any]]] = []
        for link in links:
            a, b = self.node(link["entity_type"], link["name"]), self.node(link["entity_type"], link["same_as"])
            if a != b and a in first and b in first:
                self.links.append((a, b, link))
        linked = {n for a, b, _ in self.links for n in (a, b)}
        overruled = {n for n in linked if _splits(n, edges)}  # the owner settles what the story left ambiguous
        self.ambiguous = {n for n in edges if _splits(n, edges)} - linked
        parent: dict[Node, Node] = {n: n for n in first}

        def find(n: Node) -> Node:
            while parent[n] != n:
                parent[n] = parent[parent[n]]
                n = parent[n]
            return n

        def rank(n: Node) -> tuple[bool, int]:  # a name before a description of someone unnamed (ADR 0024)
            return first[n][1].startswith(UNNAMED), first[n][0]

        def union(a: Node, b: Node) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[max(ra, rb, key=rank)] = min(ra, rb, key=rank)

        for a, nbrs in edges.items():
            for b in nbrs:
                if not {a, b} & (self.ambiguous | overruled):
                    union(a, b)
        for a, b, _ in self.links:
            union(a, b)
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
                    "type": root[0], "name": first[root][1], "names": [], "mentions": 0, "aliases": [],
                    "links": [], "persona": False}
            e["names"].append(first[n][1])
            e["mentions"] += counts.get(n, 0)
        self._persona_root = self._root.get(("character", PERSONA))
        if self._persona_root is not None:
            e = self._entities[self._persona_root]
            e["persona"] = True
            e["names"] += [h for h in hosted.values() if h not in e["names"]]
        # Every name the persona goes by in this conversation: never a mention in recall (ADR 0019, 0021).
        self.persona_names = frozenset(USER_NAMES | self.persona | (
            {norm(n) for n in self._entities[self._persona_root]["names"]} if self._persona_root else set()))
        for a, b, row in self.alias_rows:
            if a in self._root and b in self._root:
                self._entities[self._root[a]]["aliases"].append(
                    {"name": row["subject"], "other": row["value"], "turn": row.get("turn")})
        for a, _, link in self.links:
            self._entities[self._root[a]]["links"].append(
                {"id": str(link["id"]), "name": link["name"], "same_as": link["same_as"]})

    # --- lookups --------------------------------------------------------------------------------

    def node(self, entity_type: str | None, name: str | None) -> Node:
        return node(entity_type, name, self.persona)

    def is_persona(self, entity_type: str | None, name: str | None) -> bool:
        return self._persona_root is not None and self._root.get(self.node(entity_type, name)) == self._persona_root

    def status(self, entity_type: str | None, name: str | None) -> str:
        n = self.node(entity_type, name)
        return "ambiguous" if n in self.ambiguous else ("resolved" if n in self._root else "unresolved")

    def entity(self, entity_type: str | None, name: str | None) -> dict[str, Any] | None:
        # Every fact read asks for the same few names thousands of times: memoize by spelling.
        cache = self.__dict__.setdefault("_entity_cache", {})
        k = (entity_type, name)
        if k not in cache:
            root = self._root.get(self.node(entity_type, name))
            cache[k] = self._entities.get(root) if root else None
        return cache[k]

    def key(self, entity_type: str | None, name: str | None) -> str:
        """The version-key part for a mention: the entity id, or the normalized text when ambiguous
        or unknown to the resolver (ADR 0012, items 3 and 7)."""
        e = self.entity(entity_type, name)
        return e["id"] if e else "text:" + norm(name)

    def candidates(self, entity_type: str | None, name: str | None) -> list[str]:
        n = self.node(entity_type, name)
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


def _own_alias(row: dict[str, Any], persona: frozenset[str] = frozenset()) -> bool:
    """Narration may name anyone; a character's words link only the speaker's own names."""
    if row.get("source") != "character_claim":
        return True
    speaker = row.get("asserted_by")
    return bool(speaker) and node(row.get("subject_type"), row.get("subject"), persona) == node("character", speaker, persona)


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


def resolve(conversation: UUID, rows: list[dict[str, Any]], persona: Iterable[str] = (),
            links: Iterable[dict[str, Any]] = ()) -> Resolution:
    """Entities of one conversation's active assertions (rows in position order). `persona`: the persona's
    name as the host reports it for this conversation (ADR 0023), if known. `links`: the owner's current
    links of this conversation (`entity_type`, `name`, `same_as`, `id`; ADR 0025)."""
    return Resolution(conversation, rows, persona, links)
