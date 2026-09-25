"""Closed predicate registry (D6). Anything outside it becomes a `pending` assertion."""

from __future__ import annotations

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
    epistemic: str  # "world" | "belief"
    description: str
    per_object: bool = False  # single-valued per (subject, object) instead of per subject


REGISTRY: dict[str, Predicate] = {p.name: p for p in (
    Predicate("located_in", ("character", "item", "group"), ("place",), False, "single", "world",
              "where the subject currently is"),
    Predicate("has_status", ("character",), None, True, "single", "world",
              "current physical/mental condition (injured, asleep, disguised…)"),
    Predicate("identity", ("character",), None, True, "single", "world",
              "role, occupation, title or true identity"),
    Predicate("has_trait", ("character",), None, True, "multi", "world", "lasting trait, habit, appearance"),
    Predicate("relationship", ("character",), ("character",), True, "single", "world",
              "relationship of subject to object (sibling, rival, lovers…)", per_object=True),
    Predicate("feels_toward", ("character",), ("character",), True, "single", "belief",
              "subject's current feeling toward object", per_object=True),
    Predicate("possesses", ("character", "group"), ("item",), False, "multi", "world", "subject owns/carries object"),
    Predicate("member_of", ("character",), ("group",), False, "multi", "world", "subject belongs to group"),
    Predicate("knows", ("character",), None, True, "multi", "belief", "a fact/secret the subject knows"),
    Predicate("goal", ("character", "group"), None, True, "multi", "belief", "what the subject wants or plans"),
    Predicate("promised", ("character",), ("character",), True, "multi", "world", "a promise subject made to object"),
    Predicate("event", ENTITY_TYPES, None, True, "multi", "world", "a notable event involving the subject"),
    Predicate("world_fact", ("place", "group", "concept", "item"), None, True, "multi", "world",
              "a durable fact about the setting"),
    Predicate("also_called", ENTITY_TYPES, None, True, "multi", "world",
              "another name for the subject that the TARGET turn itself gives, or the listed description of a"
              " character the TARGET turn names (value: the other name)"),
    Predicate("destroyed", ("item",), None, True, "single", "world",
              "the item no longer exists or can no longer be held or used (value: how, e.g. burned, eaten)"),
    Predicate("fulfilled", ("character", "group"), None, True, "multi", "world",
              "the subject kept a promise listed in OPEN PROMISES (value: its text exactly as listed)"),
)}


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


def registry_prompt() -> str:
    lines = []
    for p in REGISTRY.values():
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


def alias_evidenced(item: dict[str, Any], turn_text: str, hints: list[dict[str, Any]] | None = None) -> bool:
    """An `also_called` assertion links two names only if both occur in the turn it comes from (ADR 0012),
    or if one does and the other is, exactly, a name of the same type that the extraction was shown in
    KNOWN ENTITIES: a turn revealing who a described character is (ADR 0024)."""
    a, b = _casefold(item.get("subject")), _casefold(item.get("value"))
    if not a or not b or a == b:
        return False
    text = _casefold(turn_text)
    listed = {_casefold(n) for h in hints or () if h.get("type") == item.get("subject_type")
              for n in [h.get("name"), *h.get("also", [])]}
    return (a in text and (b in text or b in listed)) or (b in text and a in listed)


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
PARTICIPANT_PREDICATES = frozenset({"event", "goal", "knows", "destroyed"})
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
            name = str(v or "").strip()[:60]
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
