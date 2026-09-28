"""Scene summaries and the story so far (PHASE-12, ADR 0042): a rebuildable `summarize` projection.

A scene is a fixed window of WINDOW turns of the head (turns 0–7, 8–15, …; turns as ADR 0008 counts them). It is
summarized once it is complete and LAG more turns have a reply, so the turns still being rerolled or edited are not.
A scene summary is keyed by its window's member revisions in order: an edit, delete, swipe or disable inside the
window gives the window another key, so the old summary stops being current at once (invariant 7) and the window is
queued again. A delete or insert that renumbers turns moves every later window.

The story so far is one summary of the current scene summaries, keyed by their ids in order, made once every due
window has one. A story stays current while every scene it was made from is current, so it keeps serving while the
newest window waits for its summary.

Summaries are derived rows with their generation and members (invariants 2, 10) and never replace raw text
(invariant 1). The worker writes them; nothing here runs on the request path except scheduling.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from xml.sax.saxutils import escape
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from . import generations, normtext
from .config import Settings
from .entities import norm
from .facts import memory_view
from .generations import Generation
from .ids import uuid7
from .llm import LLMError
from .packet import Line
from .threads import similarity

log = logging.getLogger("nmos.summaries")

VERSION = "summarize-v3"  # v2: OPEN SECRETS in the prompt, checked when read (PHASE-12 Q3); v3: late secrets, story
WINDOW = 8  # turns per scene (PHASE-12 Q1)
LAG = 4  # replied turns after a window before it is summarized: the last turns still change
MESSAGE_CHARS = 6000  # normalized chars of each message the model sees, as extraction's target turn
MIN_CONTENT_CHARS = 12
SCENE_CHARS = 1200  # a stored scene summary's cap
STORY_CHARS = 2400
OPEN_SECRETS = 12  # listed in a summary's prompt, newest first
# Secrets stated up to this many turns after a window can be about it: a character's knowledge of an event is often
# extracted a few turns after the event (Phase 12 step 5: one and five turns after, on the owner's chat). A summary
# written before such a secret is held until it is written again with the secret listed.
NEAR = WINDOW
# Trigram containment of a secret's content in a summary, names left out of both, that holds the summary back
# (PHASE-12 Q3). It catches a secret copied into a summary (0.76 in the real-model tier), not one reworded (0.3), and
# a summary that leaves the secret out but keeps its setting ("소라가 잠든 사이 …") scored 0.59 (0.68 with names).
LEAK_MIN = 0.7
# The same check when a character the secret is kept from is in the scene (owner, 2026-09-28, the secret gate): a
# reworded secret scores about 0.3 (a plan told in other words to the one it is kept from: 0.34), and the
# owner's summaries that left every secret out scored below it but for two scenes, which such a scene then goes without.
LEAK_NEAR = 0.3
LIVE_PRIORITY = 300  # after extraction's live and recent work (100–250)
BACKFILL_PRIORITY = 950  # after extraction's history (900); claimed oldest first

SCENE_PROMPT = """You summarize one scene of a role-play chat for its long-term memory. The scene is a run of
consecutive turns, given in order.

Write what happens in it: who is there, what they do and say that matters later, what changes (places, possessions,
relationships, plans, promises), and how the scene ends. Plain past-tense narration in the language of the chat, at
most 5 sentences. Name characters as the chat names them; the user's character is named as the chat names it.
Only what the scene shows: no guesses, no judgments, nothing from before or after it, no out-of-character notes, no
formatting.

If OPEN SECRETS are listed, each is something the characters it is kept from do not know. Never write a secret's
content, not even in other words or as a hint, and leave out the object or act it is about; the summary is read with
those characters present. At most say that the holders keep something from them, or leave the moment out.

Answer with JSON only: {"summary": "..."}"""

STORY_PROMPT = """You write "the story so far" of a role-play chat for its long-term memory, from the summaries of its
scenes, given in order.

Keep what still matters: the main events in order, what changed between the characters, and what is still
unresolved. Plain past-tense narration in the language of the chat, at most 8 sentences. Only what the summaries
say: no guesses, no judgments, no formatting.

