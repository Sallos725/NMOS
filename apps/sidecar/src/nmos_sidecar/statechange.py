"""A status window told as changes (PHASE-43 S4): the core keys' current values, and what changed since the previous
window. Pure functions over the windows `state.windows` reads; no database here."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

CORE_WINDOWS = 10  # the windows a key's change rate is read over (PHASE-43 Q3)
# Scene keys are core whatever their change rate: a story's date changes once in many turns, and is what a model
# without its status bar invents (the incident behind PHASE-43). The clock names are Phase 42's (`source_time.KEYS`).
SCENE_KEYS = frozenset({"date", "날짜", "time", "시간", "시각", "location", "place", "장소", "위치"})
_INT = re.compile(r"^\s*([+-]?\d{1,3}(?:,\d{3})+|[+-]?\d+)\s*$")
_FRACTION = re.compile(r"^\s*([+-]?[\d,]+)\s*/\s*([+-]?[\d,]+)\s*$")
_QUANTITY = re.compile(r"^(?P<name>.*?)\s*[×xX]\s*(?P<n>\d+)\s*$")
_LIST_SEPARATORS = (" / ", ", ")
LIST_MIN = 3  # items before a value counts as a list


def _num(text: str) -> int:
    return int(text.replace(",", ""))


def _signed(n: int) -> str:
    return f"+{n}" if n > 0 else f"−{-n}" if n < 0 else "+0"


def _items(value: str) -> list[str] | None:
    for sep in _LIST_SEPARATORS:
        parts = [p.strip() for p in value.split(sep)]
        if len(parts) >= LIST_MIN and all(parts):
            return parts
    return None


def _counted(items: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for item in items:
        m = _QUANTITY.match(item)
        name, n = (m["name"].strip(), int(m["n"])) if m and m["name"].strip() else (item, 1)
        out[name] = out.get(name, 0) + n
    return out


def list_change(before: str, after: str) -> str | None:
    """`+ added · − removed · name ×n (±k)`, by item name; None when either value is not a list."""
    a, b = _items(before), _items(after)
    if a is None and b is None:
        return None
    old, new = _counted(a or [before]), _counted(b or [after])
    parts = [f"+{n}" + (f" ×{new[n]}" if new[n] != 1 else "") for n in new if n not in old]
    parts += [f"−{n}" for n in old if n not in new]
    parts += [f"{n} ×{new[n]} ({_signed(new[n] - old[n])})" for n in new if n in old and new[n] != old[n]]
    return " · ".join(parts) or None


def change(before: str | None, after: str) -> str | None:
    """How `after` differs from `before`, as text for a `since_previous` mark; None when nothing to say (no previous
    value, the same value, or a text value whose new value says it all). Dates and times stay text: no arithmetic."""
    if before is None or before == after:
        return None
    if (x := _INT.match(before)) and (y := _INT.match(after)):
        return _signed(_num(y[1]) - _num(x[1]))
    if (x := _FRACTION.match(before)) and (y := _FRACTION.match(after)):
        first = _signed(_num(y[1]) - _num(x[1]))
        return first if x[2] == y[2] else f"{first}, max {_signed(_num(y[2]) - _num(x[2]))}"
    return list_change(before, after)


def scene_key(key: str) -> bool:
    """A date, time or place key, also under an entity (`도윤.location`)."""
    return key.rsplit(".", 1)[-1].strip().casefold() in SCENE_KEYS


def core_keys(windows: list[dict[str, Any]], pins: frozenset[str] | set[str] = frozenset()) -> set[str]:
    """Pinned keys, scene keys, and those that changed in at least half of the last CORE_WINDOWS windows (PHASE-43
    Q3)."""
    recent = windows[-CORE_WINDOWS:]
    counts: dict[str, int] = {}
    for prev, cur in zip(recent, recent[1:]):
        for key, value in cur["values"].items():
            if key in prev["values"] and prev["values"][key] != value:
                counts[key] = counts.get(key, 0) + 1
    floor = max(1, len(recent) // 2)
    scene = {k for w in recent for k in w["values"] if scene_key(k)}
    return set(pins) | scene | {k for k, n in counts.items() if n >= floor}


@dataclass(frozen=True)
class Told:
    key: str
    value: str  # "" when only the change is told (a list the message did not ask about)
    turn: int | None
    since_previous: str | None


def tell(windows: list[dict[str, Any]], pins: frozenset[str] | set[str] = frozenset(),
         asked: frozenset[str] | set[str] = frozenset(), by_turn: bool = True) -> list[Told]:
    """The status as core values and changes: core keys' current values; other keys only when the last window changed
    them (or first set them); a list's whole value only when the message asked about it. With one window there is
    nothing to compare: every key is new and told. Keys absent from the last window are left out."""
    if not windows:
        return []
    last = windows[-1]
    prev = windows[-2]["values"] if len(windows) > 1 else None
    core = core_keys(windows, pins)
    turn = last["turn"] if by_turn else last["position"]
    out: list[Told] = []
    for key, value in last["values"].items():
        before = None if prev is None else prev.get(key)
        changed = prev is None or before != value
        if key not in core and not changed:
            continue
        mark = change(before, value)
        listed = _items(value) is not None
        shown = "" if listed and mark and key not in asked and key not in core else value
        out.append(Told(key, shown, turn, mark))
    return sorted(out, key=lambda t: (t.key not in core, t.key not in asked))
