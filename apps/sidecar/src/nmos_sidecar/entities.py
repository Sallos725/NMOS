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
"타쿠미") is a persona name like `{{user}}`, for characters only. The extractor writes the persona either
way, so without it one person was two entities.

Since `resolve-v5` (ADR 0038) a character name of two or more words whose last word is a persona name ("아오키 타쿠미"
for the persona "타쿠미") is the persona too: the story writes the persona's full name as well, and one chat was
split in two by it (Phase 11 M0).

With `given_joins` (the recorded recall option `given_name_join`, PHASE-28 Q4, ADR 0064, proposed; off unless a
request asks for it) a character written as a three-syllable Hangul name joins the character named by its given name
alone when the story mentions both in the same turns and nothing says they are two people (`_given_joins`). It is not
a `RESOLVER_VERSION`: a request records the option, and a trace without it reads without it.

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

RESOLVER_VERSION = "resolve-v5"
GIVEN_JOIN_TURNS = 2  # turns that mention both a full name and its given name before `given_joins` joins them
USER_NAMES = {"{{user}}", "{user}", "user", "유저"}
PERSONA = "{{user}}"
UNNAMED = "?"  # the extractor names a character shown without a name by a description starting with it (ADR 0024)
_NS = UUID("6c0c7e55-2f8e-4d0a-9d3b-5a4e1f0b7c21")  # NMOS entity namespace (arbitrary, fixed)

Node = tuple[str, str]  # (type, normalized name)


def norm(name: str | None) -> str:
    return " ".join(str(name or "").casefold().split())


def _persona_name(n: str, persona: frozenset[str]) -> bool:
    """A normalized character name that is the persona: a persona name, or a full name ending with one as its
    own word (resolve-v5)."""
    head, _, last = n.rpartition(" ")
    return n in persona or (bool(head) and last in persona)


@lru_cache(maxsize=8192)
def node(entity_type: str | None, name: str | None, persona: frozenset[str] = frozenset()) -> Node:
    """(type, normalized name). `persona`: the conversation's normalized persona names beyond `USER_NAMES`.
    Pure; cached because every fact read asks for the same few names."""
    n = norm(name)
    if entity_type == "character" and (n in USER_NAMES or _persona_name(n, persona)):
        n = PERSONA
    return (entity_type or "?", n)


def mentions(row: dict[str, Any], persona: frozenset[str] = frozenset()) -> Iterable[tuple[Node, str]]:
    yield node(row.get("subject_type"), row.get("subject"), persona), row.get("subject") or ""
    if row.get("object"):
        yield node(row.get("object_type"), row.get("object"), persona), row["object"]