If OPEN SECRETS are listed, never write a secret's content, not even in other words or as a hint, and leave out the
object or act it is about: the story is read with the characters it is kept from present.

Answer with JSON only: {"summary": "..."}"""


@dataclass(frozen=True)
class Window:
    index: int
    first_turn: int
    last_turn: int
    members: tuple[UUID, ...]  # member revisions, oldest first
    key: str


def members_key(ids: list[UUID] | tuple[UUID, ...]) -> str:
    return hashlib.sha256("\n".join(str(i) for i in ids).encode()).hexdigest()[:32]


def summarizer(settings: Settings) -> Generation | None:
    """The summarize generation the settings describe (credentials excluded), or None when off. Summaries use the
    extraction model and endpoint (PHASE-12 Q6)."""
    if not (settings.summaries and settings.llm_url and settings.llm_model):
        return None
    return generations.make(
        "summarize", settings.llm_url, settings.llm_model, version=VERSION,
        prompt=generations.fingerprint(SCENE_PROMPT + STORY_PROMPT), normalizer=normtext.NORMALIZER_VERSION,
        json_mode=settings.llm_json_mode, temperature=0, window=WINDOW, lag=LAG, message_chars=MESSAGE_CHARS,
    )


def replied_turns(conn: psycopg.Connection, head: UUID, upto: int | None = None) -> int:
    """Turns of the head (up to position `upto`) that have a reply (their anchor carries a turn hash, ADR 0008)."""
    return conn.execute("SELECT coalesce(max(turn), -1) + 1 AS n FROM active_membership"
                        " WHERE commit_id = %s AND turn_hash IS NOT NULL AND (%s::int IS NULL OR position <= %s::int)",
                        (head, upto, upto)).fetchone()["n"]


def due(turns: int) -> int:
    """How many windows are complete and LAG turns old."""
    return max(0, turns - LAG) // WINDOW


def windows(conn: psycopg.Connection, head: UUID, first: int = 0, upto: int | None = None) -> list[Window]:
    """The due windows of the head (as of position `upto`), from window `first` on."""
    n = due(replied_turns(conn, head, upto))
    if n <= first:
        return []
    rows = conn.execute(
        "SELECT turn, source_revision_id AS rid FROM active_membership WHERE commit_id = %s AND turn >= %s"
        " AND turn < %s ORDER BY position", (head, first * WINDOW, n * WINDOW)).fetchall()
    grouped: dict[int, list[UUID]] = {}
    for r in rows:
        grouped.setdefault(r["turn"] // WINDOW, []).append(r["rid"])
    return [Window(i, i * WINDOW, i * WINDOW + WINDOW - 1, tuple(ids), members_key(ids))
            for i, ids in sorted(grouped.items())]


# A row current at `known_at` (a replay, ADR 0027), or now: written by then and not yet discarded then. A summary written
# again after a late secret discards the old row without changing the head, so a replay from before needs it back.
_AS_OF = ("(%s::timestamptz IS NULL OR created_at <= %s::timestamptz)"
          " AND (discarded_at IS NULL OR (%s::timestamptz IS NOT NULL AND discarded_at > %s::timestamptz))")


def _scenes(conn: psycopg.Connection, conv: UUID, key: str, ws: list[Window],
            known_at: datetime | None = None) -> dict[str, dict[str, Any]]:
    if not ws:
        return {}
    rows = conn.execute(
        "SELECT * FROM summary WHERE conversation_id = %s AND generation = %s AND level = 'scene' AND window_key = ANY(%s)"
        " AND " + _AS_OF, (conv, key, [w.key for w in ws], known_at, known_at, known_at, known_at)).fetchall()
    return {r["window_key"]: r for r in rows}


def current(conn: psycopg.Connection, conv: UUID, head: UUID, key: str | None,
            secrets: list[dict[str, Any]] | None = None, upto: int | None = None,
            known_at: datetime | None = None, present: frozenset[str] = frozenset()) -> dict[str, Any]:
    """What the head's summaries are: each due window with its current summary (or None), and the newest story made
    only from current scene summaries (it may not cover the newest windows yet). With the head's `secrets`
    (facts.memory_view), each summary that repeats one still kept from someone is marked `held`: no packet may use
    it. `upto` and `known_at` read them as an earlier request saw them (ADR 0027 replay)."""
    ws = windows(conn, head, upto=upto) if key else []
    by_key = _scenes(conn, conv, key, ws, known_at) if key else {}
    scenes = [{"window": w, "summary": by_key.get(w.key)} for w in ws]
    ids = [s["summary"]["id"] for s in scenes if s["summary"]]
    story = None
    if ids:
        have = set(ids)
        for row in conn.execute(
                "SELECT * FROM summary WHERE conversation_id = %s AND generation = %s AND level = 'story' AND " + _AS_OF
                + " ORDER BY created_at DESC, id DESC", (conv, key, known_at, known_at, known_at, known_at)).fetchall():
            if row["members"] and set(row["members"]) <= have:
                story = row
                break
    for x in scenes:
        x["held"] = held(x["summary"], secrets, present) if x["summary"] and secrets else []
    return {"scenes": scenes, "story": story, "due": len(ws), "done": len(ids),
            "story_current": bool(story) and len(story["members"]) == len(ids) == len(ws),
            "story_held": held(story, secrets, present) if story and secrets else []}


def inspect(conn: psycopg.Connection, conv: UUID, head: UUID, key: str,
            secrets: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """What the Inspector shows of a chat's summaries (PHASE-12 step 6): `current`, and for each due window and the
    story why a summary is or is not used: its latest job (queued, running, dead with its error); an earlier summary of
    the window from before an edit, swipe or delete in it (`changed`); the secrets it repeats (`leaks`) or was written
    before (`unlisted`, written again); and the secrets that keep it out of a packet only while a character they are
    kept from is in the scene (`near`, ADR 0042 amendment 3)."""
    view = current(conn, conv, head, key, secrets)
    jobs: dict[tuple[str, str], dict[str, Any]] = {}
    story_job = None
    for j in conn.execute(
            "SELECT payload->>'level' AS level, payload->>'window_key' AS window_key, status, attempts, last_error"
            " FROM job WHERE kind = 'summarize' AND conversation_id = %s AND payload->>'generation' = %s"
            " AND status <> 'obsolete' ORDER BY updated_at, id", (conv, key)).fetchall():
        jobs[(j["level"], j["window_key"])] = j  # the newest job of a window (a rewrite reuses its window key)
        if j["level"] == "story":
            story_job = j
    keys = {x["window"].key for x in view["scenes"]}
    earlier = {r["first_turn"] for r in conn.execute(
        "SELECT first_turn, window_key FROM summary WHERE conversation_id = %s AND generation = %s AND level = 'scene'"
        " AND discarded_at IS NULL", (conv, key)).fetchall() if r["window_key"] not in keys}
    secrets = secrets or []
    everyone = frozenset(norm(n) for s in secrets for n in s.get("open") or [])

    def why(row: dict[str, Any] | None) -> dict[str, list[dict[str, Any]]]:
        if row is None or not secrets:
            return {"leaks": [], "unlisted": [], "near": []}
        repeats = leaks(row["text"], secrets)
        return {"leaks": repeats, "unlisted": unlisted(row, secrets),
                "near": [s for s in leaks(row["text"], secrets, everyone) if s not in repeats]}

    for x in view["scenes"]:
        w = x["window"]
        x.update(why(x["summary"]), job=jobs.get(("scene", w.key)),
                 changed=x["summary"] is None and w.first_turn in earlier)
    story = view["story"]
    view["story_why"] = why(story)
    # The story job that matters: one for the story that would replace the shown one, or the only one there is.
    view["story_job"] = story_job if story_job and (story is None or not view["story_current"]
                                                    or view["story_why"]["unlisted"]) else None
    return view


SCENE_MIN = 0.3  # trigram containment of the message in a scene summary that brings that scene (ADR 0043)


def summary_line(level: str, row: dict[str, Any]) -> Line:
    """A summary as a packet line with its provenance (ADR 0027): the summary row, and its text as what a reply can
    echo."""
    turns = f"{row['first_turn']}–{row['last_turn']}"
    return Line("summary", f"    <Summary kind=\"{level}\" turns=\"{turns}\">{escape(row['text'])}</Summary>",
                {"summary": str(row["id"])}, row["last_turn"], f"{level} {turns}: {row['text']}", row["text"])


def packet_lines(conn: psycopg.Connection, conv: UUID, head: UUID, key: str, secrets: list[dict[str, Any]],
                 query: str, before_turn: int | None, upto: int | None = None,
                 known_at: datetime | None = None, present: frozenset[str] = frozenset()) -> list[Line]:
    """What a request offers <Story> (ADR 0043): the story so far, and the scene summary the message is about among
    windows older than the prompt's own messages (`before_turn`). A summary that repeats a secret still kept from
    someone is never offered (PHASE-12 Q3)."""
    view = current(conn, conv, head, key, secrets, upto, known_at, present)
    out: list[Line] = []
    if (story := view["story"]) and story["text"] and not view["story_held"]:
        out.append(summary_line("story", story))
    if query.strip():
        pool = [x["summary"] for x in view["scenes"] if x["summary"] and x["summary"]["text"] and not x.get("held")
                and (before_turn is None or x["window"].last_turn < before_turn)]
        scored = [(similarity(query, s["text"]), s["last_turn"], s) for s in pool]
        best = max(scored, key=lambda x: (x[0], x[1]), default=None)
        if best and best[0] >= SCENE_MIN:
            out.append(summary_line("scene", best[2]))
    return out


# As extraction.REQUEUE: a job made obsolete that is wanted again is revived.
_INSERT = ("INSERT INTO job (kind, dedupe_key, conversation_id, payload, priority) VALUES (%s, %s, %s, %s, %s)"
           " ON CONFLICT (dedupe_key) DO UPDATE SET status = 'queued', priority = EXCLUDED.priority, attempts = 0,"
           " run_after = now(), locked_at = NULL, last_error = NULL, updated_at = now() WHERE job.status = 'obsolete'")


def _scene_job(conv: UUID, key: str, w: Window, priority: int, again: str = "") -> tuple:
    return ("summarize", f"summarize:{key}:{conv}:scene:{w.key}{again}", conv,
            Jsonb({"generation": key, "level": "scene", "window_key": w.key, "first_turn": w.first_turn,
                   "last_turn": w.last_turn}), priority)


def schedule(conn: psycopg.Connection, conv: UUID, head: UUID, key: str, full: bool = True,
             priority: int = LIVE_PRIORITY) -> int:
    """Queue the due windows that have no summary, and the story once every due window has one. Idempotent.

    `full=False` (an append) looks only at the newest due window: an append changes no earlier window. Any other
    commit, and a generation's activation, look at all of them."""
    if full:
        ws = windows(conn, head)
    else:
        n = due(replied_turns(conn, head))
        ws = windows(conn, head, n - 1) if n else []
    have = _scenes(conn, conv, key, ws)
    rows = [_scene_job(conv, key, w, priority) for w in ws if w.key not in have]
    if rows:
        with conn.cursor() as cur:
            cur.executemany(_INSERT, rows)
    elif full:
        return schedule_story(conn, conv, head, key, priority)
    return len(rows)


