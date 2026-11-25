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

Since `resolve-v4` (ADR 0025) the owner's links (`entity_link`) join two names of one type whenever both
are mentioned on the head. The owner outranks the story's aliases: a name the owner links is never
ambiguous, and when the story's aliases made it ambiguous, only the owner's link joins it. An entity is
named after its first mentioned name that is not the description of an unnamed character ("?…",
`extract-v9`, ADR 0024), so a revealed character takes its name even if the description came first.

Since `resolve-v6` (Tier 1 identity fixes; owner decisions B1, B2, B4):
- An alias has a direction (subject → value: the person, then another name for them). A name whose every alias that
  counts is its own (it is the subject of each) is one person with several names, not ambiguous (세라 → Sera, 세라 →
  별빛); a name two otherwise unconnected names give as their alias is ambiguous, as before (하나 선배 → 하나, 하나
  후배 → 하나); a name that is both an alias and has aliases keeps the undirected rule. The description of an unnamed
  character ("?…") never counts toward a name's ambiguity, though two names revealed as one description still make
  that description ambiguous. An owner's link on an ambiguous name drops only the aliases by which other names
  claimed it, never its own aliases, parts or descriptions.
- The host's persona name may be composite ("Daniel Park/ 박현우", "A (B)"): every piece of it is a persona name
  (`persona_parts`), the only names `node()` folds into `{{user}}`. The names the persona is called by beyond them
  (its given name 현우, its Western first name Daniel, a Hangul spelling 대니얼 or 다니엘, a full name ending with a
  persona name as its own word, 아오키 타쿠미 for 타쿠미, not after a title such as 경비병) join the persona in
  `Resolution` as ordinary links: an owner's split separates any of them, and one another character's full name
  holds (강현우 → 현우) is not the persona's. This is the one place a spelling links names, and only to the persona.
- A lorebook entry whose keys the story mentions under several entities joins them when their names are one
  person's names (a full name and its part or given name, a romanized spelling: 윤하람, 하람, Haram) and no other
  entry names one of them with another known entity; an entry naming unrelated characters (a pair or a group) still joins nothing, and an owner's
  split between any of their names keeps them apart.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from functools import lru_cache
from typing import Any
from uuid import UUID, uuid5

RESOLVER_VERSION = "resolve-v6"
# The compilers whose alias of a name and a part of it (윤하람, 하람) the turn check passed with the part written on its
# own (extraction.PARTS_APART). Such a part does not make its full name ambiguous (`_splits`, ADR 0012 amendment of
# PHASE-28 Q4): 윤하람 → 하람 and 윤하람 → 람이 are one person's two names, not one name of two people (S1 turn 182).
PART_EDGES = frozenset({"extract-v16", "extract-v17", "extract-v18", "extract-v19", "extract-v20", "extract-v21"})
USER_NAMES = {"{{user}}", "{user}", "user", "유저"}
PERSONA = "{{user}}"
UNNAMED = "?"  # the extractor names a character shown without a name by a description starting with it (ADR 0024)
# Words before a name that make it a title and a name, not a family name and a given name: "경비병 민수" is not the
# persona 민수, "Sir Arthur" is not named Sir. Normalized (casefolded), compared without a trailing period.
TITLES = frozenset({
    "경비병", "경비", "병사", "대장", "부대장", "단장", "부단장", "기사", "기사단장", "교수", "선생", "선생님", "박사",
    "의사", "형사", "경감", "경위", "반장", "부장", "과장", "차장", "대리", "사장", "회장", "이사", "실장", "팀장",
    "국장", "원장", "왕", "왕자", "공주", "여왕", "황제", "황후", "황자", "황녀", "공작", "후작", "백작", "자작", "남작",
    "영주", "경", "상인", "신부", "수녀", "목사", "마법사", "용사", "선배", "후배", "장군", "대위", "중위", "소위",
    "하사", "병장", "상병", "일병", "이병", "집사", "하녀", "메이드", "도련님", "아가씨", "사부", "스승",
    "sir", "dame", "lord", "lady", "captain", "capt", "guard", "mr", "mrs", "ms", "miss", "mx", "dr", "prof",
    "professor", "doctor", "king", "queen", "prince", "princess", "duke", "duchess", "count", "countess", "baron",
    "baroness", "father", "mother", "sister", "brother", "uncle", "aunt", "saint", "st", "officer", "sergeant", "sgt",
    "detective", "general", "colonel", "major", "lieutenant", "lt", "commander", "master", "mistress", "madam",
    "madame", "monsieur", "señor", "senor", "herr", "frau", "agent", "inspector", "chief", "elder", "reverend", "rev",
})
_PIECES = re.compile(r"[/|·・()（）]")
_NS = UUID("6c0c7e55-2f8e-4d0a-9d3b-5a4e1f0b7c21")  # NMOS entity namespace (arbitrary, fixed)

