"""Role endings the owner should see (ADR 0064 item 4, PHASE-28 Q7). Read only, never on the request path.

The extraction and its confirmation are the same model reading the same turn: when both are wrong they agree (S1 turn
227), and a held ending only shows that they disagreed. So both kinds are listed under the Inspector's "Needs
attention", each with the owner's one action, and nothing is done on its own:

- **automatic**: an ending extract-v16 applied after its confirmation said yes, in the last `RECENT_TURNS` turns. The
  owner keeps the role by retracting the ending (`fact_retract`): the version before it is current again.
- **held**: an ending a confirmation did not confirm (a pending row, reason `extraction.HELD`). The owner applies it by
  restoring it (`fact_restore`, as a fact a re-extraction dropped): the owner's version at the end of its turn.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import psycopg

from .entities import norm
from .facts import ACTIVE_ASSERTIONS
from .repairs import _ekey
from .secrets import secret_text

HELD = "role ending not confirmed"  # extraction.HELD, the reason prefix of a held ending
RECENT_TURNS = 30  # an automatic ending older than this is no longer listed (the facts list still retracts it)

# The serving extractions' held endings: the fact read's rows (ACTIVE_ASSERTIONS), pending instead of valid.
_SERVED = "AND a.status = 'valid'"
assert ACTIVE_ASSERTIONS.count(_SERVED) == 1 and ACTIVE_ASSERTIONS.count("SELECT a.id,") == 1, "the fact read moved"
HELD_ASSERTIONS = (ACTIVE_ASSERTIONS
                   .replace("SELECT a.id,", "SELECT a.reason, a.id,")
                   .replace(_SERVED, "AND a.status = 'pending' AND a.predicate = 'role_toward' AND a.polarity = 'negative'"
                                     " AND a.reason LIKE %(held)s"))

CONFIRMATIONS = """
SELECT a.id, x.raw->'confirmations' AS confirmations
FROM assertion a JOIN extraction x ON x.id = a.extraction_id
WHERE a.id = ANY(%s)
"""


def _role(a: dict[str, Any]) -> tuple:
    return a.get("subject"), a.get("object"), a.get("value")


def _same(r: Any, a: dict[str, Any]) -> tuple:
    """A role as the chat's entities read it: the same pair under any of their names, the same value."""
    return (_ekey(r, a.get("subject_type"), a.get("subject")), _ekey(r, a.get("object_type"), a.get("object")),
            norm(a.get("value")))


def _confirmation(found: Any, a: dict[str, Any], outcome: str | None = None) -> dict[str, Any] | None:
    """The confirmation of this ending in its extraction's raw record (`extraction.confirm_endings`), if any."""
    for c in found or ():
        role = c.get("role") or {}
        if (role.get("by"), role.get("to"), role.get("role")) == _role(a) and (outcome is None or c.get("outcome") == outcome):
            return c
    return None


def automatic(conn: psycopg.Connection, view: dict[str, Any], last_turn: int | None) -> list[dict[str, Any]]:
    """The recent role endings a confirmation let through and the owner has not retracted, newest turn first: each the
    current fact (the ending, with the `id` a retraction names) and the quotes of both calls."""
    ended = [f for f in view.get("facts") or () if f.get("predicate") == "role_toward" and f.get("polarity") == "negative"
             and not f.get("owner") and not f.get("canon") and isinstance(f.get("id"), int) and f.get("turn") is not None
             and (last_turn is None or f["turn"] >= last_turn - RECENT_TURNS)]
    if not ended:
        return []
    raw = {r["id"]: r["confirmations"] for r in conn.execute(CONFIRMATIONS, ([f["id"] for f in ended],)).fetchall()}
    out = []
    for f in ended:
        c = _confirmation(raw.get(f["id"]), f, "yes")
        if c is not None:
            out.append({**f, "ending": c.get("ending"), "quote": c.get("quote")})
    return sorted(out, key=lambda f: -f["turn"])


def held(conn: psycopg.Connection, head: UUID, key: str | None, view: dict[str, Any]) -> list[dict[str, Any]]:
    """The serving extractions' endings a confirmation held, oldest turn first, as a restore names them (the columns a
    dropped fact has, `dropped.find`), with the reason and the confirmation. Not listed: one the owner restored, or a
    role the chat's memory no longer holds as current (the story ended it since)."""
    if key is None:
        return []
    rows = conn.execute(HELD_ASSERTIONS, {"head": head, "key": key, "held": HELD + "%"}).fetchall()
    if not rows:
        return []
    raw = {r["id"]: r["confirmations"] for r in conn.execute(CONFIRMATIONS, ([a["id"] for a in rows],)).fetchall()}
    r = view.get("resolution")
    restored = {(t.get("turn"), *_same(r, t.get("fact") or {}))
                for rep in view.get("repairs") or () if rep.get("kind") == "fact_restore" and not rep.get("removed_at")
                for t in [rep.get("target") or {}]}
    current = {_same(r, f) for f in view.get("facts") or ()
               if f.get("predicate") == "role_toward" and f.get("polarity") == "positive"}
    out = []
    for a in rows:
        a = dict(a)
        a["participants"] = json.loads(a["participants"]) if a.get("participants") else None
        if (a["turn"], *_same(r, a)) in restored or _same(r, a) not in current:
            continue
        out.append({**a, "text": secret_text(a), "confirmation": _confirmation(raw.get(a["id"]), a)})
    return out


# PHASE-29 Q5: an alias whose two names are both in the turn, held by its confirmation (extraction.ALIAS_HELD), is listed
# beside the held endings: a wrong hold leaves one person's two names apart, the defect Phase 28 corrected.
ALIAS_HELD = "alias not confirmed"  # extraction.ALIAS_HELD
HELD_ALIASES = (ACTIVE_ASSERTIONS
                .replace("SELECT a.id,", "SELECT a.reason, a.id,")
                .replace(_SERVED, "AND a.status = 'pending' AND a.predicate = 'also_called' AND a.reason LIKE %(held)s"))
ALIAS_CONFIRMATIONS = """
SELECT a.id, x.raw->'alias_confirmations' AS confirmations
FROM assertion a JOIN extraction x ON x.id = a.extraction_id
WHERE a.id = ANY(%s)
"""


def held_aliases(conn: psycopg.Connection, head: UUID, key: str | None, view: dict[str, Any]) -> list[dict[str, Any]]:
    """The serving extractions' aliases a confirmation held, oldest turn first, each with its confirmation. Not listed:
    one whose two names the chat's memory already holds as one entity (the owner linked them, or a later alias did)."""
    if key is None:
        return []
    rows = conn.execute(HELD_ALIASES, {"head": head, "key": key, "held": ALIAS_HELD + "%"}).fetchall()
    if not rows:
        return []
    raw = {r["id"]: r["confirmations"] for r in conn.execute(ALIAS_CONFIRMATIONS, ([a["id"] for a in rows],)).fetchall()}
    r = view.get("resolution")
    out = []
    for a in rows:
        a = dict(a)
        if r is not None and _ekey(r, a.get("subject_type"), a.get("subject")) == _ekey(r, a.get("subject_type"),
                                                                                       a.get("value")):
            continue
        found = next((c for c in raw.get(a["id"]) or () if (c.get("subject"), c.get("value"))
                      == (a.get("subject"), a.get("value"))), None)
        out.append({**a, "confirmation": found})
    return sorted(out, key=lambda a: (a.get("turn") or 0, a["id"]))
