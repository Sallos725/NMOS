"""Extraction and scene-summary coverage readers (PHASE-60 S1, S2.1).

A turn is *served* when an undiscarded extraction of any generation matches its anchor's `turn_hash`
(D20, ADR 0008, ADR 0014). A turn is *covered* when an extraction serves it and a current, not-held
scene summary holds it (D52, ADR 0042).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

import psycopg

from . import facts, summaries

_SERVED_TURNS = """
SELECT DISTINCT am.turn
FROM active_membership am
JOIN source_revision sr ON sr.id = am.source_revision_id
JOIN extraction e ON e.source_revision_id = am.source_revision_id
                 AND e.window_hash = am.turn_hash
JOIN projection_generation g ON g.key = e.extractor_key
WHERE am.commit_id = %(head)s
  AND am.turn_hash IS NOT NULL
  AND (%(upto)s::int IS NULL OR am.position <= %(upto)s::int)
  AND sr.lifecycle = 'accepted'
  AND coalesce(sr.metadata->>'disabled', '') NOT IN ('true', 'allBefore')
  AND """ + facts._KNOWN.format(t="e")

_LATEST_REPLIED_TURN = """
SELECT max(am.turn) AS turn
FROM active_membership am
WHERE am.commit_id = %(head)s
  AND am.turn_hash IS NOT NULL
  AND (%(upto)s::int IS NULL OR am.position <= %(upto)s::int)
"""


@dataclass(frozen=True)
class Coverage:
    """Extraction and summary coverage of a conversation head as of a request."""

    recorded_through_turn: int | None
    covered_through_turn: int | None
    latest_replied_turn: int | None = None
    served_turns: frozenset[int] = frozenset()
    covered_turns: frozenset[int] = frozenset()

    def response_dict(self) -> dict[str, int | None]:
        return {
            "recorded_through_turn": self.recorded_through_turn,
            "covered_through_turn": self.covered_through_turn,
        }

    def recorded_dict(self) -> dict[str, int | None]:
        return {
            "recorded_through_turn": self.recorded_through_turn,
            "covered_through_turn": self.covered_through_turn,
            "latest_replied_turn": self.latest_replied_turn,
        }


def contiguous_through(turns: set[int] | frozenset[int]) -> int | None:
    """Largest T >= 0 such that every turn 0..T is in `turns`, or None when 0 is absent."""
    t = 0
    while t in turns:
        t += 1
    return t - 1 if t > 0 else None


def extraction_state(
    conn: psycopg.Connection,
    head: UUID,
    upto: int | None = None,
    known_at: datetime | None = None,
) -> tuple[frozenset[int], int | None]:
    """(turns served by any extractor generation, latest replied turn) on `head` as of `upto` and `known_at`."""
    params = {"head": head, "upto": upto, "known_at": known_at}
    served = frozenset(r["turn"] for r in conn.execute(_SERVED_TURNS, params).fetchall())
    latest = conn.execute(_LATEST_REPLIED_TURN, {"head": head, "upto": upto}).fetchone()["turn"]
    return served, latest


def read(
    conn: psycopg.Connection,
    conv_id: UUID,
    head: UUID,
    summarize_key: str | None = None,
    *,
    extractor_key: str | None = None,
    secrets: list[dict[str, Any]] | None = None,
    upto: int | None = None,
    known_at: datetime | None = None,
    served: frozenset[int] | None = None,
    latest_replied: int | None = None,
) -> Coverage:
    """Read extraction and summary coverage for `head` up to `upto` (as of `known_at` for a replay)."""
    if served is None:
        served, latest_replied = extraction_state(conn, head, upto=upto, known_at=known_at)
    recorded = max(served) if served else None
    summarized: set[int] = set()
    if summarize_key and served:
        view = summaries.current(conn, conv_id, head, summarize_key, None, upto=upto, known_at=known_at)
        have = [x for x in view["scenes"] if x["summary"] is not None]
        if have:
            if secrets is None and extractor_key:
                secrets = facts.memory_view(conn, head, extractor_key, upto, known_at)["secrets"]
            for x in have:
                if not secrets or not summaries.held(x["summary"], secrets):
                    w = x["window"]
                    summarized.update(range(w.first_turn, w.last_turn + 1))
    covered = frozenset(served & summarized)
    return Coverage(
        recorded_through_turn=recorded,
        covered_through_turn=contiguous_through(covered),
        latest_replied_turn=latest_replied,
        served_turns=served,
        covered_turns=covered,
    )
