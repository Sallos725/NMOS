"""Canon facts (Phase 14 step 5, PHASE-14 Q3–Q5, ADR 0047): what the chat's canon says, read by the extraction model
as a projection of its own.

A `canon` generation (its own kind, so the message extractor and its generation do not change) reads a canon revision
in parts of at most PART_CHARS, at most MAX_PARTS of them, one model call each. Each part's answer is stored as an
extraction of the revision (window `canon:<part>`) with its assertions, as a turn's are, so a new generation or a
rebuild keeps the older rows for audit.

Which revisions it reads (Q3), of the canon in force:
- the card's story fields and greeting, the author's note and the persona: always, once per text;
- a lorebook entry: once a request's prompt held it (the host activated it, H19), then each new text of it.

A read takes the canon facts of the manifest its request names (none while the sidecar lacks it), from the extractions
NMOS had by then, as facts from before turn 0: turn -1, positions below every message's, and `canon` set to the key.

What a read of a text depends on besides the text and the generation: the names the host's name macros stand for, when
the text has them (the card's name and the persona's, as the manifest gives them). They are part of the window
(`canon:<part>:<names>`, `plain` for a lorebook entry or the note without the macros), so a renamed card or persona is
read again, and a read takes only the windows of its manifest's names. The persona and the card's fields always have
the names (a persona names USER without the macro, and the model is told who CHARACTER and USER are): another chat's
read of them under other names is never theirs. A text counts as read once every part of it is.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections.abc import Callable
from datetime import datetime
from functools import lru_cache
from typing import Any
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from . import generations, normtext, noteblocks
from .canon import MACRO, MACRO_SQL
from .config import Settings
from .generations import Generation
from .ids import uuid7
from .llm import NO_CALL, LLMError, metered
from .predicates import REGISTRY, registry_prompt, stored_knowledge

log = logging.getLogger("nmos.canon")

VERSION = "canon-v1"
VERSION_V2 = "canon-v2"  # PHASE-64 (ADR 0091): conditional forms of address on `addresses` (paired with extract-v20)
# What canon states about how things stand. Open business (goals, promises, threats, debts, questions) and the
# story's own moves (fulfilled, resolved, learned, destroyed) belong to the story; `also_called` too, since canon's
# names come from the lorebook keys without a model (ADR 0046).
PREDICATES = frozenset({"located_in", "has_status", "identity", "has_trait", "relationship", "role_toward",
                        "feels_toward", "addresses", "possesses", "member_of", "knows", "event", "world_fact"})
PART_CHARS = 6000  # normalized characters per model call, as a turn's target (extraction.TARGET_CHARS)
MAX_PARTS = 4  # a longer text is read in its first 24,000 characters; the rest is recorded as not read
MIN_CHARS = 12
PRIORITY = 150  # after live turns (100), before a first sight's window (210)
POSITION_BASE = -1_000_000  # canon rows sort before every message (positions start at 0)

PROMPT = """You extract durable facts for the long-term memory of a role-play chat from its CANON: a text the chat is
built on (the character card, the user's persona, the author's note or a lorebook entry), not the story itself.
What it states is how things stand before the story begins; the story may change it later.

Allowed predicates (anything else is rejected):
{registry}

Entity types: character, place, item, group, concept.
Rules:
- Extract lasting facts the TEXT states about characters, places, items, groups and the setting: who someone is,
  their traits and appearance, their condition, their relationships and feelings toward others, how they speak to
  and address each other, where they live or are, what they own, what they belong to, what they know, what happened
  before the story (`event`), and durable facts about the world (`world_fact`).
- Only the setting is evidence. Instructions to the AI or the writer (how to write, rules for replies, formats,
  output or status-window templates, style notes), OOC notes, variables and example dialogues given as examples are
  not facts: extract nothing from them, even when they state something plainly.
- CHARACTER is the card's character and USER the user's character, named as given below; use those names for them.
  If USER has no name, write "{{{{user}}}}". Name everyone else exactly as the TEXT does (keep its language).
- `value` is a short phrase in the TEXT's language, never translated; `evidence` is a short quote from the TEXT.
- Give `subject_type`, and `object_type` whenever `object` is set, from the entity types above.
- `epistemic`: "stated" if explicit, "implied" if strongly implied.
- `polarity`: "negative" when the TEXT says the relation does not hold; otherwise "positive".
- `modality`: "actual" for what is true in the setting; "hypothetical" for plans, possibilities and unconfirmed
  rumors; "dreamed" for dreams and visions; "unknown" when the TEXT does not settle it.
- `source`: "narration" for what the TEXT states; "character_claim" for what a character says in quoted dialogue
  (a greeting's lines), with `asserted_by` set to that character.
- `salience`, for `event` only: "major" for what shapes a character or the world from then on (a death, a betrayal,
  a hidden identity, a meeting that matters), "minor" otherwise.
- `because`, for `event`, `feels_toward`, `relationship` and `has_status` only: the cause when the TEXT states it;
  null otherwise. Never guess a cause.
- Knowledge (who in the story is aware of the fact): `knowledge` is "public" when it is openly known, "limited" when
  only some characters know it or it is kept from someone, "unknown" when the TEXT does not say. For "limited":
  `known_by` lists the characters shown to know it; `hidden_from` only characters it is deliberately kept from (a
  secret, a hidden identity). Otherwise use [] for both. Never list characters the TEXT does not name.
- Prefer the facts a later scene would need, at most 30. An empty list is a good answer for a text of instructions.

Answer with JSON only: {{"assertions": [{{"subject": "...", "subject_type": "...", "predicate": "...",
"object": "... or null", "object_type": "... or null", "value": "... or null", "polarity": "positive|negative",
"modality": "actual|hypothetical|dreamed|unknown", "source": "narration|character_claim",
"asserted_by": "... or null", "salience": "major|minor (event only)", "because": "... or null",
"epistemic": "stated", "confidence": 0.0-1.0, "evidence": "...",
"knowledge": "public|limited|unknown", "known_by": [], "hidden_from": []}}]}}"""

SOURCES = {"card:desc": "the character card's description", "card:personality": "the character card's personality",
           "card:scenario": "the character card's scenario",
           "card:greeting": "the character card's greeting (the scene the story opens with)",
           "note": "the author's note", "persona": "the user's persona (USER described)"}

# canon-v2 (PHASE-64, ADR 0091): conditional forms of address in cards, lorebooks, notes and personas.
CANON_ADDRESS_RULE = """- `address_condition`, for `addresses` only: when the TEXT states a form of address or speech level that applies
  only in a specific situation or recurring habit (e.g. formal in public or at work, informal when alone, or
  another specific condition such as in disguise, during missions, or involuntarily slipping into a given name
  when flustered or overcome by emotion), give `{{"scope": "...", "when": "..."}}`; null for a general/default
  form of address. `scope`: "public", "private" or "situational" (never invent a condition the TEXT does not
  state). `when`: a short phrase of at most 60 characters in the TEXT's language naming the condition (required
  for "situational"). If the TEXT states multiple forms (e.g. public vs private, or a default plus a situational
  habit), emit one `addresses` assertion for each.
