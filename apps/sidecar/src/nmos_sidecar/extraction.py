"""Bounded LLM extraction per turn (D5, D6, D7, ADR 0008): job enqueueing, claiming and processing.

The request path only enqueues. The worker holds no transaction while waiting for the model.
Jobs and extractions are bound to an extractor generation (D20): a worker only runs jobs for the
generation its handler implements, and facts only come from the active generation.
"""

from __future__ import annotations

import json
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
from .entities import UNNAMED, norm, resolve
from .facts import fact_text, links_of, persona_of, served_assertions
from .predicates import (REGISTRY, alias_evidenced, fill_types, knowledge, participants, registry_prompt, salience,
                         semantics, validate)
from .threads import PREDICATES as THREAD_PREDICATES, fold as fold_threads
from .reconcile import Entry, RevKey, turn_layout

log = logging.getLogger("nmos.extraction")

COMPILER_VERSION = "extract-v10"  # v2: known_by / hidden_from; v3: knowledge scope (D19); v4: per turn (ADR 0008);
#                                 v5: polarity, modality, source, also_called (ADR 0012, ADR 0013);
#                                 v6: destroyed (PHASE-6, ADR 0017);
#                                 v7: promises actual, fulfilled, OPEN PROMISES, event salience (PHASE-7);
#                                 v8: typed participants `with` (PHASE-8, ADR 0021);
#                                 v9: salience by what an event changes, revealed names (ADR 0024);
#                                 v10: addresses, speech level and form of address (ADR 0028)
MIN_CONTENT_CHARS = 12
MAX_ATTEMPTS = 5
TARGET_CHARS = 6000  # normalized chars of each target-turn message the model sees (#13)
CONTEXT_CHARS = 2000  # per context message
RECENT_PRIORITY, HISTORY_PRIORITY = 250, 900  # generation rebuild: recent window first, then history
OPEN_PROMISES = 8  # open promise threads shown to the model (PHASE-7 Q3)

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
- `value` is a short phrase in the chat's language: write it in the TARGET turn's language even when
  these instructions are in English, and never translate names. `evidence` is a short quote from the
  TARGET turn.
- Give `subject_type`, and `object_type` whenever `object` is set, from the entity types above.
- `epistemic`: "stated" if explicit, "implied" if strongly implied. Skip jokes, OOC text, UI/status
  boilerplate, and anything that only restates earlier facts.
- `polarity`: "negative" when the TARGET turn says the relation does not hold or no longer holds (lost,
  gave away, left, is not, did not); otherwise "positive". For a loss, give the relation that ended
  with "negative" (e.g. possesses, negative).
- `destroyed` only when the TARGET turn ends an item's existence or use: burned, torn to pieces, eaten,
  drunk, used up, shattered beyond use. Not when it is only damaged, hidden, dropped or lost (a loss is
  possesses, negative).
- `modality`: "actual" for what happens or is true in the story; "hypothetical" for plans, intentions,
  conditions, questions and speculation that have not happened; "dreamed" for dreams, visions and
  imagination; "unknown" when the text does not settle it. Label these instead of skipping them when
  they matter to the story.
- `source`: "narration" for the story's own narration, including the user's description of their
  character's actions; "character_claim" for something a character says or writes in the story, with
  `asserted_by` set to that character. A statement in dialogue is a claim even if it is probably true.
- Unnamed characters: a character the TARGET turn shows without a name is named by a short description
  in the chat's language that starts with "?" (e.g. "?검은 망토의 남자"). If UNNAMED CHARACTERS are listed
  and the TARGET turn, read with CONTEXT, shows that one of them is a character it names, add
  `also_called`: the name as subject, the listed description exactly as listed as value.
- `also_called` only when the TARGET turn itself gives both names for the same entity (e.g. "하나(Hana)"),
  or for an unnamed character it reveals (above).
- `promised` when a character makes a promise. A promise that was made is "actual", although what it
  promises lies in the future; "hypothetical" only when making the promise is itself only considered.
- If OPEN PROMISES are listed: `fulfilled` (subject: who made the promise; value: its text exactly as
  listed) when the TARGET turn carries one out; `promised` with "negative" (subject, object and value as
  listed) when the TARGET turn breaks or withdraws one, or its recipient releases it. Not when a
  promise is only mentioned, remembered or still pending.
