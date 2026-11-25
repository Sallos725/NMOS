"""Who is in the scene, and which facts only some of them know (PHASE-10 step 4, ADR 0034). Pure.

The scene cast is read from what the request already has: the characters the last CAST_TURNS turns before
the current one are about (subjects, objects and typed participants of their assertions, Phase 8), every
character named in the user's message or the previous reply (extraction lags one turn behind), a known entity
or a name in knowledge marks, under any name it goes by in this request (`aliases`, ADR 0058), and the persona.
Characters compare by entity (ADR 0012), and every name the persona goes by is the persona, so aliases are one person.

A limited fact is private in this scene when someone in the cast is not among the characters shown to know
it (`known_by`); with nobody in the cast, nothing is. Public, unknown and unmarked facts are never private.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Iterable, Mapping
from typing import Any

from .entities import USER_NAMES, Resolution, names_persona, norm
from .variants import widened

CAST_TURNS = 2
PERSONA = "{{user}}"
LATIN = re.compile(r"[a-z0-9]+")


def _words(text: str) -> str:
    """A normalized text as its Latin words, space-padded: a whole-word match is a substring of it."""
    return f" {' '.join(LATIN.findall(text))} "


def _said(name: str, said: str, words: str) -> bool:
    """A normalized name in the normalized message (`words` = `_words(said)`): a Latin name as whole words ("ren" is
    not in "current"), as `divergence._named_in`; any other as written, since a Korean particle joins its name."""
    if len(name) < 2:
        return False
    if not name.isascii():
        return name in said
    w = _words(name)
    return w != "  " and w in words


def is_persona(r: Resolution, name: str) -> bool:
    """Every name the persona goes by in `r` (ADR 0023, resolve-v6): uses the conversation's resolution when the name
    is a known entity (so a split NPC or title-prefixed NPC is never hijacked), and `names_persona` for mark-only names."""
    if r.is_persona("character", name):
        return True
    if r.entity("character", name) is not None:
        return False
    return norm(name) in r.persona_names or names_persona("character", name, r.persona)


def key(r: Resolution, name: str) -> str:
    """A character's key; the persona under any of its names is one key."""
    return r.key("character", PERSONA if is_persona(r, name) else name)


def names(scene: dict[str, str], r: Resolution | None,
          aliases: Mapping[str, frozenset[str]] | None = None) -> frozenset[str]:
    """Every normalized name the scene's characters go by, for matching knowledge marks and the message."""
    out = {norm(n) for n in scene.values()}
    if r is not None:
        for e in r.entities():
            if e["id"] in scene:
                out |= {norm(n) for n in e["names"]}
    return frozenset(n for n in widened(out, aliases) if len(n) >= 2)


def cast(rows: list[dict[str, Any]], r: Resolution | None, query: str = "", previous_ai: str = "",
         now: int | None = None, turns: int = CAST_TURNS,
         aliases: Mapping[str, frozenset[str]] | None = None, marks: Iterable[str] = (),
         excluded: Collection[str] = ()) -> dict[str, str]:
    """{entity key: display name} of the characters in the scene. `now` is the current turn (the user's
    message); without it, the last turn any row comes from counts as the last one before it. `marks`: more names in
    knowledge marks (an open thread's, ADR 0058). `excluded`: ids of the entities the owner marked not a character
    (PHASE-47, `memory_view`'s `excluded`), never in the cast, so no fact is private for them."""
    if r is None:
        return {}
    out: dict[str, str] = {}

    def add(name: str | None) -> None:
        if name:
            e = r.entity("character", name)
            out.setdefault(key(r, name), e["name"] if e else name)

    if now is not None:
        until = now - 1
    else:
        until = max((row["turn"] for row in rows if row.get("turn") is not None), default=-1)
    since = until - turns + 1
    marked: set[str] = set(marks)  # names in knowledge marks: someone a secret is kept from may be named only there
    for row in rows:
        if row.get("known_by") or row.get("hidden_from"):
            marked.update(row.get("known_by") or ())
            marked.update(row.get("hidden_from") or ())
        if row.get("turn") is None or row.get("canon") or row.get("carried") or not since <= row["turn"] <= until:
            continue  # canon and a carried row (ADR 0085) are before the story: never the scene (ADR 0047)
        if row.get("subject_type") == "character":
            add(row["subject"])
        if row.get("object_type") == "character":
            add(row.get("object"))
        for p in row.get("participants") or ():
            if p.get("type") == "character":
                add(p["name"])
    said = norm(f"{query} {previous_ai}")
    words = _words(said)
    known: dict[str, dict[str, Any]] = {}  # every name a character goes by in this request -> that character
    for e in r.entities():
        if e["type"] != "character" or e.get("persona"):
            continue
        names_of = widened(e["names"], aliases) - USER_NAMES
        for n in names_of:
            known.setdefault(n, e)
        if any(_said(n, said, words) for n in names_of):
            out.setdefault(e["id"], e["name"])
    for name in marked:
        if not is_persona(r, name) and any(_said(n, said, words) for n in widened([name], aliases)):
            e = r.entity("character", name) or known.get(norm(name))
            if e is not None:  # a mark's given name ("이안") is the character it is a variant of ("백이안")
                out.setdefault(e["id"], e["name"])
            else:
                add(name)
    add(PERSONA)
    if excluded:
        out = {k: v for k, v in out.items() if str(k) not in excluded}
    return out


def private(f: dict[str, Any], scene: dict[str, str], r: Resolution | None) -> bool:
    """Whether a fact (or promise) only some of the scene's characters know."""
    if not scene or r is None or f.get("knowledge") != "limited":
        return False
    known = {key(r, n) for n in f.get("known_by") or ()}
    return bool(set(scene) - known)


def narrator_knows(f: dict[str, Any], narrator: str, r: Resolution | None) -> bool:
    """First person (ADR 0035): the narrator knows public and unmarked facts and limited ones that list them."""
    if f.get("knowledge") != "limited":
        return True
    if r is None:
        return norm(narrator) in {norm(n) for n in f.get("known_by") or ()}
    return key(r, narrator) in {key(r, n) for n in f.get("known_by") or ()}


def display(r: Resolution, name: str) -> str:
    """A character's name as the story spells it: the persona under its host name rather than `{{user}}`."""
    e = r.entity("character", PERSONA if is_persona(r, name) else name)
    return e["name"] if e else name


def missing(f: dict[str, Any], scene: dict[str, str], r: Resolution) -> tuple[list[str], list[str]]:
    """(holders, characters in the scene not shown to know it), display names, for a withheld line."""
    known = {key(r, n) for n in f.get("known_by") or ()}
    holders = list(dict.fromkeys(scene.get(key(r, n)) or display(r, n) for n in f.get("known_by") or ()))
    return holders, [name for k, name in scene.items() if k not in known]
