"""Closed predicate registry (D6). Anything outside it becomes a `pending` assertion."""

from __future__ import annotations

import ast
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from .entities import node

ENTITY_TYPES = ("character", "place", "item", "group", "concept")


@dataclass(frozen=True)
class Predicate:
    name: str
    subject_types: tuple[str, ...]
    object_types: tuple[str, ...] | None  # None: no object entity
    needs_value: bool
    cardinality: str  # "single": newer supersedes older per (subject[, object]); "multi": accumulates
    description: str
    per_object: bool = False  # single-valued per (subject, object) instead of per subject


REGISTRY: dict[str, Predicate] = {p.name: p for p in (
    Predicate("located_in", ("character", "item", "group"), ("place",), False, "single",
              "where the subject currently is"),
    Predicate("has_status", ("character",), None, True, "single",
              "current physical/mental condition (injured, asleep, disguised…)"),
    Predicate("identity", ("character",), None, True, "single",
              "role, occupation, title or true identity"),
    Predicate("has_trait", ("character",), None, True, "multi", "lasting trait, habit, appearance"),
    Predicate("relationship", ("character",), ("character",), True, "single",
              "personal relationship of subject to object: kin, romance, rivalry, friendship (sibling, rival, lovers…);"
              " a role such as tenant or employer is role_toward", per_object=True),
    Predicate("role_toward", ("character",), ("character",), True, "single",
              "the subject's role toward the object: tenant of, landlord of, employer of, works for, teacher of,"
              " student of, master of, servant of, guardian of, ward of… (value: the subject's side, e.g. tenant:"
              " rents a room in the object's house)", per_object=True),
    Predicate("feels_toward", ("character",), ("character",), True, "single",
              "subject's current feeling toward object", per_object=True),
    Predicate("addresses", ("character",), ("character",), True, "single",
              "how the subject now speaks to and calls the object, as the story settles it: speech level and form"
              " of address (value e.g. informal speech, calls them 'Takumi')", per_object=True),
    Predicate("possesses", ("character", "group"), ("item",), False, "multi", "subject owns/carries object"),
    Predicate("member_of", ("character",), ("group",), False, "multi", "subject belongs to group"),
    Predicate("knows", ("character",), None, True, "multi", "a fact/secret the subject knows"),
    Predicate("goal", ("character", "group"), None, True, "multi",
              "an aim, plan or task the subject is set on, lasting beyond the moment (not a passing wish)"),
    Predicate("question", ("character", "group"), None, True, "multi",
              "something the subject wants to know that the story leaves unanswered, or a mystery"),
    Predicate("threat", ("character", "group", "place"), None, True, "multi",
              "a danger that now hangs over the subject and has not played out (value: what threatens)"),
    Predicate("owes", ("character", "group"), ("character", "group"), True, "multi",
              "a debt, favor or return the subject owes the object (value: what)"),
    Predicate("promised", ("character",), ("character",), True, "multi", "a promise subject made to object"),
    Predicate("event", ENTITY_TYPES, None, True, "multi", "a notable event involving the subject"),
    Predicate("world_fact", ("place", "group", "concept", "item"), None, True, "multi",
              "a durable fact about the setting"),
    Predicate("also_called", ENTITY_TYPES, None, True, "multi",
              "another name for the subject that the TARGET turn itself gives, or the listed description of a"
              " character the TARGET turn names (value: the other name)"),
    Predicate("destroyed", ("item",), None, True, "single",
              "the item no longer exists or can no longer be held or used (value: how, e.g. burned, eaten)"),
    Predicate("fulfilled", ("character", "group"), None, True, "multi",
              "the subject kept a promise listed in OPEN PROMISES (value: its text exactly as listed)"),
    Predicate("learned", ("character",), None, True, "multi",
              "the subject found out a listed secret (value: its text as listed); filled from `secrets`"),
    Predicate("resolved", ("character", "group", "place"), None, True, "multi",
              "the TARGET turn ends a thread listed in OPEN THREADS (subject: its owner as listed; value: its text"
              " exactly as listed; with `outcome`)"),
)}

# Predicates the worker fills from other parts of the model's answer, never asked for directly (PHASE-10:
# `learned` comes from the `secrets` check, ADR 0033). They stay in REGISTRY, so stored rows validate and read.
DERIVED = frozenset({"learned"})


# Read-side supersession that REGISTRY's own fields do not express (ADR 0011). For these predicates an
# item has one current holder: the subject of its latest assertion; earlier holders stay in its
# history. Kept outside REGISTRY on purpose: the extractor generation fingerprints repr(REGISTRY)
# (D20), and this rule changes only how stored assertions are read, never what is extracted, so it
# must not force a re-extraction.
HOLDER_PER_ITEM = frozenset({"possesses"})


