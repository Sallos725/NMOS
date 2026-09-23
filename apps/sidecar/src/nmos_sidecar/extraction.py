"""Bounded LLM extraction per turn (D5, D6, D7, ADR 0008): job enqueueing, claiming and processing.

The request path only enqueues. The worker holds no transaction while waiting for the model.
Jobs and extractions are bound to an extractor generation (D20): a worker only runs jobs for the
generation its handler implements, and facts only come from the active generation.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from . import generations, normtext
from .config import Settings
from .generations import Generation
from .ids import uuid7
from .entities import USER_NAMES, norm, resolve
from .facts import ACTIVE_ASSERTIONS
from .predicates import REGISTRY, alias_evidenced, knowledge, registry_prompt, semantics, validate
from .reconcile import Entry, RevKey, turn_layout

log = logging.getLogger("nmos.extraction")

COMPILER_VERSION = "extract-v5"  # v2: known_by / hidden_from; v3: knowledge scope (D19); v4: per turn (ADR 0008);
#                                 v5: polarity, modality, source, also_called (ADR 0012, ADR 0013)
MIN_CONTENT_CHARS = 12
MAX_ATTEMPTS = 5
TARGET_CHARS = 6000  # normalized chars of each target-turn message the model sees (#13)
CONTEXT_CHARS = 2000  # per context message
RECENT_PRIORITY, HISTORY_PRIORITY = 250, 900  # generation rebuild: recent window first, then history

SYSTEM_PROMPT = """You extract durable story facts for the long-term memory of a role-play chat.
You are given the recent CONTEXT turns and ONE TARGET turn: the user's message(s) and the reply to
them. Extract only facts that the TARGET turn establishes or changes; use CONTEXT only to resolve
who/what is meant. When the reply contradicts, refuses or changes what the user's message attempts or
claims, the reply decides what happened.

Allowed predicates (anything else is rejected):
{registry}

Entity types: character, place, item, group, concept.
Rules:
- If KNOWN ENTITIES are listed, use a listed name when the TARGET turn clearly refers to that entity,
  and a new name when it may be a different one.