Node = tuple[str, str]  # (type, normalized name)


def norm(name: str | None) -> str:
    return " ".join(str(name or "").casefold().split())


@lru_cache(maxsize=256)
def _primary(persona: frozenset[str]) -> frozenset[str]:
    """The persona's names as the host gives them: each name whole, and each piece of a composite one ("daniel park/
    박현우" → itself, "daniel park", "박현우"; "a (b)" → itself, "a", "b"). Normalized."""
    out: set[str] = set()
    for p in persona:
        n = norm(p)
        if not n:
            continue
        out.add(n)
        out.update(q for piece in _PIECES.split(n) if (q := norm(piece)))
    return frozenset(out - USER_NAMES)


def _titled(words: list[str]) -> bool:
    return any(w.rstrip(".") in TITLES for w in words)


def persona_parts(persona: Iterable[str]) -> tuple[frozenset[str], frozenset[str]]:
    """(primary, derived) normalized persona names. Primary: the host's names and the pieces of a composite one, the
    only names `node()` folds into `{{user}}`. Derived: the names a story calls the persona by that `Resolution`
    links to it, splittably — the given name of a Hangul full name (박현우 → 현우, 남궁세연 → 세연, 박 현우 → 현우),
    the first word of a Latin name (daniel park → daniel), and the first and the last word of a Hangul name of several
    words whose first is not a Korean family name (아오키 타쿠미 → 아오키, 타쿠미; 세라 델 모렌 → 세라, 모렌: the
    order may be either). A title is never a derived name. Spellings across scripts (대니얼 for Daniel) are matched
    in `Resolution`."""
    from .variants import FAMILY, FAMILY_TWO, HANGUL, given  # variants imports this module

    primary = _primary(frozenset(n for n in map(norm, persona) if n))
    derived: set[str] = set()
    for q in primary:
        words = q.split()
        if len(words) == 1:
            if g := given(q):
                derived.add(g)
            continue
        if g := given(q):  # 박 현우
            derived.add(g)
        head = [w for w in words if w.rstrip(".") not in TITLES]
        if not head:
            continue
        if all(re.fullmatch(r"[a-z][a-z'.-]*", w) for w in words):
            derived.add(head[0])
        elif all(HANGUL.fullmatch(w) for w in head):
            if head[0] in FAMILY or head[0] in FAMILY_TWO:
                derived.add(" ".join(head[1:]))
            else:
                derived.add(head[-1])
                derived.add(head[0])
    return primary, frozenset(d for d in derived if len(d) >= 2 and d not in primary and d not in TITLES)


@lru_cache(maxsize=8192)
def node(entity_type: str | None, name: str | None, persona: frozenset[str] = frozenset()) -> Node:
    """(type, normalized name). `persona`: the conversation's normalized persona names beyond `USER_NAMES`; a
    composite one counts by each of its pieces (`persona_parts`). Only those exact names fold into `{{user}}`: a
    full name ending with one (아오키 타쿠미) or a name derived from one (현우 for 박현우) joins the persona in
    `Resolution`, where an owner's split can undo it. Pure; cached because every fact read asks for the same few
    names."""
    n = norm(name)
    if entity_type == "character" and (n in USER_NAMES or n in _primary(persona)):
        n = PERSONA
    return (entity_type or "?", n)


