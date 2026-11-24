"""Return-gap and settled-thread rules for packet-v20 (PHASE-60 S4, ADR 0082 items 4, 5).

Pure: no database, standard library only.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Iterable
from typing import Any

RUN_GAP = 5
RUN_START_MAX = 5
GAP_MIN = 40
SETTLED_TURNS = 15
SETTLED_MAX = 3
SETTLED_BAD = ("broken", "failed", "abandoned")
SETTLED_GOOD = ("kept", "achieved", "paid", "answered", "averted")

_SETTLED_BAD_SET = frozenset(SETTLED_BAD)
_SETTLED_ALLOWED = _SETTLED_BAD_SET | frozenset(SETTLED_GOOD)


def return_gap(
    appearances: Iterable[int],
    served: Callable[[int], bool] | Collection[int],
    now: int,
) -> int | None:
    """Served turns a character was absent before its current run, or None.

    Turns no extraction serves are not counted: an unextracted turn is unknown, not an absence
    (invariant 4, ADR 0082 item 4).
    """
    turns = sorted({t for t in appearances if t <= now})
    if not turns or turns[-1] < now - RUN_GAP:
        return None
    idx = len(turns) - 1
    while idx > 0 and turns[idx] - turns[idx - 1] <= RUN_GAP:
        idx -= 1
    run_start = turns[idx]
    if run_start < now - RUN_START_MAX or idx == 0:
        return None
    previous = turns[idx - 1]
    if callable(served):
        gap = sum(1 for t in range(previous + 1, run_start) if served(t))
    else:
        served_turns = served if isinstance(served, (set, frozenset, range, dict)) else set(served)
        gap = sum(1 for t in range(previous + 1, run_start) if t in served_turns)
    return gap if gap >= GAP_MIN else None


def back_after_label(gap: int) -> str:
    """Format a return gap rounded to the nearest ten, halves up (45 -> '~50 turns')."""
    rounded = ((gap + 5) // 10) * 10
    return f"~{rounded} turns"


def _pos(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else -1


def settled(
    threads: list[dict[str, Any]],
    now: int,
    involved: Callable[[dict[str, Any]], bool],
) -> list[dict[str, Any]]:
    """Threads closed within SETTLED_TURNS of `now` for which `involved` holds.

    Ordered bad outcomes before good outcomes, then newest closing turn first, then newest
    position; capped at SETTLED_MAX (ADR 0082 item 5).
    """
    picked: list[tuple[int, int, int, int, dict[str, Any]]] = []
    oldest = now - SETTLED_TURNS
    for t in threads:
        status = t.get("status")
        if status not in _SETTLED_ALLOWED:
            continue
        closed_by = t.get("closed_by")
        closed_turn = closed_by.get("turn") if isinstance(closed_by, dict) else None
        if not isinstance(closed_turn, int) or isinstance(closed_turn, bool):
            continue
        if not (oldest <= closed_turn <= now):
            continue
        if not involved(t):
            continue
        bucket = 0 if status in _SETTLED_BAD_SET else 1
        closed_pos = _pos(closed_by.get("position"))
        thread_pos = _pos(t.get("position"))
        picked.append((bucket, -closed_turn, -closed_pos, -thread_pos, t))
    picked.sort(key=lambda item: item[:4])
    return [item[4] for item in picked[:SETTLED_MAX]]
