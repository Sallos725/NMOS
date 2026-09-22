"""Bounded LLM extraction (D5, D6, D7): job enqueueing, claiming and processing.

The request path only enqueues. The worker holds no transaction while waiting for the model.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from .ids import uuid7
from .packet import clean_text
from .predicates import registry_prompt, validate
from .reconcile import Entry, RevKey, window_hashes

log = logging.getLogger("nmos.extraction")

COMPILER_VERSION = "extract-v1"
MIN_CONTENT_CHARS = 12
MAX_ATTEMPTS = 5

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

Answer with JSON only: {{"assertions": [{{"subject": "...", "subject_type": "...", "predicate": "...",
"object": "... or null", "object_type": "... or null", "value": "... or null", "epistemic": "stated",
"confidence": 0.0-1.0, "evidence": "..."}}]}}"""


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
    extract: bool = True,
    embed_model: str | None = None,
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
    if old_head is None and backfill >= 0:
        fresh = [(pair, pos) for pair, pos in fresh if pos >= len(manifest) - backfill]
    rows = []
    priority = 100 if old_head is not None else 200  # live turns before backfill
    for (key, win), pos in fresh:
        rev = ids[key]
        if extract:
            rows.append(("extract", f"extract:{rev}:{win}:{COMPILER_VERSION}", conv_id,
                         Jsonb({"revision_id": str(rev), "window_hash": win}), priority))
        if embed_model:
            # Embeddings depend on content only; they run first because recall uses them directly.
            rows.append(("embed", f"embed:{rev}:{embed_model}", conv_id, Jsonb({"revision_id": str(rev)}), priority - 50))
    if rows:
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO job (kind, dedupe_key, conversation_id, payload, priority) VALUES (%s, %s, %s, %s, %s)"
                " ON CONFLICT (dedupe_key) DO NOTHING",
                rows,
            )
    return len(rows)