def names_persona(entity_type: str | None, name: str | None, persona: Iterable[str] = ()) -> bool:
    """Whether a name, read without a conversation's resolution, is the persona: a name `node()` folds into
    `{{user}}`, or one the story calls it by (`_persona_matcher`: 아오키 타쿠미 for 타쿠미, 현우 for 박현우). For callers
    that check one name against the host's persona name (extraction's role check); a read uses `Resolution`, where
    the owner's splits and other characters' full names also count."""
    if node(entity_type, name, frozenset(n for n in map(norm, persona) if n))[1] == PERSONA:
        return True
    return entity_type == "character" and _persona_matcher(*persona_parts(persona))(norm(name))


def mentions(row: dict[str, Any], persona: frozenset[str] = frozenset()) -> Iterable[tuple[Node, str]]:
    yield node(row.get("subject_type"), row.get("subject"), persona), row.get("subject") or ""
    if row.get("object"):
        yield node(row.get("object_type"), row.get("object"), persona), row["object"]


class Resolution:
    def __init__(self, conversation: UUID, rows: list[dict[str, Any]], persona: Iterable[str] = (),
                 links: Iterable[dict[str, Any]] = (), splits: Iterable[dict[str, Any]] = (),
                 canon: Iterable[dict[str, Any]] = ()):
        self.conversation = conversation
        links, splits = list(links), list(splits)
        # The host's persona names and the pieces of a composite one (`node()` folds them), and the names derived
        # from them that join the persona below, splittably.
        self.persona, derived = persona_parts(persona)
        persona_node: Node = ("character", PERSONA)
        first: dict[Node, tuple[int, str]] = {}  # node → (order, spelling) of its first mention on the head
        counts: dict[Node, int] = {}
        edges: dict[Node, set[Node]] = {}
        out: dict[Node, set[Node]] = {}  # an alias's direction: its subject → its value (the person → another name)
        parts: dict[Node, set[Node]] = {}  # a full name → the parts of it its aliases checked apart name (PART_EDGES)
        self.alias_rows: list[tuple[Node, Node, dict[str, Any]]] = []
        hosted: dict[str, str] = {}  # the host's persona names as the story spells them (a node keeps one spelling)
        for row in rows:
            for n, spelling in mentions(row, self.persona):
                first.setdefault(n, (len(first), spelling))
                counts[n] = counts.get(n, 0) + 1
                if n == persona_node and norm(spelling) in self.persona:
                    hosted.setdefault(norm(spelling), spelling)
            if (row["predicate"] == "also_called" and row.get("modality", "actual") == "actual"
                    and norm(row.get("value")) and _own_alias(row, self.persona)):
                a, b = self.node(row.get("subject_type"), row.get("subject")), self.node(row.get("subject_type"), row["value"])
                if a != b:
                    first.setdefault(b, (len(first), row["value"]))
                    edges.setdefault(a, set()).add(b)
                    edges.setdefault(b, set()).add(a)
                    out.setdefault(a, set()).add(b)
                    self.alias_rows.append((a, b, row))
                    # By the names as written: the persona's node is {{user}}, but 한서윤 → 서윤 is still a full name
                    # and its given name (a persona with one more alias read as ambiguous before).
                    sa, sb = norm(row.get("subject")), norm(row["value"])
                    whole, part = (a, b) if len(sa) > len(sb) else (b, a)
                    if row.get("compiler") in PART_EDGES and min(sa, sb, key=len) in max(sa, sb, key=len):
                        parts.setdefault(whole, set()).add(part)
        for row in rows:  # second pass: participants rank below every resolve-v1 name source
            for p in row.get("participants") or ():  # stored by predicates.participants(): typed, named
                n = self.node(p["type"], p["name"])
                first.setdefault(n, (len(first), p.get("name")))
                counts[n] = counts.get(n, 0) + 1
                if n == persona_node and norm(p["name"]) in self.persona:
                    hosted.setdefault(norm(p["name"]), p["name"])
        # The story's names for the persona beyond the host's (resolve-v6): they join it below, as links an owner's
        # split undoes. The persona's node is there for them even when the story never writes a persona name itself,
        # so an owner's link or split can name it.
        of_persona = _persona_matcher(self.persona, derived)
        called = [n for n in first if n[0] == "character" and n != persona_node and of_persona(n[1])]
        synthetic = bool(called) and persona_node not in first
        if synthetic:
            first[persona_node] = (len(first), PERSONA)
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
                for x, y in ((a, b), (b, a)):
                    edges.get(x, set()).discard(y)
                    out.get(x, set()).discard(y)
        self.alias_rows = [(a, b, row) for a, b, row in self.alias_rows
                           if not any({a, b} == {x, y} for x, y, _ in self.splits)]
        linked = {n for a, b, _ in self.links for n in (a, b)}
        # The owner settles what the story left ambiguous: an owner-linked name drops the aliases by which other names
        # claimed it (the owner's link joins the right one), and keeps its own aliases, parts and descriptions. A
        # description has no direction: it drops every name it was revealed as.
        overruled = {n for n in linked if _splits(n, edges, parts, out)}
        contested = {n: {m for m in _counted(n, edges, parts) if n[1].startswith(UNNAMED) or n in out.get(m, ())}
                     for n in overruled}
        self.ambiguous = {n for n in edges if _splits(n, edges, parts, out)} - linked
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

        def joins(a: Node, b: Node) -> bool:
            return not ({a, b} & self.ambiguous or b in contested.get(a, ()) or a in contested.get(b, ()))

        for a, nbrs in edges.items():
            for b in nbrs:
                if joins(a, b):
                    union(a, b)
        for a, b, _ in self.links:
            union(a, b)
        # The persona's derived names join it unless the owner split a name they go by from a name the persona goes
        # by, the owner linked them to another name, another name gives one of them as its alias, or another
        # character's full name holds them (강현우 → 현우 is 강현우's, not 박현우's).
        cut = [tuple(k) for k, v in latest.items() if v == "split" and len(k) == 2 and all(x in parent for x in k)]
        self.persona_links: list[tuple[Node, Node, dict[str, Any]]] = []
        held = [m for m in first if m[0] == "character" and m != persona_node and m not in called]
        for v in called:
            if v in self.ambiguous or find(v) == find(persona_node):
                continue
            rv, rp = find(v), find(persona_node)
            if any({find(a), find(b)} == {rv, rp} for a, b in cut):
                continue
            group = {m for m in first if find(m) == rv}
            if any(m in linked and m not in called for m in group):
                continue
            # another name gives one of these as its alias (카이토 → 현우, Daniel Craig → 대니얼): it is that name's
            if any(m not in called and m != persona_node and out.get(m, set()) & group for m in group):
                continue
            if any(_holds(m[1], v[1]) for m in held if find(m) != rp):
                continue
            parent[find(v)] = find(persona_node)
            self.persona_links.append((persona_node, v, {}))
        if persona_node in first and (rp := find(persona_node)) != persona_node:  # the persona's id never moves
            parent[persona_node] = persona_node
            parent[rp] = persona_node
        if synthetic and not any(find(n) == persona_node for n in first if n != persona_node):
            del first[persona_node], parent[persona_node]
            cut = [(a, b) for a, b in cut if persona_node not in (a, b)]
        self._root = {n: find(n) for n in first if n not in self.ambiguous}
        # A split whose names are still one entity, and the names that still join them.
        self.split_via: dict[str, list[str]] = {}
        accepted = {a: {b for b in nbrs if joins(a, b)} for a, nbrs in edges.items()}
        for a, b, split in self.splits:
            if a in self._root and b in self._root and self._root[a] == self._root[b]:
                self.split_via[str(split["id"])] = [
                    first[n][1] for n in _path(a, b, accepted, self.links + self.persona_links)[1:-1]]
        # Names from canon (PHASE-14 Q6, ADR 0046), on top of the story's resolution: a lorebook entry's keys name one
        # thing. A key entries give to two entities is ambiguous, the persona never takes a canon alias, and an owner's
        # split keeps an alias or a join out (ADR 0044). resolve-v6: when the story knows the entry's keys under several
        # characters whose names are one person's (윤하람, 하람, Haram) and no other entry names one of them with another
        # known entity, the entry joins them; an entry naming unrelated characters (a pair, a group) joins nothing. When the keys the story knows then
        # name one entity, a character other than the persona, and no key names anything else the story knows, the keys
        # it does not know become that entity's aliases (K31).
        known: dict[str, set[Node]] = {}
        for n in first:
            known.setdefault(n[1], set()).add(n)
        persona_root = self._root.get(persona_node)
        entries: list[tuple[dict[str, Any], list[tuple[Node, str]], bool]] = []
        for item in canon:
            names = [n for n in dict.fromkeys(item.get("names") or ()) if norm(n)]
            nodes = [(self.node("character", n), n) for n in names]
            bad = (any(x in self.ambiguous for x, _ in nodes)
                   or any(x[0] != "character" for n in names for x in known.get(norm(n), ())))
            entries.append((item, nodes, bad))
        touched: dict[Node, set[int]] = {}  # a known entity → the entries naming it
        named: list[set[Node]] = []  # an entry → the known entities it names
        for i, (_, nodes, _) in enumerate(entries):
            named.append({self._root[x] for x, _ in nodes if x in self._root})
            for r in named[-1]:
                touched.setdefault(r, set()).add(i)
        joined = False
        for i, (item, nodes, bad) in enumerate(entries):
            roots = named[i]
            # another entry naming one of them may name it alone or with these (a character's second entry); one
            # naming it with another known entity pulls it elsewhere, and neither joins
            if (bad or len(roots) < 2 or persona_root in roots or any(r[0] != "character" for r in roots)
                    or any(not named[j] <= roots for r in roots for j in touched[r] - {i})):
                continue
            mentioned = [x for x, _ in nodes if x in self._root]
            for j, x in enumerate(mentioned):
                for y in mentioned[j + 1:]:
                    if find(x) == find(y) or not (_holds(x[1], y[1]) or _holds(y[1], x[1]) or _spelled(x[1], y[1])):
                        continue
                    rx, ry = find(x), find(y)
                    if any({find(a), find(b)} == {rx, ry} for a, b in cut):
                        continue
                    union(x, y)
                    joined = True
                    self.alias_rows.append((x, y, {"subject": first[x][1], "value": first[y][1], "turn": None,
                                                   "canon": item.get("key")}))
        if joined:
            self._root = {n: find(n) for n in first if n not in self.ambiguous}
        claims: dict[Node, dict[Node, tuple[str, Any]]] = {}  # alias → entity root → (spelling, entry key)
        for item, nodes, bad in entries:
            roots = {self._root[x] for x, _ in nodes if x in self._root}
            if bad or len(roots) != 1:
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
        self._persona_root = self._root.get(persona_node)
        if self._persona_root is not None:
            e = self._entities[self._persona_root]
            e["persona"] = True
            e["names"] += [h for h in hosted.values() if h not in e["names"]]
        # Every name the persona goes by in this conversation: never a mention in recall (ADR 0019, 0021). A derived
        # name counts unless the story gives it to another entity or another character's full name holds it.
        others = [m for m in held if self._root.get(m) != self._persona_root or self._persona_root is None]
        free = {d for d in derived
                if (dn := ("character", d)) not in self.ambiguous
                and (dn not in self._root or self._root[dn] == self._persona_root)
                and not any(_holds(m[1], d) for m in others)}
        self.persona_names = frozenset(USER_NAMES | self.persona | free | (
            {norm(n) for n in self._entities[self._persona_root]["names"]} if self._persona_root else set()))
        for a, b, row in self.alias_rows:
            if a in self._root and b in self._root:
                self._entities[self._root[a]]["aliases"].append(
                    {"name": row["subject"], "other": row["value"], "turn": row.get("turn"),
                     **({"canon": row["canon"]} if row.get("canon") else {})})
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
    if not speaker:
        return False
    if node(row.get("subject_type"), row.get("subject"), persona) == node("character", speaker, persona):
        return True
    # the persona introducing itself under another of its names (아오키 타쿠미 says 타쿠미 is called 타쿠; resolve-v6)
    return (row.get("subject_type") == "character" and names_persona("character", row.get("subject"), persona)
            and names_persona("character", speaker, persona))


