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
)}


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
