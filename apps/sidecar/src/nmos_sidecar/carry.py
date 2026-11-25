"""A chat that carries another chat's memory (PHASE-60 S6, ADR 0085).

A `conversation_carry` link is owner input: archived, kept by rebuilds, deleted with either chat. At link time the
source chat is read once as of its head and a cutoff position, and the carried rows are stored with the link as a
frozen plain-JSON `snapshot` with each row's provenance (ids only, no verbatim message text). Nothing is re-read
from the source later. A source that itself continues an earlier chat is read with what its own link carries (its
frozen snapshot, never the earlier chat again), so a story told over three chats keeps its first chat's memory.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid5

import psycopg
from psycopg.types.json import Jsonb

from . import canonfacts, summaries
from .ids import uuid7
from .entities import PERSONA, Resolution, names_persona, norm
from .facts import fact_text, memory_view
from .threads import relevant_threads

SHAPE = 3
MAX_ROWS = 5000
MAX_NAMES = 8
FIRST_LINES = 8
MODES: tuple[str, ...] = ("continue", "regression")
# Carried rows sort after the target's canon (canonfacts.POSITION_BASE + i) and before turn 0 (positions start at 0).
CARRY_BASE = canonfacts.POSITION_BASE // 2

# The fields a snapshot row keeps. No verbatim message text (`evidence`, an owner correction's note) is stored: a
# row's provenance is the ids in its `from`, and a reader that shows a quote reads it from the source through `from`.
FACT_KEYS: tuple[str, ...] = (
    "predicate", "subject", "subject_type", "object", "object_type", "value",
    "epistemic", "confidence", "knowledge", "known_by", "hidden_from",
    "polarity", "modality", "source", "asserted_by", "salience", "participants",
    "outcome", "because", "feeling", "when_happened", "address_condition", "turn", "position", "compiler",
    "condition", "guise", "item_kind", "knowledge_scope",  # extract-v21's (PHASE-66): only on rows that have them
)
THREAD_KEYS: tuple[str, ...] = (
    "kind", "by", "to", "text", "status", "horizon", "turn", "position",
    "source", "modality", "knowledge", "known_by", "hidden_from", "names",
)


class CarryError(ValueError):
    """A carry request that cannot be carried out now (the API answers 422 with its message)."""


class NoSuchChat(CarryError):
    """A source or target conversation does not exist (the API answers 404)."""


class CarryChanged(CarryError):
    """The source changed between preview and link (the API answers 409 with the fresh preview)."""

    def __init__(self, preview: dict[str, Any], message: str = "the source changed since the preview") -> None:
        super().__init__(message)
        self.preview = preview


class TooManyRows(CarryError):
    """The reading holds more rows than a link may carry (the API answers 422 with `too_many_rows: rows=… max=…`)."""

    def __init__(self, rows: int, max_rows: int) -> None:
        super().__init__(f"the reading holds {rows} rows; a link carries at most {max_rows}")
        self.rows = rows
        self.max = max_rows


@dataclass(frozen=True)
class Keys:
    """Generation keys the reader uses when taking a frozen reading of the source chat."""

    extractor: str | None = None
    summarize: str | None = None
    canon: str | None = None


# --- pure helpers (no database) ---------------------------------------------------------------------------------

def _plain(value: Any) -> Any:
    """Recursively convert values into plain JSON-serializable Python primitives."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_plain(v) for v in value]
    return str(value)


def _positive_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def _non_negative_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


_UNSET: Any = object()


def _is_persona(r: Resolution | None, entity_type: str | None, name: str | None) -> bool:
    """Whether (entity_type, name) names the source chat's persona, including full-name spellings."""
    if not name or r is None or entity_type != "character":
        return False
    return r.is_persona(entity_type, name) or r.node(entity_type, name) == ("character", PERSONA)


def _is_persona_spelling(r: Resolution | None, entity_type: str | None, name: str | None) -> bool:
    """Whether `name` itself spells the source's persona (a host persona name, a full/derived name spelling it, or a
    `USER_NAMES` placeholder), not merely a nickname the story joined to it: an alias entry keeps its nicknames."""
    if not name or r is None:
        return False
    return r.node(entity_type, name) == ("character", PERSONA) or (
        r.is_persona(entity_type, name) and names_persona(entity_type, name, r.persona)
    )


def _map_char_name(name: str, r: Resolution | None) -> str:
    return PERSONA if _is_persona(r, "character", name) else name


def _map_name_list(names: Sequence[str], r: Resolution | None) -> list[str]:
    return list(dict.fromkeys(_map_char_name(str(n), r) for n in names))


def persona_mapped(row: Mapping[str, Any], r: Resolution | None) -> dict[str, Any]:
    """Return a plain-JSON copy of a fact, thread or alias row with every source-persona name mapped to {{user}}."""
    out: dict[str, Any] = _plain(dict(row))
    if r is None:
        return out
    # Fact row fields
    if out.get("subject") and _is_persona(r, out.get("subject_type"), out["subject"]):
        out["subject"] = PERSONA
    if out.get("object") and _is_persona(r, out.get("object_type"), out["object"]):
        out["object"] = PERSONA
    if out.get("participants"):
        out["participants"] = [
            {**p, "name": PERSONA if _is_persona(r, p.get("type"), p.get("name")) else p.get("name")}
            for p in out["participants"]
        ]
    if out.get("asserted_by") and _is_persona(r, "character", out["asserted_by"]):
        out["asserted_by"] = PERSONA
    # Knowledge marks (facts and threads)
    for field in ("known_by", "hidden_from"):
        if field in out and out[field] is not None:
            out[field] = _map_name_list(out[field], r)
    # Thread row fields
    if "predicate" not in out:
        if out.get("by") and _is_persona(r, "character", out["by"]):
            out["by"] = PERSONA
        if out.get("to") and _is_persona(r, "character", out["to"]):
            out["to"] = PERSONA
        if "names" in out and out["names"] is not None:
            out["names"] = _map_name_list(out["names"], r)
    # Alias row fields: a side is the marker only when its own spelling is the persona's (`_is_persona_spelling`); a
    # nickname the story joined to the persona stays as written, so the target joins it to its own persona.
    if "alias" in out:
        for field in ("name", "alias"):
            if _is_persona_spelling(r, out.get("entity_type"), out.get(field)):
                out[field] = PERSONA
    return out