- `addresses` when the TARGET turn settles how one character speaks to or calls another from now on:
  they agree or decide to speak informally or formally, someone asks for or allows a form of address,
  or a new form of address is used for the first time and taken up. `value`: the speech level and the
  form of address in the chat's language (e.g. "반말, '유우마'라고 부름", "존댓말(해요체), '유우마 씨'라고
  부름"). One assertion per direction (A to B and B to A are separate). It is narration when the TARGET
  turn shows it, although the evidence is dialogue. Not for a reply that merely uses some speech level
  without anyone deciding, asking or remarking on it: a slip is not a change. A change back is a new
  `addresses` with the new value. Record the turning point as an `event` as well.
- `salience`, for `event` only. "major" when the event changes the story from then on, whether it
  happens in action or only in words:
  a confession, an admission of guilt or responsibility, a secret or a hidden identity revealed (when a
  character confesses or admits something, the confession itself is a narrated event of the TARGET turn,
  besides any fact about the past act it tells of);
  a betrayal, a death, a first meeting;
  a change in how two characters treat or address each other (formal to informal speech, a new form of
  address, a first kiss or embrace, a relationship accepted or allowed);
  a decision that changes a relationship, a goal or a plan;
  a power, ability or nature shown for the first time, or an incident others must now deal with (an
  accident, an explosion, an important object destroyed, a result that changes someone's status or
  plans); record such an incident itself as an event, with whoever caused it or is most affected as
  subject.
  "minor" for routine and scene business: meals, chores, travel, small talk, repeated gestures, the
  next step of an activity already under way. Judge by what the event changes, not by how physical or
  dramatic it looks.
- `with`, for `event`, `goal`, `knows` and `destroyed` only: the other characters or groups the value
  is about (who received, who was attacked or helped, who is with the subject, who something is kept
  from), each as {{"name": "...", "type": "character|group"}}, named as the TARGET turn names them.
  Never the subject or object again, never a place or item, never someone the TARGET turn does not
  name. Being there does not mean knowing: `with` says who is involved, not who knows (that is
  `known_by`). Use [] when nobody else is involved.
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
"asserted_by": "... or null", "salience": "major|minor (event only)",
"with": [{{"name": "...", "type": "character|group"}}], "epistemic": "stated",
"confidence": 0.0-1.0, "evidence": "...",
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
            SELECT am.commit_id, am.position, am.turn, sr.id, sr.metadata, so.conversation_id,
                   c.host_persona_name
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
        target["links"] = links_of(conn, target["conversation_id"])  # the owner's (ADR 0025): hints use them
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


def earlier_assertions(conn: psycopg.Connection, ctx: dict[str, Any], key: str) -> list[dict[str, Any]]:
    """The head's served assertions before the target turn, read like facts: active sources only, one
    generation per turn."""
    target = ctx["target"]
    return [r for r in served_assertions(conn, target["commit_id"], key)
            if r["predicate"] in REGISTRY and r["turn"] is not None and r["turn"] < target["turn"]]


def entity_hints(conn: psycopg.Connection, ctx: dict[str, Any], key: str, limit: int,
                 rows: list[dict[str, Any]] | None = None) -> list[dict[str, str]]:
    """Entities mentioned on the head before the target turn, most recently mentioned first, at most
    `limit` (ADR 0012, item 5). The persona is left out under any of its names (ADR 0023): the prompt names
    it already. Since `extract-v9` a typed participant is a mention too (ADR 0024): a character first shown
    without a name is often only a participant, and a later turn can reveal its name only if it is listed."""
    target = ctx["target"]
    if rows is None:
        rows = earlier_assertions(conn, ctx, key)
    if limit <= 0 or not rows:
        return []
    r = resolve(target["conversation_id"], rows, persona_of(target.get("host_persona_name")), target.get("links") or ())
    last: dict[str, int] = {}
    seen: dict[str, list[dict[str, Any]]] = {}  # entity id → the rows that mention it, in order
    seq = 0
    for row in rows:  # position order: a later mention, or the object after the subject, is more recent
        named = [(row.get("subject_type"), row["subject"]), (row.get("object_type"), row.get("object"))]
        named += [(p["type"], p["name"]) for p in row.get("participants") or ()]
        for kind, name in named:
            e = r.entity(kind, name) if name else None
            if e and not e["persona"]:
                seq += 1
                last[e["id"]] = seq
                seen.setdefault(e["id"], []).append(row)
    by_id = {e["id"]: e for e in r.entities()}
    out = []
    for eid in sorted(last, key=last.__getitem__, reverse=True)[:limit]:
        e = by_id[eid]
        hint = {"name": e["name"], "type": e["type"]}
        if others := [n for n in e["names"] if n != e["name"]]:
            hint["also"] = others
        if unnamed(hint):  # what it looked like: the context window may have cut that turn (ADR 0024)
            hint["seen"] = [{"turn": row.get("turn"), "fact": fact_text(row)[:120],
                             "evidence": str(row.get("evidence") or "")[:160]} for row in described(seen[eid])]
        out.append(hint)
    return out


