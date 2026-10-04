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
(`canon:<part>:<names>`, `plain` for a text without the macros), so a renamed card or persona is read again, and a read
takes only the windows of its manifest's names. A text counts as read once every part of it is.
"""

from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import Callable
from datetime import datetime
from typing import Any
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from . import generations, normtext
from .canon import MACRO, MACRO_SQL
from .config import Settings
from .generations import Generation
from .ids import uuid7
from .llm import NO_CALL, LLMError, metered
from .predicates import REGISTRY, registry_prompt, stored_knowledge

log = logging.getLogger("nmos.canon")

VERSION = "canon-v1"
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


def generation(settings: Settings) -> Generation | None:
    """The canon generation the settings describe (credentials excluded), or None when off. It uses the extraction
    model and endpoint (PHASE-14 Q3)."""
    if not (settings.canon_facts and settings.llm_url and settings.llm_model):
        return None
    return generations.make(
        "canon", settings.llm_url, settings.llm_model, version=VERSION, prompt=generations.fingerprint(PROMPT),
        predicates=generations.fingerprint(repr(sorted((k, v) for k, v in REGISTRY.items() if k in PREDICATES))),
        normalizer=normtext.NORMALIZER_VERSION, json_mode=settings.llm_json_mode, temperature=0,
        part_chars=PART_CHARS, max_parts=MAX_PARTS)


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
SELECT e.conv, e.key, sr.id AS rid, CASE WHEN """ + NAMED + """ THEN e.tag ELSE 'plain' END AS wtag
FROM e
JOIN source_object so ON so.conversation_id = e.conv AND so.host_logical_id = 'canon:' || e.key
                     AND so.source_kind = 'canon'
JOIN source_revision sr ON sr.source_object_id = so.id AND sr.revision_hash = e.hash
WHERE e.key <> 'card:name'
  AND (e.key NOT LIKE 'lore:%%' OR EXISTS (SELECT 1 FROM held h WHERE h.conv = e.conv AND h.key = e.key))
"""
# A read of one revision in one window: its parts so far, and how many it has (every part records the count).
READ = """(SELECT count(*) AS calls, max((x.coverage->>'parts')::int) AS parts,
                  max((x.coverage->>'unread_chars')::int) AS unread
           FROM extraction x WHERE x.source_revision_id = f.rid AND x.extractor_key = %(gen)s
             AND x.discarded_at IS NULL AND split_part(x.window_hash, ':', 3) = f.wtag)"""
# Those not read completely yet: no part, or some parts missing (a job stopped between parts).
WANTED = ("SELECT f.* FROM (" + IN_FORCE + ") f CROSS JOIN LATERAL " + READ
          + " rd WHERE rd.parts IS NULL OR rd.calls < rd.parts")

REQUEUE = """ON CONFLICT (dedupe_key) DO UPDATE SET status = 'queued', priority = EXCLUDED.priority, attempts = 0,
    run_after = now(), locked_at = NULL, last_error = NULL, updated_at = now() WHERE job.status = 'obsolete'"""


def schedule(conn: psycopg.Connection, key: str, conv: UUID | None = None) -> int:
    """Queue what the canon generation `key` has not read (Q3), for one chat or all. Idempotent; queued jobs of other
    canon generations become obsolete."""
    with conn.transaction():
        conn.execute("UPDATE job SET status = 'obsolete', updated_at = now() WHERE kind = 'canon' AND status = 'queued'"
                     " AND payload->>'generation' IS DISTINCT FROM %s AND (%s::uuid IS NULL OR conversation_id = %s)",
                     (key, conv, conv))
        return conn.execute(
            "WITH wanted AS (" + WANTED + ")"
            " INSERT INTO job (kind, dedupe_key, conversation_id, payload, priority)"
            " SELECT 'canon', 'canon:' || w.rid || ':' || w.wtag || ':' || %(gen)s, w.conv,"
            "        jsonb_build_object('revision_id', w.rid::text, 'generation', %(gen)s), %(priority)s"
            " FROM wanted w ORDER BY w.conv, w.key " + REQUEUE,
            {"conv": conv, "gen": key, "priority": PRIORITY, "macro": MACRO_SQL}).rowcount