class Resolution:
    def __init__(self, conversation: UUID, rows: list[dict[str, Any]], persona: Iterable[str] = (),
                 links: Iterable[dict[str, Any]] = (), splits: Iterable[dict[str, Any]] = (),
                 canon: Iterable[dict[str, Any]] = (), given_joins: bool = False):
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
                if n[0] == "character" and _persona_name(norm(spelling), self.persona):
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
                if n[0] == "character" and _persona_name(norm(p["name"]), self.persona):
                    hosted.setdefault(norm(p["name"]), p["name"])
        # The owner's links and splits between names the head mentions (ADR 0025, ADR 0044); the others wait for a
        # mention. Of a link and a split of the same two names, the newer holds.
        latest: dict[frozenset, str] = {}
        for kind, item in sorted([("link", x) for x in links] + [("split", x) for x in splits],
                                 key=lambda ki: (ki[1].get("created_at") is not None, ki[1].get("created_at"))):
            latest[frozenset((self.node(item["entity_type"], item["name"]),
                              self.node(item["entity_type"], item.get("same_as") or item.get("other"))))] = kind
        self.links: list[tuple[Node, Node, dict[str, Any]]] = []
        for link in links:
            a, b = self.node(link["entity_type"], link["name"]), self.node(link["entity_type"], link["same_as"])
            if a != b and a in first and b in first and latest.get(frozenset((a, b))) == "link":
                self.links.append((a, b, link))
        # A split drops the story's aliases that join the two names directly (K8); a third name can still join them.
        self.splits: list[tuple[Node, Node, dict[str, Any]]] = []
        for split in splits:
            a, b = self.node(split["entity_type"], split["name"]), self.node(split["entity_type"], split["other"])
            if a != b and a in first and b in first and latest.get(frozenset((a, b))) == "split":
                self.splits.append((a, b, split))
                edges.get(a, set()).discard(b)
                edges.get(b, set()).discard(a)
        self.alias_rows = [(a, b, row) for a, b, row in self.alias_rows
                           if not any({a, b} == {x, y} for x, y, _ in self.splits)]
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
        # A full name and its given name (PHASE-28 Q4), after the story's aliases and the owner's links: what they joined
        # counts as one, so a given name already joined to its full name needs nothing more.
        self.given_joins: list[tuple[Node, Node]] = []
        if given_joins:
            for full, short in _given_joins(rows, first, self.persona, self.ambiguous | overruled, latest):
                if find(full) != find(short):
                    union(full, short)
                    self.given_joins.append((full, short))
        self._root = {n: find(n) for n in first if n not in self.ambiguous}
        # A split whose names are still one entity, and the names that still join them.
        self.split_via: dict[str, list[str]] = {}
        accepted = {a: {b for b in nbrs if not {a, b} & (self.ambiguous | overruled)} for a, nbrs in edges.items()}
        for a, b, split in self.splits:
            if a in self._root and b in self._root and self._root[a] == self._root[b]:
                self.split_via[str(split["id"])] = [first[n][1] for n in _path(a, b, accepted, self.links)[1:-1]]
        # Names from canon (PHASE-14 Q6, ADR 0046), on top of the story's resolution: a lorebook entry's keys name one
        # thing. When the keys the story knows all name one entity, a character other than the persona, and no key names
        # anything else the story knows, the keys it does not know become that entity's aliases (K31). A key entries
        # give to two entities is ambiguous. A canon alias never joins, splits or unsettles what the story and the owner
        # settled, and an owner's split of an alias from its entity keeps it out (ADR 0044).
        known: dict[str, set[Node]] = {}
        for n in first:
            known.setdefault(n[1], set()).add(n)
        persona_node = ("character", PERSONA)
        persona_root = self._root.get(persona_node)
        claims: dict[Node, dict[Node, tuple[str, Any]]] = {}  # alias → entity root → (spelling, entry key)
        for item in canon:
            names = [n for n in dict.fromkeys(item.get("names") or ()) if norm(n)]
            nodes = [(self.node("character", n), n) for n in names]
            roots = {self._root[x] for x, _ in nodes if x in self._root}
            if (len(roots) != 1 or any(x in self.ambiguous for x, _ in nodes)
                    or any(x[0] != "character" for n in names for x in known.get(norm(n), ()))):
                continue
            (root,) = roots
            if root == persona_root or root[0] != "character":
                continue
            for x, spelling in nodes:
                if x not in first and x != persona_node:
                    claims.setdefault(x, {}).setdefault(root, (spelling, item.get("key")))
        for x, by in claims.items():
            if len(by) > 1:  # entries of two entities claim it: ambiguous, joined to neither
                first[x] = (len(first), next(iter(by.values()))[0])
                self.ambiguous.add(x)
                edges[x] = set(by)
                continue
            ((root, (spelling, key)),) = by.items()
            members = [n for n, r in self._root.items() if r == root]
            if any(latest.get(frozenset((x, m))) == "split" for m in members):
                continue
            first[x] = (len(first), spelling)
            self._root[x] = root
            self.alias_rows.append((root, x, {"subject": first[root][1], "value": spelling, "turn": None, "canon": key}))
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
                    {"name": row["subject"], "other": row["value"], "turn": row.get("turn"),
                     **({"canon": row["canon"]} if row.get("canon") else {})})
        for a, _, link in self.links:
            self._entities[self._root[a]]["links"].append(
                {"id": str(link["id"]), "name": link["name"], "same_as": link["same_as"]})
        for full, short in self.given_joins:  # listed like an alias, so a read can show what the option joined
            self._entities[self._root[full]]["aliases"].append(
                {"name": first[full][1], "other": first[short][1], "turn": None, "given_name": True})

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


