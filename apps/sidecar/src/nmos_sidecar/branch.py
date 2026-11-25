"""PHASE-67 part 2 (audit G6.1, design decision 11c): a branched chat inherits its origin's memory.

The host gives a branch a new chat id and reissues every message id (H5, HOST-FACTS Q4), so every revision hash, and
with it every turn hash, differs from the origin's (`canonical.PAYLOAD_KEYS` hashes `chatId`). Without this module a
branch at turn 150 of a 200-turn chat starts with no memory, pays again for its recent window and loses the owner's
repairs, links, pins, exclusions and chat modes.

On the branch's first applied sync (`on_first_sync`, called by `api.do_reconcile` after `ledger.apply_plan`):

1. **The common prefix** (`find_prefix`): the branch's head and the origin's head, position by position from 0, up to
   the origin's branch-point message (the marker's `message_ref`) when the origin still shows it. A position matches
   when both revisions hold the same content and the same stored metadata but `chatId` (a chatId-free revision hash:
   role, name, swipe, `generationId`, disabled, comment flags), and both heads give it the same turn (ADR 0008). The
   prefix ends at the first position that does not. An origin missing, deleted or showing other content gives an empty
   prefix: nothing is copied and the branch is what it was before this module.
2. **Copies, never shares** (as PHASE-57 A1's canon copies): for each prefix turn whose anchor is an anchor in both
   heads, every live extraction of the origin at that anchor and turn hash (any generation, so a fallback generation
   keeps serving) and the turn's live reveal check are written again for the branch's anchor and turn hash, with their
   assertions; the embeddings of every prefix message (every projection); the scene summaries of every window whose
   turns are all prefix turns, and the stories made only of those scenes. Each copy holds the branch's revision ids,
   turn hashes and copied ids wherever the origin row held the origin's (`members`, `hints.secrets[].turn_hash`,
   `hints.checks`, the window keys), costs nothing (`usage` `{"calls": 0}`) and records its source
   (`coverage.reused_from` / `usage.inherited_from`). Rows keep the origin row's `created_at`, so the branch reads them
   exactly as the origin did (reveal staleness, story choice, repair order); nothing of the branch was read before.
3. **The owner's settings as of the branch point**, copied once: the memory mode (`memory_strict` with
   `memory_narrator`, one setting) and `replies_only`, each only where the branch still has the default; entity links, the owner repairs
   in force whose target turn and effect turn both lie in the prefix (every kind: thread, secret and fact repairs,
   restores, locks, name splits, status-flag dismissals, exclusions, character pins), and the carried-memory link
   (PHASE-60 S6) when the branch has none. Each copied row records `inherited_from`. Status pins are per card
   (`app_config`), so a branch of the same card already has them.

Then `drop_covered` takes back the extraction and embedding jobs a sync queued for what a copy already covers: no job is
queued for a prefix turn or message, on the first sync or when the branch point's reply is accepted later. All of it runs in one savepoint of the sync's transaction with a time
bound; any error rolls the savepoint back, logs a line and the branch starts without inherited memory, as before. The
marker `conversation.branch_inherit` records the outcome either way, so no later sync tries again on its own.

A branch synced before this module has no marker and is never back-filled silently; `backfill` (the endpoint
`POST /v1/conversations/{id}/branch-inherit`, with a dry run) does the same copy on request, skipping what the branch
already has of its own, with new rows stamped just before now in the origin's order so replays of the branch's
earlier requests (ADR 0027) read what they read then.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from .ids import uuid7
from .summaries import WINDOW, members_key

log = logging.getLogger("nmos.branch")

STATEMENT_TIMEOUT_MS = 2000  # each statement of the copy on the request path
LOCK_TIMEOUT_MS = 1000  # the origin's row (a concurrent delete of the origin waits for the copy, or the copy gives up)
BUDGET_S = 3.0  # the whole copy on the request path; past it the savepoint rolls back (fail-open)
MAX_PREFIX = 20000  # messages a first sync copies; a longer prefix is left to the explicit back-fill
BACKFILL_BUDGET_S = 30.0
COPY_USAGE = {"calls": 0}


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class Prefix:
    """The common prefix of a branch and its origin, positions `[0, length)`."""

    origin: UUID
    origin_head: UUID
    length: int
    rids: list[tuple[UUID, UUID]]  # per position: (origin revision, branch revision)
    turns: list[int | None]  # per position: the turn both heads give it
    anchors: list[tuple[int, int, UUID, str, UUID, str]]  # (position, turn, origin rid, hash, branch rid, hash)
    remap: dict[str, str] = field(default_factory=dict)  # origin id or hash text → the branch's

    @property
    def last_turn(self) -> int | None:
        """The last turn that lies wholly in the prefix of both heads (its anchor is an anchor in both)."""
        return max((a[1] for a in self.anchors), default=None)


def remapped(value: Any, mapping: dict[str, str]) -> Any:
    """`value` (jsonb) with every string the mapping names replaced: the origin's revision ids, message ids, turn hashes
    (also as `reveal:<hash>`) and copied row ids become the branch's."""
    if isinstance(value, str):
        return mapping.get(value, value)
    if isinstance(value, list):
        return [remapped(v, mapping) for v in value]
    if isinstance(value, dict):
        return {k: remapped(v, mapping) for k, v in value.items()}
    return value