def requeue(conn: psycopg.Connection, conv: UUID) -> int:
    """A per-chat rebuild (D22) discarded this chat's canon extractions too: its canon jobs become obsolete, so
    `schedule` queues them again."""
    return conn.execute("UPDATE job SET status = 'obsolete', locked_at = NULL, updated_at = now()"
                        " WHERE kind = 'canon' AND conversation_id = %s AND status <> 'running'", (conv,)).rowcount


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


def _source(conn: psycopg.Connection, rid: UUID) -> dict[str, Any] | None:
    """A canon revision with its key and what the canon in force says of it; None when it is not in force now (a newer
    text replaced it before its job ran)."""
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
    name = entries.get("card:name")
    character = None
    if name is not None:
        found = conn.execute(
            "SELECT sr.content FROM source_object so JOIN source_revision sr ON sr.source_object_id = so.id"
            " WHERE so.conversation_id = %s AND so.host_logical_id = 'canon:card:name' AND sr.revision_hash = %s",
            (row["conversation_id"], name["hash"])).fetchone()
        character = found["content"].strip() if found else None
    user = ((entries.get("persona") or {}).get("metadata") or {}).get("name")  # the manifest's, so reads are its own
    named_ = (row["metadata"] or {}).get("named")
    if named_ is None:
        named_ = bool(MACRO.search(row["content"]))
    return {"id": row["id"], "key": key, "conversation_id": row["conversation_id"],
            "metadata": entry.get("metadata") or {}, "character": character, "user": user if user else None,
            "wtag": names_tag(row["entries"]) if named_ else "plain"}