def _counted(n: Node, edges: dict[Node, set[Node]], parts: dict[Node, set[Node]] | None = None) -> list[Node]:
    """`n`'s alias neighbours that count toward its ambiguity: not a part of it checked apart (`parts`, PART_EDGES),
    and not the description of an unnamed character (one placeholder for one person, resolve-v6)."""
    return [m for m in edges.get(n, ()) if m not in (parts or {}).get(n, ()) and not m[1].startswith(UNNAMED)]


def _splits(n: Node, edges: dict[Node, set[Node]], parts: dict[Node, set[Node]] | None = None,
            out: dict[Node, set[Node]] | None = None) -> bool:
    """Whether `n` joins alias neighbours that are not otherwise connected: then it names more than one
    entity and must not merge them. A part of `n` checked apart (`parts`, PART_EDGES) is not counted: a full name with
    its given name and one more name is one person's names; nor is an unnamed character's description.

    `out` (resolve-v6) gives each alias's direction, subject → value. A name that is the subject of every alias that
    counts (세라 → Sera, 세라 → 별빛) is one person with several names, not ambiguous; a name some other name gives as
    its alias keeps the undirected rule (two names giving it: 하나 선배 → 하나, 하나 후배 → 하나; an alias with an
    alias of its own: 윤하람 → 람이, 람이 → 도도). A description is always read undirected: two names revealed as one
    "?…" make it ambiguous whichever way they were written."""
    nbrs = _counted(n, edges, parts)
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
    if all(m in seen for m in nbrs[1:]):
        return False
    if out is None or n[1].startswith(UNNAMED):
        return True
    return any(n in out.get(m, ()) for m in nbrs)