_PREFIX_SQL = """
SELECT b.position, b.source_revision_id AS brid, o.source_revision_id AS orid, b.turn AS bturn, o.turn AS oturn,
       b.turn_hash AS bhash, o.turn_hash AS ohash, bo.host_logical_id AS bmsg, oo.host_logical_id AS omsg,
       (o.position IS NOT NULL AND bs.content = os.content
        AND (bs.metadata - 'chatId') = (os.metadata - 'chatId')) AS same
FROM active_membership b
JOIN source_revision bs ON bs.id = b.source_revision_id
JOIN source_object bo ON bo.id = bs.source_object_id
LEFT JOIN active_membership o ON o.commit_id = %(oh)s AND o.position = b.position
LEFT JOIN source_revision os ON os.id = o.source_revision_id
LEFT JOIN source_object oo ON oo.id = os.source_object_id
WHERE b.commit_id = %(bh)s AND b.position <= %(bound)s
ORDER BY b.position
"""


def origin_of(conn: psycopg.Connection, conv_id: UUID) -> dict[str, Any] | None:
    """The branch's origin as this database holds it (the marker's chat ref, D14), locked against a concurrent delete
    for the rest of the copy; None for a chat that is no branch or whose origin is not here."""
    row = conn.execute("SELECT host, branched_from_conversation_id AS oid, branched_from_host_chat_ref AS ref,"
                       " branched_from_message_ref AS mref, head_commit_id FROM conversation WHERE id = %s",
                       (conv_id,)).fetchone()
    if row is None or not row["ref"]:
        return None
    origin = conn.execute(
        "SELECT id, head_commit_id FROM conversation WHERE (id = %s OR (%s::uuid IS NULL AND host = %s"
        " AND host_chat_ref = %s)) AND id <> %s FOR KEY SHARE",
        (row["oid"], row["oid"], row["host"], row["ref"], conv_id)).fetchone()
    if origin is None or origin["head_commit_id"] is None:
        return None
    return {"id": origin["id"], "head": origin["head_commit_id"], "message_ref": row["mref"],
            "branch_head": row["head_commit_id"]}


def find_prefix(conn: psycopg.Connection, conv_id: UUID, origin: dict[str, Any], limit: int = MAX_PREFIX) -> Prefix:
    """Match the branch's head to the origin's by content, from position 0 to the first mismatch (item 1)."""
    point = conn.execute(
        "SELECT am.position FROM active_membership am JOIN source_revision sr ON sr.id = am.source_revision_id"
        " JOIN source_object so ON so.id = sr.source_object_id WHERE am.commit_id = %s AND so.host_logical_id = %s",
        (origin["head"], origin["message_ref"])).fetchone() if origin["message_ref"] else None
    bound = min(limit - 1, point["position"]) if point else limit - 1
    rows = conn.execute(_PREFIX_SQL, {"oh": origin["head"], "bh": origin["branch_head"], "bound": bound}).fetchall()
    prefix = Prefix(origin["id"], origin["head"], 0, [], [], [])
    for r in rows:
        if not r["same"] or r["bturn"] != r["oturn"]:
            break
        prefix.rids.append((r["orid"], r["brid"]))
        prefix.turns.append(r["bturn"])
        prefix.remap[str(r["orid"])] = str(r["brid"])
        prefix.remap[r["omsg"]] = r["bmsg"]
        if r["bhash"] and r["ohash"]:
            prefix.anchors.append((r["position"], r["bturn"], r["orid"], r["ohash"], r["brid"], r["bhash"]))
            prefix.remap[r["ohash"]] = r["bhash"]
            prefix.remap["reveal:" + r["ohash"]] = "reveal:" + r["bhash"]
        prefix.length += 1
    return prefix