def promise_hints(ctx: dict[str, Any], rows: list[dict[str, Any]], limit: int = OPEN_PROMISES) -> list[dict[str, Any]]:
    """Open promise threads before the target turn whose maker or recipient the prompt names (in a
    message or as its speaker), newest first, at most `limit` (PHASE-7 Q3). The persona is always in the
    story, so it does not count as named."""
    if limit <= 0 or not rows:
        return []
    r = resolve(ctx["target"]["conversation_id"], rows, persona_of(ctx["target"].get("host_persona_name")),
                ctx["target"].get("links") or ())
    threads = [t for t in fold_threads([dict(row) for row in rows if row["predicate"] in THREAD_PREDICATES], r)[0]
               if t["status"] == "open"]
    shown = norm(" ".join(f"{_speaker(row['metadata'])}: {row['content']}" for row in ctx["context"] + ctx["members"]))
    out = []
    for t in threads:
        names = set()
        for kind, name in (("character", t["by"]), ("character", t.get("to"))):
            e = r.entity(kind, name) if name else None
            names |= {norm(n) for n in (e["names"] if e else [name] if name else [])}
        names = {n for n in names - r.persona_names if len(n) >= 2}
        if any(n in shown for n in names):
            out.append({"by": t["by"], "to": t.get("to"), "text": t["text"], "turn": t["turn"]})
    return out[:limit]


DESCRIBING = ("has_trait", "identity", "has_status")