def _given_joins(rows: list[dict[str, Any]], first: dict[Node, tuple[int, str]], persona: frozenset[str],
                 unsettled: set[Node], latest: dict[frozenset, str]) -> list[tuple[Node, Node]]:
    """(full name, given name) pairs of characters `given_joins` joins (PHASE-28 Q4, ADR 0064, proposed). A character
    written as a three-syllable Hangul name with a common family name (`variants.given`) and the character named by its
    given name alone join when all hold:

    - both are mentioned (subject, object or participant) in each of at least GIVEN_JOIN_TURNS turns;
    - no single assertion names both: one statement relating the two, or listing both, is about two people;
    - no turn gives them different values of one single-valued predicate (two places, two conditions at once), toward
      the same object when the predicate holds one value per object (two roles toward the same person);
    - no other character's full name has that given name (ADR 0058 item 3);
    - neither is the persona, and the given name is not the persona's;
    - neither name is ambiguous, and the owner has not split the two (ADR 0044).

    These do not prove identity: two people, one written in full and one only by the same given name, mentioned in
    separate assertions of the same turns, read exactly as one person called both ways, and are joined. The option is
    a measured comparison candidate for that reason (PHASE-28 Q4), off unless a request asks for it."""
    from .predicates import REGISTRY  # predicates imports this module
    from .variants import given

    persona_given = {g for n in persona | USER_NAMES if (g := given(n))}
    fulls: dict[str, list[Node]] = {}
    for n in first:
        if n[0] == "character" and n[1] != PERSONA and (g := given(n[1])):
            fulls.setdefault(g, []).append(n)
    pairs = []
    for g, (full, *others) in fulls.items():
        short = ("character", g)
        if (others or short not in first or g in persona_given or {full, short} & unsettled
                or latest.get(frozenset((full, short))) == "split"):
            continue
        pairs.append((full, short))
    if not pairs:
        return []
    wanted = {n for pair in pairs for n in pair}
    turns: dict[Any, set[Node]] = {}
    together: set[frozenset] = set()  # names one assertion names together (any two of them: two people)
    # (turn, predicate, the object when the predicate is per object) → node → the values it holds there in that turn
    held: dict[tuple, dict[Node, set[str]]] = {}
    for row in rows:
        named = {node(row.get("subject_type"), row.get("subject"), persona)}
        if row.get("object"):
            named.add(node(row.get("object_type"), row["object"], persona))
        named |= {node(p["type"], p["name"], persona) for p in row.get("participants") or ()}
        named &= wanted
        if not named:
            continue
        if len(named) > 1:
            together.update(frozenset((a, b)) for a in named for b in named if a != b)
        if row.get("turn") is None:
            continue
        turns.setdefault(row["turn"], set()).update(named)
        pred = REGISTRY.get(row.get("predicate"))
        subject = node(row.get("subject_type"), row.get("subject"), persona)
        if (pred is not None and pred.cardinality == "single" and subject in wanted
                and row.get("polarity", "positive") == "positive" and row.get("modality", "actual") == "actual"):
            if pred.per_object:  # one value per object: two values toward the same one (a role, a feeling) are two
                where = (row["turn"], row["predicate"], node(row.get("object_type"), row.get("object"), persona))
                what = norm(row.get("value"))
            else:
                where, what = (row["turn"], row["predicate"]), norm(row.get("object") or row.get("value"))
            held.setdefault(where, {}).setdefault(subject, set()).add(what)
    out = []
    for full, short in pairs:
        if frozenset((full, short)) in together:
            continue
        if sum(1 for named in turns.values() if full in named and short in named) < GIVEN_JOIN_TURNS:
            continue
        if any(full in by and short in by and by[full] != by[short] for by in held.values()):
            continue
        out.append((full, short))
    return out


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


def _path(a: Node, b: Node, edges: dict[Node, set[Node]], links: list[tuple[Node, Node, Any]]) -> list[Node]:
    """A shortest chain of aliases and owner links from a to b (both ends included), or [a, b] when none."""
    graph = {n: set(v) for n, v in edges.items()}
    for x, y, _ in links:
        graph.setdefault(x, set()).add(y)
        graph.setdefault(y, set()).add(x)
    back, queue = {a: a}, [a]
    while queue:
        n = queue.pop(0)
        if n == b:
            out = [b]
            while out[-1] != a:
                out.append(back[out[-1]])
            return out[::-1]
        for m in sorted(graph.get(n, ())):
            if m not in back:
                back[m] = n
                queue.append(m)
    return [a, b]


def resolve(conversation: UUID, rows: list[dict[str, Any]], persona: Iterable[str] = (),
            links: Iterable[dict[str, Any]] = (), splits: Iterable[dict[str, Any]] = (),
            canon: Iterable[dict[str, Any]] = (), given_joins: bool = False) -> Resolution:
    """Entities of one conversation's active assertions (rows in position order). `persona`: the persona's
    name as the host reports it for this conversation (ADR 0023), if known. `links`: the owner's current
    links of this conversation (`entity_type`, `name`, `same_as`, `id`; ADR 0025). `given_joins`: the recall option
    `given_name_join` (PHASE-28 Q4)."""
    return Resolution(conversation, rows, persona, links, splits, canon, given_joins)