def _columns(conn: psycopg.Connection, table: str) -> list[tuple[str, str]]:
    """The table's columns and types, in order: a copy carries every column, also those a later migration adds."""
    return [(r["column_name"], r["data_type"]) for r in conn.execute(
        "SELECT column_name, data_type FROM information_schema.columns WHERE table_schema = current_schema()"
        " AND table_name = %s ORDER BY ordinal_position", (table,)).fetchall()]


class _Copier:
    """One copy: planned rows are written in the origin's `created_at` order, each stamped by `stamp`."""

    def __init__(self, conn: psycopg.Connection, conv_id: UUID, prefix: Prefix, backfill: bool, deadline: float):
        self.conn, self.conv, self.prefix, self.backfill, self.deadline = conn, conv_id, prefix, backfill, deadline
        self.counts: dict[str, int] = {}
        self.cols: dict[str, list[tuple[str, str]]] = {}
        self.planned: list[tuple[datetime, str, Callable[[datetime], bool]]] = []

    def check(self) -> None:
        if time.perf_counter() > self.deadline:
            raise BudgetExceeded("branch copy took longer than its bound")

    def count(self, name: str, n: int = 1) -> None:
        self.counts[name] = self.counts.get(name, 0) + n

    def columns(self, table: str) -> list[tuple[str, str]]:
        if table not in self.cols:
            self.cols[table] = _columns(self.conn, table)
        return self.cols[table]

    def insert(self, table: str, row: dict[str, Any], conflict: str = "ON CONFLICT DO NOTHING") -> bool:
        cols = self.columns(table)
        values = [Jsonb(row.get(c)) if t == "jsonb" and row.get(c) is not None else row.get(c) for c, t in cols]
        names = ", ".join(c for c, _ in cols)
        marks = ", ".join(["%s"] * len(cols))
        return self.conn.execute(f"INSERT INTO {table} ({names}) VALUES ({marks}) {conflict} RETURNING 1",
                                 values).fetchone() is not None

    def run(self) -> None:
        """Write the planned rows oldest first. A first sync keeps each origin row's time; a back-fill stamps them just
        before now, one microsecond apart in the same order."""
        self.planned.sort(key=lambda p: p[0])
        base = self.conn.execute("SELECT clock_timestamp() AS t").fetchone()["t"] if self.backfill else None
        n = len(self.planned)
        for i, (at, name, write) in enumerate(self.planned):
            if i % 64 == 0:
                self.check()
            stamp = base - timedelta(microseconds=n - i) if base is not None else at
            if write(stamp):
                self.count(name)
        self.planned = []