"""
_CANON_PREFER_AT = "- Prefer the facts a later scene would need,"
_CANON_BECAUSE_ANSWER = '"because": "... or null",'
_CANON_ADDRESS_ANSWER = (_CANON_BECAUSE_ANSWER + ' "address_condition": {{"scope": "public|private|situational",'
                         ' "when": "... or null"}} or null (addresses only),')


def _v2(prompt: str) -> str:
    assert prompt.count(_CANON_PREFER_AT) == 1 and prompt.count(_CANON_BECAUSE_ANSWER) == 1, "a canon-v1 rule moved"
    return (prompt.replace(_CANON_PREFER_AT, CANON_ADDRESS_RULE + _CANON_PREFER_AT, 1)
            .replace(_CANON_BECAUSE_ANSWER, _CANON_ADDRESS_ANSWER, 1))


PROMPT_V2 = _v2(PROMPT)
assert CANON_ADDRESS_RULE not in PROMPT and CANON_ADDRESS_RULE in PROMPT_V2


def version_of(settings: Settings) -> str:
    """The canon reader version for `settings` (PHASE-64, ADR 0091): `canon-v2` with `extract-v20` (conditional forms
    of address), `canon-v1` otherwise so all earlier pinned canon keys stay unchanged."""
    from .extraction import ADDRESS_CONDITIONS, compiler_of
    return VERSION_V2 if compiler_of(settings) in ADDRESS_CONDITIONS else VERSION


def prompt_of(version: str) -> str:
    return PROMPT_V2 if version == VERSION_V2 else PROMPT


# The rules a canon read's answer becomes rows with (PHASE-66 part 5, owner decision 2026-11-25), as
# `extraction.REVISION` is for a turn's: `revision` in the spec, a bump alone a carry-on (no text is read again: what
# no canon generation has read whole is, `READ_ANY`). A read is reused for another chat only from the same key, so the
# first chat to show an already read text after a bump pays for that read once.
# 0 (no field): the production base, Phase 64 (`cdf2c9a`).
# 1 (Tier 1 and its review fixes), against the base:
#   - the answer goes through the turn rows' rules: polarity ("negated", "neg", "false", "no", JSON false negative; an
#     unknown word parks the row pending), the model's own markers stripped and its rows capped at 40 (`own_items`),
#     NUL characters stripped;
#   - the persona and the card's fields are always read under the manifest's names (B7; a `plain` read made before
#     stays served until one under the names is complete).
REVISION = 1


def generation(settings: Settings) -> Generation | None:
    """The canon generation the settings describe (credentials excluded), or None when off. It uses the extraction
    model and endpoint (PHASE-14 Q3)."""
    if not (settings.canon_facts and settings.llm_url and settings.llm_model):
        return None
    ver = version_of(settings)
    return generations.make(
        "canon", settings.llm_url, settings.llm_model, version=ver, prompt=generations.fingerprint(prompt_of(ver)),
        predicates=generations.fingerprint(repr(sorted((k, v) for k, v in REGISTRY.items() if k in PREDICATES))),
        normalizer=normtext.active(), json_mode=settings.llm_json_mode,
        part_chars=PART_CHARS, max_parts=MAX_PARTS,
        **generations.request_spec(settings.llm_extra_body, settings.llm_no_temperature),
        **generations.revision(REVISION))


def always(key: str) -> bool:
    """A key read whether or not a prompt held it: the card's story fields and greeting, the note, the persona."""
    return not key.startswith("lore:") and key != "card:name"


def names_tag(entries: list[dict[str, Any]]) -> str:
    """The names a manifest gives the host's name macros (the card's name by its hash, the persona's name), as the
    window of a text that has the macros. NAMES_TAG is the same in SQL."""
    by = {e["key"]: e for e in entries}
    name = (by.get("card:name") or {}).get("hash") or ""
    user = ((by.get("persona") or {}).get("metadata") or {}).get("name") or ""
    return hashlib.sha256(f"{name}\n{user}".encode()).hexdigest()[:12]


NAMES_TAG = """left(encode(sha256(convert_to(
    coalesce((SELECT y->>'hash' FROM jsonb_array_elements({e}) y WHERE y->>'key' = 'card:name' LIMIT 1), '') || E'\\n' ||
    coalesce((SELECT y->'metadata'->>'name' FROM jsonb_array_elements({e}) y WHERE y->>'key' = 'persona' LIMIT 1), ''),
    'UTF8')), 'hex'), 12)"""
