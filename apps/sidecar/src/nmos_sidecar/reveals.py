"""Reveal checks (Phase 22, PHASE-22 Q1–Q4, ADR 0057): did a character find out a secret in a turn extracted before it?

A turn extracted before an earlier turn's secret was could not report finding it out: OPEN SECRETS listed nothing
(K29). "Extract all history" used to discard such a turn's extraction and extract the turn again, a new model call that
worded every fact anew and dropped some (AGE-25). It now keeps the extraction and asks a reveal check: one small call
with the turn's OPEN SECRETS, CONTEXT and TARGET, answered with `secrets` only and checked as a turn extraction's
(`extraction.revealed`).

A check is stored as canon facts are (ADR 0047): an extraction of a generation of its own kind, `reveal`, against the
turn's anchor revision under the window `reveal:<turn hash>`, its hints naming the extraction it checked (`checks`) and
the secrets it listed. A read serves its `learned` rows with the turn while the extraction it checked is the one
serving the turn (`facts.ACTIVE_ASSERTIONS`): a rebuild, a re-extraction after a join's undo or a new extractor
generation serves the turn with another extraction, and the check stops counting with it. A later check of the same
turn replaces the earlier one, whatever its generation (one live check per turn), listing every secret still open
before the turn.
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
from .extraction import (ASSERTION_COLUMNS, COMPILER_VERSION, CONTEXT_CHARS, HISTORY_PRIORITY, TARGET_CHARS,
                         build_prompt, coverage_of, earlier_assertions, load_context, normalize, revealed, secret_hints,
                         shown_target)
from .generations import Generation
from .ids import uuid7
from .llm import NO_CALL, LLMError, metered
from .secrets import NOT_SECRETS

log = logging.getLogger("nmos.reveals")

VERSION = "reveal-v1"
WINDOW = "reveal:"  # + the turn hash: a window no turn has, so nothing that reads a turn's extractions takes a check

PROMPT = """You check one turn of a role-play chat for secrets found out, for the chat's long-term memory.
OPEN SECRETS lists what was kept from someone earlier in the story (S1, S2, …): what it is, who knows it, and whom it
is kept from. CONTEXT is the turns before the TARGET turn, shown only so you understand it.

Report in `secrets` each listed secret that a character it is kept from finds out in the TARGET turn itself: told it,
overhearing it, seeing it happen, catching the holders at it, or plainly working it out. `found_out_by` names only
characters the secret is kept from, as listed; `evidence` quotes the TARGET turn. A hint, a related remark, a suspicion
or a guess is not finding out, and neither is something found out in CONTEXT. Most turns reveal none: then
"secrets": [].

