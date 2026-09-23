"""Closed predicate registry (D6). Anything outside it becomes a `pending` assertion."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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
              "another name for the subject that the TARGET turn itself gives (value: the other name)"),
)}


# Read-side supersession that REGISTRY's own fields do not express (ADR 0011). For these predicates an
# item has one current holder: the subject of its latest assertion; earlier holders stay in its
# history. Kept outside REGISTRY on purpose: the extractor generation fingerprints repr(REGISTRY)
# (D20), and this rule changes only how stored assertions are read, never what is extracted, so it
# must not force a re-extraction.
HOLDER_PER_ITEM = frozenset({"possesses"})


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


def alias_evidenced(item: dict[str, Any], turn_text: str) -> bool:
    """An `also_called` assertion links two names only if both occur in the turn it comes from (ADR 0012)."""
    names = [_casefold(item.get("subject")), _casefold(item.get("value"))]
    text = _casefold(turn_text)
    return all(names) and names[0] != names[1] and all(n in text for n in names)


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
