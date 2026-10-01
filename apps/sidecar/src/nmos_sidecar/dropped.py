"""Facts a re-extraction dropped (Phase 22, PHASE-22 Q5–Q7, ADR 0044 amendment 3). Read only, never on the request path.

A turn extracted again by the same generation (a rebuild, the re-extraction after a join's undo, K29's re-extraction
before Phase 22) gets a new model call that words every fact anew and may leave some out (AGE-25). For each turn of the
head whose serving extraction of the active generation replaced a discarded one of the same generation and turn hash,
the narrated facts of the replaced extraction (the latest discarded before it) are compared with the new extraction's,
one to one (`repairs.restated`); a fact neither stated again nor held as narration anywhere in the chat's memory (the
same predicate, subject and object, as entities) is dropped. The owner may restore it (`fact_restore`); nothing is done
on its own. A new extractor generation is not compared: it words facts its own way by design.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import psycopg

from .predicates import REGISTRY, stored_knowledge
from .repairs import RESTORED, _ekey, restated
from .secrets import secret_text

NOT_FACTS = frozenset({"learned", "also_called"})  # a reveal and a name link are not facts (ADR 0033, 0012)

PAIRS = """
SELECT am.turn, am.turn_hash, n.id AS new, o.id AS old
FROM active_membership am
JOIN extraction n ON n.source_revision_id = am.source_revision_id AND n.window_hash = am.turn_hash
                 AND n.extractor_key = %(key)s AND n.discarded_at IS NULL
JOIN LATERAL (SELECT o.id FROM extraction o
              WHERE o.source_revision_id = n.source_revision_id AND o.window_hash = n.window_hash
                AND o.extractor_key = n.extractor_key AND o.discarded_at IS NOT NULL AND o.created_at < n.created_at
              ORDER BY o.discarded_at DESC, o.created_at DESC LIMIT 1) o ON true
WHERE am.commit_id = %(head)s AND am.turn_hash IS NOT NULL
ORDER BY am.turn
"""

ROWS = """
SELECT id, extraction_id, subject, subject_type, predicate, object, object_type, value, epistemic, confidence, evidence,
       knowledge, known_by, hidden_from, polarity, modality, source, asserted_by, salience, participants::text AS participants,
       outcome, because
FROM assertion WHERE extraction_id = ANY(%s) AND status = 'valid' ORDER BY id
"""


def _fact(a: dict[str, Any]) -> bool:
    """A fact memory keeps: narrated (legacy rows without a source count as narration) and actual (ADR 0013)."""
    return (a["predicate"] in REGISTRY and a["predicate"] not in NOT_FACTS and (a.get("source") or "narration") == "narration"
            and (a.get("modality") or "actual") == "actual")


def find(conn: psycopg.Connection, head: UUID, key: str | None, view: dict[str, Any]) -> list[dict[str, Any]]:
    """The head's dropped facts (Q5), oldest turn first. `view` is the chat's memory now (`facts.memory_view`): its
    resolution compares names, and its rows (the owner's restores among them) tell what memory still holds. Each is
    the replaced extraction's assertion as served rows are, with its turn, the turn's hash and its line (`text`)."""
    if key is None:
        return []
    pairs = conn.execute(PAIRS, {"head": head, "key": key}).fetchall()
    if not pairs:
        return []
    by: dict[UUID, list[dict[str, Any]]] = {}
    for row in conn.execute(ROWS, ([p["old"] for p in pairs] + [p["new"] for p in pairs],)).fetchall():
        row = dict(row)
        row["participants"] = json.loads(row["participants"]) if row["participants"] else None
        if row["known_by"] or row["hidden_from"]:
            stored_knowledge(row)
        by.setdefault(row["extraction_id"], []).append(row)
    r = view.get("resolution")
    held = {(a["predicate"], _ekey(r, a.get("subject_type"), a["subject"]), _ekey(r, a.get("object_type"), a.get("object")))
            for a in view.get("assertions") or () if (a.get("source") or "narration") == "narration"}
    out = []
    for p in pairs:
        old = [a for a in by.get(p["old"], []) if _fact(a)]
        again = restated(old, by.get(p["new"], []), r)
        for i, a in enumerate(old):
            if i in again or (a["predicate"], _ekey(r, a.get("subject_type"), a["subject"]),
                              _ekey(r, a.get("object_type"), a.get("object"))) in held:
                continue
            out.append({**a, "turn": p["turn"], "turn_hash": p["turn_hash"], "text": secret_text(a),
                        "replaced": str(p["old"]), "by": str(p["new"])})
    return out

