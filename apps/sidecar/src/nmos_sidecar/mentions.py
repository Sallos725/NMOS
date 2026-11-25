"""Pure @name mention parser for per-request character pinning (PHASE-60 S8, ADR 0087).

An `@` at the start of a word followed by a known normalized character name or alias (with at most
one trailing Korean particle from `keywords._SOURCE_PARTICLES`) resolves to that character's key.
An `@` inside a word (such as an email address or handle) or before an unknown name does nothing.

Tier 1 (B5): a name may also carry a vocative (`@하람아`, `@세라야`), an honorific written onto it (`@세라님`,
`@기현씨`), or an honorific and then one particle (`@세라님께서`, `@세라님은`); a name runs to three
words (`@세라 델 모렌`), and an apostrophe inside a word belongs to it (`@O'Connor`). `aliases` (optional, as
`variants.aliases` gives them) widens each name by the other names its character goes by in this request.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping

from .entities import norm
from .keywords import _SOURCE_PARTICLES

# Longest particle first so compound particles (e.g. "에서는", "에게는") beat shorter suffixes. A vocative (아, 야, 여) and
# the honorific subject particles (께서, 께) end a name the way a particle does.
_PARTICLES: tuple[str, ...] = tuple(sorted({*_SOURCE_PARTICLES, "께서", "께", "아", "야", "여"}, key=len, reverse=True))
# Honorifics written onto a name; one may come before the particle (세라님께서, 기현씨는).
_HONORIFICS: tuple[str, ...] = ("님", "씨", "군", "양")
MAX_WORDS = 3  # a name of up to three words (세라 델 모렌)

# Non-whitespace characters allowed immediately before `@` (never letter, digit, `_`, `.` or `-`).
_BEFORE_OK: frozenset[str] = frozenset("([{\"'“‘「『,!?…")

# Characters that terminate a mention token after `@`.
_AFTER_STOP: frozenset[str] = frozenset(",.!?…:;)]}\"'”’」』")


def _read_token(text: str, start: int) -> tuple[str, int]:
    end = start
    length = len(text)
    while end < length and not text[end].isspace():
        if text[end] in _AFTER_STOP:
            # An apostrophe between two letters is part of the word (O'Connor, D’Arcy); otherwise it closes a quote.
            if not (text[end] in "'’" and end > start and text[end - 1].isalpha()
                    and end + 1 < length and text[end + 1].isalpha()):
                break
        end += 1
    return text[start:end], end


def _stems(key: str) -> Iterable[str]:
    """The name `key` may be once a trailing honorific, a particle, or an honorific and then a particle is taken off,
    longest particle first."""
    for particle in ("", *_PARTICLES):
        if particle and not key.endswith(particle):
            continue
        stem = key[: len(key) - len(particle)]
        if not stem:
            continue
        if particle:
            yield stem
        for honorific in _HONORIFICS:
            if stem.endswith(honorific) and len(stem) > len(honorific):
                yield stem[: -len(honorific)]


def _match(candidate: str, names: Mapping[str, str]) -> str | None:
    key = norm(candidate)
    if not key:
        return None
    if key in names:
        return names[key]
    for stem in _stems(key):
        if stem in names:
            return names[stem]
    return None


def _widen(names: Mapping[str, str], aliases: Mapping[str, Iterable[str]] | None) -> Mapping[str, str]:
    """`names` and each name's other names in this request (`variants.aliases`): a name the caller gave keeps its
    key, and an other name two keys would share names neither."""
    if not aliases:
        return names
    extra: dict[str, set[str]] = {}
    for name, k in names.items():
        for other in aliases.get(name, ()):
            if (o := norm(other)) and o not in names:
                extra.setdefault(o, set()).add(k)
    return {**names, **{o: next(iter(ks)) for o, ks in extra.items() if len(ks) == 1}}


def at_mentions(
    query: str,
    names: Mapping[str, str],
    blocked: Collection[str] = (),
    aliases: Mapping[str, Iterable[str]] | None = None,
) -> list[str]:
    """Return pinned character keys named by `@mention` in `query`, in first-appearance order.

    `names` maps each normalized character name or alias to its caller-chosen key. Keys in
    `blocked` (such as the persona or excluded characters) are never returned. `aliases` (optional):
    normalized name → the other normalized names it goes by in this request (`variants.aliases`).
    """
    names = _widen(names, aliases)
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
        words, ends = [token], [end]
        while len(words) < MAX_WORDS:  # the following words on the same line
            cur = ends[-1]
            if not (cur < length and query[cur].isspace() and query[cur] not in "\r\n"):
                break
            nxt = cur + 1
            while nxt < length and query[nxt].isspace() and query[nxt] not in "\r\n":
                nxt += 1
            word, word_end = _read_token(query, nxt)
            if not word or word.startswith("@"):
                break
            words.append(word)
            ends.append(word_end)
        matched: str | None = None
        for count in range(len(words), 0, -1):  # the longest name first
            matched = _match(" ".join(words[:count]), names)
            if matched is not None:
                i = ends[count - 1]
                break
        if matched is not None and matched not in blocked_set and matched not in seen:
            seen.add(matched)
            out.append(matched)
    return out