Answer with JSON only: {"secrets": [{"secret": "S1", "found_out_by": ["..."], "evidence": "..."}]}"""


def generation(settings: Settings) -> Generation | None:
    """The reveal generation the settings describe (credentials excluded), or None when extraction is off. It uses the
    extraction model and endpoint, and the extractor's context settings (PHASE-22 Q2); its key names every part that
    changes its output (Q3)."""
    if not (settings.llm_url and settings.llm_model):
        return None
    return generations.make(
        "reveal", settings.llm_url, settings.llm_model, version=VERSION, prompt=generations.fingerprint(PROMPT),
        compiler=COMPILER_VERSION, normalizer=normtext.NORMALIZER_VERSION,  # its input and its answer's check
        json_mode=settings.llm_json_mode, temperature=0, context_turns=settings.extract_turns,
        target_chars=TARGET_CHARS, context_chars=CONTEXT_CHARS)


# A stored secret, as secrets.is_secret reads one.
IS_SECRET = """s.status = 'valid' AND s.knowledge = 'limited' AND cardinality(s.hidden_from) > 0
    AND s.predicate <> ALL(%(not_secrets)s) AND coalesce(s.modality, 'actual') <> 'dreamed'"""

# Turns of the head whose extraction of `key` needs a check of the reveal generation `rkey` (K29, audit G2, ADR 0057):
# - its extraction was made, and its check (if any) read its OPEN SECRETS, before a secret of an earlier turn could be
#   listed (`seen`: when the turn last looked for reveals);
# - its check is another reveal generation's (the latest check of a turn is the one served, item 3);
# - its check listed a secret as kept from someone whom an earlier turn found it out for (a reveal served now: of that
#   turn's extraction of `key` or of its latest check): two workers checked them at once, in either order, and the
#   listing may have given one of its at most OPEN_SECRETS slots to that secret. Judged by what the check listed, not by
#   when it was stored.
UNCHECKED = """
WITH anchor AS (
    SELECT am.turn, am.source_revision_id AS rid, am.turn_hash
    FROM conversation c JOIN active_membership am ON am.commit_id = c.head_commit_id
    WHERE c.id = %(conv)s AND am.turn_hash IS NOT NULL
),
checked AS (  -- each turn's live check: the latest made (one per turn since review 2026-10-01; ADR 0057 amendment 1)
    SELECT DISTINCT ON (a.turn) a.turn, r.id, r.hints, r.extractor_key AS rkey,
           coalesce((r.hints->>'read_at')::timestamptz, r.created_at) AS read_at
    FROM anchor a JOIN extraction r ON r.source_revision_id = a.rid AND r.window_hash = %(window)s || a.turn_hash
    WHERE r.discarded_at IS NULL
    ORDER BY a.turn, r.created_at DESC, r.id DESC
),
cur AS (
    SELECT a.turn, a.rid, a.turn_hash, x.id AS xid, x.created_at, k.id AS check_id, k.rkey,
           greatest(x.created_at, k.read_at) AS seen
    FROM anchor a JOIN extraction x ON x.source_revision_id = a.rid AND x.window_hash = a.turn_hash
    LEFT JOIN checked k ON k.turn = a.turn AND k.hints->>'checks' = x.id::text
    WHERE x.extractor_key = %(key)s AND x.discarded_at IS NULL
),
found AS (  -- reveals served now, by the turn that made them: the turn's extraction of `key` and its latest check
    SELECT c.turn, s.subject, s.value FROM cur c
    JOIN assertion s ON s.extraction_id IN (c.xid, c.check_id)
    WHERE s.status = 'valid' AND s.predicate = 'learned'
),
stale AS (  -- checks that listed a secret as kept from someone an earlier turn found it out for
    SELECT DISTINCT c.check_id AS id FROM cur c JOIN checked k ON k.id = c.check_id
    CROSS JOIN LATERAL jsonb_array_elements(k.hints->'secrets') h
    JOIN found f ON f.turn < c.turn AND f.value = '[turn ' || (h->>'turn') || '] ' || (h->>'text')
                AND h->'kept_from' ? f.subject
),
secret_turn AS (
    SELECT DISTINCT c.turn, c.rid, c.turn_hash FROM cur c JOIN assertion s ON s.extraction_id = c.xid WHERE """ + IS_SECRET + """
),
shown AS (  -- when each such turn's content, with a secret, could be listed: one span per extraction, any generation
    SELECT DISTINCT st.turn, y.created_at AS since, y.discarded_at AS until
    FROM secret_turn st JOIN extraction y ON y.source_revision_id = st.rid AND y.window_hash = st.turn_hash
    WHERE EXISTS (SELECT 1 FROM assertion s WHERE s.extraction_id = y.id AND """ + IS_SECRET + """)
)
SELECT t.turn, t.rid, t.turn_hash, t.xid FROM cur t
WHERE EXISTS (
    SELECT 1 FROM secret_turn st
    WHERE st.turn < t.turn AND NOT EXISTS (
        SELECT 1 FROM shown v WHERE v.turn = st.turn AND v.since < t.seen AND (v.until IS NULL OR v.until > t.seen)))
   OR t.check_id IS NOT NULL AND (t.rkey <> %(rkey)s OR t.check_id IN (SELECT id FROM stale))
ORDER BY t.turn
"""


def unchecked(conn: psycopg.Connection, key: str, rkey: str, conv: UUID) -> list[dict[str, Any]]:
    """Turns of the head whose extraction of `key` needs a check of the reveal generation `rkey` (UNCHECKED)."""
    return conn.execute(UNCHECKED, {"conv": conv, "key": key, "rkey": rkey, "window": WINDOW,
                                    "not_secrets": sorted(NOT_SECRETS)}).fetchall()


def schedule(conn: psycopg.Connection, key: str, extractor_key: str, conv: UUID) -> int:
    """Per-chat "extract all history" (PHASE-22 Q1, Q4): queue a check of each turn that needs one, at background
    priority, so `extraction.claim` takes them oldest first. A turn already queued or running is left alone; one checked
    before, which needs a check again, is queued again. Idempotent."""
    turns = unchecked(conn, extractor_key, key, conv)
    if not turns:
        return 0
    with conn.transaction():
        return conn.execute(
            """
            INSERT INTO job (kind, dedupe_key, conversation_id, payload, priority)
            SELECT 'reveal', 'reveal:' || t.xid || ':' || %(key)s, %(conv)s,
                   jsonb_build_object('extraction_id', t.xid::text, 'revision_id', t.rid::text,
                                      'window_hash', t.turn_hash, 'generation', %(key)s),
                   %(priority)s
            FROM unnest(%(xids)s::uuid[], %(rids)s::uuid[], %(hashes)s::text[], %(turns)s::int[]) AS t(xid, rid, turn_hash, turn)
            ORDER BY t.turn
            ON CONFLICT (dedupe_key) DO UPDATE SET status = 'queued', priority = EXCLUDED.priority, attempts = 0,
                run_after = now(), locked_at = NULL, last_error = NULL, updated_at = now()
            WHERE job.status IN ('done', 'obsolete', 'dead')
            """,
            {"key": key, "conv": conv, "priority": HISTORY_PRIORITY, "xids": [t["xid"] for t in turns],
             "rids": [t["rid"] for t in turns], "hashes": [t["turn_hash"] for t in turns],
             "turns": [t["turn"] for t in turns]},
        ).rowcount


def coverage(conn: psycopg.Connection, key: str | None, conv: UUID) -> dict[str, int]:
    """This chat's checks of `key`: queued or running, failed, and made (live)."""
    if key is None:
        return {"pending": 0, "failed": 0, "checked": 0}
    jobs = {r["status"]: r["n"] for r in conn.execute(
        "SELECT status, count(*) AS n FROM job WHERE kind = 'reveal' AND conversation_id = %s"
        " AND payload->>'generation' = %s AND status IN ('queued', 'running', 'dead') GROUP BY status",
        (conv, key)).fetchall()}
    checked = conn.execute(
        "SELECT count(*) AS n FROM extraction x JOIN source_revision sr ON sr.id = x.source_revision_id"
        " JOIN source_object so ON so.id = sr.source_object_id"
        " WHERE so.conversation_id = %s AND x.extractor_key = %s AND x.discarded_at IS NULL", (conv, key)).fetchone()["n"]
    return {"pending": jobs.get("queued", 0) + jobs.get("running", 0), "failed": jobs.get("dead", 0), "checked": checked}