def whereabouts(a: dict[str, Any]) -> bool:
    """An item's holder (`possesses`), its place (`located_in` of an item) and its end (`destroyed`) are one
    whereabouts per item (PHASE-6 Q2, Q3): the newer one is current and closes the others; a holder or
    place after the end is disputed (Q4). Read-side only, like HOLDER_PER_ITEM."""
    return (a["predicate"] in HOLDER_PER_ITEM or a["predicate"] == "destroyed"
            or (a["predicate"] == "located_in" and a.get("subject_type") == "item"))


def registry_prompt(only: frozenset[str] | None = None) -> str:
    """The predicates a prompt allows, one per line; `only` narrows them (canon facts, ADR 0047)."""
    lines = []
    for p in REGISTRY.values():
        if p.name in DERIVED or (only is not None and p.name not in only):
            continue
        obj = f", object: {'|'.join(p.object_types)}" if p.object_types else ""
        val = ", value: text" if p.needs_value else ""
        lines.append(f"- {p.name} (subject: {'|'.join(p.subject_types)}{obj}{val}) — {p.description}")
    return "\n".join(lines)


def validate(item: dict[str, Any]) -> tuple[str, str | None]:
    """('valid', None) or ('pending', reason) for one raw assertion."""
    pred = REGISTRY.get(str(item.get("predicate") or ""))
    if pred is None:
        return "pending", "unknown predicate"
    if not str(item.get("subject") or "").strip():
        return "pending", "missing subject"
    if item.get("subject_type") not in pred.subject_types:
        return "pending", f"subject_type must be {pred.subject_types}"
    if pred.object_types is not None:
        if not str(item.get("object") or "").strip():
            return "pending", "missing object"
        if item.get("object_type") not in pred.object_types:
            return "pending", f"object_type must be {pred.object_types}"
    if pred.needs_value and not str(item.get("value") or "").strip():
        return "pending", "missing value"
    return "valid", None


def _casefold(text: str | None) -> str:
    return " ".join(str(text or "").casefold().split())


def fill_types(items: list[Any], hints: list[dict[str, Any]] | None = None) -> list[tuple[Any, str | None]]:
    """Each item with a missing subject/object type filled, and a note, when evidence settles the type.

    Models sometimes leave `object_type` empty on a name they typed elsewhere in the same reply
    (`relationship` to someone who is `character` two lines up); validation would park the fact as
    pending. A name's type counts when the reply or the KNOWN ENTITIES hints give it exactly one entity
    type. A given type is never replaced, and conflicting evidence fills nothing.
    """
    seen: dict[str, set[str]] = {}

    def add(name: Any, entity_type: Any) -> None:
        if entity_type in ENTITY_TYPES and _casefold(name):
            seen.setdefault(_casefold(name), set()).add(entity_type)

    for item in items:
        if isinstance(item, dict):
            add(item.get("subject"), item.get("subject_type"))
            add(item.get("object"), item.get("object_type"))
    for hint in hints or []:
        for name in [hint.get("name"), *hint.get("also", [])]:
            add(name, hint.get("type"))

    out: list[tuple[Any, str | None]] = []
    for item in items:
        if not isinstance(item, dict):
            out.append((item, None))
            continue
        filled, notes = item, []
        for role in ("subject", "object"):
            key = f"{role}_type"
            types = seen.get(_casefold(item.get(role)), set())
            if item.get(key) in (None, "", "null") and len(types) == 1:
                filled = {**filled, key: next(iter(types))}
                notes.append(f"{key} inferred")
        out.append((filled, "; ".join(notes) or None))
    return out


def _worded(c: str) -> bool:
    """A letter or digit of a script written with spaces between words: Hangul or Latin (PHASE-28 Q6: the languages
    `extract-v16`'s rules are written for)."""
    return c.isalnum() and (c.isdigit() or "\uac00" <= c <= "\ud7a3" or "\u1100" <= c <= "\u11ff"
                            or "\u3130" <= c <= "\u318f" or (c.isalpha() and unicodedata.name(c, "").startswith("LATIN")))


def mentioned(name: str, text: str) -> bool:
    """`name` written in `text` as a word of its own: not inside another word (S1: 람이 is not in 하람이, 이안 not in
    백이안). A Hangul or Latin name must start a word; a Latin name must also end one (Ann is not in Anna), while a
    Hangul one may take a particle (하람이, 하람은). A name in another script counts anywhere, as before (NMO-34)."""
    if not name:
        return False
    start = text.find(name)
    while start >= 0:
        end = start + len(name)
        before = text[start - 1] if start else ""
        after = text[end] if end < len(text) else ""
        head_ok = not (_worded(name[0]) and before and _worded(before))
        tail_ok = not (_worded(name[-1]) and not ("\uac00" <= name[-1] <= "\ud7a3") and after and _worded(after)
                       and not ("\uac00" <= after <= "\ud7a3"))
        if head_ok and tail_ok:
            return True
        start = text.find(name, start + 1)
    return False


