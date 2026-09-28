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
from typing import Any
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from . import generations, normtext
from .config import Settings
from .generations import Generation
from .ids import uuid7
from .llm import LLMError

log = logging.getLogger("nmos.summaries")

VERSION = "summarize-v1"
WINDOW = 8  # turns per scene (PHASE-12 Q1)
LAG = 4  # replied turns after a window before it is summarized: the last turns still change
MESSAGE_CHARS = 6000  # normalized chars of each message the model sees, as extraction's target turn
MIN_CONTENT_CHARS = 12
SCENE_CHARS = 1200  # a stored scene summary's cap
STORY_CHARS = 2400
LIVE_PRIORITY = 300  # after extraction's live and recent work (100–250)
BACKFILL_PRIORITY = 950  # after extraction's history (900); claimed oldest first

SCENE_PROMPT = """You summarize one scene of a role-play chat for its long-term memory. The scene is a run of
consecutive turns, given in order.

Write what happens in it: who is there, what they do and say that matters later, what changes (places, possessions,
relationships, plans, promises), and how the scene ends. Plain past-tense narration in the language of the chat, at
most 5 sentences. Name characters as the chat names them; the user's character is named as the chat names it.
Only what the scene shows: no guesses, no judgments, nothing from before or after it, no out-of-character notes, no
formatting.

Answer with JSON only: {"summary": "..."}"""