def described(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """At most two rows about an unnamed character for its hint: the latest that describes it (trait,
    identity, status), then the latest of any kind."""
    picked = [r for r in reversed(rows) if r["predicate"] in DESCRIBING][:1]
    if rows[-1] not in picked:
        picked.append(rows[-1])
    return picked


def unnamed(hint: dict[str, Any]) -> bool:
    """A character known only by descriptions so far: every name it goes by starts with "?"."""
    return hint["type"] == "character" and all(n.startswith(UNNAMED) for n in [hint["name"], *hint.get("also", [])])


def hints_block(hints: list[dict[str, Any]]) -> list[str]:
    """KNOWN ENTITIES, and apart from them the characters shown so far without a name, so the model
    checks each one against the target turn (ADR 0024)."""
    lines = []
    if named := [h for h in hints if not unnamed(h)]:
        lines += ["KNOWN ENTITIES (names already used in this story):"]
        lines += [f"- {' / '.join([h['name'], *h.get('also', [])])} ({h['type']})" for h in named] + [""]
    if nameless := [h for h in hints if unnamed(h)]:
        lines += ["UNNAMED CHARACTERS (shown earlier without a name; say who one is if the TARGET turn reveals it):"]
        for h in nameless:
            lines.append(f"- {' / '.join([h['name'], *h.get('also', [])])}")
            for seen in h.get("seen") or ():
                lines.append(f"  seen in turn {seen['turn']}: {seen['fact']}"
                             + (f' ("{seen["evidence"]}")' if seen.get("evidence") else ""))
        lines.append("")
    return lines


def promises_block(promises: list[dict[str, Any]]) -> list[str]:
    if not promises:
        return []
    lines = ["OPEN PROMISES (made earlier in this story, not yet kept or broken):"]
    lines += [f"- {p['by']}" + (f" → {p['to']}" if p.get("to") else "") + f": {p['text']} (turn {p['turn']})"
              for p in promises]
    return lines + [""]


def build_prompt(ctx: dict[str, Any], hints: list[dict[str, Any]] | None = None,
                 promises: list[dict[str, Any]] | None = None) -> str:
    lines = hints_block(hints or []) + promises_block(promises or []) + ["CONTEXT:"]
    for row in ctx["context"]:
        lines.append(f"[turn {row['turn']}] {_speaker(row['metadata'])}: {row['content'][:CONTEXT_CHARS]}")
    if len(lines) == 1:
        lines.append("(none)")
    lines += ["", f"TARGET turn {ctx['target']['turn']}:"]
    lines += [f"{_speaker(row['metadata'])}: {row['content'][:TARGET_CHARS]}" for row in ctx["members"]]
    if nameless := [h["name"] for h in hints or [] if unnamed(h)]:
        lines += ["", "Before answering, check each UNNAMED CHARACTER: " + ", ".join(nameless) + ". If the TARGET"
                  " turn shows that one is a character it names, add {\"subject\": \"<that name>\","
                  " \"predicate\": \"also_called\", \"value\": \"<the description as listed>\"}."]
    return "\n".join(lines)


def coverage_of(ctx: dict[str, Any]) -> dict[str, int]:
    """How much of the normalized target turn/context the model saw (#13)."""
    sizes = [len(r["content"]) for r in ctx["members"]]
    return {"target_chars": sum(sizes), "target_used": sum(min(n, TARGET_CHARS) for n in sizes),
            "target_messages": len(sizes), "context_messages": len(ctx["context"]),
            "context_truncated": sum(1 for r in ctx["context"] if len(r["content"]) > CONTEXT_CHARS)}


ASSERTION_COLUMNS = ("subject", "subject_type", "predicate", "object", "object_type", "value", "epistemic",
                     "confidence", "evidence", "status", "reason", "knowledge", "known_by", "hidden_from",
                     "polarity", "modality", "source", "asserted_by", "salience", "participants")


def normalize(items: list[Any], turn_text: str, hints: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Model output → assertion rows (at most 40): missing entity types filled from the reply or the
    hints (`fill_types`), registry validation (D6), knowledge scope (D19), polarity/modality/source
    (ADR 0013) and the alias evidence check (ADR 0012, ADR 0024). Pure, so the real-model evaluation
    (`tools/eval_extraction_model.py`) applies exactly what the worker does."""
    out = []
    for item, inferred in fill_types(items[:40], hints):
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
        if status == "valid" and item.get("predicate") == "also_called" and not alias_evidenced(item, turn_text, hints):
            status, reason = "pending", "alias not stated in the turn"
        if status == "valid" and unclaimed:
            status, reason = "pending", unclaimed
        for extra in (note, inferred):
            if extra:
                reason = f"{reason}; {extra}" if reason else extra
        out.append({"subject": text("subject", 120) or "?", "subject_type": text("subject_type", 20),
                    "predicate": text("predicate", 40) or "?", "object": text("object", 120),
                    "object_type": text("object_type", 20), "value": text("value"),
                    "epistemic": "implied" if item.get("epistemic") == "implied" else "stated",
                    "confidence": confidence, "evidence": text("evidence"), "status": status, "reason": reason,
                    "knowledge": scope, "known_by": known_by, "hidden_from": hidden_from, "polarity": polarity,
                    "modality": modality, "source": source, "asserted_by": asserted_by, "salience": salience(item),
                    "participants": participants(item) if status == "valid" else None})
    return out


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
    promises: list[dict[str, Any]] = []
    if sum(len(r["content"]) for r in ctx["members"]) < MIN_CONTENT_CHARS:
        parsed, raw = {"assertions": []}, ""
    else:
        limit = gen.spec.get("hints", 0)
        earlier = earlier_assertions(conn, ctx, gen.key)
        hints = entity_hints(conn, ctx, gen.key, limit, earlier) if limit > 0 else None
        promises = promise_hints(ctx, earlier)
        parsed, raw = complete(SYSTEM_PROMPT.format(registry=registry_prompt()), build_prompt(ctx, hints, promises))
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
             None if hints is None and not promises else Jsonb({"entities": hints or [], "promises": promises})),
        ).fetchone()
        if inserted is None:
            return "done"
        rows = [(extraction_id, revision_id, *(Jsonb(a[c]) if c == "participants" and a[c] is not None else a[c]
                                               for c in ASSERTION_COLUMNS))
                for a in normalize(items, turn_text, hints)]
        if rows:
            with conn.cursor() as cur:
                cur.executemany(
                    f"INSERT INTO assertion (extraction_id, source_revision_id, {', '.join(ASSERTION_COLUMNS)})"
                    f" VALUES ({', '.join(['%s'] * (2 + len(ASSERTION_COLUMNS)))})",
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
        SELECT h.conv, h.head, h.n, h.turns, am.position, am.turn, am.turn_hash, sr.id AS rid
        FROM heads h
        JOIN active_membership am ON am.commit_id = h.head
        JOIN source_revision sr ON sr.id = am.source_revision_id
        WHERE sr.lifecycle = 'accepted'
          AND coalesce(sr.metadata->>'isComment', 'false') <> 'true'
          AND coalesce(sr.metadata->>'disabled', '') NOT IN ('true', 'allBefore')
    )
"""

# An earlier generation still serves turn e: one of its extractions matches the head (ADR 0014).
OLDER_SERVES = """EXISTS (SELECT 1 FROM active_membership t
                   JOIN extraction x ON x.source_revision_id = t.source_revision_id
                                    AND x.window_hash = t.turn_hash
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