def _plan_extractions(c: _Copier) -> dict[UUID, UUID]:
    """Item 2: every live extraction of a prefix anchor's turn (any generation) and its live reveal check, planned under
    the branch's anchor and turn hash. Returns origin extraction id → copy id, filled as `run` writes them."""
    p = c.prefix
    if not p.anchors:
        return {}
    rows = c.conn.execute(
        "SELECT x.* FROM extraction x JOIN unnest(%s::uuid[], %s::text[]) a(rid, h)"
        " ON x.source_revision_id = a.rid AND x.window_hash IN (a.h, 'reveal:' || a.h)"
        " WHERE x.discarded_at IS NULL ORDER BY x.created_at, x.id",
        ([a[2] for a in p.anchors], [a[3] for a in p.anchors])).fetchall()
    ids = {r["id"]: uuid7() for r in rows}
    for old, new in ids.items():
        p.remap[str(old)] = str(new)
    written: dict[UUID, UUID] = {}
    origin = str(p.origin)

    def plan(r: dict[str, Any]) -> None:
        check = r["window_hash"].startswith("reveal:")

        def write(at: datetime) -> bool:
            checked = (r["hints"] or {}).get("checks") if check else None
            if check and (checked is None or UUID(checked) not in written):
                return False  # a check is copied only with the extraction it checked
            row = dict(r)
            for k, v in r.items():
                if isinstance(v, (dict, list)) and k not in ("members", "usage"):
                    row[k] = remapped(v, p.remap)
            coverage = row.get("coverage") or {}
            row.update(id=ids[r["id"]], source_revision_id=UUID(p.remap[str(r["source_revision_id"])]),
                       window_hash=p.remap[r["window_hash"]],
                       members=[UUID(p.remap[str(m)]) for m in r["members"] or [] if str(m) in p.remap] or None,
                       coverage={**coverage, "reused_from": coverage.get("reused_from") or str(r["id"]),
                                 "inherited_from": origin},
                       usage={**COPY_USAGE, "inherited_from": str(r["id"])}, created_at=at)
            if check and c.backfill and row.get("hints") and row["hints"].get("read_at"):
                row["hints"] = {**row["hints"], "read_at": at.isoformat()}  # when it looked, in the copy's order
            if not c.insert("extraction", row):
                return False  # the branch has its own (a back-fill): its own wins
            written[r["id"]] = ids[r["id"]]
            return True

        c.planned.append((r["created_at"], "reveal_checks" if check else "extractions", write))

    for r in rows:
        if r["window_hash"] in p.remap:
            plan(r)
    return written  # filled as `run` writes them


def _copy_assertions(c: _Copier, written: dict[UUID, UUID]) -> None:
    if not written:
        return
    cols = [n for n, _ in c.columns("assertion") if n not in ("id", "extraction_id", "source_revision_id")]
    names = ", ".join(cols)
    n = c.conn.execute(
        f"INSERT INTO assertion (extraction_id, source_revision_id, {names})"
        f" SELECT m.n, r.b, {', '.join('a.' + k for k in cols)} FROM assertion a"
        " JOIN unnest(%s::uuid[], %s::uuid[]) m(o, n) ON a.extraction_id = m.o"
        " JOIN unnest(%s::uuid[], %s::uuid[]) r(o, b) ON r.o = a.source_revision_id ORDER BY a.id",
        (list(written), list(written.values()), [o for o, _ in c.prefix.rids], [b for _, b in c.prefix.rids])).rowcount
    c.count("assertions", n)


def _copy_embeddings(c: _Copier) -> None:
    """Item 2: every prefix message's embeddings, every projection (content only, D20), unless the branch has its own."""
    p = c.prefix
    if not p.rids:
        return
    picked = []
    for name, _ in c.columns("revision_embedding"):
        if name == "source_revision_id":
            picked.append("r.b")
        elif name == "usage":
            picked.append("jsonb_build_object('calls', 0, 'inherited_from', e.source_revision_id::text)")
        elif name == "created_at":
            picked.append("CASE WHEN %(backfill)s THEN clock_timestamp() ELSE e.created_at END")
        else:
            picked.append("e." + name)
    names = ", ".join(n for n, _ in c.columns("revision_embedding"))
    n = c.conn.execute(
        f"INSERT INTO revision_embedding ({names}) SELECT {', '.join(picked)} FROM revision_embedding e"
        " JOIN unnest(%(o)s::uuid[], %(b)s::uuid[]) r(o, b) ON e.source_revision_id = r.o"
        " WHERE NOT EXISTS (SELECT 1 FROM revision_embedding y WHERE y.source_revision_id = r.b"
        " AND y.projection = e.projection) ON CONFLICT DO NOTHING",
        {"o": [o for o, _ in p.rids], "b": [b for _, b in p.rids], "backfill": c.backfill}).rowcount
    c.count("embedding_chunks", n)


