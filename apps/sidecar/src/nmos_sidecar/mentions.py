"""Pure @name mention parser for per-request character pinning (PHASE-60 S8, ADR 0087).

An `@` at the start of a word followed by a known normalized character name or alias (with at most
one trailing Korean particle from `keywords._SOURCE_PARTICLES`) resolves to that character's key.
An `@` inside a word (such as an email address or handle) or before an unknown name does nothing.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping

from .entities import norm
from .keywords import _SOURCE_PARTICLES

# Longest particle first so compound particles (e.g. "에서는", "에게는") beat shorter suffixes.
_PARTICLES: tuple[str, ...] = tuple(sorted(_SOURCE_PARTICLES, key=len, reverse=True))

# Non-whitespace characters allowed immediately before `@` (never letter, digit, `_`, `.` or `-`).
_BEFORE_OK: frozenset[str] = frozenset("([{\"'“‘「『,!?…")

# Characters that terminate a mention token after `@`.
_AFTER_STOP: frozenset[str] = frozenset(",.!?…:;)]}\"'”’」』")


def _read_token(text: str, start: int) -> tuple[str, int]:
    end = start
    length = len(text)
    while end < length and not text[end].isspace() and text[end] not in _AFTER_STOP:
        end += 1
    return text[start:end], end


def _match(candidate: str, names: Mapping[str, str]) -> str | None:
    key = norm(candidate)
    if not key:
        return None
    if key in names:
        return names[key]
    for particle in _PARTICLES:
        if key.endswith(particle):
            stem = key[: -len(particle)]
            if stem and stem in names:
                return names[stem]
    return None


def at_mentions(
    query: str,
    names: Mapping[str, str],
    blocked: Collection[str] = (),
) -> list[str]:
    """Return pinned character keys named by `@mention` in `query`, in first-appearance order.

    `names` maps each normalized character name or alias to its caller-chosen key. Keys in
    `blocked` (such as the persona or excluded characters) are never returned.
    """
    if not query or not names:
        return []
    blocked_set = set(blocked)
    seen: set[str] = set()
    out: list[str] = []
    length = len(query)
    i = 0
    while i < length:
        pos = query.find("@", i)
        if pos < 0:
            break
        i = pos + 1
        if pos > 0 and not (query[pos - 1].isspace() or query[pos - 1] in _BEFORE_OK):
            continue
        token, end = _read_token(query, pos + 1)
        if not token:
            continue
        matched: str | None = None
        if end < length and query[end].isspace() and query[end] not in "\r\n":
            nxt = end + 1
            while nxt < length and query[nxt].isspace() and query[nxt] not in "\r\n":
                nxt += 1
            second, second_end = _read_token(query, nxt)
            if second and not second.startswith("@"):
                matched = _match(f"{token} {second}", names)
                if matched is not None:
                    i = second_end
        if matched is None:
            matched = _match(token, names)
            if matched is not None:
                i = end
        if matched is not None and matched not in blocked_set and matched not in seen:
            seen.add(matched)
            out.append(matched)
    return out