# Whether a stored canon revision has the name macros (recorded at sync since this step; older ones are checked).
NAMED = "coalesce((sr.metadata->>'named')::boolean, sr.content ~* %(macro)s)"
# The window suffix of a read of entry `e` (its key) of revision `sr`: the manifest's names for the persona, the card's
# fields and a text with the macros; `plain` otherwise. `wtag` is the same in Python.
NTAG = "CASE WHEN e.key = 'persona' OR e.key LIKE 'card:%%' OR " + NAMED + " THEN e.tag ELSE 'plain' END"
WTAG = NTAG + " AS wtag"
# Owner decision 2026-11-25 (carry forward): a persona or card text without the macros was read `plain` before Tier 1
# B7. Such a read stays served, and stays the read of its generation, until a complete read under the names exists:
# B7 changed what a new read is, not what an earlier one was worth (no paid re-read on deploy). `CARRY`: whether entry
# `e` of revision `sr` may have one. Never a text with the macros, a lorebook entry or the note.
CARRY = "((e.key = 'persona' OR e.key LIKE 'card:%%') AND NOT " + NAMED + ")"
# One read per (revision, generation), never both (duplicate facts) and never neither: the one under the names when it
# is complete or there is no `plain` read, else the carried `plain` one. A read under one window suffix is complete
# when every part the text has under that suffix is there, not discarded: as many parts as the `parts` each part
# records (`READ`). So a names read that started and stopped beside a `plain` one serves nothing and is not resumed.
# GTAG (what a generation reads, wants, covers and dedupes), READ_ANY, ROWS and `carried_tag` all choose so.
_COMPLETE_OF = ("(SELECT coalesce(count(*) >= max((y.coverage->>'parts')::int), false) FROM extraction y"
                " WHERE y.source_revision_id = sr.id AND y.extractor_key = %(gen)s AND y.discarded_at IS NULL"
                " AND split_part(y.window_hash, ':', 3) = {tag})")
_READ_OF = ("EXISTS (SELECT 1 FROM extraction y WHERE y.source_revision_id = sr.id AND y.extractor_key = %(gen)s"
            " AND y.discarded_at IS NULL AND split_part(y.window_hash, ':', 3) = {tag})")
GTAG = ("CASE WHEN " + CARRY + " AND NOT " + _COMPLETE_OF.format(tag="e.tag") + " AND " + _READ_OF.format(tag="'plain'")
        + " THEN 'plain' ELSE " + NTAG + " END AS wtag")

# The revisions a canon generation reads, of each chat's canon in force: the card's fields, the note and the persona,
# and each lorebook entry some recorded request's prompt held; with the window suffix a read of it has now.
IN_FORCE = """
WITH chats AS (
    SELECT c.id, m.entries, """ + NAMES_TAG.format(e="m.entries") + """ AS tag
    FROM conversation c JOIN canon_manifest m ON m.conversation_id = c.id AND m.id = c.canon_manifest_id
    WHERE c.canon_manifest_id IS NOT NULL AND (%(conv)s::uuid IS NULL OR c.id = %(conv)s::uuid)
),
e AS (
    SELECT ch.id AS conv, ch.tag, x->>'key' AS key, x->>'hash' AS hash
    FROM chats ch CROSS JOIN LATERAL jsonb_array_elements(ch.entries) x
),
held AS (
    SELECT DISTINCT t.conversation_id AS conv, k.key
    FROM retrieval_trace t JOIN chats ch ON ch.id = t.conversation_id
    CROSS JOIN LATERAL jsonb_array_elements_text(t.canon_held) k(key)
    WHERE t.canon_held <> '[]'::jsonb AND k.key LIKE 'lore:%%'
)
SELECT e.conv, e.key, sr.id AS rid, """ + GTAG + """, """ + NTAG + """ AS ntag, """ + CARRY + """ AS carry
FROM e
JOIN source_object so ON so.conversation_id = e.conv AND so.host_logical_id = 'canon:' || e.key
                     AND so.source_kind = 'canon'
JOIN source_revision sr ON sr.source_object_id = so.id AND sr.revision_hash = e.hash
WHERE e.key <> 'card:name'
  AND (e.key NOT LIKE 'lore:%%' OR EXISTS (SELECT 1 FROM held h WHERE h.conv = e.conv AND h.key = e.key))
"""
# A read of one revision in one window: its parts so far, and how many it has (every part records the count).
READ = """(SELECT count(*) AS calls, max((x.coverage->>'parts')::int) AS parts,
                  max((x.coverage->>'unread_chars')::int) AS unread,
                  count(*) FILTER (WHERE x.coverage ? 'reused_from') AS reused
           FROM extraction x WHERE x.source_revision_id = f.rid AND x.extractor_key = %(gen)s
             AND x.discarded_at IS NULL AND split_part(x.window_hash, ':', 3) = f.wtag)"""
# Whether a carry-on peer of the generation (`generations.peers`: only `revision` or `normalizer` differs, PHASE-66
# part 5) has read the text whole, each generation's read chosen as in READ_ANY: it counts as the generation's own.
READ_PEERS = ("(SELECT coalesce(bool_or(r.n >= r.parts), false) AS complete FROM ("
              " SELECT count(*) AS n, max((x.coverage->>'parts')::int) AS parts FROM extraction x"
              " WHERE x.source_revision_id = f.rid AND x.extractor_key = ANY(%(peers)s) AND x.discarded_at IS NULL"
              " AND (split_part(x.window_hash, ':', 3) = f.ntag"
              " OR (f.carry AND split_part(x.window_hash, ':', 3) = 'plain'))"
              " GROUP BY x.extractor_key, split_part(x.window_hash, ':', 3)) r)")
# Those not read completely yet: some parts missing (a job stopped between parts), or no part and no carry-on peer's
# whole read.
WANTED = ("SELECT f.* FROM (" + IN_FORCE + ") f CROSS JOIN LATERAL " + READ + " rd CROSS JOIN LATERAL " + READ_PEERS
          + " rp WHERE (rd.parts IS NOT NULL AND rd.calls < rd.parts) OR (rd.parts IS NULL AND NOT rp.complete)")