def process(conn: psycopg.Connection, job: dict[str, Any], complete: Callable[[str, str], tuple[Any, ...]],
            gen: Generation) -> str:
    """Read one canon revision (every part not read yet) and store its facts. Returns the final job status."""
    from .extraction import ASSERTION_COLUMNS, normalize  # the same normalizer as a turn's (ADR 0013, D6, D19)

    if job["payload"].get("generation") != gen.key:
        raise ValueError(f"job generation {job['payload'].get('generation')} is not handler generation {gen.key}")
    rid = UUID(job["payload"]["revision_id"])
    src = _source(conn, rid)
    if src is None:
        return "obsolete"
    text = named(normtext.get(conn, rid)["clean_content"], src["character"], src["user"])
    pieces, unread = parts(text)
    done = {r["window_hash"] for r in conn.execute(
        "SELECT window_hash FROM extraction WHERE source_revision_id = %s AND extractor_key = %s"
        " AND discarded_at IS NULL", (rid, gen.key)).fetchall()}
    count = len(pieces) or 1
    system = PROMPT.format(registry=registry_prompt(PREDICATES))
    total = 0
    for i, piece in enumerate(pieces or [""]):
        window = f"canon:{i}:{src['wtag']}"
        if window in done:
            continue
        if len(piece) < MIN_CHARS:
            parsed, raw, usage = {"assertions": []}, "", NO_CALL
        else:
            parsed, raw, usage = metered(complete, system, build_prompt(src["key"], src["metadata"], src["character"],
                                                                        src["user"], piece, i, len(pieces)))
        items = parsed.get("assertions")
        if not isinstance(items, list):
            raise LLMError("model reply has no `assertions` list")
        rows = normalize(items, piece)
        for a in rows:
            if a["status"] == "valid" and a["predicate"] not in PREDICATES:
                a["status"], a["reason"] = "pending", "not a canon predicate"
        coverage = {"chars": len(text), "part": i, "parts": count, "part_chars": len(piece), "unread_chars": unread}
        with conn.transaction():
            xid = uuid7()
            inserted = conn.execute(
                "INSERT INTO extraction (id, source_revision_id, window_hash, compiler_version, extractor_key, model,"
                " raw, coverage, members, hints, usage) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                " ON CONFLICT DO NOTHING RETURNING id",
                (xid, rid, window, VERSION, gen.key, gen.model, Jsonb({"reply": raw[:20000]}), Jsonb(coverage), [rid],
                 Jsonb({"canon": src["key"], "character": src["character"], "user": src["user"]}),
                 Jsonb(usage) if usage is not None else None)).fetchone()
            if inserted is None:
                continue
            values = [(xid, rid, *(Jsonb(a[c]) if c == "participants" and a[c] is not None else a[c]
                                   for c in ASSERTION_COLUMNS)) for a in rows]
            if values:
                with conn.cursor() as cur:
                    cur.executemany(
                        f"INSERT INTO assertion (extraction_id, source_revision_id, {', '.join(ASSERTION_COLUMNS)})"
                        f" VALUES ({', '.join(['%s'] * (2 + len(ASSERTION_COLUMNS)))})", values)
        total += len(rows)
    log.info("canon read conversation=%s key=%s parts=%d assertions=%d unread_chars=%d", src["conversation_id"],
             src["key"], len(pieces), total, unread)
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
    SELECT e.key, e.ord, sr.id AS rid, CASE WHEN """ + NAMED + """ THEN e.tag ELSE 'plain' END AS wtag
    FROM e JOIN source_object so ON so.conversation_id = %(conv)s AND so.host_logical_id = 'canon:' || e.key
                                AND so.source_kind = 'canon'
    JOIN source_revision sr ON sr.source_object_id = so.id AND sr.revision_hash = e.hash
    WHERE EXISTS (SELECT 1 FROM extraction x WHERE x.source_revision_id = sr.id)
),
live AS (
    SELECT r.key, r.ord, r.rid, x.id AS xid, x.window_hash, x.extractor_key, x.compiler_version,
           first_value(x.extractor_key) OVER (PARTITION BY r.rid
               ORDER BY x.extractor_key = %(gen)s DESC, g.activated_at DESC, g.key) AS chosen
    FROM r JOIN extraction x ON x.source_revision_id = r.rid AND split_part(x.window_hash, ':', 3) = r.wtag
    JOIN projection_generation g ON g.key = x.extractor_key AND g.kind = 'canon'
    -- as of `at` for a replay; with no `at`, as of the request's transaction start (now(), the database's clock and
    -- the instant its trace records), so an extraction committed during the request is read by neither it nor a replay
    WHERE x.created_at <= coalesce(%(at)s::timestamptz, now())
      AND (x.discarded_at IS NULL OR x.discarded_at > coalesce(%(at)s::timestamptz, now()))
)
SELECT a.id, a.subject, a.subject_type, a.predicate, a.object, a.object_type, a.value, a.epistemic, a.confidence,
       a.evidence, a.knowledge, a.known_by, a.hidden_from, a.polarity, a.modality, a.source, a.asserted_by, a.salience,
       a.participants::text AS participants, a.outcome, a.because,
       l.key AS canon, l.extractor_key AS generation, l.compiler_version AS compiler, l.rid