def claim(conn: psycopg.Connection, kinds: tuple[str, ...]) -> dict[str, Any] | None:
    with conn.transaction():
        conn.execute(
            "UPDATE job SET status = 'queued', locked_at = NULL, updated_at = now()"
            " WHERE status = 'running' AND locked_at < now() - interval '10 minutes'"
        )
        return conn.execute(
            """
            UPDATE job SET status = 'running', locked_at = now(), attempts = attempts + 1, updated_at = now()
            WHERE id = (SELECT id FROM job WHERE status = 'queued' AND run_after <= now() AND kind = ANY(%s)
                        ORDER BY priority, id DESC FOR UPDATE SKIP LOCKED LIMIT 1)
            RETURNING *
            """,
            (list(kinds),),
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


def load_context(conn: psycopg.Connection, revision_id: UUID, window_hash: str, window: int) -> dict[str, Any] | None:
    """Target revision + previous `window` head members, or None if the head no longer shows this window."""
    with conn.transaction():
        target = conn.execute(
            """
            SELECT am.commit_id, am.position, sr.content, sr.metadata, so.conversation_id
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
            SELECT am.position, sr.content, sr.metadata FROM active_membership am
            JOIN source_revision sr ON sr.id = am.source_revision_id
            WHERE am.commit_id = %s AND am.position >= %s AND am.position < %s ORDER BY am.position
            """,
            (target["commit_id"], target["position"] - window, target["position"]),
        ).fetchall()
        done = conn.execute(
            "SELECT 1 FROM extraction WHERE source_revision_id = %s AND window_hash = %s AND compiler_version = %s",
            (revision_id, window_hash, COMPILER_VERSION),
        ).fetchone()
    return {"target": target, "context": context, "done": bool(done)}


def _speaker(meta: dict[str, Any]) -> str:
    return meta.get("name") or ("USER" if meta.get("role") == "user" else "CHARACTER")


def build_prompt(ctx: dict[str, Any]) -> str:
    lines = ["CONTEXT:"]
    for row in ctx["context"]:
        if row["metadata"].get("isComment") or row["metadata"].get("disabled") in (True, "true"):
            continue
        lines.append(f"[turn {row['position']}] {_speaker(row['metadata'])}: {clean_text(row['content'])[:2000]}")
    if len(lines) == 1:
        lines.append("(none)")
    t = ctx["target"]
    lines += ["", f"TARGET [turn {t['position']}] {_speaker(t['metadata'])}:", clean_text(t["content"])[:6000]]
    return "\n".join(lines)


def process_extract(conn: psycopg.Connection, job: dict[str, Any], complete: Callable[[str, str], tuple[dict, str]],
                    model_name: str, window: int) -> str:
    """Returns the final job status."""
    revision_id = UUID(job["payload"]["revision_id"])
    window_hash = job["payload"]["window_hash"]
    ctx = load_context(conn, revision_id, window_hash, window)
    if ctx is None:
        return "obsolete"  # the head changed; a newer job covers the new window
    if ctx["done"]:
        return "done"
    if len(clean_text(ctx["target"]["content"])) < MIN_CONTENT_CHARS:
        parsed, raw = {"assertions": []}, ""
    else:
        parsed, raw = complete(SYSTEM_PROMPT.format(registry=registry_prompt()), build_prompt(ctx))
    items = parsed.get("assertions")
    if not isinstance(items, list):
        items = []
    with conn.transaction():
        extraction_id = uuid7()
        inserted = conn.execute(
            "INSERT INTO extraction (id, source_revision_id, window_hash, compiler_version, model, raw)"
            " VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING RETURNING id",
            (extraction_id, revision_id, window_hash, COMPILER_VERSION, model_name, Jsonb({"reply": raw[:20000]})),
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
            rows.append((extraction_id, revision_id, text("subject", 120) or "?", text("subject_type", 20),
                         text("predicate", 40) or "?", text("object", 120), text("object_type", 20), text("value"),
                         "implied" if item.get("epistemic") == "implied" else "stated", confidence,
                         text("evidence"), status, reason))
        if rows:
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO assertion (extraction_id, source_revision_id, subject, subject_type, predicate, object,"
                    " object_type, value, epistemic, confidence, evidence, status, reason)"
                    " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    rows,
                )
    log.info("extracted revision=%s window=%s assertions=%d", revision_id, window_hash, len(rows))
    return "done"


def job_counts(conn: psycopg.Connection) -> dict[str, int]:
    return {r["status"]: r["n"] for r in conn.execute("SELECT status, count(*) AS n FROM job GROUP BY status").fetchall()}



def backfill_jobs(conn: psycopg.Connection, extract: bool, embed_model: str | None, backfill: int) -> int:
    """After enabling or changing a model: queue the latest `backfill` eligible head messages of every chat."""
    total = 0
    eligible = """
        FROM conversation c
        JOIN active_membership am ON am.commit_id = c.head_commit_id
        JOIN source_revision sr ON sr.id = am.source_revision_id
        WHERE sr.lifecycle = 'accepted' AND am.window_hash IS NOT NULL
          AND coalesce(sr.metadata->>'isComment', 'false') <> 'true'
          AND coalesce(sr.metadata->>'disabled', '') NOT IN ('true', 'allBefore')
          AND am.position >= (SELECT count(*) FROM active_membership x WHERE x.commit_id = c.head_commit_id) - %(n)s
    """
    if extract:
        total += conn.execute(
            "INSERT INTO job (kind, dedupe_key, conversation_id, payload, priority)"
            " SELECT 'extract', 'extract:' || sr.id || ':' || am.window_hash || ':' || %(ver)s, c.id,"
            " jsonb_build_object('revision_id', sr.id::text, 'window_hash', am.window_hash), 250" + eligible +
            " ON CONFLICT (dedupe_key) DO NOTHING",
            {"n": backfill, "ver": COMPILER_VERSION},
        ).rowcount
    if embed_model:
        total += conn.execute(
            "INSERT INTO job (kind, dedupe_key, conversation_id, payload, priority)"
            " SELECT 'embed', 'embed:' || sr.id || ':' || %(model)s, c.id,"
            " jsonb_build_object('revision_id', sr.id::text), 200" + eligible +
            " ON CONFLICT (dedupe_key) DO NOTHING",
            {"n": backfill, "model": embed_model},
        ).rowcount
    return total
