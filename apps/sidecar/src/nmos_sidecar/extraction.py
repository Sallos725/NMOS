"""Bounded LLM extraction (D5, D6, D7): job enqueueing, claiming and processing.

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
from .predicates import REGISTRY, registry_prompt, validate
from .reconcile import Entry, RevKey, window_hashes

log = logging.getLogger("nmos.extraction")

COMPILER_VERSION = "extract-v2"  # v2: known_by / hidden_from
MIN_CONTENT_CHARS = 12
MAX_ATTEMPTS = 5
TARGET_CHARS = 6000  # normalized chars of the target message the model sees (#13)
CONTEXT_CHARS = 2000  # per context message
RECENT_PRIORITY, HISTORY_PRIORITY = 250, 900  # generation rebuild: recent window first, then history

SYSTEM_PROMPT = """You extract durable story facts for the long-term memory of a role-play chat.
You are given recent CONTEXT messages and ONE TARGET message. Extract only facts that the TARGET
message establishes or changes; use CONTEXT only to resolve who/what is meant.

Allowed predicates (anything else is rejected):
{registry}

Entity types: character, place, item, group, concept.
Rules:
- Name entities exactly as the story does (keep the chat's language). The user's persona is "{{{{user}}}}"
  only if no name is given.
- `value` is a short phrase in the chat's language. `evidence` is a short quote from the TARGET.
- `epistemic`: "stated" if explicit, "implied" if strongly implied. Skip speculation, jokes, OOC text,
  UI/status boilerplate, and anything that only restates earlier facts.
- Prefer few, high-value facts. An empty list is a good answer for small talk.
- Knowledge: `known_by` lists who knows or witnessed the fact (use names; include "{{{{user}}}}" when the
  user's character knows). `hidden_from` lists characters it is explicitly kept from (a whispered
  secret, a hidden identity, something done while others were away). Use [] when everyone present
  knows or it is unclear. Never guess about characters who are not in the story.

Answer with JSON only: {{"assertions": [{{"subject": "...", "subject_type": "...", "predicate": "...",
"object": "... or null", "object_type": "... or null", "value": "... or null", "epistemic": "stated",
"confidence": 0.0-1.0, "evidence": "...", "known_by": [], "hidden_from": []}}]}}"""


def enqueue_after_apply(
    conn: psycopg.Connection,
    conv_id: UUID,
    old_head: list[Entry] | None,
    old_lifecycle: dict[RevKey, str],
    manifest: list[Entry],
    new_lifecycle: dict[RevKey, str],
    ids: dict[RevKey, UUID],
    window: int,
    backfill: int,
    extractor_key: str | None = None,
    embed_key: str | None = None,
    embed_backfill: int = 2000,
) -> int:
    """Queue extraction (and embedding) for (revision, window) pairs that became eligible with this sync.

    Eligible = accepted, not a comment, not disabled. Pairs that were already eligible under the
    previous head are skipped; on first sight of a chat only the latest `backfill` positions are queued.
    """
    def eligible(entries: list[Entry], lifecycle: dict[RevKey, str]) -> dict[tuple[RevKey, str], int]:
        wins = window_hashes([e.key for e in entries], window)
        return {
            (e.key, wins[i]): i for i, e in enumerate(entries)
            if lifecycle.get(e.key) == "accepted" and not e.is_comment and e.disabled not in (True, "allBefore")
        }

    now = eligible(manifest, new_lifecycle)
    before = eligible(old_head, old_lifecycle) if old_head else {}
    fresh = [(pair, pos) for pair, pos in now.items() if pair not in before]
    rows = []
    priority = 100 if old_head is not None else 200  # live turns before backfill
    for (key, win), pos in fresh:
        rev = ids[key]
        first_sight = old_head is None
        if extractor_key and not (first_sight and pos < len(manifest) - backfill):
            rows.append(("extract", f"extract:{rev}:{win}:{extractor_key}", conv_id,
                         Jsonb({"revision_id": str(rev), "window_hash": win, "generation": extractor_key}), priority))
        if embed_key and not (first_sight and pos < len(manifest) - embed_backfill):
            # Embeddings depend on content only; they run first because recall uses them directly.
            rows.append(("embed", f"embed:{rev}:{embed_key}", conv_id,
                         Jsonb({"revision_id": str(rev), "generation": embed_key}), priority - 50))
    if rows:
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO job (kind, dedupe_key, conversation_id, payload, priority) VALUES (%s, %s, %s, %s, %s)"
                " ON CONFLICT (dedupe_key) DO NOTHING",
                rows,
            )
    return len(rows)


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
        conn.execute("UPDATE job SET status = %s, locked_at = NULL, updated_at = now() WHERE id = %s", (status, job_id))


def fail(conn: psycopg.Connection, job: dict[str, Any], error: str) -> None:
    dead = job["attempts"] >= MAX_ATTEMPTS
    with conn.transaction():
        conn.execute(
            "UPDATE job SET status = %s, locked_at = NULL, last_error = %s, updated_at = now(),"
            " run_after = now() + make_interval(secs => %s) WHERE id = %s",
            ("dead" if dead else "queued", error[:1000], min(600, 15 * 2 ** job["attempts"]), job["id"]),
        )


def load_context(conn: psycopg.Connection, revision_id: UUID, window_hash: str, window: int,
                 extractor_key: str) -> dict[str, Any] | None:
    """Target revision + previous `window` head members, or None if the head no longer shows this window."""
    with conn.transaction():
        target = conn.execute(
            """
            SELECT am.commit_id, am.position, sr.id, sr.metadata, so.conversation_id
            FROM active_membership am
            JOIN conversation c ON c.head_commit_id = am.commit_id
            JOIN source_revision sr ON sr.id = am.source_revision_id
            JOIN source_object so ON so.id = sr.source_object_id
            WHERE am.source_revision_id = %s AND am.window_hash = %s
            """,
            (revision_id, window_hash),
        ).fetchone()
        if target is None:
            return None
        context = conn.execute(
            """
            SELECT am.position, sr.id, sr.metadata FROM active_membership am
            JOIN source_revision sr ON sr.id = am.source_revision_id
            WHERE am.commit_id = %s AND am.position >= %s AND am.position < %s ORDER BY am.position
            """,
            (target["commit_id"], target["position"] - window, target["position"]),
        ).fetchall()
        done = conn.execute(
            "SELECT 1 FROM extraction WHERE source_revision_id = %s AND window_hash = %s AND extractor_key = %s",
            (revision_id, window_hash, extractor_key),
        ).fetchone()
        # Model input is the normalized projection (#9), the same text lexical recall and embeddings see.
        for row in [target, *context]:
            row["content"] = normtext.get(conn, row["id"])["clean_content"]
    return {"target": target, "context": context, "done": bool(done)}


def _speaker(meta: dict[str, Any]) -> str:
    return meta.get("name") or ("USER" if meta.get("role") == "user" else "CHARACTER")


def build_prompt(ctx: dict[str, Any]) -> str:
    lines = ["CONTEXT:"]
    for row in ctx["context"]:
        if row["metadata"].get("isComment") or row["metadata"].get("disabled") in (True, "true"):
            continue
        lines.append(f"[turn {row['position']}] {_speaker(row['metadata'])}: {row['content'][:CONTEXT_CHARS]}")
    if len(lines) == 1:
        lines.append("(none)")
    t = ctx["target"]
    lines += ["", f"TARGET [turn {t['position']}] {_speaker(t['metadata'])}:", t["content"][:TARGET_CHARS]]
    return "\n".join(lines)


def coverage_of(ctx: dict[str, Any]) -> dict[str, int]:
    """How much of the normalized target/context the model saw (#13)."""
    target = len(ctx["target"]["content"])
    return {"target_chars": target, "target_used": min(target, TARGET_CHARS), "context_messages": len(ctx["context"]),
            "context_truncated": sum(1 for r in ctx["context"] if len(r["content"]) > CONTEXT_CHARS)}


def process_extract(conn: psycopg.Connection, job: dict[str, Any], complete: Callable[[str, str], tuple[dict, str]],
                    gen: Generation, window: int) -> str:
    """Returns the final job status."""
    if job["payload"].get("generation") != gen.key:
        # claim() never hands a handler another generation's job; refuse rather than mislabel output.
        raise ValueError(f"job generation {job['payload'].get('generation')} is not handler generation {gen.key}")
    revision_id = UUID(job["payload"]["revision_id"])
    window_hash = job["payload"]["window_hash"]
    ctx = load_context(conn, revision_id, window_hash, window, gen.key)
    if ctx is None:
        return "obsolete"  # the head changed; a newer job covers the new window
    if ctx["done"]:
        return "done"
    if len(ctx["target"]["content"]) < MIN_CONTENT_CHARS:
        parsed, raw = {"assertions": []}, ""
    else:
        parsed, raw = complete(SYSTEM_PROMPT.format(registry=registry_prompt()), build_prompt(ctx))
    items = parsed.get("assertions")
    if not isinstance(items, list):
        items = []
    with conn.transaction():
        extraction_id = uuid7()
        inserted = conn.execute(
            "INSERT INTO extraction (id, source_revision_id, window_hash, compiler_version, extractor_key, model, raw,"
            " coverage) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING RETURNING id",
            (extraction_id, revision_id, window_hash, COMPILER_VERSION, gen.key, gen.model,
             Jsonb({"reply": raw[:20000]}), Jsonb(coverage_of(ctx))),
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
            def names(key: str) -> list[str] | None:
                value = item.get(key)
                if not isinstance(value, list):
                    return None
                out = [str(v).strip()[:60] for v in value if str(v or "").strip()]
                return out[:12] or None

            rows.append((extraction_id, revision_id, text("subject", 120) or "?", text("subject_type", 20),
                         text("predicate", 40) or "?", text("object", 120), text("object_type", 20), text("value"),
                         "implied" if item.get("epistemic") == "implied" else "stated", confidence,
                         text("evidence"), status, reason, names("known_by"), names("hidden_from")))
        if rows:
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO assertion (extraction_id, source_revision_id, subject, subject_type, predicate, object,"
                    " object_type, value, epistemic, confidence, evidence, status, reason, known_by, hidden_from)"
                    " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    rows,
                )
    log.info("extracted revision=%s window=%s assertions=%d", revision_id, window_hash, len(rows))
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
        json_mode=settings.llm_json_mode, temperature=0, window=settings.extract_window,
        target_chars=TARGET_CHARS, context_chars=CONTEXT_CHARS,
    )


# Eligible (revision, window) pairs of every head: accepted, not a comment, not disabled. `n` is the
# head length, so `position >= n - backfill` is the recent window.
ELIGIBLE = """
    heads AS (
        SELECT c.id AS conv, c.head_commit_id AS head,
               (SELECT count(*) FROM active_membership x WHERE x.commit_id = c.head_commit_id) AS n
        FROM conversation c
        WHERE c.head_commit_id IS NOT NULL AND (%(conv)s::uuid IS NULL OR c.id = %(conv)s::uuid)
    ),
    elig AS (
        SELECT h.conv, h.n, am.position, sr.id AS rid, am.window_hash
        FROM heads h
        JOIN active_membership am ON am.commit_id = h.head
        JOIN source_revision sr ON sr.id = am.source_revision_id
        WHERE sr.lifecycle = 'accepted' AND am.window_hash IS NOT NULL
          AND coalesce(sr.metadata->>'isComment', 'false') <> 'true'
          AND coalesce(sr.metadata->>'disabled', '') NOT IN ('true', 'allBefore')
    )
"""


def schedule_generation(conn: psycopg.Connection, key: str, backfill: int, conv: UUID | None = None) -> int:
    """Queue what the active extractor generation is missing (#8). Idempotent.

    Policy: the latest `backfill` eligible messages of each chat first, then — at background priority —
    every older pair that an earlier generation had covered, so an upgrade restores the coverage that
    existed instead of shrinking it to the recent window. Queued jobs of other generations become
    obsolete; their extractions stay for audit.
    """
    with conn.transaction():
        conn.execute("UPDATE job SET status = 'obsolete', updated_at = now() WHERE kind = 'extract'"
                     " AND status = 'queued' AND payload->>'generation' IS DISTINCT FROM %s", (key,))
        return conn.execute(
            "WITH" + ELIGIBLE + """
            INSERT INTO job (kind, dedupe_key, conversation_id, payload, priority)
            SELECT 'extract', 'extract:' || e.rid || ':' || e.window_hash || ':' || %(key)s, e.conv,
                   jsonb_build_object('revision_id', e.rid::text, 'window_hash', e.window_hash, 'generation', %(key)s),
                   CASE WHEN e.position >= e.n - %(n)s THEN %(recent)s ELSE %(history)s END
            FROM elig e
            WHERE NOT EXISTS (SELECT 1 FROM extraction x WHERE x.source_revision_id = e.rid
                                AND x.window_hash = e.window_hash AND x.extractor_key = %(key)s)
              AND (e.position >= e.n - %(n)s
                   OR EXISTS (SELECT 1 FROM extraction x WHERE x.source_revision_id = e.rid
                                AND x.window_hash = e.window_hash AND x.extractor_key IS DISTINCT FROM %(key)s))
            ON CONFLICT (dedupe_key) DO NOTHING
            """,
            {"conv": conv, "key": key, "n": backfill, "recent": RECENT_PRIORITY, "history": HISTORY_PRIORITY},
        ).rowcount


def coverage(conn: psycopg.Connection, key: str | None, conv: UUID | None = None) -> dict[UUID, dict[str, Any]]:
    """Per conversation: how much of the head the active extractor generation has compiled (#8, #13)."""
    rows = conn.execute(
        "WITH" + ELIGIBLE + """
        SELECT e.conv,
               count(*) AS eligible,
               count(*) FILTER (WHERE cur.id IS NOT NULL) AS compiled,
               count(*) FILTER (WHERE cur.id IS NULL AND j.status IN ('queued', 'running')) AS pending,
               count(*) FILTER (WHERE cur.id IS NULL AND j.status = 'dead') AS failed,
               count(*) FILTER (WHERE cur.id IS NULL AND EXISTS (
                   SELECT 1 FROM extraction x WHERE x.source_revision_id = e.rid AND x.window_hash = e.window_hash
                     AND x.extractor_key IS DISTINCT FROM %(key)s)) AS historical_only,
               count(*) FILTER (WHERE (cur.coverage->>'target_used')::int < (cur.coverage->>'target_chars')::int)
                   AS target_truncated
        FROM elig e
        LEFT JOIN extraction cur ON cur.source_revision_id = e.rid AND cur.window_hash = e.window_hash
                                AND cur.extractor_key = %(key)s
        LEFT JOIN job j ON j.dedupe_key = 'extract:' || e.rid || ':' || e.window_hash || ':' || %(key)s
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