def _again(missing: list[dict[str, Any]]) -> str:
    """A job key suffix for writing a summary again because of these secrets (its first job is done)."""
    return ":" + members_key(sorted(secret_key(s) for s in missing))[:12] if missing else ""


def schedule_story(conn: psycopg.Connection, conv: UUID, head: UUID, key: str, priority: int = LIVE_PRIORITY,
                   secrets: list[dict[str, Any]] | None = None) -> int:
    """Queue the story of the current scene summaries when every due window has one and no story of them exists, or
    the one that does was written before a secret it must keep (`unlisted`)."""
    view = current(conn, conv, head, key)
    if not view["due"] or view["done"] < view["due"]:
        return 0
    missing = unlisted(view["story"], secrets) if view["story_current"] and secrets else []
    if view["story_current"] and not missing:
        return 0
    ids = [s["summary"]["id"] for s in view["scenes"]]
    story_key = members_key(ids)
    conn.execute(_INSERT, ("summarize", f"summarize:{key}:{conv}:story:{story_key}{_again(missing)}", conv,
                           Jsonb({"generation": key, "level": "story", "window_key": story_key,
                                  "members": [str(i) for i in ids]}), priority))
    return 1


def schedule_stale(conn: psycopg.Connection, conv: UUID, key: str, priority: int = LIVE_PRIORITY) -> int:
    """Queue the summaries written before a secret they must keep, again with it listed (after an extraction that
    may have stated one)."""
    row = conn.execute("SELECT head_commit_id FROM conversation WHERE id = %s", (conv,)).fetchone()
    if row is None or row["head_commit_id"] is None:
        return 0
    head = row["head_commit_id"]
    secrets = head_secrets(conn, head)
    if not secrets:
        return 0
    view = current(conn, conv, head, key)
    rows = [_scene_job(conv, key, x["window"], priority, _again(missing)) for x in view["scenes"]
            if x["summary"] and (missing := unlisted(x["summary"], secrets))]
    if rows:
        with conn.cursor() as cur:
            cur.executemany(_INSERT, rows)
        return len(rows)  # the story follows once they are written
    return schedule_story(conn, conv, head, key, priority, secrets)