- Name entities exactly as the story does (keep the chat's language). The user's persona is "{{{{user}}}}"
  only if no name is given.
- `value` is a short phrase in the chat's language. `evidence` is a short quote from the TARGET turn.
- `epistemic`: "stated" if explicit, "implied" if strongly implied. Skip jokes, OOC text, UI/status
  boilerplate, and anything that only restates earlier facts.
- `polarity`: "negative" when the TARGET turn says the relation does not hold or no longer holds (lost,
  gave away, left, is not, did not); otherwise "positive". For a loss, give the relation that ended
  with "negative" (e.g. possesses, negative).
- `modality`: "actual" for what happens or is true in the story; "hypothetical" for plans, intentions,
  conditions, questions and speculation that have not happened; "dreamed" for dreams, visions and
  imagination; "unknown" when the text does not settle it. Label these instead of skipping them when
  they matter to the story.
- `source`: "narration" for the story's own narration, including the user's description of their
  character's actions; "character_claim" for something a character says or writes in the story, with
  `asserted_by` set to that character. A statement in dialogue is a claim even if it is probably true.
- `also_called` only when the TARGET turn itself gives both names for the same entity (e.g. "하나(Hana)").
- Prefer few, high-value facts. An empty list is a good answer for small talk.
- Knowledge (who in the story is aware of the fact):
  `knowledge` is "public" when it is openly known (said to everyone present, common knowledge in the
  world), "limited" when only some characters know it or it is kept from someone, and "unknown" when
  the messages do not show who knows. Do not guess; "unknown" is a good answer.
  For "limited": `known_by` lists characters shown to know or witness it (names; include "{{{{user}}}}"
  when the user's character knows) and `hidden_from` lists characters it is explicitly kept from (a
  whispered secret, a hidden identity, something done while others were away). Characters not listed
  are unknown, not unaware. Otherwise use [] for both. Never list characters who are not in the story.

Answer with JSON only: {{"assertions": [{{"subject": "...", "subject_type": "...", "predicate": "...",
"object": "... or null", "object_type": "... or null", "value": "... or null", "polarity": "positive|negative",
"modality": "actual|hypothetical|dreamed|unknown", "source": "narration|character_claim",
"asserted_by": "... or null", "epistemic": "stated", "confidence": 0.0-1.0, "evidence": "...",
"knowledge": "public|limited|unknown", "known_by": [], "hidden_from": []}}]}}"""


# A job key names one unit of work (revision, window, generation). If that work was made obsolete
# (generation switched away, provider disabled, head moved) and is wanted again, the row is revived.
REQUEUE = """ON CONFLICT (dedupe_key) DO UPDATE SET status = 'queued', priority = EXCLUDED.priority, attempts = 0,
    run_after = now(), locked_at = NULL, last_error = NULL, updated_at = now() WHERE job.status = 'obsolete'"""


def enqueue_after_apply(
    conn: psycopg.Connection,
    conv_id: UUID,
    old_head: list[Entry] | None,
    old_lifecycle: dict[RevKey, str],
    manifest: list[Entry],
    new_lifecycle: dict[RevKey, str],
    ids: dict[RevKey, UUID],
    turns: int,
    backfill: int,
    extractor_key: str | None = None,
    embed_key: str | None = None,
    embed_backfill: int = 2000,
) -> int:
    """Queue extraction of turns and embedding of messages that became eligible with this sync.

    A turn is eligible once its anchor (last reply) is accepted, i.e. the user continued from it (D5,
    ADR 0008); a message is eligible for embedding when it is accepted, not a comment and not disabled.
    Work that was already eligible under the previous head is skipped. On first sight of a chat only
    the latest `backfill` turns and `embed_backfill` messages are queued.
    """
    def complete_turns(entries: list[Entry], lifecycle: dict[RevKey, str]) -> tuple[dict[tuple[RevKey, str], int], int]:
        """Accepted anchors → turn index, and the number of turns that have a reply."""
        anchored = [(entries[i].key, h, t) for i, (t, h) in enumerate(turn_layout(entries, turns)) if h is not None]
        return ({(key, h): t for key, h, t in anchored if lifecycle.get(key) == "accepted"},
                max((t for _, _, t in anchored), default=-1) + 1)

    def messages(entries: list[Entry], lifecycle: dict[RevKey, str]) -> dict[RevKey, int]:
        return {e.key: i for i, e in enumerate(entries)
                if lifecycle.get(e.key) == "accepted" and not e.is_comment and e.disabled not in (True, "allBefore")}

    first_sight = old_head is None
    priority = 200 if first_sight else 100  # live turns before backfill
    rows = []
    if extractor_key:
        now, count = complete_turns(manifest, new_lifecycle)
        before = complete_turns(old_head, old_lifecycle)[0] if old_head else {}
        for (key, turn_hash), turn in now.items():
            if (key, turn_hash) in before or (first_sight and turn < count - backfill):
                continue
            rev = ids[key]
            rows.append(("extract", f"extract:{rev}:{turn_hash}:{extractor_key}", conv_id,
                         Jsonb({"revision_id": str(rev), "window_hash": turn_hash, "generation": extractor_key}),
                         priority))
    if embed_key:
        now_msgs = messages(manifest, new_lifecycle)
        before_msgs = messages(old_head, old_lifecycle) if old_head else {}
        for key, pos in now_msgs.items():
            if key in before_msgs or (first_sight and pos < len(manifest) - embed_backfill):
                continue
            # Embeddings depend on content only; they run first because recall uses them directly.
            rev = ids[key]
            rows.append(("embed", f"embed:{rev}:{embed_key}", conv_id,
                         Jsonb({"revision_id": str(rev), "generation": embed_key}), priority - 50))
    if rows:
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO job (kind, dedupe_key, conversation_id, payload, priority) VALUES (%s, %s, %s, %s, %s) "
                + REQUEUE,
                rows,
            )
    return len(rows)


def retire(conn: psycopg.Connection, kind: str) -> int:
    """The provider for `kind` was turned off: no queued job of that kind may start (#18). A request
    already in flight finishes; its job keeps the obsolete status."""
    return conn.execute("UPDATE job SET status = 'obsolete', locked_at = NULL, updated_at = now()"
                        " WHERE kind = %s AND status IN ('queued', 'running')", (kind,)).rowcount


def claim(conn: psycopg.Connection, handled: dict[str, str]) -> dict[str, Any] | None:
    """Claim the next job whose (kind, generation) a handler implements; others stay queued."""
    with conn.transaction():
        conn.execute(
            "UPDATE job SET status = 'queued', locked_at = NULL, updated_at = now()"
            " WHERE status = 'running' AND locked_at < now() - interval '10 minutes'"
        )
        return conn.execute(
            """
            UPDATE job SET status = 'running', locked_at = now(), attempts = attempts + 1, updated_at = now()
            WHERE id = (SELECT id FROM job WHERE status = 'queued' AND run_after <= now()
                          AND kind || '|' || coalesce(payload->>'generation', '') = ANY(%s)
                        ORDER BY priority, id DESC FOR UPDATE SKIP LOCKED LIMIT 1)
            RETURNING *
            """,
            ([f"{kind}|{key}" for kind, key in handled.items()],),
        ).fetchone()


def finish(conn: psycopg.Connection, job_id: int, status: str) -> None:
    with conn.transaction():
        conn.execute("UPDATE job SET status = %s, locked_at = NULL, updated_at = now() WHERE id = %s"
                     " AND status = 'running'", (status, job_id))


def fail(conn: psycopg.Connection, job: dict[str, Any], error: str) -> None:
    dead = job["attempts"] >= MAX_ATTEMPTS
    with conn.transaction():
        conn.execute(
            "UPDATE job SET status = %s, locked_at = NULL, last_error = %s, updated_at = now(),"
            " run_after = now() + make_interval(secs => %s) WHERE id = %s AND status = 'running'",
            ("dead" if dead else "queued", error[:1000], min(600, 15 * 2 ** job["attempts"]), job["id"]),
        )


def load_context(conn: psycopg.Connection, revision_id: UUID, turn_hash: str, turns: int,
                 extractor_key: str) -> dict[str, Any] | None:
    """Target turn (anchored at `revision_id`) + the previous `turns` turns of the head, or None if the
    head no longer shows this turn with this context."""
    with conn.transaction():
        target = conn.execute(
            """
            SELECT am.commit_id, am.position, am.turn, sr.id, sr.metadata, so.conversation_id
            FROM active_membership am
            JOIN conversation c ON c.head_commit_id = am.commit_id
            JOIN source_revision sr ON sr.id = am.source_revision_id
            JOIN source_object so ON so.id = sr.source_object_id
            WHERE am.source_revision_id = %s AND am.turn_hash = %s
            """,
            (revision_id, turn_hash),
        ).fetchone()
        if target is None:
            return None
        rows = conn.execute(
            """
            SELECT am.position, am.turn, sr.id, sr.metadata FROM active_membership am
            JOIN source_revision sr ON sr.id = am.source_revision_id
            WHERE am.commit_id = %s AND am.turn >= %s AND am.turn <= %s ORDER BY am.position
            """,
            (target["commit_id"], target["turn"] - turns, target["turn"]),
        ).fetchall()
        done = conn.execute(
            "SELECT 1 FROM extraction WHERE source_revision_id = %s AND window_hash = %s AND extractor_key = %s"
            " AND discarded_at IS NULL",
            (revision_id, turn_hash, extractor_key),
        ).fetchone()
        # Model input is the normalized projection (#9), the same text lexical recall and embeddings see.
        for row in rows:
            row["content"] = normtext.get(conn, row["id"])["clean_content"]
    members = [r for r in rows if r["turn"] == target["turn"]]
    context = [r for r in rows if r["turn"] < target["turn"]]
    return {"target": target, "members": members, "context": context, "done": bool(done)}


def _speaker(meta: dict[str, Any]) -> str:
    return meta.get("name") or ("USER" if meta.get("role") == "user" else "CHARACTER")


def entity_hints(conn: psycopg.Connection, ctx: dict[str, Any], key: str, limit: int) -> list[dict[str, str]]:
    """Entities mentioned on the head before the target turn, most recently mentioned first, at most
    `limit` (ADR 0012, item 5). Read like facts: active sources only, one generation per turn. The
    persona is left out: the prompt names it already."""
    target = ctx["target"]
    rows = [r for r in conn.execute(ACTIVE_ASSERTIONS, {"head": target["commit_id"], "key": key}).fetchall()
            if r["predicate"] in REGISTRY and r["turn"] is not None and r["turn"] < target["turn"]]
    if limit <= 0 or not rows:
        return []
    r = resolve(target["conversation_id"], rows)
    last: dict[str, int] = {}
    seq = 0
    for row in rows:  # position order: a later mention, or the object after the subject, is more recent
        for kind, name in ((row.get("subject_type"), row["subject"]), (row.get("object_type"), row.get("object"))):
            e = r.entity(kind, name) if name else None
            if e and not any(norm(n) in USER_NAMES for n in e["names"]):
                seq += 1
                last[e["id"]] = seq
    by_id = {e["id"]: e for e in r.entities()}
    out = []
    for eid in sorted(last, key=last.__getitem__, reverse=True)[:limit]:
        e = by_id[eid]
        hint = {"name": e["name"], "type": e["type"]}
        if others := [n for n in e["names"] if n != e["name"]]:
            hint["also"] = others
        out.append(hint)
    return out


def hints_block(hints: list[dict[str, Any]]) -> list[str]:
    if not hints:
        return []
    lines = ["KNOWN ENTITIES (names already used in this story):"]
    lines += [f"- {' / '.join([h['name'], *h.get('also', [])])} ({h['type']})" for h in hints]
    return lines + [""]


def build_prompt(ctx: dict[str, Any], hints: list[dict[str, Any]] | None = None) -> str:
    lines = hints_block(hints or []) + ["CONTEXT:"]
    for row in ctx["context"]:
        lines.append(f"[turn {row['turn']}] {_speaker(row['metadata'])}: {row['content'][:CONTEXT_CHARS]}")
    if len(lines) == 1:
        lines.append("(none)")
    lines += ["", f"TARGET turn {ctx['target']['turn']}:"]
    lines += [f"{_speaker(row['metadata'])}: {row['content'][:TARGET_CHARS]}" for row in ctx["members"]]
    return "\n".join(lines)


def coverage_of(ctx: dict[str, Any]) -> dict[str, int]:
    """How much of the normalized target turn/context the model saw (#13)."""
    sizes = [len(r["content"]) for r in ctx["members"]]
    return {"target_chars": sum(sizes), "target_used": sum(min(n, TARGET_CHARS) for n in sizes),
            "target_messages": len(sizes), "context_messages": len(ctx["context"]),
            "context_truncated": sum(1 for r in ctx["context"] if len(r["content"]) > CONTEXT_CHARS)}


def process_extract(conn: psycopg.Connection, job: dict[str, Any], complete: Callable[[str, str], tuple[dict, str]],
                    gen: Generation, turns: int) -> str:
    """Returns the final job status."""
    if job["payload"].get("generation") != gen.key:
        # claim() never hands a handler another generation's job; refuse rather than mislabel output.
        raise ValueError(f"job generation {job['payload'].get('generation')} is not handler generation {gen.key}")
    revision_id = UUID(job["payload"]["revision_id"])
    window_hash = job["payload"]["window_hash"]  # the anchor's turn hash (ADR 0008)
    ctx = load_context(conn, revision_id, window_hash, turns, gen.key)
    if ctx is None:
        return "obsolete"  # the head changed; a newer job covers the new window
    if ctx["done"]:
        return "done"
    hints: list[dict[str, Any]] | None = None
    if sum(len(r["content"]) for r in ctx["members"]) < MIN_CONTENT_CHARS:
        parsed, raw = {"assertions": []}, ""
    else:
        limit = gen.spec.get("hints", 0)
        hints = entity_hints(conn, ctx, gen.key, limit) if limit > 0 else None
        parsed, raw = complete(SYSTEM_PROMPT.format(registry=registry_prompt()), build_prompt(ctx, hints))
    items = parsed.get("assertions")
    if not isinstance(items, list):
        items = []
    turn_text = "\n".join(r["content"] for r in ctx["members"])
    with conn.transaction():
        extraction_id = uuid7()
        inserted = conn.execute(
            "INSERT INTO extraction (id, source_revision_id, window_hash, compiler_version, extractor_key, model, raw,"
            " coverage, members, hints) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
            " ON CONFLICT DO NOTHING RETURNING id",
            (extraction_id, revision_id, window_hash, COMPILER_VERSION, gen.key, gen.model,
             Jsonb({"reply": raw[:20000]}), Jsonb(coverage_of(ctx)), [r["id"] for r in ctx["members"]],
             None if hints is None else Jsonb(hints)),
        ).fetchone()
        if inserted is None:
            return "done"
        rows = []
        for item in items[:40]:
            if not isinstance(item, dict):
                continue
            status, reason = validate(item)

            def text(key: str, limit: int = 300) -> str | None:
                value = item.get(key)
                return str(value).strip()[:limit] if value not in (None, "", "null") else None

            try:
                confidence = float(item.get("confidence")) if item.get("confidence") is not None else None
            except (TypeError, ValueError):
                confidence = None
            scope, known_by, hidden_from, note = knowledge(item)
            polarity, modality, source, asserted_by, unclaimed = semantics(item)
            if status == "valid" and item.get("predicate") == "also_called" and not alias_evidenced(item, turn_text):
                status, reason = "pending", "alias not stated in the turn"
            if status == "valid" and unclaimed:
                status, reason = "pending", unclaimed
            if note:
                reason = f"{reason}; {note}" if reason else note
            rows.append((extraction_id, revision_id, text("subject", 120) or "?", text("subject_type", 20),
                         text("predicate", 40) or "?", text("object", 120), text("object_type", 20), text("value"),
                         "implied" if item.get("epistemic") == "implied" else "stated", confidence,
                         text("evidence"), status, reason, scope, known_by, hidden_from, polarity, modality, source,
                         asserted_by))
        if rows:
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO assertion (extraction_id, source_revision_id, subject, subject_type, predicate, object,"
                    " object_type, value, epistemic, confidence, evidence, status, reason, knowledge, known_by,"
                    " hidden_from, polarity, modality, source, asserted_by)"
                    " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    rows,
                )
    log.info("extracted turn=%s revision=%s assertions=%d", ctx["target"]["turn"], revision_id, len(rows))
    return "done"


def job_counts(conn: psycopg.Connection) -> dict[str, int]:
    return {r["status"]: r["n"] for r in conn.execute("SELECT status, count(*) AS n FROM job GROUP BY status").fetchall()}


def extractor(settings: Settings) -> Generation | None:
    """The extractor generation the settings describe (credentials excluded), or None when off."""
    if not (settings.llm_url and settings.llm_model):
        return None
    return generations.make(
        "extract", settings.llm_url, settings.llm_model,
        compiler=COMPILER_VERSION, prompt=generations.fingerprint(SYSTEM_PROMPT),
        predicates=generations.fingerprint(repr(sorted(REGISTRY.items()))), normalizer=normtext.NORMALIZER_VERSION,
        json_mode=settings.llm_json_mode, temperature=0, unit="turn", context_turns=settings.extract_turns,
        target_chars=TARGET_CHARS, context_chars=CONTEXT_CHARS, hints=settings.extract_hints,
    )


# Eligible head members of every chat: accepted, not a comment, not disabled. `n` is the head length
# and `turns` its number of turns that have a reply, so `position >= n - backfill` / `turn >= turns - backfill` is the
# recent window. Extraction uses the anchors (`turn_hash IS NOT NULL`, ADR 0008), embedding every row.
ELIGIBLE = """
    heads AS (
        SELECT c.id AS conv, c.head_commit_id AS head,
               (SELECT count(*) FROM active_membership x WHERE x.commit_id = c.head_commit_id) AS n,
               (SELECT coalesce(max(x.turn), -1) + 1 FROM active_membership x
                WHERE x.commit_id = c.head_commit_id AND x.turn_hash IS NOT NULL) AS turns
        FROM conversation c
        WHERE c.head_commit_id IS NOT NULL AND (%(conv)s::uuid IS NULL OR c.id = %(conv)s::uuid)
    ),
    elig AS (
        SELECT h.conv, h.head, h.n, h.turns, am.position, am.turn, am.turn_hash, sr.id AS rid, am.window_hash
        FROM heads h
        JOIN active_membership am ON am.commit_id = h.head
        JOIN source_revision sr ON sr.id = am.source_revision_id
        WHERE sr.lifecycle = 'accepted' AND am.window_hash IS NOT NULL
          AND coalesce(sr.metadata->>'isComment', 'false') <> 'true'
          AND coalesce(sr.metadata->>'disabled', '') NOT IN ('true', 'allBefore')
    )
"""

# An earlier generation still serves turn e: one of its extractions matches the head (ADR 0014).
OLDER_SERVES = """EXISTS (SELECT 1 FROM active_membership t
                   JOIN extraction x ON x.source_revision_id = t.source_revision_id
                                    AND x.window_hash IN (t.turn_hash, t.window_hash)
                   JOIN projection_generation g ON g.key = x.extractor_key
                   WHERE t.commit_id = e.head AND t.turn = e.turn AND x.discarded_at IS NULL
                     AND x.extractor_key <> %(key)s)"""

# A rebuild discarded turn e's extractions and nothing serves it yet (D22). A rebuild interrupted before
# its jobs were queued is completed by the next scheduling run.
REBUILD_PENDING = """(EXISTS (SELECT 1 FROM active_membership t
                    JOIN extraction x ON x.source_revision_id = t.source_revision_id
                    WHERE t.commit_id = e.head AND t.turn = e.turn AND x.discarded_at IS NOT NULL)
                AND NOT """ + OLDER_SERVES + """)"""


def schedule_generation(conn: psycopg.Connection, key: str, backfill: int, conv: UUID | None = None,
                        history: bool = False) -> int:
    """Queue what the active extractor generation is missing (#8). Idempotent.

    Policy (ADR 0014): the latest `backfill` complete turns of each chat. Older turns keep being served
    by the earlier generation that covered them, and move to this one only on request: `history` queues
    every older turn at background priority (per-chat "extract all history", D22). A rebuild's discarded
    turns are always queued. Queued jobs of other generations become obsolete; their extractions stay
    for audit and for fallback.
    """
    with conn.transaction():
        conn.execute("UPDATE job SET status = 'obsolete', updated_at = now() WHERE kind = 'extract'"
                     " AND status = 'queued' AND payload->>'generation' IS DISTINCT FROM %s", (key,))
        return conn.execute(
            "WITH" + ELIGIBLE + """
            INSERT INTO job (kind, dedupe_key, conversation_id, payload, priority)
            SELECT 'extract', 'extract:' || e.rid || ':' || e.turn_hash || ':' || %(key)s, e.conv,
                   jsonb_build_object('revision_id', e.rid::text, 'window_hash', e.turn_hash, 'generation', %(key)s),
                   CASE WHEN e.turn >= e.turns - %(n)s THEN %(recent)s ELSE %(history)s END
            FROM elig e
            WHERE e.turn_hash IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM extraction x WHERE x.source_revision_id = e.rid
                                AND x.window_hash = e.turn_hash AND x.extractor_key = %(key)s
                                AND x.discarded_at IS NULL)
              AND (e.turn >= e.turns - %(n)s OR %(all)s OR """ + REBUILD_PENDING + """)
            ORDER BY e.conv, e.turn  -- claim() takes the highest id first: newest turns first
            """ + REQUEUE,
            {"conv": conv, "key": key, "n": backfill, "all": history, "recent": RECENT_PRIORITY,
             "history": HISTORY_PRIORITY},
        ).rowcount


def retry_failed(conn: psycopg.Connection, kind: str, key: str, conv: UUID) -> int:
    """Dead jobs of this chat and generation become obsolete, so the next scheduling run revives them
    (per-chat "extract all history", D22: nothing the chat is missing stays failed)."""
    return conn.execute("UPDATE job SET status = 'obsolete', updated_at = now() WHERE kind = %s AND status = 'dead'"
                        " AND conversation_id = %s AND payload->>'generation' = %s", (kind, conv, key)).rowcount


def discard(conn: psycopg.Connection, conv: UUID) -> int:
    """Per-chat rebuild (D22): this chat's extractions of every generation stop counting (kept for
    audit), so no older generation serves a turn meanwhile (ADR 0014), and its extract jobs become
    obsolete, so `schedule_generation` queues every turn again."""
    with conn.transaction():
        n = conn.execute(
            "UPDATE extraction x SET discarded_at = now() FROM source_revision sr, source_object so"
            " WHERE sr.id = x.source_revision_id AND so.id = sr.source_object_id AND so.conversation_id = %s"
            " AND x.discarded_at IS NULL",
            (conv,),
        ).rowcount
        conn.execute("UPDATE job SET status = 'obsolete', locked_at = NULL, updated_at = now()"
                     " WHERE kind = 'extract' AND conversation_id = %s", (conv,))
    return n


def coverage(conn: psycopg.Connection, key: str | None, conv: UUID | None = None) -> dict[UUID, dict[str, Any]]:
    """Per conversation: how many complete turns of the head the active extractor generation has
    compiled (#8, #13, ADR 0008). `historical_only`: turns it has not compiled that an earlier
    generation still serves (ADR 0014)."""
    rows = conn.execute(
        "WITH" + ELIGIBLE + """
        SELECT e.conv,
               count(*) AS eligible,
               count(*) FILTER (WHERE cur.id IS NOT NULL) AS compiled,
               count(*) FILTER (WHERE cur.id IS NULL AND j.status IN ('queued', 'running')) AS pending,
               count(*) FILTER (WHERE cur.id IS NULL AND j.status = 'dead') AS failed,
               count(*) FILTER (WHERE cur.id IS NULL AND """ + OLDER_SERVES + """) AS historical_only,
               count(*) FILTER (WHERE (cur.coverage->>'target_used')::int < (cur.coverage->>'target_chars')::int)
                   AS target_truncated
        FROM elig e
        LEFT JOIN extraction cur ON cur.source_revision_id = e.rid AND cur.window_hash = e.turn_hash
                                AND cur.extractor_key = %(key)s AND cur.discarded_at IS NULL
        LEFT JOIN job j ON j.dedupe_key = 'extract:' || e.rid || ':' || e.turn_hash || ':' || %(key)s
        WHERE e.turn_hash IS NOT NULL
        GROUP BY e.conv
        """,
        {"conv": conv, "key": key or ""},
    ).fetchall()
    out = {}
    for r in rows:
        stats = {k: r[k] for k in ("eligible", "compiled", "pending", "failed", "historical_only", "target_truncated")}
        stats["not_queued"] = r["eligible"] - r["compiled"] - r["pending"] - r["failed"]
        stats["percent"] = round(100 * r["compiled"] / r["eligible"], 1) if r["eligible"] else 100.0
        stats["complete"] = r["compiled"] == r["eligible"]
        out[r["conv"]] = stats
    return out