def _char_entity_id(r: Resolution, name: str | None) -> str | None:
    if not name:
        return None
    ent = r.entity("character", name)
    return str(ent["id"]) if ent is not None else None


def _involved_ids(row: Mapping[str, Any], r: Resolution, *, is_thread: bool) -> set[str]:
    """Source character entity ids involved in a fact (subject/object/participants) or thread (by/to/names)."""
    ids: set[str] = set()
    if is_thread:
        for name in (row.get("by"), row.get("to"), *(row.get("names") or ())):
            if (eid := _char_entity_id(r, name)) is not None:
                ids.add(eid)
        return ids
    if row.get("subject_type") == "character":
        if (eid := _char_entity_id(r, row.get("subject"))) is not None:
            ids.add(eid)
    if row.get("object_type") == "character" and row.get("object"):
        if (eid := _char_entity_id(r, row.get("object"))) is not None:
            ids.add(eid)
    for p in row.get("participants") or ():
        if p.get("type") == "character":
            if (eid := _char_entity_id(r, p.get("name"))) is not None:
                ids.add(eid)
    return ids


def _resolve_named(names: Sequence[str], r: Resolution) -> list[tuple[str, str]]:
    """Resolve character spellings to deduplicated (entity_id, first_spelling) pairs preserving order."""
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for name in names:
        eid = _char_entity_id(r, name)
        if eid is not None and eid not in seen:
            seen.add(eid)
            out.append((eid, name))
    return out


def rememberers(
    row: Mapping[str, Any],
    names: Sequence[str],
    r: Resolution,
    *,
    is_thread: bool | None = None,
) -> list[str]:
    """Named characters (in the order of `names`, as spelled there) who remember `row` under regression's epistemic
    rules, whether or not they are its subject, object, participant, maker or recipient:
      (a) knowledge == 'public': all named (a world fact, an item's whereabouts, another's public event);
      (b) knowledge == 'limited' with non-empty known_by: named in known_by (a third party's secret they were told);
      (c) otherwise (unknown, missing, or limited with empty known_by): only named involved in the row;
    always minus any named in hidden_from. The persona is a named character like any other.
    """
    thread_row = ("by" in row and "predicate" not in row) if is_thread is None else is_thread
    named = _resolve_named(names, r)
    if not named:
        return []
    named_ids = {eid for eid, _ in named}
    involved = _involved_ids(row, r, is_thread=thread_row)

    raw_known = row.get("known_by") or ()
    known_ids = {eid for n in raw_known if (eid := _char_entity_id(r, n)) is not None}
    hidden_ids = {eid for n in (row.get("hidden_from") or ()) if (eid := _char_entity_id(r, n)) is not None}

    knowledge = row.get("knowledge")
    if knowledge == "public":
        base_ids = named_ids
    elif knowledge == "limited" and len(raw_known) > 0:
        base_ids = named_ids & known_ids
    else:
        base_ids = named_ids & involved

    kept_ids = base_ids - hidden_ids
    return [spelling for eid, spelling in named if eid in kept_ids]


def _memory_excluded_ids(view: Mapping[str, Any]) -> set[str]:
    excluded = view.get("excluded") or {}
    out = {str(eid) for eid, info in excluded.items() if (info or {}).get("scope") == "memory"}
    for ent in view.get("entities") or ():
        if ent.get("excluded") == "memory":
            out.add(str(ent["id"]))
    return out