FROM live l JOIN assertion a ON a.extraction_id = l.xid
WHERE l.extractor_key = l.chosen AND a.status = 'valid'
ORDER BY l.ord, l.window_hash, a.id
"""


# The host's blocks (H20, ADR 0047 amendment 2): `{{#if …}}`, `{{#if_pure …}}`, `{{#when …}}`, `{{#each …}}` and
# `{{#func name …}}` show their body only for some values of the chat's variables, or not as written; `{{#pure}}`,
# `{{#pure_display}}`, `{{#code}}` and `{{#escape…}}` show it; `{{/…}}` closes the innermost block. The model reads a
# text with every branch, so a fact read inside a conditional body may come from a branch the host never shows.
TAG = re.compile(r"\{\{#([^{}]*)(\}\})?|\{\{/(?!/)[^{}]*\}\}")  # an opener's head (to a brace), or a closer
CHUNK = 12  # characters of evidence (spaces removed) looked for at a time
CACHED = 4096
# Per revision: its raw text without spaces (casefolded), where each of those characters stands, and its conditional
# spans; None for a text without them. Per revision and evidence: the verdict. A revision's content never changes.
Blocks = tuple[str, list[int], list[tuple[int, int]]]
_texts: dict[UUID, Blocks | None] = {}
_verdicts: dict[tuple[UUID, str], bool] = {}


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


def _blocks(conn: psycopg.Connection, rids: set[UUID]) -> dict[UUID, Blocks | None]:
    """The blocks of each revision in `rids`, read once per process. The raw content is read, not a normalized text,
    so a verdict does not depend on the normalizer (a replay of an older generation reads the same)."""
    known = {r: _texts[r] for r in rids if r in _texts}
    missing = [r for r in rids if r not in known]
    if missing:
        found = {row["id"]: blocks_of(row["content"]) for row in conn.execute(
            "SELECT id, content FROM source_revision WHERE id = ANY(%s) AND content LIKE '%%{{#%%'",
            (missing,)).fetchall()}
        fresh = {r: found.get(r) for r in missing}
        _texts.update(fresh)  # published whole: another request sees a revision's blocks or nothing
        known.update(fresh)
        for old in list(_texts)[:max(0, len(_texts) - CACHED)]:
            _texts.pop(old, None)
    return known


def shown(blocks: Blocks | None, rid: UUID, evidence: str | None) -> bool:
    """Whether a canon fact is served: its text has no conditional block, or its evidence is found outside them at
    least as often as only inside (in pieces of CHUNK characters, spaces and case ignored, since the model quotes the
    text with names in place of the macros). Evidence found nowhere is not served (fail closed)."""
    if blocks is None:
        return True
    verdict = _verdicts.get((rid, evidence or ""))
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
        verdict = outside > 0 and outside >= inside
        _verdicts[(rid, evidence or "")] = verdict
        for old in list(_verdicts)[:max(0, len(_verdicts) - CACHED * 4)]:
            _verdicts.pop(old, None)
    return verdict


def rows(conn: psycopg.Connection, conv: UUID, mid: str | None, key: str | None,
         known_at: datetime | None = None) -> list[dict[str, Any]]:
    """The canon facts of manifest `mid` as a read takes them (ADR 0047): before turn 0, in the manifest's key order,
    without those read inside a conditional block (amendment 2)."""
    if not mid or not key:
        return []
    # Prepared at its first use on a connection: planning it takes longer than running it (PHASE-14 step 6).
    out = conn.execute(ROWS, {"conv": conv, "mid": mid, "gen": key, "macro": MACRO_SQL,
                              "at": known_at}, prepare=True).fetchall()
    blocks = _blocks(conn, {a["rid"] for a in out})
    out = [a for a in out if shown(blocks[a["rid"]], a.pop("rid"), a["evidence"])]
    for i, a in enumerate(out):
        a.update(position=POSITION_BASE + i, turn=-1, turn_hash=f"canon:{a['canon']}",
                 host_logical_id=f"canon:{a['canon']}", listed_hash=None, participants=None)
        if a["known_by"] or a["hidden_from"]:
            stored_knowledge(a)
    return out


def coverage(conn: psycopg.Connection, key: str | None, conv: UUID) -> dict[str, Any]:
    """How much of the chat's canon in force the canon generation has read (Q3; the Inspector shows the calls made):
    texts to read, read, queued and failed; the model calls made; characters left unread."""
    if not key:
        return {}
    rows_ = conn.execute(
        "SELECT f.key, rd.calls, rd.parts, rd.unread,"
        "  (SELECT j.status FROM job j WHERE j.dedupe_key = 'canon:' || f.rid || ':' || f.wtag || ':' || %(gen)s) AS job"
        " FROM (" + IN_FORCE + ") f CROSS JOIN LATERAL " + READ + " rd",
        {"conv": conv, "gen": key, "macro": MACRO_SQL}).fetchall()
    return {"wanted": len(rows_), "read": sum(1 for r in rows_ if r["parts"] and r["calls"] >= r["parts"]),
            "pending": sum(1 for r in rows_ if r["job"] in ("queued", "running")),
            "failed": sum(1 for r in rows_ if r["job"] == "dead"),
            "calls": sum(r["calls"] for r in rows_), "unread_chars": sum(r["unread"] or 0 for r in rows_),
            "keys": {r["key"]: {"calls": r["calls"], "job": r["job"]} for r in rows_}}