def _holds(full: str, part: str) -> bool:
    """Whether the normalized name `part` is a part of the normalized full name `full` a story calls its bearer by:
    one of its words (daniel of daniel craig, 현우 of 박 현우), its given name (현우 of 강현우, 세연 of 남궁세연), or
    the end of a one-word Hangul name (현우 of 도현우)."""
    from .variants import HANGUL, given  # variants imports this module

    if not part or full == part:
        return False
    words = full.split()
    return (part in words or given(full) == part
            or (len(words) == 1 and bool(HANGUL.fullmatch(full)) and len(full) > len(part) and full.endswith(part)))


def _spelled(a: str, b: str) -> bool:
    """Whether one normalized name is the other's romanized spelling on the fixed keys (Haram, 하람; ADR 0058)."""
    from .variants import hangul_keys, latin_keys

    for x, y in ((a, b), (b, a)):
        lk = latin_keys(x)
        if lk and (lk & hangul_keys(y.replace(" ", "")) or any(lk & hangul_keys(w) for w in y.split())):
            return True
    return False


def _persona_matcher(primary: frozenset[str], derived: frozenset[str]) -> Any:
    """Whether a normalized character name is one the story calls the persona by beyond its primary names (resolve-v6):
    a derived name (`persona_parts`); a full name ending with a primary name as its own word, not after a title
    (아오키 타쿠미 for 타쿠미, not 경비병 타쿠미; resolve-v5's rule, now splittable); a Hangul word spelling a Latin
    persona name, by the fixed keys or with its vowels folded (다니엘, 대니얼 for Daniel); and a Latin name spelling
    a Hangul one (Hyunwoo for 현우)."""
    from .variants import HANGUL, LOOSE_MIN, hangul_keys, key, latin_keys, loose

    if not primary:
        return lambda n: False
    names = primary | derived
    latin = {k for q in names for k in latin_keys(q)}
    hangul = {k for q in names for w in q.split() for k in hangul_keys(w)}
    loose_keys = {lk for k in latin if len(lk := loose(k)) >= LOOSE_MIN}

    def match(n: str) -> bool:
        if not n or n in USER_NAMES or n in primary or n.startswith(UNNAMED) or n in TITLES:
            return False
        if n in derived:
            return True
        words = n.split()
        if len(words) >= 2:
            return words[-1] in primary and not _titled(words[:-1])
        if HANGUL.fullmatch(n):
            ks = hangul_keys(n)
            return bool(ks & latin) or bool({loose(k) for k in ks} & loose_keys)
        return bool(latin_keys(n)) and key(n) in hangul

    return match


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
            canon: Iterable[dict[str, Any]] = ()) -> Resolution:
    """Entities of one conversation's active assertions (rows in position order). `persona`: the persona's
    name as the host reports it for this conversation (ADR 0023), if known. `links`: the owner's current
    links of this conversation (`entity_type`, `name`, `same_as`, `id`; ADR 0025)."""
    return Resolution(conversation, rows, persona, links, splits, canon)
