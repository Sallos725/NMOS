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
from .entities import norm
from .extraction import (ASSERTION_COLUMNS, COMPILER_VERSION, CONTEXT_CHARS, HISTORY_PRIORITY, ONTOLOGY,
                         _with_carried, assertion_values, no_nul, build_prompt, coverage_of, earlier_assertions, load_context, normalize,
                         revealed, secret_hints, shown_target, with_cap)
from .generations import Generation
from .ids import uuid7
from .llm import NO_CALL, LLMError, metered
from .predicates import registry_for
from .secrets import NOT_SECRETS, _heads, _split, is_secret, matches, secret_text
from .secrets import _hits as reveal_hits

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
        compiler=COMPILER_VERSION, normalizer=normtext.active(),  # its input and its answer's check
        json_mode=settings.llm_json_mode, context_turns=settings.extract_turns,
        **generations.request_spec(settings.llm_extra_body, settings.llm_no_temperature),
        target_chars=settings.extract_target_chars, context_chars=CONTEXT_CHARS)  # the cap: PHASE-62 S1


# A stored secret, as secrets.is_secret reads one.
IS_SECRET = """s.status = 'valid' AND s.knowledge = 'limited' AND cardinality(s.hidden_from) > 0
    AND s.predicate <> ALL(%(not_secrets)s) AND coalesce(s.modality, 'actual') <> 'dreamed'"""

# Turns of the head whose serving extraction needs a check of the reveal generation `rkey` (K29, audit G2, ADR 0057):
# - its extraction was made, and its check (if any) read its OPEN SECRETS, before a secret an earlier turn holds now
#   could be listed (`seen`: when the turn last looked for reveals). Judged per secret (Tier 2 C5): another extraction of
#   that earlier turn, of any generation, counts only while it held the same secret, so a re-extraction that found a
#   new secret B in a turn that already had A (a Phase 62 cap raise) makes the later turns look again;
# - its check is another reveal generation's (the latest check of a turn is the one served, item 3);
# - its check listed a secret as kept from someone whom an earlier turn found it out for (a reveal served now: of that
#   turn's serving extraction or of its latest check): two workers checked them at once, in either order, and the
#   listing may have given one of its at most OPEN_SECRETS slots to that secret. Judged by what the check listed, not by
#   when it was stored (`stale`, in Python).
# A turn's extraction is the one serving it, as `facts.ACTIVE_ASSERTIONS` chooses it (`chosen_id`, Tier 2 C5): `key`'s,
# else the newest activated generation's, so a turn served by an earlier generation after a carry-on model change
# (PHASE-57) or a cap raise (PHASE-62) is checked too, and a check is made of the extraction a read serves it with. Such a
# turn's secrets count for the turns after it either way; the turn itself is left out while `key`'s extraction of it is
# queued or running ("extract all history" queues every turn `key` has not extracted, before it queues the checks).
_SERVING = """
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
serving AS (  -- ACTIVE_ASSERTIONS' window: `key`'s extraction first, then the newest activated generation's
    SELECT DISTINCT ON (a.turn) a.turn, a.rid, a.turn_hash, x.id AS xid, x.created_at
    FROM anchor a JOIN extraction x ON x.source_revision_id = a.rid AND x.window_hash = a.turn_hash
    JOIN projection_generation g ON g.key = x.extractor_key
    WHERE x.discarded_at IS NULL
    ORDER BY a.turn, x.extractor_key = %(key)s DESC, g.activated_at DESC, g.key, x.created_at DESC, x.id DESC
),
cur AS (
    SELECT s.turn, s.rid, s.turn_hash, s.xid, k.id AS check_id, k.rkey, k.hints->'secrets' AS listed, k.read_at,
           greatest(s.created_at, k.read_at) AS seen
    FROM serving s LEFT JOIN checked k ON k.turn = s.turn AND k.hints->>'checks' = s.xid::text
)"""

UNCHECKED = _SERVING + """
SELECT t.turn, t.rid, t.turn_hash, t.xid, t.check_id, t.listed, t.read_at, t.seen,
       (t.check_id IS NOT NULL AND t.rkey <> %(rkey)s)
       OR EXISTS (  -- the owner reopened an earlier turn's secret after this turn looked (review F11): kept it again,
           SELECT 1 FROM owner_repair r  -- or took back a found-out in force when it looked
           WHERE r.conversation_id = %(conv)s AND coalesce((r.target->>'turn')::int, -1) < t.turn
             AND ((r.kind = 'secret_keep' AND r.created_at > t.seen AND r.removed_at IS NULL)
                  OR (r.kind = 'secret_found_out' AND r.created_at <= t.seen AND r.removed_at > t.seen))) AS needs
FROM cur t
WHERE NOT EXISTS (  -- a turn queued for `key`'s extraction is extracted with what is open by then: no paid check of it
    SELECT 1 FROM job j WHERE j.dedupe_key = 'extract:' || t.rid || ':' || t.turn_hash || ':' || %(key)s
      AND j.status IN ('queued', 'running'))
ORDER BY t.turn
"""