def schedule_all(conn: psycopg.Connection, key: str, conv: UUID | None = None) -> int:
    """Everything a generation is missing in every chat (or one), at background priority, newest chats first
    (PHASE-12 Q7): backfill jobs are claimed in the order they are queued."""
    heads = conn.execute("SELECT id, head_commit_id FROM conversation WHERE head_commit_id IS NOT NULL"
                         " AND (%s::uuid IS NULL OR id = %s::uuid) ORDER BY created_at DESC, id DESC",
                         (conv, conv)).fetchall()
    with conn.transaction():
        conn.execute("UPDATE job SET status = 'obsolete', updated_at = now() WHERE kind = 'summarize'"
                     " AND status = 'queued' AND payload->>'generation' IS DISTINCT FROM %s", (key,))
        return sum(schedule(conn, h["id"], h["head_commit_id"], key, priority=BACKFILL_PRIORITY) for h in heads)


def _speaker(meta: dict[str, Any]) -> str:
    return meta.get("name") or ("USER" if meta.get("role") == "user" else "CHARACTER")


def _cut(text: str, cap: int) -> str:
    """At most `cap` characters, ending at a sentence end when there is one in the last third."""
    text = " ".join(text.split())
    if len(text) <= cap:
        return text
    head = text[:cap]
    end = max(head.rfind(p) for p in (". ", "! ", "? ", "다. ", "요. ", "。"))
    return head[:end + 1].rstrip() if end >= cap * 2 // 3 else head.rstrip()


