"""Reused spans between two texts (ADR 0027): what a reply took from a packet line (echo), and whether an
excerpt only repeats a fact line (packet-v1). Pure.

For Korean (or other CJK) text a span is a run of 4 characters, spaces ignored; for Latin-script text,
a word of at least 4 letters that is not a common one. Spans the request itself held do not count: a span
whose first or last 3 characters occur in the user's message or the previous reply is that request's
word with another ending (Korean particles: "비밀번호가" asked, "비밀번호는" in the reply).
"""

from __future__ import annotations

import re

from .entities import norm

SPAN_WIDE = 4  # characters of a reused span when the content is mostly Korean (or other non-Latin script)
WORD_MIN = 4  # otherwise a reused word: at least this long and not a common word
COMMON = frozenset("that this with from have they them their there what when where which about into your said "
                   "says will would been were than then also just like only some very over".split())


def _squash(text: str | None) -> str:
    return "".join(norm(text).split())


def _grams(text: str, n: int) -> set[str]:
    return {text[i: i + n] for i in range(len(text) - n + 1)}


def _wide(text: str) -> bool:
    return sum(1 for ch in text if ord(ch) > 0x2E7F) * 2 >= len(text)  # mostly CJK or Hangul


def _words(text: str | None) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9']+", norm(text)) if len(w) >= WORD_MIN and w not in COMMON}


def reuse(content: str | None, reply: str | None, request: tuple[str | None, ...] = ()) -> float:
    """Share of the content's spans (Korean) or words (Latin script) the reply reuses that the request
    itself did not contain (see the module notes); 0.0 when none. Content shorter than a span counts
    whole."""
    c, r = _squash(content), _squash(reply)
    if not c or not r:
        return 0.0
    asked = [_squash(x) for x in request if x]
    if not _wide(c):
        words, said = _words(content), set().union(*(_words(x) for x in request if x)) if request else set()
        if not words:
            return 1.0 if c in r and not any(c in a for a in asked) else 0.0
        return len({w for w in words & _words(reply) if w not in said}) / len(words)
    n = SPAN_WIDE
    if len(c) <= n:
        return 1.0 if c in r and not any(c in a for a in asked) else 0.0
    grams = _grams(c, n)
    # A span whose first or last n-1 characters the request holds is the request's word with another
    # ending (Korean particles: "비밀번호가" asked, "비밀번호는" in the reply), not reuse.
    reused = {g for g in grams & _grams(r, n) if not any(g[:-1] in a or g[1:] in a for a in asked)}
    return len(reused) / len(grams)


def reused(content: str | None, reply: str | None, request: tuple[str | None, ...] = ()) -> bool:
    return reuse(content, reply, request) > 0