def alias_evidenced(item: dict[str, Any], turn_text: str, hints: list[dict[str, Any]] | None = None,
                    apart: bool = False) -> bool:
    """An `also_called` assertion links two names only if both occur in the turn it comes from (ADR 0012),
    or if one does and the other is, exactly, a name of the same type that the extraction was shown in
    KNOWN ENTITIES: a turn revealing who a described character is (ADR 0024).

    `apart` (extract-v16, PHASE-28 Q4): when one name is part of the other (윤하나, 하나), the turn must write both: the
    full name, and the part on its own, not only inside the full name (which would otherwise count as both). A full name
    known from earlier turns does not stand in for it: a part alone may be someone else's name.

    Also with `apart` (ADR 0064 item 2, the owner's S1 review of `4e76c70`): a known name the turn does not write stands
    in only for a character the turn is about, so it must be a description of someone unnamed (`?…`, the reveal of
    ADR 0024) or a character the turn writes by another of its known names (윤하람 for a turn that writes 하람). A known
    character the turn never names is not joined to a name in it (S1 turn 81: 백이안, absent, and 곽 조합장)."""
    a, b = _casefold(item.get("subject")), _casefold(item.get("value"))
    if not a or not b or a == b:
        return False
    text = _casefold(turn_text)
    known = [{_casefold(n) for n in [h.get("name"), *h.get("also", [])]} - {""}
             for h in hints or () if h.get("type") == item.get("subject_type")]
    listed = set().union(*known)
    # extract-v16 (PHASE-29): a name counts as written only as a word of its own (`mentioned`); extract-v15 as before
    def written(name: str, where: str = text) -> bool:
        return mentioned(name, where) if apart else name in where

    if apart and (a in b or b in a):
        whole, part = (a, b) if b in a else (b, a)
        return written(whole) and written(part, text.replace(whole, " "))
    if not ((written(a) and (written(b) or b in listed)) or (written(b) and a in listed)):
        return False
    return not apart or all(name.startswith("?") or any(written(other) for names in known if name in names
                                                        for other in names - {name})
                            for name in (a, b) if not written(name))


POLARITIES = ("positive", "negative")
MODALITIES = ("actual", "hypothetical", "dreamed", "unknown")
SOURCES = ("narration", "character_claim")


def semantics(item: dict[str, Any]) -> tuple[str, str, str, str | None, str | None]:
    """(polarity, modality, source, asserted_by, pending reason) for one raw assertion (ADR 0013).

    A missing or unrecognised modality is `unknown`, never `actual`: only actual assertions form facts,
    so a guess would turn plans or dreams into state. A missing source follows the speaker: with
    `asserted_by` it is a character's claim, otherwise narration. A claim needs its speaker.
    """
    polarity = "negative" if str(item.get("polarity") or "").strip().lower() == "negative" else "positive"
    modality = str(item.get("modality") or "").strip().lower()
    if modality not in MODALITIES:
        modality = "unknown"
    speaker = str(item.get("asserted_by") or "").strip()[:60] or None
    source = str(item.get("source") or "").strip().lower()
    if source not in SOURCES:
        source = "character_claim" if speaker else "narration"
    if source == "narration":
        return polarity, modality, source, None, None
    return polarity, modality, source, speaker, None if speaker else "character_claim without asserted_by"


# Predicates whose value can involve other people (PHASE-8 Q3: the measured set). Kept outside REGISTRY
# like HOLDER_PER_ITEM: the extraction prompt states it, and the prompt is part of the generation (D20).
PARTICIPANT_PREDICATES = frozenset({"event", "goal", "knows", "destroyed", "threat"})  # threat: who threatens (v13)
PARTICIPANT_TYPES = ("character", "group")
MAX_PARTICIPANTS = 6


def participants(item: dict[str, Any]) -> list[dict[str, str]] | None:
    """The typed participants of one raw assertion (PHASE-8 Q2), or None.

    `with` is a list of {"name", "type"} objects, type `character` or `group`. Kept only on the
    participant predicates; an entry without a name of at most 60 characters or with another type is
    dropped, and so is the subject, the object and a repeat of the same (type, normalized name). At most
    MAX_PARTICIPANTS remain. Nothing here is inferred from the value text.
    """
    raw = item.get("with")
    if item.get("predicate") not in PARTICIPANT_PREDICATES or not isinstance(raw, list):
        return None
    taken = {node(item.get("subject_type"), item.get("subject"))}
    if item.get("object"):
        taken.add(node(item.get("object_type"), item.get("object")))
    out: list[dict[str, str]] = []
    for entry in raw:
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
            continue
        name, kind = entry["name"].strip(), entry.get("type")
        if not name or len(name) > 60 or kind not in PARTICIPANT_TYPES or node(kind, name) in taken:
            continue
        taken.add(node(kind, name))
        out.append({"name": name, "type": kind})
        if len(out) == MAX_PARTICIPANTS:
            break
    return out or None