def reply_text(parsed: dict[str, Any], cap: int) -> str:
    text = parsed.get("summary")
    if not isinstance(text, str):  # an answer without one fails the job, so it is retried (as G3 for extraction)
        raise LLMError("model reply has no `summary` text")
    return _cut(text, cap)


def content(secret: dict[str, Any]) -> str:
    """What a secret says, without its head ("하나 knows: …" → "…")."""
    head, sep, body = secret["text"].partition(": ")
    return body if sep else head


def window_secrets(secrets: list[dict[str, Any]], last_turn: int, limit: int = OPEN_SECRETS) -> list[dict[str, Any]]:
    """The secrets a summary up to `last_turn` must keep: stated by NEAR turns after it and still kept from someone,
    newest first."""
    kept = [s for s in secrets
            if s.get("open") and (s.get("turn") if s.get("turn") is not None else -1) <= last_turn + NEAR]
    return sorted(kept, key=lambda s: s.get("position") or 0, reverse=True)[:limit]


def secret_key(secret: dict[str, Any]) -> str:
    return " ".join(content(secret).casefold().split())


def unlisted(row: dict[str, Any], secrets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The secrets a summary must keep that its prompt did not list: stated after it was written. Until it is written
    again with them listed, no packet may use it."""
    listed = (row.get("coverage") or {}).get("secrets")
    listed = set(listed) if isinstance(listed, list) else set()
    return [s for s in window_secrets(secrets, row["last_turn"]) if secret_key(s) not in listed]


def held(row: dict[str, Any], secrets: list[dict[str, Any]], present: frozenset[str] = frozenset()) -> list[dict[str, Any]]:
    """Why a summary may not be used: the secrets it repeats (`leaks`) or was not told about (`unlisted`)."""
    return leaks(row["text"], secrets, present) + unlisted(row, secrets)


def unnamed(text: str, names: list[str]) -> str:
    for name in sorted({n for n in names if n}, key=len, reverse=True):
        text = text.replace(name, " ")
    return text


def leak_score(secret: dict[str, Any], text: str) -> float:
    """How much of a secret's content the text repeats, the names of its holders and of those it is kept from left out
    of both: names and a scene's setting are shared with everything written about it."""
    names = [*secret.get("holders", []), *secret.get("open", [])]
    return similarity(unnamed(content(secret), names), unnamed(text, names))


def leaks(text: str, secrets: list[dict[str, Any]], present: frozenset[str] = frozenset()) -> list[dict[str, Any]]:
    """The secrets still kept from someone whose content the text repeats (PHASE-12 Q3). Checked when a summary is read:
    a secret extracted after the summary was written counts too. With a character it is kept from among `present`
    (the scene's names, normalized) the bar is LEAK_NEAR, low enough to catch a secret said in other words."""
    out = []
    for s in secrets:
        if not s.get("open") or not text:
            continue
        bar = LEAK_NEAR if any(norm(n) in present for n in s["open"]) else LEAK_MIN
        if leak_score(s, text) >= bar:
            out.append(s)
    return out


def secrets_block(secrets: list[dict[str, Any]]) -> list[str]:
    if not secrets:
        return []
    return (["OPEN SECRETS (never write their content):"]
            + [f"- {', '.join(s['holders'])} keep from {', '.join(s['open'])}: {content(s)}" for s in secrets] + [""])


def scene_prompt(rows: list[dict[str, Any]], w: Window, secrets: list[dict[str, Any]] | None = None) -> str:
    lines = secrets_block(secrets or []) + [f"SCENE: turns {w.first_turn}–{w.last_turn}", ""]
    lines += [f"[turn {r['turn']}] {_speaker(r['metadata'])}: {r['content'][:MESSAGE_CHARS]}" for r in rows]
    return "\n".join(lines)


def story_prompt(scenes: list[dict[str, Any]], secrets: list[dict[str, Any]] | None = None) -> str:
    return "\n".join(secrets_block(secrets or []) + ["SCENES:", ""]
                     + [f"[turns {s['first_turn']}–{s['last_turn']}] {s['text']}" for s in scenes])


def _insert(conn: psycopg.Connection, conv: UUID, gen: Generation, level: str, window_key: str, members: list[UUID],
            first: int | None, last: int | None, text: str, raw: str, coverage: dict[str, int] | None) -> bool:
    return conn.execute(
        "INSERT INTO summary (id, conversation_id, generation, level, window_key, members, first_turn, last_turn,"
        " text, raw, coverage) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING RETURNING id",
        (uuid7(), conv, gen.key, level, window_key, members, first, last, text, Jsonb({"reply": raw[:20000]}),
         Jsonb(coverage) if coverage is not None else None)).fetchone() is not None


def head_secrets(conn: psycopg.Connection, head: UUID) -> list[dict[str, Any]]:
    """The head's secrets as the facts of the active extractor generation fold them (ADR 0033)."""
    key = generations.active(conn, "extract")
    return memory_view(conn, head, key)["secrets"] if key else []


def process(conn: psycopg.Connection, job: dict[str, Any], complete: Callable[[str, str], tuple[dict, str]],
            gen: Generation) -> str:
    """Summarize one scene or the story; returns the final job status. No transaction is held while the model
    answers."""
    payload = job["payload"]
    if payload.get("generation") != gen.key:
        raise ValueError(f"job generation {payload.get('generation')} is not handler generation {gen.key}")
    conv = job["conversation_id"]
    row = conn.execute("SELECT head_commit_id FROM conversation WHERE id = %s", (conv,)).fetchone()
    if row is None or row["head_commit_id"] is None:
        return "obsolete"
    head = row["head_commit_id"]
    if payload["level"] == "scene":
        w = next((w for w in windows(conn, head, payload["first_turn"] // WINDOW)
                  if w.key == payload["window_key"]), None)
        if w is None:
            return "obsolete"  # the head changed inside the window; a newer job covers what it shows now
        secrets = head_secrets(conn, head)
        old = _scenes(conn, conv, gen.key, [w]).get(w.key)
        if old is not None and not unlisted(old, secrets):
            return "done"
        rows = conn.execute(
            "SELECT am.turn, sr.id, sr.metadata FROM active_membership am JOIN source_revision sr"
            " ON sr.id = am.source_revision_id WHERE am.commit_id = %s AND am.turn BETWEEN %s AND %s"
            " ORDER BY am.position", (head, w.first_turn, w.last_turn)).fetchall()
        for r in rows:
            r["content"] = normtext.get(conn, r["id"])["clean_content"]
        sizes = [len(r["content"]) for r in rows]
        coverage = {"chars": sum(sizes), "used": sum(min(n, MESSAGE_CHARS) for n in sizes), "messages": len(rows)}
        kept = window_secrets(secrets, w.last_turn)
        coverage["secrets"] = [secret_key(s) for s in kept]
        if sum(sizes) < MIN_CONTENT_CHARS:
            text, raw = "", ""
        else:
            parsed, raw = complete(SCENE_PROMPT, scene_prompt(rows, w, kept))
            text = reply_text(parsed, SCENE_CHARS)
        with conn.transaction():
            if old is not None:  # written again with the secrets it was not told about (`unlisted`)
                conn.execute("UPDATE summary SET discarded_at = now() WHERE id = %s", (old["id"],))
            _insert(conn, conv, gen, "scene", w.key, list(w.members), w.first_turn, w.last_turn, text, raw, coverage)
        log.info("summarized scene conversation=%s turns=%d-%d chars=%d", conv, w.first_turn, w.last_turn, len(text))
        with conn.transaction():
            schedule_story(conn, conv, head, gen.key, job["priority"], secrets)
        return "done"
    view = current(conn, conv, head, gen.key)
    ids = [s["summary"]["id"] for s in view["scenes"] if s["summary"]]
    if view["done"] < view["due"] or [str(i) for i in ids] != payload["members"]:
        return "obsolete"  # the scenes changed; a newer story job covers them
    secrets = head_secrets(conn, head)
    if view["story_current"] and not unlisted(view["story"], secrets):
        return "done"
    scenes = [s["summary"] for s in view["scenes"]]
    kept = window_secrets(secrets, scenes[-1]["last_turn"])
    # A scene that repeats a secret gives the story nothing of its text (it would pass the secret on); its turns stay
    # in the story's range, told by the scenes around them.
    told = [{**s, "text": "(left out: it repeats a secret)"} if leaks(s["text"], secrets) else s for s in scenes]
    parsed, raw = complete(STORY_PROMPT, story_prompt(told, kept))
    text = reply_text(parsed, STORY_CHARS)
    with conn.transaction():
        conn.execute("UPDATE summary SET discarded_at = now() WHERE conversation_id = %s AND generation = %s"
                     " AND level = 'story' AND window_key = %s AND discarded_at IS NULL", (conv, gen.key, payload["window_key"]))
        _insert(conn, conv, gen, "story", payload["window_key"], ids, scenes[0]["first_turn"], scenes[-1]["last_turn"],
                text, raw, {"scenes": len(scenes), "secrets": [secret_key(s) for s in kept]})
    log.info("summarized story conversation=%s scenes=%d chars=%d", conv, len(scenes), len(text))
    return "done"