def process(conn: psycopg.Connection, job: dict[str, Any], complete: Callable[[str, str], tuple[Any, ...]],
            gen: Generation, turns: int) -> str:
    """Check one turn (PHASE-22 Q2). Returns the final job status."""
    payload = job["payload"]
    if payload.get("generation") != gen.key:
        raise ValueError(f"job generation {payload.get('generation')} is not handler generation {gen.key}")
    checked = UUID(payload["extraction_id"])
    revision_id, turn_hash = UUID(payload["revision_id"]), payload["window_hash"]
    base = conn.execute("SELECT extractor_key FROM extraction WHERE id = %s AND discarded_at IS NULL",
                        (checked,)).fetchone()
    if base is None:
        return "obsolete"  # a rebuild or a re-extraction replaced the extraction; its turn is extracted again
    ctx = load_context(conn, revision_id, turn_hash, turns, base["extractor_key"])
    if ctx is None:
        return "obsolete"  # the head changed; the turn is extracted again
    read_at = conn.execute("SELECT clock_timestamp() AS t").fetchone()["t"]  # when it looked (UNCHECKED's `seen`)
    secrets = secret_hints(ctx, earlier_assertions(conn, ctx, base["extractor_key"]))
    if not secrets:
        parsed, raw, usage = {"secrets": []}, "", NO_CALL  # nothing open before the turn: checked without a call
    else:
        parsed, raw, usage = metered(complete, PROMPT, build_prompt(ctx, None, None, secrets, None))
        if not isinstance(parsed.get("secrets"), list):  # retried, then counted failed
            raise LLMError("model reply has no `secrets` list")
    turn_text = "\n".join(r["content"] for r in ctx["members"])
    items = revealed(parsed, secrets, turn_text)
    with conn.transaction():
        # Still this worker's job (as process_extract), and still the turn's extraction?
        if job.get("locked_at") is not None and conn.execute(
                "SELECT 1 FROM job WHERE id = %s AND status = 'running' AND locked_at = %s FOR UPDATE",
                (job["id"], job["locked_at"])).fetchone() is None:
            return "obsolete"
        if conn.execute("SELECT 1 FROM extraction WHERE id = %s AND discarded_at IS NULL FOR SHARE",
                        (checked,)).fetchone() is None:
            return "obsolete"
        window = WINDOW + turn_hash  # one live check per turn, whatever its generation (ADR 0057 amendment 1):
        # workers of two generations may store the same turn's at once, so replace under a lock of the turn's window
        conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 57))", (f"{revision_id}:{window}",))
        conn.execute("UPDATE extraction SET discarded_at = now() WHERE source_revision_id = %s AND window_hash = %s"
                     " AND discarded_at IS NULL", (revision_id, window))
        check_id = uuid7()
        conn.execute(
            "INSERT INTO extraction (id, source_revision_id, window_hash, compiler_version, extractor_key, model, raw,"
            " coverage, members, hints, usage) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (check_id, revision_id, window, VERSION, gen.key, gen.model, Jsonb({"reply": raw[:20000]}),
             Jsonb(coverage_of(ctx)), [r["id"] for r in ctx["members"]],
             Jsonb({"checks": str(checked), "secrets": secrets, "read_at": read_at.isoformat()}),
             Jsonb(usage) if usage is not None else None))
        rows = [(check_id, revision_id, *(Jsonb(a[c]) if c == "participants" and a[c] is not None else a[c]
                                          for c in ASSERTION_COLUMNS))
                for a in normalize(items, turn_text, None, shown_target(ctx))]
        if rows:
            with conn.cursor() as cur:
                cur.executemany(
                    f"INSERT INTO assertion (extraction_id, source_revision_id, {', '.join(ASSERTION_COLUMNS)})"
                    f" VALUES ({', '.join(['%s'] * (2 + len(ASSERTION_COLUMNS)))})",
                    rows,
                )
    log.info("reveal check turn=%s revision=%s secrets=%d reveals=%d", ctx["target"]["turn"], revision_id,
             len(secrets), len(rows))
    return "done"