# Whether any canon generation has read the text whole (PHASE-57 A3): a model change carried on, a sync or a startup
# reads only what none has. A read the active generation stopped between parts still goes on. Each generation's read is
# one (CARRY, GTAG): the names read when complete, else a carried `plain` one; so a generation has read the text whole
# exactly when its names read or its carried `plain` read is complete.
READ_ANY = """(SELECT coalesce(bool_or(r.n >= r.parts), false) AS complete FROM (
               SELECT count(*) AS n, max((x.coverage->>'parts')::int) AS parts
               FROM extraction x JOIN projection_generation g ON g.key = x.extractor_key AND g.kind = 'canon'
               WHERE x.source_revision_id = f.rid AND x.discarded_at IS NULL
                 AND (split_part(x.window_hash, ':', 3) = f.ntag
                      OR (f.carry AND split_part(x.window_hash, ':', 3) = 'plain'))
               GROUP BY x.extractor_key, split_part(x.window_hash, ':', 3)) r)"""
WANTED_ANY = ("SELECT f.* FROM (" + IN_FORCE + ") f CROSS JOIN LATERAL " + READ + " rd CROSS JOIN LATERAL " + READ_ANY
              + " ra WHERE (rd.parts IS NOT NULL AND rd.calls < rd.parts) OR NOT ra.complete")

# A job wanted again is revived with its new payload: a rebuild's read is `fresh` (PHASE-57 A1).
REQUEUE = """ON CONFLICT (dedupe_key) DO UPDATE SET status = 'queued', priority = EXCLUDED.priority, attempts = 0,
    run_after = now(), locked_at = NULL, last_error = NULL, updated_at = now(), payload = EXCLUDED.payload
    WHERE job.status = 'obsolete'"""


def schedule(conn: psycopg.Connection, key: str, conv: UUID | None = None, any_generation: bool = False,
             fresh: bool = False) -> int:
    """Queue what the canon generation `key` has not read (Q3), for one chat or all. Idempotent; queued jobs of other
    canon generations become obsolete. With `any_generation` (PHASE-57 A3), only what no canon generation has read
    whole. With `fresh` (a rebuild, PHASE-57 A1), the reads skip the lookup for another chat's identical read."""
    with conn.transaction():
        conn.execute("UPDATE job SET status = 'obsolete', updated_at = now() WHERE kind = 'canon' AND status = 'queued'"
                     " AND payload->>'generation' IS DISTINCT FROM %s AND (%s::uuid IS NULL OR conversation_id = %s)",
                     (key, conv, conv))
        payload = ("jsonb_build_object('revision_id', w.rid::text, 'generation', %(gen)s"
                   + (", 'fresh', true)" if fresh else ")"))
        return conn.execute(
            "WITH wanted AS (" + (WANTED_ANY if any_generation else WANTED) + ")"
            " INSERT INTO job (kind, dedupe_key, conversation_id, payload, priority)"
            " SELECT 'canon', 'canon:' || w.rid || ':' || w.wtag || ':' || %(gen)s, w.conv, " + payload + ", %(priority)s"
            " FROM wanted w ORDER BY w.conv, w.key " + REQUEUE,
            {"conv": conv, "gen": key, "peers": generations.peers(conn, key), "priority": PRIORITY,
             "macro": MACRO_SQL}).rowcount


def requeue(conn: psycopg.Connection, conv: UUID) -> int:
    """A per-chat rebuild (D22) discarded this chat's canon extractions too: its canon jobs become obsolete, so
    `schedule` queues them again."""
    return conn.execute("UPDATE job SET status = 'obsolete', locked_at = NULL, updated_at = now()"
                        " WHERE kind = 'canon' AND conversation_id = %s", (conv,)).rowcount


def name_dependent(key: str, named_: bool) -> bool:
    """Whether a read of entry `key` depends on the manifest's names (WTAG in SQL): the persona and the card's fields
    always; any other text when it has the name macros."""
    return key == "persona" or key.startswith("card:") or named_


def wtag(key: str, named_: bool, entries: list[dict[str, Any]]) -> str:
    return names_tag(entries) if name_dependent(key, named_) else "plain"


def carried_tag(conn: psycopg.Connection, rid: UUID, gen: str, key: str, named_: bool, tag: str) -> str:
    """The window suffix generation `gen`'s read of revision `rid` has (GTAG in SQL): `plain` for a persona or card
    text without the macros that `gen` read `plain` and has not read completely under the names (`tag`: every part
    the text has under it), else `tag`."""
    if named_ or not (key == "persona" or key.startswith("card:")) or tag == "plain":
        return tag
    seen = conn.execute(
        "SELECT count(*) FILTER (WHERE split_part(window_hash, ':', 3) = %(tag)s) AS n,"
        " max((coverage->>'parts')::int) FILTER (WHERE split_part(window_hash, ':', 3) = %(tag)s) AS parts,"
        " coalesce(bool_or(split_part(window_hash, ':', 3) = 'plain'), false) AS plain FROM extraction"
        " WHERE source_revision_id = %(rid)s AND extractor_key = %(gen)s AND discarded_at IS NULL",
        {"tag": tag, "rid": rid, "gen": gen}).fetchone()
    complete = seen["parts"] is not None and seen["n"] >= seen["parts"]
    return "plain" if seen["plain"] and not complete else tag