STORY_PROMPT = """You write "the story so far" of a role-play chat for its long-term memory, from the summaries of its
scenes, given in order.

Keep what still matters: the main events in order, what changed between the characters, and what is still
unresolved. Plain past-tense narration in the language of the chat, at most 8 sentences. Only what the summaries
say: no guesses, no judgments, no formatting.

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


def replied_turns(conn: psycopg.Connection, head: UUID) -> int:
    """Turns of the head that have a reply (their anchor carries a turn hash, ADR 0008)."""
    return conn.execute("SELECT coalesce(max(turn), -1) + 1 AS n FROM active_membership"
                        " WHERE commit_id = %s AND turn_hash IS NOT NULL", (head,)).fetchone()["n"]


def due(turns: int) -> int:
    """How many windows are complete and LAG turns old."""
    return max(0, turns - LAG) // WINDOW


def windows(conn: psycopg.Connection, head: UUID, first: int = 0) -> list[Window]:
    """The due windows of the head, from window `first` on."""
    n = due(replied_turns(conn, head))
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


def _scenes(conn: psycopg.Connection, conv: UUID, key: str, ws: list[Window]) -> dict[str, dict[str, Any]]:
    if not ws:
        return {}
    rows = conn.execute(
        "SELECT * FROM summary WHERE conversation_id = %s AND generation = %s AND level = 'scene'"
        " AND discarded_at IS NULL AND window_key = ANY(%s)", (conv, key, [w.key for w in ws])).fetchall()
    return {r["window_key"]: r for r in rows}


def current(conn: psycopg.Connection, conv: UUID, head: UUID, key: str | None) -> dict[str, Any]:
    """What the head's summaries are: each due window with its current summary (or None), and the newest story made
    only from current scene summaries (it may not cover the newest windows yet)."""
    ws = windows(conn, head) if key else []
    by_key = _scenes(conn, conv, key, ws) if key else {}
    scenes = [{"window": w, "summary": by_key.get(w.key)} for w in ws]
    ids = [s["summary"]["id"] for s in scenes if s["summary"]]
    story = None
    if ids:
        have = set(ids)
        for row in conn.execute(
                "SELECT * FROM summary WHERE conversation_id = %s AND generation = %s AND level = 'story'"
                " AND discarded_at IS NULL ORDER BY created_at DESC, id DESC", (conv, key)).fetchall():
            if row["members"] and set(row["members"]) <= have:
                story = row
                break
    return {"scenes": scenes, "story": story, "due": len(ws), "done": len(ids),
            "story_current": bool(story) and len(story["members"]) == len(ids) == len(ws)}


# As extraction.REQUEUE: a job made obsolete that is wanted again is revived.
_INSERT = ("INSERT INTO job (kind, dedupe_key, conversation_id, payload, priority) VALUES (%s, %s, %s, %s, %s)"
           " ON CONFLICT (dedupe_key) DO UPDATE SET status = 'queued', priority = EXCLUDED.priority, attempts = 0,"
           " run_after = now(), locked_at = NULL, last_error = NULL, updated_at = now() WHERE job.status = 'obsolete'")


def _scene_job(conv: UUID, key: str, w: Window, priority: int) -> tuple:
    return ("summarize", f"summarize:{key}:{conv}:scene:{w.key}", conv,
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


def schedule_story(conn: psycopg.Connection, conv: UUID, head: UUID, key: str, priority: int = LIVE_PRIORITY) -> int:
    """Queue the story of the current scene summaries when every due window has one and no story of them exists."""
    view = current(conn, conv, head, key)
    if not view["due"] or view["done"] < view["due"] or view["story_current"]:
        return 0
    ids = [s["summary"]["id"] for s in view["scenes"]]
    story_key = members_key(ids)
    conn.execute(_INSERT, ("summarize", f"summarize:{key}:{conv}:story:{story_key}", conv,
                           Jsonb({"generation": key, "level": "story", "window_key": story_key,
                                  "members": [str(i) for i in ids]}), priority))
    return 1


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


def scene_prompt(rows: list[dict[str, Any]], w: Window) -> str:
    lines = [f"SCENE: turns {w.first_turn}–{w.last_turn}", ""]
    lines += [f"[turn {r['turn']}] {_speaker(r['metadata'])}: {r['content'][:MESSAGE_CHARS]}" for r in rows]
    return "\n".join(lines)


def story_prompt(scenes: list[dict[str, Any]]) -> str:
    return "\n".join(["SCENES:", ""] + [f"[turns {s['first_turn']}–{s['last_turn']}] {s['text']}" for s in scenes])


def _insert(conn: psycopg.Connection, conv: UUID, gen: Generation, level: str, window_key: str, members: list[UUID],
            first: int | None, last: int | None, text: str, raw: str, coverage: dict[str, int] | None) -> bool:
    return conn.execute(
        "INSERT INTO summary (id, conversation_id, generation, level, window_key, members, first_turn, last_turn,"
        " text, raw, coverage) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING RETURNING id",
        (uuid7(), conv, gen.key, level, window_key, members, first, last, text, Jsonb({"reply": raw[:20000]}),
         Jsonb(coverage) if coverage is not None else None)).fetchone() is not None


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
        if payload["window_key"] in _scenes(conn, conv, gen.key, [w]):
            return "done"
        rows = conn.execute(
            "SELECT am.turn, sr.id, sr.metadata FROM active_membership am JOIN source_revision sr"
            " ON sr.id = am.source_revision_id WHERE am.commit_id = %s AND am.turn BETWEEN %s AND %s"
            " ORDER BY am.position", (head, w.first_turn, w.last_turn)).fetchall()
        for r in rows:
            r["content"] = normtext.get(conn, r["id"])["clean_content"]
        sizes = [len(r["content"]) for r in rows]
        coverage = {"chars": sum(sizes), "used": sum(min(n, MESSAGE_CHARS) for n in sizes), "messages": len(rows)}
        if sum(sizes) < MIN_CONTENT_CHARS:
            text, raw = "", ""
        else:
            parsed, raw = complete(SCENE_PROMPT, scene_prompt(rows, w))
            text = reply_text(parsed, SCENE_CHARS)
        with conn.transaction():
            _insert(conn, conv, gen, "scene", w.key, list(w.members), w.first_turn, w.last_turn, text, raw, coverage)
        log.info("summarized scene conversation=%s turns=%d-%d chars=%d", conv, w.first_turn, w.last_turn, len(text))
        with conn.transaction():
            schedule_story(conn, conv, head, gen.key, job["priority"])
        return "done"
    view = current(conn, conv, head, gen.key)
    ids = [s["summary"]["id"] for s in view["scenes"] if s["summary"]]
    if view["done"] < view["due"] or [str(i) for i in ids] != payload["members"]:
        return "obsolete"  # the scenes changed; a newer story job covers them
    if view["story_current"]:
        return "done"
    scenes = [s["summary"] for s in view["scenes"]]
    parsed, raw = complete(STORY_PROMPT, story_prompt(scenes))
    text = reply_text(parsed, STORY_CHARS)
    with conn.transaction():
        _insert(conn, conv, gen, "story", payload["window_key"], ids, scenes[0]["first_turn"], scenes[-1]["last_turn"],
                text, raw, {"scenes": len(scenes)})
    log.info("summarized story conversation=%s scenes=%d chars=%d", conv, len(scenes), len(text))
    return "done"