# Each secret a turn's serving extraction holds now (the columns `secrets.secret_text` reads).
_FIELDS = "s.subject, s.predicate, s.object, s.value, s.address_condition, s.hidden_from"
SECRETS_NOW = _SERVING + """
SELECT c.turn, c.rid, c.turn_hash, """ + _FIELDS + """
FROM cur c JOIN assertion s ON s.extraction_id = c.xid WHERE """ + IS_SECRET + """ ORDER BY c.turn, s.id"""
# Every secret any extraction of these turns held, with when that extraction lived.
SECRETS_HELD = """
SELECT y.id AS yid, y.source_revision_id AS rid, y.window_hash AS turn_hash, y.created_at, y.discarded_at, """ + _FIELDS + """
FROM unnest(%(rids)s::uuid[], %(hashes)s::text[]) AS t(rid, h)
JOIN extraction y ON y.source_revision_id = t.rid AND y.window_hash = t.h
JOIN assertion s ON s.extraction_id = y.id WHERE """ + IS_SECRET

# Reveals served now, by the turn that made them: the turn's serving extraction and its latest check, each with the
# hash its listed turn had (as ACTIVE_ASSERTIONS reads `listed_hash`) and when it was stored.
FOUND = _SERVING + """
SELECT c.turn, s.subject, s.value, x.created_at AS stored_at,
       (SELECT h->>'turn_hash' FROM jsonb_array_elements(x.hints->'secrets') h
        WHERE '[turn ' || (h->>'turn') || '] ' || (h->>'text') = s.value LIMIT 1) AS listed_hash
FROM cur c
JOIN assertion s ON s.extraction_id IN (c.xid, c.check_id)
JOIN extraction x ON x.id = s.extraction_id
WHERE s.status = 'valid' AND s.predicate = 'learned'
"""


def _stale(rows: list[dict[str, Any]], found: list[dict[str, Any]]) -> set[UUID]:
    """Checks that listed a secret as kept from someone an earlier turn found it out for. A reveal counts for a listed
    secret when its value is the listing's text (as before Tier 2), or, when it was stored after the check read its
    OPEN SECRETS, when the read side's fold would end that secret with it (`secrets._hits`: a reworded listing of the
    same turn). The second is bounded by time so a check made again, which reads after the reveal, is settled whatever
    the fold made of it: a match looser than the fold's would otherwise queue the turn on every press. Names compare
    as normalized text (a reveal's subject is the name as listed, `extraction.revealed`)."""
    out: set[UUID] = set()
    for t in rows:
        listed = t["listed"] if isinstance(t["listed"], list) else []
        if t["check_id"] is None or not listed:
            continue
        earlier = [f for f in found if f["turn"] < t["turn"]]
        for h in listed:
            if not isinstance(h, dict) or t["check_id"] in out:
                continue
            kept = {norm(n) for n in h.get("kept_from") or () if isinstance(n, str)}
            text = f"[turn {h.get('turn')}] {h.get('text')}"
            pool = [{"text": h.get("text"), "turn": h.get("turn"), "turn_hash": h.get("turn_hash")}]
            for f in earlier:
                if norm(f["subject"]) not in kept:
                    continue
                if f["value"] == text or (t["read_at"] is not None and f["stored_at"] > t["read_at"]
                                          and reveal_hits(pool, f["value"], f["listed_hash"])):
                    out.add(t["check_id"])
                    break
    return out


def _held(secret: dict[str, Any], held: list[dict[str, Any]], now: list[dict[str, Any]], seen: Any) -> bool:
    """Whether an extraction of the secret's turn that was live at `seen` held it, as the read side's fold would take
    a reveal of either for the other (`secrets`' rules, review F10): the same line; the same head with like content
    (`matches`); or the same head when it is the turn's only secret with that head, now and in that extraction (a
    re-extraction that reworded its value). Its `hidden_from` must still cover the secret's: someone new it is kept
    from could not have been listed."""
    text = secret_text(secret)
    head = _split(text)[1]
    alone = sum(1 for s in now if s["rid"] == secret["rid"] and _heads(_split(secret_text(s))[1], head) is True) == 1
    live = [h for h in held if h["rid"] == secret["rid"] and h["turn_hash"] == secret["turn_hash"]
            and h["created_at"] < seen and (h["discarded_at"] is None or h["discarded_at"] > seen)
            and set(h["hidden_from"] or ()) >= set(secret["hidden_from"] or ())]
    for h in live:
        other = secret_text(h)
        if other == text or matches(text, other):
            return True
        same = [x for x in live if x["yid"] == h["yid"] and _heads(_split(secret_text(x))[1], head) is True]
        if alone and len(same) == 1 and same[0] is h:
            return True
    return False