# extract-v13 (PHASE-11, ADR 0039): how a `resolved` ends its thread, and on which predicates a stated cause is kept.
OUTCOMES = ("achieved", "abandoned", "failed", "answered", "averted", "paid")
CAUSED = frozenset({"event", "feels_toward", "relationship", "has_status", "goal"})


def outcome(item: dict[str, Any]) -> str | None:
    """The outcome of a `resolved` (one of OUTCOMES); None for anything else, or when missing or invalid."""
    if item.get("predicate") != "resolved":
        return None
    value = str(item.get("outcome") or "").strip().lower()
    return value if value in OUTCOMES else None


def because(item: dict[str, Any]) -> str | None:
    """The cause the model quoted, on CAUSED predicates only, at most 200 characters; never inferred here."""
    if item.get("predicate") not in CAUSED:
        return None
    value = str(item.get("because") or "").strip()
    return value[:200] if value and value.casefold() not in ("null", "none", "-") else None


SALIENCES = ("major", "minor")


def salience(item: dict[str, Any]) -> str | None:
    """`major` / `minor` for an `event` (PHASE-7 Q4, ADR 0020); None for anything else, or when missing or
    invalid. Unlabeled events rank as before."""
    if item.get("predicate") != "event":
        return None
    value = str(item.get("salience") or "").strip().lower()
    return value if value in SALIENCES else None


KNOWLEDGE_SCOPES = ("public", "limited", "unknown")


def knowledge(item: dict[str, Any]) -> tuple[str, list[str] | None, list[str] | None, str | None]:
    """(scope, known_by, hidden_from, note) for one raw assertion (D19).

    Unknown is a real state and is never turned into "does not know". A name in both lists is
    contradictory evidence: it is dropped from both (that character's awareness is unknown) and noted.
    """
    def names(key: str) -> list[str]:
        value = item.get(key)
        if not isinstance(value, list):
            return []
        out: list[str] = []
        for v in value:
            name = mark_name(v)
            if name and name.casefold() not in {o.casefold() for o in out}:
                out.append(name)
        return out[:12]

    known, hidden = names("known_by"), names("hidden_from")
    both = {n.casefold() for n in known} & {n.casefold() for n in hidden}
    note = None
    if both:
        note = "contradictory knowledge for: " + ", ".join(n for n in known if n.casefold() in both)
        known = [n for n in known if n.casefold() not in both]
        hidden = [n for n in hidden if n.casefold() not in both]
    scope = str(item.get("knowledge") or "").strip().lower()
    if hidden:
        scope = "limited"  # "public except X" is limited
    elif scope == "public":
        known = []  # everyone knows; a list adds nothing
    elif known:
        scope = "limited"
    else:
        scope = "unknown"  # includes "limited" with nobody named
    return scope, known or None, hidden or None, note


# How a {"name": …} entry was stored before mark_name() read the name out of it: str() of the dict, e.g.
# "{'name': '타쿠미', 'type': 'character'}". The placeholder "{{user}}" does not match.
_NAME_REPR = re.compile(r"""\{(?:'[a-z_]+': (?:'[^']*'|"[^"]*"), )*'name': ('(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*")""")


def mark_name(entry: Any) -> str:
    """One known_by / hidden_from entry as a name of at most 60 characters ("" when there is none).

    The model sometimes lists {"name", "type"} objects, the shape of participants (PHASE-8): only the name is
    kept. So is the name inside such an object's stored repr (see stored_knowledge).
    """
    if isinstance(entry, dict):
        name = entry.get("name")
        return name.strip()[:60] if isinstance(name, str) else ""
    text = str(entry or "").strip()
    m = _NAME_REPR.match(text)
    if m:
        text = str(ast.literal_eval(m.group(1))).strip()
    return text[:60]


def stored_knowledge(row: dict[str, Any]) -> None:
    """Correct, in place, the knowledge marks of a stored assertion that kept {"name", …} objects as their
    repr: the marks are read again through knowledge(), as validation now reads them. The stored row stays
    as written. Rows without such an entry are left untouched."""
    if any(isinstance(n, str) and _NAME_REPR.match(n)
           for key in ("known_by", "hidden_from") for n in row.get(key) or ()):
        row["knowledge"], row["known_by"], row["hidden_from"], _ = knowledge(row)