def _character_entities(view: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """The source's characters a regression may name, most mentioned first: the persona among them (the protagonist
    may be the one who goes back), the ones the owner left out of memory not."""
    r: Resolution | None = view.get("resolution")
    ents = view.get("entities") if view.get("entities") is not None else (r.entities() if r is not None else [])
    gone = _memory_excluded_ids(view)
    ordered = sorted(ents, key=lambda e: -int(e.get("mentions") or 0))
    return [e for e in ordered if e.get("type") == "character" and str(e["id"]) not in gone]


def _characters(view: Mapping[str, Any]) -> list[str]:
    """Each character's display spelling (a name `_validate_mode_and_names` takes as it is)."""
    return [str(e["name"]) for e in _character_entities(view)]


def _persona_character(view: Mapping[str, Any]) -> str | None:
    """Which of `_characters` is the source's persona (its display spelling), or None: the panel marks it."""
    return next((str(e["name"]) for e in _character_entities(view) if e.get("persona")), None)


def _validate_mode_and_names(
    mode: str,
    names: Sequence[str] | None,
    r: Resolution | None,
    mem_excluded: set[str],
) -> list[str]:
    if mode not in MODES:
        raise CarryError(f"mode must be one of: {', '.join(MODES)}")
    raw = [str(n).strip() for n in (names or ())]
    if mode == "continue":
        if raw:
            raise CarryError("continue mode takes no character names")
        return []
    if not raw or len(raw) > MAX_NAMES:
        raise CarryError(f"regression mode needs 1 to {MAX_NAMES} character names")
    seen: set[str] = set()
    kept: list[str] = []
    for name in raw:
        # The persona is a character of the source too ({{user}} or any spelling of it): its regression is allowed.
        ent = r.entity("character", name) if (name and r is not None) else None
        if ent is None or str(ent["id"]) in mem_excluded:
            raise CarryError(f"{name} is no character of the source")
        eid = str(ent["id"])
        if eid not in seen:
            seen.add(eid)
            kept.append(name)
    return kept


def _provenance(
    source_id: UUID | str,
    row: Mapping[str, Any],
    revisions: Mapping[int, UUID | str],
    *,
    generation: str | None = None,
    turn: Any = _UNSET,
) -> dict[str, Any]:
    aid = _positive_int(row.get("id"))
    rev = revisions.get(aid) if aid is not None else None
    repair = row.get("repair")
    gen = generation if generation is not None else row.get("generation")
    raw_turn = row.get("turn") if turn is _UNSET else turn
    src_turn = _non_negative_int(raw_turn) if aid is not None else None
    return {
        "conversation": str(source_id),
        "assertion": aid,
        "revision": str(rev) if rev is not None else None,
        "generation": str(gen) if gen is not None else None,
        "repair": str(repair) if repair is not None else None,
        "turn": src_turn,
    }


def _from(source_id: UUID | str, row: Mapping[str, Any], revisions: Mapping[int, UUID | str], **kw: Any) -> dict[str, Any]:
    """A snapshot row's provenance: a row the source itself carries from an earlier chat keeps that chat's (its
    `carried_from`), so a row read through two links still names the chat and assertion it was first said in."""
    carried_from = row.get("carried_from")
    if row.get("carried") and isinstance(carried_from, Mapping):
        return _plain(dict(carried_from))
    return _provenance(source_id, row, revisions, **kw)


def _apply_regression_marks(mapped: dict[str, Any], rems: list[str]) -> dict[str, Any]:
    mapped["orig_knowledge"] = mapped.get("knowledge")
    mapped["orig_known_by"] = mapped.get("known_by")
    mapped["knowledge"] = "limited"
    mapped["known_by"] = rems
    return mapped


def served_generations(snapshot: Mapping[str, Any]) -> list[str]:
    """Sorted distinct generation keys that served the stored rows in `snapshot`."""
    gens: set[str] = set()
    for bucket in ("facts", "aliases", "threads"):
        for row in snapshot.get(bucket) or ():
            gen = (row.get("from") or {}).get("generation")
            if gen:
                gens.add(str(gen))
    story = snapshot.get("story")
    if isinstance(story, Mapping):
        gen = (story.get("from") or {}).get("generation")
        if gen:
            gens.add(str(gen))
    return sorted(gens)


def snapshot_of(
    view: Mapping[str, Any],
    story_info: Mapping[str, Any] | None,
    mode: str,
    names: Sequence[str] | None,
    source_id: UUID | str,
    revisions: Mapping[int, UUID | str] | None = None,
) -> dict[str, Any]:
    """Build the frozen plain-JSON `snapshot` from a source memory view and optional summary info.

    Rows the source itself carries from an earlier chat (`carried`, a source read with its own `continue` link) are
    taken like its own, each keeping its first chat's provenance (`_from`). Regression rememberers and `names` store
    the source's persona as the marker {{user}}: the source's persona is the target's (S6)."""
    r: Resolution | None = view.get("resolution")
    mem_excluded = _memory_excluded_ids(view)
    resolved_names = _validate_mode_and_names(mode, names, r, mem_excluded)
    rev_map: Mapping[int, UUID | str] = revisions or {}

    # Facts: newest first (source position descending), canon rows left out.
    source_facts = sorted(
        (f for f in (view.get("facts") or ()) if not f.get("canon")),
        key=lambda f: f.get("position") or 0,
        reverse=True,
    )
    fact_rows: list[dict[str, Any]] = []
    for row in source_facts:
        if mode == "regression":
            assert r is not None
            rems = rememberers(row, resolved_names, r, is_thread=False)
            if not rems:
                continue
        else:
            rems = []
        trimmed = {k: row[k] for k in FACT_KEYS if k in row}
        mapped = persona_mapped(trimmed, r)
        if mode == "regression":
            _apply_regression_marks(mapped, _map_name_list(rems, r))
        mapped["from"] = _from(source_id, row, rev_map)
        fact_rows.append(mapped)

    alias_rows = _alias_entries(r, mode, resolved_names, source_id, rev_map)

    # Threads: open only for continue; any status (filtered by rememberers) for regression.
    assertions_by_id: dict[Any, Mapping[str, Any]] = {
        a["id"]: a for a in (view.get("assertions") or ()) if "id" in a
    }
    thread_rows: list[dict[str, Any]] = []
    for t in view.get("threads") or ():
        if mode == "continue" and t.get("status") != "open":
            continue
        if mode == "regression":
            assert r is not None
            rems = _map_name_list(rememberers(t, resolved_names, r, is_thread=True), r)
            if not rems:
                continue
        else:
            rems = []
        trimmed = {k: t[k] for k in THREAD_KEYS if k in t}
        mapped = persona_mapped(trimmed, r)
        closed_by = t.get("closed_by")
        mapped["closed_turn"] = closed_by.get("turn") if (t.get("status") != "open" and isinstance(closed_by, Mapping)) else None
        opening = assertions_by_id.get(t.get("id"))
        # The opening assertion, kept like a fact row (its provenance is the thread's `from`), so a reader can fold
        # the thread again from it as `threads.fold` opens one.
        opening_row: dict[str, Any] | None = (
            persona_mapped({k: opening[k] for k in FACT_KEYS if k in opening}, r) if opening is not None else None
        )
        if mode == "regression":
            _apply_regression_marks(mapped, rems)
            if opening_row is not None:
                _apply_regression_marks(opening_row, list(rems))
        mapped["opening"] = opening_row
        gen = opening.get("generation") if opening is not None else t.get("generation")
        src_turn = opening.get("turn") if opening is not None else t.get("turn")
        mapped["from"] = _from(source_id, t, rev_map, generation=gen, turn=src_turn)
        thread_rows.append(mapped)

    # Story (continue only): held if it repeats or omits a kept secret.
    story_row: dict[str, Any] | None = None
    story_left_out: str | None = None
    if mode == "continue" and story_info:
        s = story_info.get("story")
        if isinstance(s, Mapping) and s.get("text"):
            if story_info.get("story_held"):
                story_left_out = "secret"
            else:
                story_row = _plain({
                    "text": s["text"],
                    "first_turn": s.get("first_turn"),
                    "last_turn": s.get("last_turn"),
                    "from": {
                        "conversation": str(source_id),
                        "summary": str(s["id"]),
                        "generation": s.get("generation"),
                        "turn": None,
                    },
                })

    return _plain({
        "shape": SHAPE,
        "mode": mode,
        "names": _map_name_list(resolved_names, r),
        "facts": fact_rows,
        "aliases": alias_rows,
        "threads": thread_rows,
        "story": story_row,
        "story_left_out": story_left_out,
        "characters": _characters(view),
        "persona_character": _persona_character(view),
    })


def _alias_entries(
    r: Resolution | None,
    mode: str,
    named: Sequence[str],
    source_id: UUID | str,
    revisions: Mapping[int, UUID | str],
) -> list[dict[str, Any]]:
    """The source's names for one entity, as alias entries: its story's `also_called` rows (its own, and those it
    carries from an earlier chat) and the owner's joins (`entity_link`, provenance `link`), so names joined in the
    source stay one entity in the target. Canon aliases left out (the target reads its own canon). `continue`: every
    entity's; `regression`: only the named characters' (their other spellings of the previous timeline). An entry
    whose two sides spell the same name after the persona mapping says nothing and is left out."""
    if r is None:
        return []
    keep: set[str] | None = None
    if mode == "regression":
        keep = {eid for eid, _ in _resolve_named(named, r)}
    out: list[dict[str, Any]] = []
    seen: set[tuple[Any, str, str]] = set()

    def add(entry: dict[str, Any], provenance: dict[str, Any]) -> None:
        if keep is not None and _resolved_id(r, entry.get("entity_type"), entry.get("name")) not in keep:
            return
        mapped = persona_mapped(entry, r)
        key = (mapped.get("entity_type"), norm(mapped.get("name")), norm(mapped.get("alias")))
        if not key[1] or not key[2] or key[1] == key[2] or key in seen:
            return
        seen.add(key)
        mapped["from"] = provenance
        out.append(mapped)

    for _, _, row in r.alias_rows:
        if row.get("canon") or (_positive_int(row.get("id")) is None and not row.get("carried")):
            continue
        add({
            "entity_type": row.get("subject_type"),
            "name": row.get("subject"),
            "alias": row.get("value"),
            "turn": row.get("turn") if not row.get("carried") else None,
            "compiler": row.get("compiler"),  # a part edge holds in the target too (entities.PART_EDGES)
        }, _from(source_id, row, revisions))
    for _, _, link in r.links:
        add({"entity_type": link.get("entity_type"), "name": link.get("name"), "alias": link.get("same_as"),
             "turn": None, "compiler": None},
            {"conversation": str(source_id), "assertion": None, "revision": None, "generation": None,
             "repair": None, "turn": None, "link": str(link["id"])})
    return out


def fingerprint(reading: Mapping[str, Any]) -> str:
    """Stable sha256 hex digest of everything a carry link would store (no link id or timestamp)."""
    cutoff = reading["cutoff"]
    payload = _plain({
        "source": str(reading["source"]),
        "mode": reading["mode"],
        "names": list(reading["names"]),
        "cutoff": {
            "commit": str(cutoff["commit"]),
            "position": cutoff["position"],
            "turn": cutoff["turn"],
        },
        "generations": reading["generations"],
        "snapshot": reading["snapshot"],
    })
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def preview_of(
    reading: Mapping[str, Any],
    labels: Mapping[str, Any],
    replaces: UUID | str | None = None,
    persona: str | None = None,
) -> dict[str, Any]:
    """Summarize a frozen reading for the owner before linking. With `persona` (the target's host persona name), the
    lines shown spell the stored persona marker as the target will read it (`Carried.for_persona`); the reading and
    its fingerprint are untouched."""
    snap = reading["snapshot"]
    shown = [_persona_named(f, persona) if persona and persona != PERSONA else f for f in snap["facts"][:FIRST_LINES]]
    lines: list[str] = [fact_text(f) for f in shown]
    if len(lines) < FIRST_LINES:
        for t in snap["threads"]:
            if len(lines) >= FIRST_LINES:
                break
            text = t.get("text")
            if text:
                lines.append(str(text))
    return _plain({
        "mode": reading["mode"],
        "source": {
            "id": str(reading["source"]),
            "character": labels.get("character"),
            "chat": labels.get("chat"),
        },
        "cutoff": reading["cutoff"],
        "counts": {
            "facts": len(snap["facts"]),
            "aliases": len(snap["aliases"]),
            "threads": len(snap["threads"]),
            "story": snap["story"] is not None,
        },
        "first_lines": lines,
        "characters": list(snap["characters"]),
        "persona_character": snap.get("persona_character"),
        "fingerprint": reading["fingerprint"],
        "replaces": str(replaces) if replaces is not None else None,
    })


@dataclass(frozen=True)
class Carried:
    """What a target chat's read takes from its link in force (`target_rows`). Pure data, never changed by a read."""

    link: str  # the link id
    source: str  # the source conversation id
    mode: str  # "continue" | "regression"
    names: tuple[str, ...]
    rows: tuple[dict[str, Any], ...]  # continue: assertion-like rows for the fold and the target's Resolution
    regression: tuple[dict[str, Any], ...]  # regression: the stored rows, each with "line": "fact" | "thread"
    story: dict[str, Any] | None  # continue: the snapshot's story, else None

    def for_persona(self, name: str | None) -> Carried:
        """These rows as a target whose persona the host names `name` (`conversation.host_persona_name`) reads them:
        the stored marker {{user}} in a character name field (and in a regression's `names`, a persona who regresses)
        is spelled `name`, so a carried line names the target's persona as the host does (S6: the source's persona is
        the target's persona). The target's resolution reads `name` as its persona (ADR 0023), so every row keeps its
        entity; without a name the rows are as stored. Pure: the link's rows and its stored snapshot are left
        unchanged."""
        if not name or name == PERSONA:
            return self
        return replace(self, names=tuple(dict.fromkeys(name if n == PERSONA else n for n in self.names)),
                       rows=tuple(_persona_named(x, name) for x in self.rows),
                       regression=tuple(_persona_named(x, name) for x in self.regression))


def _persona_named(row: Mapping[str, Any], name: str) -> dict[str, Any]:
    """A copy of a carried row with the persona marker in each character name field (those `persona_mapped` writes,
    and a regression thread's opening) spelled `name`; a non-character name and every free text stay as stored."""
    def char(value: Any) -> Any:
        return name if value == PERSONA else value

    def names(values: Any) -> Any:
        return list(dict.fromkeys(char(v) for v in values)) if isinstance(values, (list, tuple)) else values

    out = dict(row)
    for field, kind in (("subject", "subject_type"), ("object", "object_type")):
        if out.get(kind) == "character":
            out[field] = char(out.get(field))
    if out.get("participants"):
        out["participants"] = type(out["participants"])(
            {**p, "name": char(p.get("name"))} if p.get("type") == "character" else p for p in out["participants"])
    for field in ("asserted_by", "by", "to"):
        if field in out:
            out[field] = char(out[field])
    for field in ("known_by", "hidden_from", "names"):
        if out.get(field) is not None:
            out[field] = names(out[field])
    if isinstance(out.get("opening"), Mapping):
        out["opening"] = _persona_named(out["opening"], name)
    return out


def _carried_id(link_id: str, kind: str, index: int) -> int:
    """A stable negative row id, unique per (link, kind, index): never an assertion's (those are positive)."""
    return -(uuid5(UUID(link_id), f"{kind}:{index}").int % 2**62) - 1


def _carried_row(stored: Mapping[str, Any], link_id: str, kind: str, index: int, position: int,
                 provenance: Any) -> dict[str, Any]:
    """A new assertion-like row from a stored snapshot row: before turn 0 at `position`, flagged `carried`."""
    row = {k: _plain(v) for k, v in stored.items() if k not in ("from", "opening")}
    participants = row.get("participants")
    row.update(
        id=_carried_id(link_id, kind, index), position=position, turn=-1,
        turn_hash=f"carried:{link_id}", host_logical_id=f"carried:{link_id}", listed_hash=None,
        generation=(provenance or {}).get("generation"), compiler=stored.get("compiler"), evidence="",
        participants=tuple(dict(p) for p in participants) if participants else None,
        known_by=list(row["known_by"]) if row.get("known_by") else None,
        hidden_from=list(row["hidden_from"]) if row.get("hidden_from") else None,
        modality=row.get("modality") or "actual", source=row.get("source") or "narration",
        carried=link_id, carried_from=_plain(provenance),
    )
    for field in ("subject", "subject_type", "object", "object_type", "value", "polarity"):
        row.setdefault(field, None)
    return row


def target_rows(link: Mapping[str, Any]) -> Carried:
    """What a target's read carries from `link`, a link row with its `snapshot` (as `in_force` or `by_id` return it).

    `continue`: the snapshot's facts oldest first, then each open thread's opening, then the aliases as `also_called`
    rows, each a new row before turn 0 (position CARRY_BASE + i, turn -1) with a negative id and `carried` set to the
    link id. `regression`: no rows; copies of the stored facts and threads, kept apart, each with a stable negative id
    and the link's `host_logical_id`. Pure."""
    link_id, source = str(link["id"]), str(link["source_conversation_id"])
    snap: Mapping[str, Any] = link.get("snapshot") or {}
    mode = str(link.get("mode") or snap.get("mode"))
    names = tuple(str(n) for n in (snap.get("names") or link.get("entity_names") or ()))
    if mode == "regression":
        kept = [{**_plain(dict(f)), "line": "fact"} for f in snap.get("facts") or ()]
        kept += [{**_plain(dict(t)), "line": "thread"} for t in snap.get("threads") or ()]
        for i, row in enumerate(kept):
            row["carried"], row["carried_from"] = link_id, row.get("from")
            # A line's identity (its ledger ref, a memory mode's lookup), never an assertion's or a continue row's.
            row["id"] = _carried_id(link_id, f"regression:{row['line']}", i)
            row["host_logical_id"] = f"carried:{link_id}"
        return Carried(link_id, source, mode, names, (), tuple(kept), None)
    rows: list[dict[str, Any]] = []
    for i, f in enumerate(reversed(list(snap.get("facts") or ()))):  # stored newest first
        rows.append(_carried_row(f, link_id, "fact", i, CARRY_BASE + len(rows), f.get("from")))
    for i, t in enumerate(snap.get("threads") or ()):
        if t.get("opening"):
            rows.append(_carried_row(t["opening"], link_id, "thread", i, CARRY_BASE + len(rows), t.get("from")))
    for i, a in enumerate(snap.get("aliases") or ()):
        alias = {"subject": a.get("name"), "subject_type": a.get("entity_type"), "value": a.get("alias"),
                 "predicate": "also_called", "modality": "actual", "source": "narration", "polarity": "positive",
                 "object": None, "object_type": None, "compiler": a.get("compiler")}
        rows.append(_carried_row(alias, link_id, "alias", i, CARRY_BASE + len(rows), a.get("from")))
    story = snap.get("story")
    return Carried(link_id, source, mode, names, tuple(rows), (), _plain(dict(story)) if story else None)


def _resolved_id(r: Resolution | None, entity_type: str | None, name: str | None) -> str | None:
    ent = r.entity(entity_type, name) if (r is not None and name) else None
    return str(ent["id"]) if ent is not None else None


def _line_entities(row: Mapping[str, Any], r: Resolution | None, *, thread: bool) -> set[str]:
    """The entity ids a carried line is about, through the target's resolution: a fact's subject, object and
    participants; a thread's maker and recipient."""
    if thread:
        found = (_resolved_id(r, "character", row.get("by")), _resolved_id(r, "character", row.get("to")))
        return {eid for eid in found if eid is not None}
    ids = {str(e["id"]) for e in (row.get("subject_entity"), row.get("object_entity"))
           if isinstance(e, Mapping) and e.get("id") is not None}
    for p in row.get("participants") or ():
        if (eid := _resolved_id(r, p.get("type"), p.get("name"))) is not None:
            ids.add(eid)
    return ids


def _panel_line(row: Mapping[str, Any], opening: Mapping[str, Any] | None, *, thread: bool) -> dict[str, Any]:
    """A plain copy of a carried row with the keys a panel line reads: a thread names its opening's predicate (else
    its kind), its maker and recipient as subject and object, and its text as value."""
    line: dict[str, Any] = _plain(dict(row))
    when = row.get("when_happened") or ((opening or {}).get("when_happened") if thread else None)
    if thread:
        line.update(kind="thread", predicate=(opening or {}).get("predicate") or row.get("kind"),
                    subject=row.get("by"), object=row.get("to"), value=row.get("text"))
    else:
        line["kind"] = "fact"
    for key in ("knowledge", "known_by", "hidden_from", "carried", "carried_from"):
        line.setdefault(key, None)
    line.pop("when_happened", None)
    if when:
        line["when_happened"] = _plain(when)
    return line


def regression_threads(
    threads: Sequence[dict[str, Any]],
    query: str,
    previous_ai: str,
    in_context: set[str],
    limit: int,
    persona: frozenset[str] = frozenset(),
    about: bool = False,
    aliases: Mapping[str, frozenset[str]] | None = None,
    named: set[str] | None = None,
) -> list[dict[str, Any]]:
    """A regression link's threads (`view["regression"]` lines with `line == "thread"`) the message brings up, scored as
    `threads.relevant_threads` scores open threads (a mention in the user's message, then in the previous reply; with
    `about`, the promise's words), but whatever their status: in the previous timeline a promise kept, broken or
    dropped is still what its rememberers remember, so a closed one is ranked too. Each thread comes back as given
    (its `status` unchanged), at most `limit`, in that ranking. Pure."""
    shadows = [{**t, "status": "open"} for t in threads]
    by_shadow = {id(s): t for s, t in zip(shadows, threads)}
    picked = relevant_threads(shadows, query, previous_ai, in_context, limit, persona, about=about, aliases=aliases,
                              named=named)
    return [by_shadow[id(s)] for s in picked]


def panel_lines(view: Mapping[str, Any], entity_id: str | None = None) -> list[dict[str, Any]]:
    """The lines a target's panel shows for its link in force, from its memory view (`memory_view` with `carried`).

    `continue`: the view's carried facts, then its carried open threads, in the view's order. `regression`: the
    view's regression rows in order. With `entity_id` (a person's sheet): only the lines about that entity, and for
    `regression` none unless the entity is one of the link's names. Each line is a plain JSON copy; the view is
    left unchanged. Pure."""
    carried = view.get("carried")
    if carried is None:
        return []
    r: Resolution | None = view.get("resolution")
    if carried["mode"] == "regression":
        if entity_id is not None and entity_id not in {
                eid for n in carried.get("names") or () if (eid := _resolved_id(r, "character", n)) is not None}:
            return []
        rows = [(x, x.get("line") == "thread") for x in view.get("regression") or ()]
    else:
        rows = [(f, False) for f in view.get("facts") or () if f.get("carried")]
        rows += [(t, True) for t in view.get("threads") or () if t.get("status") == "open" and t.get("carried")]
    openings = {a["id"]: a for a in view.get("assertions") or () if a.get("carried")}
    out: list[dict[str, Any]] = []
    for row, thread in rows:
        if entity_id is not None and entity_id not in _line_entities(row, r, thread=thread):
            continue
        opening = (row.get("opening") or openings.get(row.get("id"))) if thread else None
        out.append(_panel_line(row, opening, thread=thread))
    return out


# --- database reading -------------------------------------------------------------------------------------------

def _as_uuid(value: UUID | str) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _validate_pair(
    conn: psycopg.Connection,
    target_id: UUID | str,
    source_id: UUID | str,
    *,
    lock: bool = False,
) -> dict[str, Any]:
    tgt, src = _as_uuid(target_id), _as_uuid(source_id)
    if tgt == src:
        raise CarryError("a chat never carries itself")
    sql = (
        "SELECT id, host_character_name, host_chat_name FROM conversation"
        " WHERE id = ANY(%s) ORDER BY id"
        + (" FOR UPDATE" if lock else "")
    )
    found = {r["id"]: r for r in conn.execute(sql, ([tgt, src],)).fetchall()}
    if tgt not in found:
        raise NoSuchChat(f"no conversation {tgt}")
    if src not in found:
        raise NoSuchChat(f"no conversation {src}")
    s = found[src]
    return {"character": s["host_character_name"], "chat": s["host_chat_name"]}


def cutoff_of(
    conn: psycopg.Connection,
    source_id: UUID | str,
    cutoff_turn: int | None = None,
) -> tuple[UUID, int, int | None]:
    """Resolve the source's head commit and cutoff (position, turn), or raise NoSuchChat / CarryError."""
    src = _as_uuid(source_id)
    row = conn.execute("SELECT head_commit_id FROM conversation WHERE id = %s", (src,)).fetchone()
    if row is None:
        raise NoSuchChat(f"no conversation {src}")
    head: UUID | None = row["head_commit_id"]
    if head is None:
        raise CarryError("the source has no messages")
    if cutoff_turn is None:
        last = conn.execute(
            "SELECT position, turn FROM active_membership WHERE commit_id = %s ORDER BY position DESC LIMIT 1",
            (head,),
        ).fetchone()
        if last is None:
            raise CarryError("the source has no messages")
        return head, int(last["position"]), last["turn"]
    found = conn.execute(
        "SELECT max(position) AS position FROM active_membership WHERE commit_id = %s AND turn = %s",
        (head, cutoff_turn),
    ).fetchone()
    if found is None or found["position"] is None:
        raise CarryError(f"turn {cutoff_turn} is not on the source's current head")
    return head, int(found["position"]), cutoff_turn


def _fetch_revisions(conn: psycopg.Connection, view: Mapping[str, Any], mode: str) -> dict[int, UUID]:
    """Fetch source_revision_id for every stored assertion referenced by the reading, in one query."""
    ids: set[int] = set()
    for row in view.get("facts") or ():
        if not row.get("canon") and (aid := _positive_int(row.get("id"))) is not None:
            ids.add(aid)
    r: Resolution | None = view.get("resolution")
    if r is not None:  # regression keeps its named characters' aliases too
        for _, _, row in r.alias_rows:
            if not row.get("canon") and (aid := _positive_int(row.get("id"))) is not None:
                ids.add(aid)
    for t in view.get("threads") or ():
        if mode == "continue" and t.get("status") != "open":
            continue
        if (aid := _positive_int(t.get("id"))) is not None:
            ids.add(aid)
    if not ids:
        return {}
    rows = conn.execute(
        "SELECT id, source_revision_id FROM assertion WHERE id = ANY(%s)",
        (sorted(ids),),
    ).fetchall()
    return {int(r["id"]): r["source_revision_id"] for r in rows}


def take_reading(
    conn: psycopg.Connection,
    source_id: UUID | str,
    mode: str,
    names: Sequence[str] | None,
    keys: Keys,
    cutoff_turn: int | None = None,
    target_id: UUID | str | None = None,
) -> dict[str, Any]:
    """Read the source chat once as of its head and cutoff_turn and return the frozen reading. Writes nothing.

    A source that continues an earlier chat (its own `continue` link in force) is read with that link's frozen rows,
    as its own requests read it, so they come along (Arc 1 -> Arc 2 -> Arc 3) where its story has not replaced them;
    never the earlier chat itself, and never a link whose source is `target_id` (the target's own memory back)."""
    if mode not in MODES:
        raise CarryError(f"mode must be one of: {', '.join(MODES)}")
    raw_names = [str(n).strip() for n in (names or ())]
    if mode == "continue" and raw_names:
        raise CarryError("continue mode takes no character names")
    if mode == "regression" and (not raw_names or len(raw_names) > MAX_NAMES):
        raise CarryError(f"regression mode needs 1 to {MAX_NAMES} character names")

    src = _as_uuid(source_id)
    head, position, turn = cutoff_of(conn, src, cutoff_turn)
    own = in_force(conn, src)
    chained = (target_rows(own) if own is not None and own["mode"] == "continue"
               and (target_id is None or _as_uuid(own["source_conversation_id"]) != _as_uuid(target_id)) else None)
    view = memory_view(conn, head, keys.extractor, upto=position, canon_key=keys.canon, carried=chained)
    revisions = _fetch_revisions(conn, view, mode)
    # A story that repeats an open secret even in other words (LEAK_NEAR) is not frozen into the link: the target
    # reads it in every scene, with whoever the secret is kept from.
    everyone = frozenset(norm(n) for s in view["secrets"] for n in s.get("open") or ())
    story_info = (
        summaries.current(conn, src, head, keys.summarize, view["secrets"], upto=position, present=everyone)
        if mode == "continue" and keys.summarize
        else None
    )
    snap = snapshot_of(view, story_info, mode, raw_names, src, revisions)
    total = len(snap["facts"]) + len(snap["aliases"]) + len(snap["threads"])
    if total > MAX_ROWS:
        raise TooManyRows(total, MAX_ROWS)

    gens = {
        "extractor": keys.extractor,
        "summarize": keys.summarize,
        "canon": keys.canon,
        "served": served_generations(snap),
    }
    reading: dict[str, Any] = {
        "source": str(src),
        "mode": mode,
        "names": snap["names"],
        "cutoff": {"commit": str(head), "position": position, "turn": turn},
        "generations": gens,
        "snapshot": snap,
    }
    reading["fingerprint"] = fingerprint(reading)
    return reading


def preview(
    conn: psycopg.Connection,
    target_id: UUID | str,
    source_id: UUID | str,
    mode: str,
    names: Sequence[str] | None,
    keys: Keys,
    cutoff_turn: int | None = None,
) -> dict[str, Any]:
    """Validate target/source and return a preview of what linking would carry. Writes nothing."""
    tgt, src = _as_uuid(target_id), _as_uuid(source_id)
    labels = _validate_pair(conn, tgt, src, lock=False)
    reading = take_reading(conn, src, mode, names, keys, cutoff_turn=cutoff_turn, target_id=tgt)
    current = conn.execute(
        "SELECT id FROM conversation_carry WHERE target_conversation_id = %s AND removed_at IS NULL",
        (tgt,),
    ).fetchone()
    replaces = current["id"] if current is not None else None
    named = conn.execute("SELECT host_persona_name FROM conversation WHERE id = %s", (tgt,)).fetchone()
    return preview_of(reading, labels, replaces, persona=named["host_persona_name"] if named else None)


# --- the link store ---------------------------------------------------------------------------------------------
# A link is owner input. A stored link is never changed except for `removed_at`; at most one link per target is in
# force (removed_at IS NULL, the partial unique index). Nothing here reads the source again after the link is made.
# A reading takes the source's own `continue` link's frozen rows (`take_reading`), never the chat that link reads.

LINK_COLUMNS: tuple[str, ...] = (
    "id", "target_conversation_id", "source_conversation_id", "mode", "entity_names",
    "cutoff_commit_id", "cutoff_position", "cutoff_turn", "generations", "created_at", "removed_at",
)


def _columns(snapshot: bool) -> str:
    return ", ".join((*LINK_COLUMNS, "snapshot") if snapshot else LINK_COLUMNS)


def link(
    conn: psycopg.Connection,
    target_id: UUID | str,
    source_id: UUID | str,
    mode: str,
    names: Sequence[str] | None,
    keys: Keys,
    cutoff_turn: int | None = None,
    expect: str | None = None,
) -> dict[str, Any]:
    """Link the target to carry the source's frozen reading, replacing the target's link in force, in one transaction.

    `expect` is the fingerprint of the preview the owner saw; when the source's reading no longer matches it, nothing
    is written and `CarryChanged` carries the fresh preview. Returns {"link": <the new link without its snapshot>,
    "replaced": <the id of the link it replaced, or None>}."""
    tgt, src = _as_uuid(target_id), _as_uuid(source_id)
    with conn.transaction():
        labels = _validate_pair(conn, tgt, src, lock=True)
        reading = take_reading(conn, src, mode, names, keys, cutoff_turn=cutoff_turn, target_id=tgt)
        current = conn.execute(
            "SELECT id FROM conversation_carry WHERE target_conversation_id = %s AND removed_at IS NULL",
            (tgt,),
        ).fetchone()
        replaced: UUID | None = current["id"] if current is not None else None
        if expect is not None and expect != reading["fingerprint"]:
            raise CarryChanged(preview_of(reading, labels, replaced))
        # One instant, read under the locks: `now()` is the transaction's start, before any wait for them, so a link
        # that waited on another would stamp it removed before it was made (review F3). The replaced link's
        # `removed_at` is the new link's `created_at`, the order `as_of` and `history` read.
        at = conn.execute("SELECT clock_timestamp() AS at").fetchone()["at"]
        if replaced is not None:  # before the insert: the partial unique index allows one link in force
            conn.execute("UPDATE conversation_carry SET removed_at = %s WHERE id = %s", (at, replaced))
        cutoff = reading["cutoff"]
        row = conn.execute(
            "INSERT INTO conversation_carry (id, target_conversation_id, source_conversation_id, mode, entity_names,"
            " cutoff_commit_id, cutoff_position, cutoff_turn, generations, snapshot, created_at)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
            f" RETURNING {_columns(False)}",
            (
                uuid7(), tgt, src, reading["mode"], Jsonb(reading["names"]),
                _as_uuid(cutoff["commit"]), cutoff["position"], cutoff["turn"],
                Jsonb(reading["generations"]), Jsonb(reading["snapshot"]), at,
            ),
        ).fetchone()
    return {"link": dict(row), "replaced": replaced}


def unlink(conn: psycopg.Connection, target_id: UUID | str) -> dict[str, Any] | None:
    """Remove the target's link in force (kept for the record with `removed_at`); None when there is none."""
    row = conn.execute(
        "UPDATE conversation_carry SET removed_at = now()"
        " WHERE target_conversation_id = %s AND removed_at IS NULL"
        f" RETURNING {_columns(False)}",
        (_as_uuid(target_id),),
    ).fetchone()
    return dict(row) if row is not None else None


def in_force(conn: psycopg.Connection, target_id: UUID | str, snapshot: bool = True) -> dict[str, Any] | None:
    """The target's link in force now, or None."""
    row = conn.execute(
        f"SELECT {_columns(snapshot)} FROM conversation_carry"
        " WHERE target_conversation_id = %s AND removed_at IS NULL",
        (_as_uuid(target_id),),
    ).fetchone()
    return dict(row) if row is not None else None


def as_of(conn: psycopg.Connection, target_id: UUID | str, at: datetime) -> dict[str, Any] | None:
    """The target's link that was in force at `at` (for a replay), or None. A replacement's `created_at` equals the
    replaced link's `removed_at`, so exactly one link answers at every instant a link was in force."""
    row = conn.execute(
        f"SELECT {_columns(True)} FROM conversation_carry"
        " WHERE target_conversation_id = %s AND created_at <= %s AND (removed_at IS NULL OR removed_at > %s)"
        " ORDER BY created_at DESC LIMIT 1",
        (_as_uuid(target_id), at, at),
    ).fetchone()
    return dict(row) if row is not None else None


def by_id(conn: psycopg.Connection, link_id: UUID | str) -> dict[str, Any] | None:
    """A recorded link with its snapshot, removed since or not (a replay reads the link its request had)."""
    row = conn.execute(
        f"SELECT {_columns(True)} FROM conversation_carry WHERE id = %s",
        (_as_uuid(link_id),),
    ).fetchone()
    return dict(row) if row is not None else None


def history(conn: psycopg.Connection, target_id: UUID | str, snapshot: bool = False) -> dict[str, Any]:
    """The target's link in force and its removed links, newest first."""
    rows = conn.execute(
        f"SELECT {_columns(snapshot)} FROM conversation_carry WHERE target_conversation_id = %s"
        " ORDER BY created_at DESC, id DESC",
        (_as_uuid(target_id),),
    ).fetchall()
    current = next((dict(r) for r in rows if r["removed_at"] is None), None)
    return {"in_force": current, "removed": [dict(r) for r in rows if r["removed_at"] is not None]}