def _carried_since(conn: psycopg.Connection, conv: UUID) -> Any:
    """When the chat's continue link in force was made, if it carries a secret (F7: a turn that looked before it could
    not have listed one); None otherwise."""
    from . import carry  # carry imports facts and canonfacts, which import extraction

    link = carry.in_force(conn, conv)
    if link is None or link.get("mode") != "continue":
        return None
    rows = carry.target_rows(link).rows
    return link["created_at"] if any(is_secret(x) for x in rows if x.get("predicate")) else None


def unchecked(conn: psycopg.Connection, key: str, rkey: str, conv: UUID) -> list[dict[str, Any]]:
    """Turns of the head whose serving extraction (`key`'s first) needs a check of the reveal generation `rkey`
    (UNCHECKED, `_held`): turn, revision, turn hash and the extraction to check (`xid`)."""
    params = {"conv": conv, "key": key, "rkey": rkey, "window": WINDOW, "not_secrets": sorted(NOT_SECRETS)}
    rows = conn.execute(UNCHECKED, params).fetchall()
    stale: set[UUID] = set()
    if any(r["check_id"] is not None and r["listed"] for r in rows):
        stale = _stale(rows, conn.execute(FOUND, params).fetchall())
    now = conn.execute(SECRETS_NOW, params).fetchall() if rows else []
    held = conn.execute(SECRETS_HELD, {"rids": [s["rid"] for s in now], "hashes": [s["turn_hash"] for s in now],
                                       "not_secrets": params["not_secrets"]}).fetchall() if now else []
    carried = _carried_since(conn, conv) if rows else None

    def needs(t: dict[str, Any]) -> bool:
        if t["needs"] or t["check_id"] in stale or (carried is not None and t["seen"] < carried):
            return True
        return any(s["turn"] < t["turn"] and not _held(s, held, now, t["seen"]) for s in now)
    return [{k: r[k] for k in ("turn", "rid", "turn_hash", "xid")} for r in rows if needs(r)]


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
    with_cap(ctx, gen)  # the check reads the TARGET at its own generation's cap (PHASE-62 S1)
    read_at = conn.execute("SELECT clock_timestamp() AS t").fetchone()["t"]  # when it looked (UNCHECKED's `seen`)
    # The earlier turns as a read serves them now: the active extractor's first (Tier 2 C5). The checked extraction
    # may be an earlier generation's that still serves its turn; preferring its key would list the secrets of
    # earlier turns that generation extracted, not the ones served.
    key = generations.active(conn, "extract") or base["extractor_key"]
    # Listed as the serving extractor's worker lists them (review F3): its compiler's registry, so a guise kept from
    # someone (extract-v21) is a secret here too, and for a compiler of ONTOLOGY its solo secrets, ranked by the TARGET.
    spec = conn.execute("SELECT spec FROM projection_generation WHERE key = %s", (key,)).fetchone()
    compiler = (spec["spec"] or {}).get("compiler") if spec else None
    earlier = earlier_assertions(conn, ctx, key, registry_for(compiler))
    carried = ctx["target"].get("carried") or None  # a carried secret is checked as the worker lists it (F7)
    shown = shown_target(ctx)  # the TARGET as the model is shown it: the evidence check reads this (Tier 1 D2)
    onto = {"turn_text": shown, "include_solo": True} if compiler in ONTOLOGY else {}
    secrets = secret_hints(ctx, earlier, carried=carried, **onto)
    resolution = _with_carried(ctx, earlier, carried)[1] if secrets else None  # who a reveal names (Tier 1 C4)
    if not secrets:
        parsed, raw, usage = {"secrets": []}, "", NO_CALL  # nothing open before the turn: checked without a call
    else:
        parsed, raw, usage = metered(complete, PROMPT, build_prompt(ctx, None, None, secrets, None))
        if not isinstance(parsed.get("secrets"), list):  # retried, then counted failed
            raise LLMError("model reply has no `secrets` list")
    turn_text = "\n".join(r["content"] for r in ctx["members"])
    items = revealed(parsed, secrets, shown, resolution)  # as `process_extract` does (Tier 2 C5, D2)
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
            (check_id, revision_id, window, VERSION, gen.key, gen.model, Jsonb({"reply": no_nul(raw[:20000])}),
             Jsonb(coverage_of(ctx)), [r["id"] for r in ctx["members"]],
             Jsonb({"checks": str(checked), "secrets": secrets, "read_at": read_at.isoformat()}),
             Jsonb(usage) if usage is not None else None))
        rows = [(check_id, revision_id, *assertion_values(a))
                for a in normalize(items, turn_text, None, shown)]
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