def _copy_turn_personas(c: _Copier) -> None:
    """Audit B4.3: preserve each inherited prefix revision's recorded `persona_name` from the origin chat."""
    if not c.prefix.rids:
        return
    c.conn.execute(
        "UPDATE source_revision b SET persona_name = o.persona_name"
        " FROM unnest(%s::uuid[], %s::uuid[]) r(o, b)"
        " JOIN source_revision o ON o.id = r.o"
        " WHERE b.id = r.b AND o.persona_name IS NOT NULL AND b.persona_name IS DISTINCT FROM o.persona_name",
        ([o for o, _ in c.prefix.rids], [b for _, b in c.prefix.rids]),
    )


def _windows(p: Prefix) -> list[tuple[int, int, list[UUID], list[UUID]]]:
    """The scene windows wholly inside the prefix: (first turn, last turn, origin members, branch members)."""
    complete = {a[1] for a in p.anchors}
    by_window: dict[int, list[int]] = {}
    for pos, turn in enumerate(p.turns):
        if turn is not None:
            by_window.setdefault(turn // WINDOW, []).append(pos)
    out = []
    for i, positions in sorted(by_window.items()):
        if all(t in complete for t in range(i * WINDOW, i * WINDOW + WINDOW)):
            out.append((i * WINDOW, i * WINDOW + WINDOW - 1, [p.rids[q][0] for q in positions],
                        [p.rids[q][1] for q in positions]))
    return out


def _plan_summaries(c: _Copier) -> None:
    """Item 2: the scene summaries of the windows inside the prefix (any generation) and the stories made only of
    them, with the branch's window keys and members."""
    p = c.prefix
    windows = _windows(p)
    if not windows:
        return
    keys = {members_key(o): (members_key(b), b) for _, _, o, b in windows}
    scenes = c.conn.execute(
        "SELECT * FROM summary WHERE conversation_id = %s AND level = 'scene' AND window_key = ANY(%s)"
        " AND discarded_at IS NULL ORDER BY created_at, id", (p.origin, list(keys))).fetchall()
    ids = {r["id"]: uuid7() for r in scenes}
    written: set[UUID] = set()
    origin = str(p.origin)

    def common(r: dict[str, Any], at: datetime) -> dict[str, Any]:
        coverage = remapped(r.get("coverage"), p.remap) or {}
        return {**r, "raw": remapped(r.get("raw"), p.remap), "conversation_id": c.conv, "created_at": at,
                "coverage": {**coverage, "reused_from": coverage.get("reused_from") or str(r["id"]),
                             "inherited_from": origin},
                "usage": {**COPY_USAGE, "inherited_from": str(r["id"])}}

    def scene(r: dict[str, Any]) -> Callable[[datetime], bool]:
        def write(at: datetime) -> bool:
            key, members = keys[r["window_key"]]
            if not c.insert("summary", {**common(r, at), "id": ids[r["id"]], "window_key": key, "members": members}):
                return False
            written.add(r["id"])
            return True
        return write

    for r in scenes:
        c.planned.append((r["created_at"], "scene_summaries", scene(r)))
    if not scenes:
        return
    stories = c.conn.execute(
        "SELECT * FROM summary WHERE conversation_id = %s AND level = 'story' AND discarded_at IS NULL"
        " AND cardinality(members) > 0 AND members <@ %s::uuid[] ORDER BY created_at, id",
        (p.origin, list(ids))).fetchall()

    def story(r: dict[str, Any]) -> Callable[[datetime], bool]:
        def write(at: datetime) -> bool:
            if not all(m in written for m in r["members"]):
                return False
            members = [ids[m] for m in r["members"]]
            return c.insert("summary", {**common(r, at), "id": uuid7(), "window_key": members_key(members),
                                        "members": members})
        return write

    for r in stories:
        c.planned.append((r["created_at"], "stories", story(r)))


def reanchor_repair(rep: dict[str, Any], prefix: Prefix) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """An origin repair's (target, value) for the branch, or None when it is not inherited (item 4).

    An anchored repair (PHASE-67 part 4, migration 0043) is inherited when every message and revision its anchor names
    is in the prefix (`repairs.reanchor`, by the prefix's map): its target's turn, and the first message of the turn it
    takes effect from (by default the origin's head when it was made: as of the branch point a repair that takes effect
    later was not in force). Its anchor is moved onto the branch's messages in `rep` (the row the caller copies), so the
    branch reads it by its own messages and a later renumbering of the branch keeps it. A legacy repair (no anchor) is
    inherited when the turn its target was stated in and the turn it takes effect both lie in the prefix; a target
    outside any turn (a name, canon at turn -1, a carried row) always is. Either way the stored target and value are
    re-anchored by prefix position and content: the origin's turn hashes, revision ids and message ids become the
    branch's at the same position (`find_prefix` matched them by content); a hash the origin's head no longer shows
    stays as it was and matches nothing in the branch either, as in the origin.
    """
    from .repairs import reanchor  # PHASE-67 part 4: the one re-anchoring rule

    target, value = rep.get("target") or {}, rep.get("value") or {}
    if rep.get("anchor"):
        moved = reanchor(rep["anchor"], prefix.remap)
        if moved is None:
            return None
        rep["anchor"] = moved
        return remapped(target, prefix.remap), remapped(value, prefix.remap)
    last = prefix.last_turn

    def inside(turn: Any) -> bool:
        return turn is None or not isinstance(turn, int) or turn < 0 or (last is not None and turn <= last)

    if not inside(target.get("turn")) or not inside(value.get("turn")):
        return None
    return remapped(target, prefix.remap), remapped(value, prefix.remap)


def _plan_settings(c: _Copier) -> None:
    """Item 4: the origin's owner input as of now (the branch point, for the first sync), copied once."""
    p, conn = c.prefix, c.conn
    # The memory mode is one setting (ADR 0035: one PUT writes strict and narrator together), `replies_only` another
    # (PHASE-48); each is inherited only while the branch still has the default, the one sign of its own choice.
    mode = conn.execute(
        "UPDATE conversation b SET memory_strict = o.memory_strict, memory_narrator = o.memory_narrator"
        " FROM conversation o WHERE b.id = %s AND o.id = %s AND NOT b.memory_strict AND b.memory_narrator IS NULL"
        " AND (o.memory_strict OR o.memory_narrator IS NOT NULL) RETURNING b.id", (c.conv, p.origin)).fetchone()
    if mode:
        c.count("memory_mode")
    if conn.execute("UPDATE conversation b SET replies_only = true FROM conversation o WHERE b.id = %s AND o.id = %s"
                    " AND NOT b.replies_only AND o.replies_only RETURNING b.id", (c.conv, p.origin)).fetchone():
        c.count("replies_only")
    for r in conn.execute("SELECT * FROM entity_link WHERE conversation_id = %s AND removed_at IS NULL"
                          " ORDER BY created_at, id", (p.origin,)).fetchall():
        def link(r: dict[str, Any] = r) -> Callable[[datetime], bool]:
            def write(at: datetime) -> bool:
                if conn.execute("SELECT 1 FROM entity_link WHERE conversation_id = %s AND entity_type = %s"
                                " AND name = %s AND same_as = %s", (c.conv, r["entity_type"], r["name"],
                                                                    r["same_as"])).fetchone():
                    return False  # the branch has (or had, and removed) its own
                return c.insert("entity_link", {**r, "id": uuid7(), "conversation_id": c.conv, "created_at": at,
                                                "inherited_from": r["id"]}, conflict="")
            return write
        c.planned.append((r["created_at"], "entity_links", link()))
    batches: dict[UUID, UUID] = {}
    for r in conn.execute("SELECT * FROM owner_repair WHERE conversation_id = %s AND removed_at IS NULL"
                          " ORDER BY created_at, id", (p.origin,)).fetchall():
        moved = reanchor_repair(r, p)
        if moved is None:
            c.count("repairs_not_inherited")
            continue

        def repair(r: dict[str, Any] = r, moved: tuple[dict, dict] = moved) -> Callable[[datetime], bool]:
            def write(at: datetime) -> bool:
                target, value = moved
                if conn.execute("SELECT 1 FROM owner_repair WHERE conversation_id = %s AND kind = %s AND target = %s"
                                " AND value = %s", (c.conv, r["kind"], Jsonb(target), Jsonb(value))).fetchone():
                    return False  # the branch has (or had) its own
                batch = batches.setdefault(r["batch_id"], uuid7()) if r.get("batch_id") else None
                return c.insert("owner_repair", {**r, "id": uuid7(), "conversation_id": c.conv, "target": target,
                                                 "value": value, "batch_id": batch, "created_at": at,
                                                 "inherited_from": r["id"]}, conflict="")
            return write
        c.planned.append((r["created_at"], "repairs", repair()))
    carry = conn.execute("SELECT * FROM conversation_carry WHERE target_conversation_id = %s AND removed_at IS NULL",
                         (p.origin,)).fetchone()
    if carry is not None and carry["source_conversation_id"] != c.conv:
        def link_carry(at: datetime) -> bool:
            if conn.execute("SELECT 1 FROM conversation_carry WHERE target_conversation_id = %s AND removed_at IS NULL",
                            (c.conv,)).fetchone():
                return False  # the branch carries its own
            return c.insert("conversation_carry", {**carry, "id": uuid7(), "target_conversation_id": c.conv,
                                                   "created_at": at, "inherited_from": carry["id"]})
        c.planned.append((carry["created_at"], "carry_link", link_carry))


def inherit(conn: psycopg.Connection, conv_id: UUID, *, backfill: bool = False, budget_s: float = BUDGET_S,
            limit: int = MAX_PREFIX) -> dict[str, Any]:
    """Find the prefix and copy what the origin holds for it (items 1, 2, 4). The caller holds the transaction."""
    started = time.perf_counter()
    origin = origin_of(conn, conv_id)
    if origin is None or origin["branch_head"] is None:
        return {"status": "no_origin"}
    prefix = find_prefix(conn, conv_id, origin, limit)
    out: dict[str, Any] = {"origin": str(prefix.origin), "origin_head": str(prefix.origin_head),
                           "prefix": prefix.length, "turns": len(prefix.anchors), "last_turn": prefix.last_turn}
    if prefix.length == 0:
        return {**out, "status": "empty"}
    c = _Copier(conn, conv_id, prefix, backfill, started + budget_s)
    written = _plan_extractions(c)
    _plan_summaries(c)
    _plan_settings(c)
    c.check()
    c.run()
    _copy_assertions(c, written)
    c.check()
    _copy_embeddings(c)
    _copy_turn_personas(c)
    c.check()
    return {**out, "status": "done", "copied": c.counts, "ms": round((time.perf_counter() - started) * 1000, 1)}


def _bounded(conn: psycopg.Connection, statement_ms: int) -> dict[str, str]:
    before = conn.execute("SELECT current_setting('statement_timeout') AS s, current_setting('lock_timeout') AS l"
                          ).fetchone()
    conn.execute("SELECT set_config('statement_timeout', %s, true), set_config('lock_timeout', %s, true)",
                 (str(statement_ms), str(LOCK_TIMEOUT_MS)))
    return before


def _restore(conn: psycopg.Connection, before: dict[str, str]) -> None:
    conn.execute("SELECT set_config('statement_timeout', %s, true), set_config('lock_timeout', %s, true)",
                 (before["s"], before["l"]))


def _mark(conn: psycopg.Connection, conv_id: UUID, marker: dict[str, Any]) -> None:
    conn.execute("UPDATE conversation SET branch_inherit = %s WHERE id = %s", (Jsonb(marker), conv_id))


def on_first_sync(conn: psycopg.Connection, conv_id: UUID) -> dict[str, Any] | None:
    """Item 5 and 6: the copy on a branch's first applied sync, in a savepoint bounded by `BUDGET_S`; fail-open. Runs
    once: the marker is written whatever happened, and never overwritten here."""
    if conn.execute("SELECT branch_inherit IS NULL AND branched_from_host_chat_ref IS NOT NULL AS due"
                    " FROM conversation WHERE id = %s", (conv_id,)).fetchone()["due"] is not True:
        return None
    started = time.perf_counter()
    try:
        with conn.transaction():
            before = _bounded(conn, STATEMENT_TIMEOUT_MS)
            result = inherit(conn, conv_id)
            _restore(conn, before)
    except Exception as e:  # noqa: BLE001 — the branch starts without inherited memory, as before (item 6)
        log.warning("branch memory not inherited conversation=%s (%s: %s)", conv_id, type(e).__name__,
                    str(e).splitlines()[0][:200] if str(e) else "")
        result = {"status": "failed", "error": type(e).__name__}
    result = {**result, "by": "first_sync", "ms": round((time.perf_counter() - started) * 1000, 1),
              "at": conn.execute("SELECT clock_timestamp() AS t").fetchone()["t"].isoformat()}
    _mark(conn, conv_id, result)
    if result["status"] == "done":
        log.info("branch memory inherited conversation=%s origin=%s prefix=%s copied=%s ms=%s", conv_id,
                 result["origin"], result["prefix"], result["copied"], result["ms"])
    return result


def backfill(conn: psycopg.Connection, conv_id: UUID, dry_run: bool = True) -> dict[str, Any]:
    """Item 5: the explicit copy for a branch synced before this module (or one whose first copy failed). Copies only
    what the branch does not have of its own; zero model and embedding calls. With `dry_run` the same copy runs and is
    rolled back, so the counts are what it would write. The caller holds the conversation's lock."""
    started = time.perf_counter()
    result: dict[str, Any] = {}
    try:
        with conn.transaction() as tx:
            before = _bounded(conn, int(BACKFILL_BUDGET_S * 1000))
            result = inherit(conn, conv_id, backfill=True, budget_s=BACKFILL_BUDGET_S, limit=10 ** 9)
            _restore(conn, before)
            if result["status"] == "done":
                result["jobs_settled"] = drop_covered(conn, conv_id, any_chat=True)
            if dry_run:
                raise psycopg.Rollback(tx)
    except Exception as e:  # noqa: BLE001 — nothing was written; the answer says why
        log.warning("branch back-fill failed conversation=%s (%s)", conv_id, type(e).__name__)
        result = {"status": "failed", "error": type(e).__name__}
    result = {**result, "dry_run": dry_run, "ms": round((time.perf_counter() - started) * 1000, 1)}
    if not dry_run and result["status"] == "done":
        marker = conn.execute("SELECT branch_inherit FROM conversation WHERE id = %s", (conv_id,)).fetchone()
        _mark(conn, conv_id, {**result, "by": "backfill", "before": (marker or {}).get("branch_inherit"),
                              "at": conn.execute("SELECT clock_timestamp() AS t").fetchone()["t"].isoformat()})
    return result


_COVERED = """(
    (j.kind = 'extract' AND EXISTS (
        SELECT 1 FROM extraction x WHERE x.source_revision_id = (j.payload->>'revision_id')::uuid
          AND x.window_hash = j.payload->>'window_hash' AND x.discarded_at IS NULL
          -- the job's generation, or a copy of any generation: an earlier one the origin still served the turn with
          -- serves it in the branch as it did there (ADR 0014, PHASE-57 carry on), with no call
          AND (x.extractor_key = j.payload->>'generation' OR x.coverage ? 'inherited_from')))
    OR (j.kind = 'embed' AND EXISTS (
        SELECT 1 FROM revision_embedding e WHERE e.source_revision_id = (j.payload->>'revision_id')::uuid
          AND e.projection = j.payload->>'generation')))"""


def drop_covered(conn: psycopg.Connection, conv_id: UUID, any_chat: bool = False) -> int:
    """Take back the queued extraction and embedding jobs of an inheriting branch whose result a copy already holds, so
    no job is queued for a prefix turn or message: a row this transaction inserted (`created_at = now()`, the
    transaction's time) is deleted, as if never queued; an older row this sync queued again (`REQUEUE`) is settled
    `done`, what the worker would make of it without a call. The first sync deletes them all; a later one (the tail
    reply accepted, its turn copied) the one it queued. Only a branch whose copy is done (the marker) is touched, unless
    `any_chat` (the back-fill); for any other chat the marker test is a one-time filter and nothing is scanned."""
    inherited = "TRUE" if any_chat else ("EXISTS (SELECT 1 FROM conversation c WHERE c.id = %(c)s"
                                         " AND c.branch_inherit->>'status' = 'done')")
    where = f"j.conversation_id = %(c)s AND j.status = 'queued' AND {inherited} AND {_COVERED}"
    n = conn.execute(f"DELETE FROM job j WHERE {where} AND j.created_at = now()", {"c": conv_id}).rowcount
    return n + conn.execute(f"UPDATE job j SET status = 'done', updated_at = now() WHERE {where}",
                            {"c": conv_id}).rowcount