def manifest_names(conn: psycopg.Connection, conv: UUID,
                   entries: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    """The names a manifest gives the host's name macros: the card's name (its revision's text) and the persona's."""
    by = {e["key"]: e for e in entries}
    name = by.get("card:name")
    character = None
    if name is not None:
        found = conn.execute(
            "SELECT sr.content FROM source_object so JOIN source_revision sr ON sr.source_object_id = so.id"
            " WHERE so.conversation_id = %s AND so.host_logical_id = 'canon:card:name' AND sr.revision_hash = %s",
            (conv, name["hash"])).fetchone()
        character = found["content"].strip() if found else None
    user = ((by.get("persona") or {}).get("metadata") or {}).get("name")  # the manifest's, so reads are its own
    return character, user or None


def named(text: str, character: str | None, user: str | None) -> str:
    """The host's name macros replaced by the names they stand for (the host does the same in a prompt)."""
    return MACRO.sub(lambda m: (user if m[1].lower() == "user" else character) or m[0], text)


def parts(text: str) -> tuple[list[str], int]:
    """The text in parts of at most PART_CHARS, cut at a paragraph or line end where one is near, at most MAX_PARTS;
    and how many characters were left unread."""
    out: list[str] = []
    rest = text.strip()
    while rest and len(out) < MAX_PARTS:
        if len(rest) <= PART_CHARS:
            out.append(rest)
            rest = ""
            break
        cut = max(rest.rfind("\n\n", 0, PART_CHARS), rest.rfind("\n", 0, PART_CHARS))
        if cut < PART_CHARS // 2:
            cut = PART_CHARS
        out.append(rest[:cut].strip())
        rest = rest[cut:].strip()
    return [p for p in out if p], len(rest)


def describe(key: str, metadata: dict[str, Any]) -> str:
    if key in SOURCES:
        return SOURCES[key]
    comment = metadata.get("comment")
    keys = metadata.get("keys") or []
    what = f"a lorebook entry \"{comment}\"" if comment else "a lorebook entry"
    return what + (f" (activated by: {', '.join(keys[:12])})" if keys else " (always active)")


def build_prompt(key: str, metadata: dict[str, Any], character: str | None, user: str | None, text: str, part: int,
                 count: int) -> str:
    lines = [f"SOURCE: {describe(key, metadata)}", f"CHARACTER: {character or '(unnamed)'}",
             f"USER: {user or '{{user}}'}", "",
             f"TEXT (part {part + 1} of {count}):" if count > 1 else "TEXT:", text]
    return "\n".join(lines)


def _source(conn: psycopg.Connection, rid: UUID, gen: str | None = None) -> dict[str, Any] | None:
    """A canon revision with its key and what the canon in force says of it; None when it is not in force now (a newer
    text replaced it before its job ran). With `gen`, its window suffix is the one that generation's read has
    (`carried_tag`)."""
    row = conn.execute(
        "SELECT sr.id, sr.revision_hash, sr.content, sr.metadata, so.host_logical_id, so.conversation_id, m.entries"
        " FROM source_revision sr JOIN source_object so ON so.id = sr.source_object_id AND so.source_kind = 'canon'"
        " JOIN conversation c ON c.id = so.conversation_id"
        " JOIN canon_manifest m ON m.conversation_id = c.id AND m.id = c.canon_manifest_id"
        " WHERE sr.id = %s", (rid,)).fetchone()
    if row is None:
        return None
    key = row["host_logical_id"].removeprefix("canon:")
    entries = {e["key"]: e for e in row["entries"]}
    entry = entries.get(key)
    if entry is None or entry["hash"] != row["revision_hash"]:
        return None
    character, user = manifest_names(conn, row["conversation_id"], row["entries"])
    named_ = (row["metadata"] or {}).get("named")
    if named_ is None:
        named_ = bool(MACRO.search(row["content"]))
    tag = wtag(key, bool(named_), row["entries"])
    if gen is not None:
        tag = carried_tag(conn, row["id"], gen, key, bool(named_), tag)
    return {"id": row["id"], "key": key, "conversation_id": row["conversation_id"],
            "metadata": entry.get("metadata") or {}, "character": character, "user": user, "wtag": tag}


def input_of(src: dict[str, Any], piece: str, part: int, count: int) -> str:
    """The fingerprint of what a part's read sends the model besides the generation's own system prompt (PHASE-57 A1):
    the source line, the part, its text with the macros replaced, and the names whenever the read depends on them
    (`wtag`: the persona, the card's fields, a text with the macros), as a chat already keeps a `plain` text's read
    when its persona is renamed (ADR 0047)."""
    named_ = src["wtag"] != "plain"
    fields = [describe(src["key"], src["metadata"]), str(part), str(count),
              (src["character"] or "") if named_ else "", (src["user"] or "") if named_ else "", piece]
    return generations.fingerprint("\x1f".join(fields))


def reusable(conn: psycopg.Connection, key: str, fingerprint: str, rid: UUID) -> dict[str, Any] | None:
    """The newest read of another revision by this canon generation that answered the same input, not discarded."""
    return conn.execute(
        "SELECT id, coverage FROM extraction WHERE extractor_key = %s AND coverage ? 'input'"
        " AND coverage->>'input' = %s AND discarded_at IS NULL AND source_revision_id <> %s"
        " ORDER BY created_at DESC, id DESC LIMIT 1", (key, fingerprint, rid)).fetchone()


def _still_claimed(conn: psycopg.Connection, job: dict[str, Any]) -> bool:
    return job.get("locked_at") is None or conn.execute(
        "SELECT 1 FROM job WHERE id = %s AND status = 'running' AND locked_at = %s FOR UPDATE",
        (job["id"], job["locked_at"])).fetchone() is not None


def process(conn: psycopg.Connection, job: dict[str, Any], complete: Callable[[str, str], tuple[Any, ...]],
            gen: Generation) -> str:
    """Read one canon revision (every part not read yet) and store its facts. Returns the final job status."""
    from .extraction import ASSERTION_COLUMNS, assertion_values, normalize, own_items  # the same normalizer as a turn's (ADR 0013, D6, D19)

    if job["payload"].get("generation") != gen.key:
        raise ValueError(f"job generation {job['payload'].get('generation')} is not handler generation {gen.key}")
    rid = UUID(job["payload"]["revision_id"])
    src = _source(conn, rid, gen.key)
    if src is None:
        return "obsolete"
    text = named(normtext.get(conn, rid)["clean_content"], src["character"], src["user"])
    if src["key"] == "note":  # NMOS's own sections are not canon (PHASE-50 S5): an older plugin sends them whole
        text = noteblocks.strip_blocks(text)[0]
    pieces, unread = parts(text)
    done = {r["window_hash"] for r in conn.execute(
        "SELECT window_hash FROM extraction WHERE source_revision_id = %s AND extractor_key = %s"
        " AND discarded_at IS NULL", (rid, gen.key)).fetchall()}
    ver = gen.spec.get("version", VERSION)
    is_v2 = ver == VERSION_V2
    count = len(pieces) or 1
    system = prompt_of(ver).format(registry=registry_prompt(PREDICATES))
    total = reused = 0
    fresh = bool(job["payload"].get("fresh"))  # a rebuild reads its own chat again (PHASE-57 A1)
    hints = Jsonb({"canon": src["key"], "character": src["character"], "user": src["user"]})
    for i, piece in enumerate(pieces or [""]):
        window = f"canon:{i}:{src['wtag']}"
        if window in done:
            continue
        fingerprint = input_of(src, piece, i, len(pieces))
        coverage = {"chars": len(text), "part": i, "parts": count, "part_chars": len(piece), "unread_chars": unread,
                    "input": fingerprint}
        match = None if fresh or len(piece) < MIN_CHARS else reusable(conn, gen.key, fingerprint, rid)
        if match is not None:  # another chat's read of the same input: copied, not shared (PHASE-57 A1)
            root = (match["coverage"] or {}).get("reused_from") or str(match["id"])
            with conn.transaction():
                if not _still_claimed(conn, job):
                    return "obsolete"
                xid = uuid7()
                inserted = conn.execute(
                    "INSERT INTO extraction (id, source_revision_id, window_hash, compiler_version, extractor_key, model,"
                    " raw, coverage, members, hints, usage) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                    " ON CONFLICT DO NOTHING RETURNING id",
                    (xid, rid, window, ver, gen.key, gen.model, Jsonb({"reused_from": root}),
                     Jsonb({**coverage, "reused_from": root}), [rid], hints, Jsonb(NO_CALL))).fetchone()
                if inserted is None:
                    continue
                columns = ", ".join(ASSERTION_COLUMNS)
                copied = conn.execute(
                    f"INSERT INTO assertion (extraction_id, source_revision_id, {columns})"
                    f" SELECT %s, %s, {columns} FROM assertion WHERE extraction_id = %s ORDER BY id",
                    (xid, rid, match["id"])).rowcount
            total += copied
            reused += 1
            continue
        if len(piece) < MIN_CHARS:
            parsed, raw, usage = {"assertions": []}, "", NO_CALL
        else:
            parsed, raw, usage = metered(complete, system, build_prompt(src["key"], src["metadata"], src["character"],
                                                                        src["user"], piece, i, len(pieces)))
        items = parsed.get("assertions")
        if not isinstance(items, list):
            raise LLMError("model reply has no `assertions` list")
        rows = normalize(own_items(items), piece, address_conditions=is_v2)  # the model's own, capped (review F5)
        for a in rows:
            if a.get("address_condition") and a["address_condition"].get("scope") == "all":
                a["address_condition"] = None  # canon is the initial baseline: no earlier split to unify
            if a["status"] == "valid" and a["predicate"] not in PREDICATES:
                a["status"], a["reason"] = "pending", "not a canon predicate"
        with conn.transaction():
            if not _still_claimed(conn, job):
                return "obsolete"
            xid = uuid7()
            inserted = conn.execute(
                "INSERT INTO extraction (id, source_revision_id, window_hash, compiler_version, extractor_key, model,"
                " raw, coverage, members, hints, usage) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                " ON CONFLICT DO NOTHING RETURNING id",
                (xid, rid, window, ver, gen.key, gen.model, Jsonb({"reply": raw[:20000]}), Jsonb(coverage), [rid],
                 hints, Jsonb(usage) if usage is not None else None)).fetchone()
            if inserted is None:
                continue
            values = [(xid, rid, *assertion_values(a)) for a in rows]
            if values:
                with conn.cursor() as cur:
                    cur.executemany(
                        f"INSERT INTO assertion (extraction_id, source_revision_id, {', '.join(ASSERTION_COLUMNS)})"
                        f" VALUES ({', '.join(['%s'] * (2 + len(ASSERTION_COLUMNS)))})", values)
        total += len(rows)
    log.info("canon read conversation=%s key=%s parts=%d reused=%d assertions=%d unread_chars=%d",
             src["conversation_id"], src["key"], len(pieces), reused, total, unread)
    return "done"


# The canon facts of one manifest: each entry's revision, one generation per revision (the given one first, then the
# most recently activated that read it, as ADR 0014 serves turns), as of a time for a replay (ADR 0027).
ROWS = """
WITH m AS (
    SELECT entries, """ + NAMES_TAG.format(e="entries") + """ AS tag
    FROM canon_manifest WHERE conversation_id = %(conv)s AND id = %(mid)s
),
e AS (
    SELECT x->>'key' AS key, x->>'hash' AS hash, t.ord, m.tag
    FROM m CROSS JOIN LATERAL jsonb_array_elements(m.entries) WITH ORDINALITY AS t(x, ord)
),
r AS (
    SELECT e.key, e.ord, sr.id AS rid, """ + WTAG + """, """ + CARRY + """ AS carry
    FROM e JOIN source_object so ON so.conversation_id = %(conv)s AND so.host_logical_id = 'canon:' || e.key
                                AND so.source_kind = 'canon'
    JOIN source_revision sr ON sr.source_object_id = so.id AND sr.revision_hash = e.hash
    WHERE EXISTS (SELECT 1 FROM extraction x WHERE x.source_revision_id = sr.id)
),
reads AS (  -- one read per generation (CARRY): the names read when complete or alone, else the carried `plain` one;
            -- complete as of `at`, since the window is taken over the rows the WHERE keeps
    SELECT r.key, r.ord, r.rid, x.id AS xid, x.window_hash, x.extractor_key, x.compiler_version, g.activated_at,
           split_part(x.window_hash, ':', 3) <> r.wtag AS carried,
           bool_or(split_part(x.window_hash, ':', 3) <> r.wtag) OVER w AS plain,
           coalesce(count(*) FILTER (WHERE split_part(x.window_hash, ':', 3) = r.wtag) OVER w
                    >= max((x.coverage->>'parts')::int) FILTER (WHERE split_part(x.window_hash, ':', 3) = r.wtag) OVER w,
                    false) AS named
    FROM r JOIN extraction x ON x.source_revision_id = r.rid
                            AND (split_part(x.window_hash, ':', 3) = r.wtag
                                 OR (r.carry AND split_part(x.window_hash, ':', 3) = 'plain'))
    JOIN projection_generation g ON g.key = x.extractor_key AND g.kind = 'canon'
    -- as of `at` for a replay; with no `at`, as of the request's transaction start (now(), the database's clock and
    -- the instant its trace records), so an extraction committed during the request is read by neither it nor a replay
    WHERE x.created_at <= coalesce(%(at)s::timestamptz, now())
      AND (x.discarded_at IS NULL OR x.discarded_at > coalesce(%(at)s::timestamptz, now()))
    WINDOW w AS (PARTITION BY r.rid, x.extractor_key)
),
live AS (
    SELECT d.key, d.ord, d.rid, d.xid, d.window_hash, d.extractor_key, d.compiler_version,
           first_value(d.extractor_key) OVER (PARTITION BY d.rid
               ORDER BY d.extractor_key = %(gen)s DESC, d.activated_at DESC, d.extractor_key) AS chosen
    FROM reads d WHERE d.carried = (d.plain AND NOT d.named)  -- the carried rows exactly when `plain` is the one
)
SELECT a.id, a.subject, a.subject_type, a.predicate, a.object, a.object_type, a.value, a.epistemic, a.confidence,
       a.evidence, a.knowledge, a.known_by, a.hidden_from, a.polarity, a.modality, a.source, a.asserted_by, a.salience,
       a.participants::text AS participants, a.outcome, a.because, a.address_condition::text AS address_condition,
       l.key AS canon, l.extractor_key AS generation, l.compiler_version AS compiler, l.rid
FROM live l JOIN assertion a ON a.extraction_id = l.xid
WHERE l.extractor_key = l.chosen AND a.status = 'valid'
ORDER BY l.ord, l.window_hash, a.id
"""


@lru_cache(maxsize=4096)
def _parse_address_condition(text: str) -> dict[str, Any]:
    return json.loads(text)


# The host's blocks (H20, ADR 0047 amendment 2): `{{#if …}}`, `{{#if_pure …}}`, `{{#when …}}`, `{{#each …}}` and
# `{{#func name …}}` show their body only for some values of the chat's variables, or not as written; `{{#pure}}`,
# `{{#pure_display}}`, `{{#code}}` and `{{#escape…}}` show it; `{{/…}}` closes the innermost block. The model reads a
# text with every branch, so a fact read inside a conditional body may come from a branch the host never shows.
TAG = re.compile(r"\{\{#([^{}]*)(\}\})?|\{\{/(?!/)[^{}]*\}\}")  # an opener's head (to a brace), or a closer
CHUNK = 12  # characters of evidence (spaces removed) looked for at a time
CACHED = 4096
# Per revision and the names its manifest gives the macros: its text as the model read it (cleaned, the macros
# replaced) without spaces (casefolded), where each of those characters stands, and its conditional spans; None for a
# text without them. Per revision, names and evidence: the verdict. A revision's content never changes.
Blocks = tuple[str, list[int], list[tuple[int, int]]]
Names = tuple[str | None, str | None]
_texts: dict[tuple[UUID, str | None, str | None], Blocks | None] = {}
_verdicts: dict[tuple[UUID, str | None, str | None, str], bool] = {}
_blockless: set[UUID] = set()  # revisions without a block tag, whatever the names
_names: dict[tuple[UUID, str], Names] = {}  # per chat and manifest (a manifest's entries never change)


def _opens(head: str, whole: bool) -> bool | None:
    """Whether a tag `{{#head…` opens a block that hides its body (True) or shows it (False), as the host's
    `blockStartMatcher` decides (case-sensitive, in its order); None: no block. `whole`: the tag ends right after
    `head` (no nested macro follows)."""
    if head.startswith(("if", "when")):
        return True
    if whole and head in ("pure", "pure_display", "puredisplay", "code"):
        return False
    if head.startswith("escape"):
        return False
    if head.startswith("each") or (head.startswith("func") and " " in head):
        return True
    return None


def conditional_spans(text: str) -> list[tuple[int, int]]:
    """The spans of `text` inside a block that shows its body only conditionally (an unclosed one runs to the end)."""
    stack: list[tuple[int, bool]] = []
    spans: list[tuple[int, int]] = []
    for m in TAG.finditer(text):
        if m[1] is not None:
            hides = _opens(m[1], m[2] is not None)
            if hides is not None:
                stack.append((m.start(), hides))
        elif stack:
            start, hides = stack.pop()
            if hides:
                spans.append((start, m.end()))
    spans += [(start, len(text)) for start, hides in stack if hides]
    return spans


def blocks_of(text: str) -> Blocks | None:
    spans = conditional_spans(text)
    if not spans:
        return None
    flat: list[str] = []
    index: list[int] = []
    for i, ch in enumerate(text):
        if not ch.isspace():
            folded = ch.casefold()  # may be longer than the character (ß → ss)
            flat.append(folded)
            index += [i] * len(folded)
    return "".join(flat), index, spans


def _marks(text: str) -> list[bool | str | None]:
    """The block tags of a text as the host reads them, in order: what each opener does, and each closer."""
    return [_opens(m[1], m[2] is not None) if m[1] is not None else "/" for m in TAG.finditer(text)]


def read_blocks(content: str, character: str | None, user: str | None) -> Blocks | None:
    """The blocks of a canon revision's raw `content` in the text its extraction read: cleaned as the normalizer
    cleans it (markup dropped) and the name macros replaced, so evidence the model quoted with the names in place
    and without the markup is found where it stands. When the cleaning changed the block tags themselves, the raw
    text with the macros replaced is used."""
    text, whole = named(normtext.clean(content), character, user), named(content, character, user)
    return blocks_of(text if _marks(text) == _marks(whole) else whole)


def _blocks(conn: psycopg.Connection, rids: set[UUID],
            names: Callable[[], Names] = lambda: (None, None)) -> dict[UUID, Blocks | None]:
    """The blocks of each revision in `rids` under its manifest's names (`names`, asked only when a revision with a
    block tag is not cached yet), read once per process."""
    out: dict[UUID, Blocks | None] = {r: None for r in rids if r in _blockless}
    missing = [r for r in rids if r not in out]
    if not missing:
        return out
    character, user = names()
    for r in missing:
        if (r, character, user) in _texts:
            out[r] = _texts[(r, character, user)]
    missing = [r for r in missing if r not in out]
    if missing:
        found = {row["id"]: row["content"] for row in conn.execute(
            "SELECT id, content FROM source_revision WHERE id = ANY(%s) AND content LIKE '%%{{#%%'",
            (missing,)).fetchall()}
        for r in missing:  # published whole: another request sees a revision's blocks or nothing
            if r in found:
                out[r] = _texts[(r, character, user)] = read_blocks(found[r], character, user)
            else:
                out[r] = None
                _blockless.add(r)
        for old in list(_texts)[:max(0, len(_texts) - CACHED)]:
            _texts.pop(old, None)
        while len(_blockless) > CACHED * 4:
            _blockless.pop()
    return out


def shown(blocks: Blocks | None, rid: UUID, evidence: str | None, names: Names = (None, None)) -> bool:
    """Whether a canon fact is served: its text has no conditional block, or its evidence is found outside them and
    no piece of it only inside (in pieces of CHUNK characters, spaces and case ignored), in the text as the model
    read it (`read_blocks` under `names`). Evidence found nowhere is not served, and neither is evidence that is
    partly only in a block (fail closed): a block that restates an unconditional sentence and adds a sentence of its
    own gives a quote of both, and the fact may come from the branch the host does not show."""
    if blocks is None:
        return True
    verdict = _verdicts.get((rid, *names, evidence or ""))
    if verdict is None:
        flat, index, spans = blocks
        quote = "".join((evidence or "").split()).casefold()
        pieces = [quote] if len(quote) <= CHUNK else [quote[i:i + CHUNK] for i in range(0, len(quote) - CHUNK + 1, 4)]
        outside = inside = 0
        for piece in filter(None, pieces):
            at = flat.find(piece)
            if at < 0:
                continue
            while at >= 0 and any(a <= index[at] < b for a, b in spans):
                at = flat.find(piece, at + 1)
            if at >= 0:
                outside += 1
            else:
                inside += 1
        verdict = outside > 0 and inside == 0
        _verdicts[(rid, *names, evidence or "")] = verdict
        for old in list(_verdicts)[:max(0, len(_verdicts) - CACHED * 4)]:
            _verdicts.pop(old, None)
    return verdict


def _manifest_names(conn: psycopg.Connection, conv: UUID, mid: str) -> Names:
    """`manifest_names` of manifest `mid`, read once per process."""
    got = _names.get((conv, mid))
    if got is None:
        row = conn.execute("SELECT entries FROM canon_manifest WHERE conversation_id = %s AND id = %s",
                           (conv, mid)).fetchone()
        got = manifest_names(conn, conv, row["entries"]) if row else (None, None)
        _names[(conv, mid)] = got
        for old in list(_names)[:max(0, len(_names) - CACHED)]:
            _names.pop(old, None)
    return got


def rows(conn: psycopg.Connection, conv: UUID, mid: str | None, key: str | None,
         known_at: datetime | None = None) -> list[dict[str, Any]]:
    """The canon facts of manifest `mid` as a read takes them (ADR 0047): before turn 0, in the manifest's key order,
    without those read inside a conditional block (amendment 2)."""
    if not mid or not key:
        return []
    # Prepared at its first use on a connection: planning it takes longer than running it (PHASE-14 step 6).
    out = conn.execute(ROWS, {"conv": conv, "mid": mid, "gen": key, "macro": MACRO_SQL,
                              "at": known_at}, prepare=True).fetchall()
    names: list[Names] = []

    def manifest() -> Names:
        if not names:
            names.append(_manifest_names(conn, conv, mid))
        return names[0]

    blocks = _blocks(conn, {a["rid"] for a in out}, manifest)
    kept = []
    for a in out:
        rid = a.pop("rid")
        b = blocks[rid]
        if shown(b, rid, a["evidence"], manifest() if b is not None else (None, None)):
            kept.append(a)
    out = kept
    for i, a in enumerate(out):
        a.update(position=POSITION_BASE + i, turn=-1, turn_hash=f"canon:{a['canon']}",
                 host_logical_id=f"canon:{a['canon']}", listed_hash=None, participants=None)
        if (cond := a.pop("address_condition")) is not None:
            a["address_condition"] = _parse_address_condition(cond)
        if a["known_by"] or a["hidden_from"]:
            stored_knowledge(a)
    return out


def coverage(conn: psycopg.Connection, key: str | None, conv: UUID) -> dict[str, Any]:
    """How much of the chat's canon in force the canon generation has read (Q3; the Inspector shows the calls made):
    texts to read, read, queued and failed; the model calls made; characters left unread."""
    if not key:
        return {}
    rows_ = conn.execute(
        "SELECT f.key, rd.calls, rd.parts, rd.unread, rd.reused,"
        "  (SELECT j.status FROM job j WHERE j.dedupe_key = 'canon:' || f.rid || ':' || f.wtag || ':' || %(gen)s) AS job"
        " FROM (" + IN_FORCE + ") f CROSS JOIN LATERAL " + READ + " rd",
        {"conv": conv, "gen": key, "macro": MACRO_SQL}).fetchall()
    return {"wanted": len(rows_), "read": sum(1 for r in rows_ if r["parts"] and r["calls"] >= r["parts"]),
            "pending": sum(1 for r in rows_ if r["job"] in ("queued", "running")),
            "failed": sum(1 for r in rows_ if r["job"] == "dead"),
            "calls": sum(r["calls"] for r in rows_), "unread_chars": sum(r["unread"] or 0 for r in rows_),
            "reused": sum(r["reused"] for r in rows_),  # parts copied from another chat's read (PHASE-57 A1)
            "keys": {r["key"]: {"calls": r["calls"], "job": r["job"]} for r in rows_}}
