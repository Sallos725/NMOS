"""Pure read-side word rule for a character who is gone (PHASE-60 S3, ADR 0082).

The rule errs toward not pinning; a missed pin is today's behaviour, a wrong pin silences a living character.
The word lists are read-side constants of `packet-v20`: a change to them is a new policy, so traces replay.
"""

from __future__ import annotations

import re
import unicodedata

from .entities import norm

GONE_KO: tuple[str, ...] = (
    "사망",
    "죽음",
    "죽었",
    "전사",
    "실종",
    "행방불명",
    "떠남",
    "추방",
)

GONE_EN: tuple[str, ...] = (
    "dead",
    "killed",
    "deceased",
    "missing",
    "vanished",
    "departed for good",
    "exiled",
)

RECOVERED_KO: tuple[str, ...] = (
    "회복",
    "생존",
    "귀환",
    "부활",
)

RECOVERED_EN: tuple[str, ...] = (
    "recovered",
    "returned",
    "alive",
    "revived",
)

NEAR_MISS: tuple[str, ...] = (
    "죽지 않",
    "죽을 뻔",
    "죽은 척",
    "죽은 줄 알았",
    "not dead",
    "nearly died",
    "presumed",
)

NOT_PLACES: frozenset[str] = frozenset({
    "행방불명",
    "실종",
    "저승",
    "사후세계",
    "missing",
    "the afterlife",
    "afterlife",
})


_KO_FOLLOWERS = "함했하됨되한된당다음"
_EN_FOLLOWERS: tuple[str, ...] = (
    "in",
    "at",
    "on",
    "after",
    "since",
    "from",
    "without",
    "and",
    "by",
    "during",
    "for good",
)


def _en_pattern(phrases: tuple[str, ...]) -> re.Pattern[str]:
    ordered = sorted(phrases, key=len, reverse=True)
    return re.compile(r"\b(?:" + "|".join(re.escape(p) for p in ordered) + r")\b")


_GONE_KO_RE = re.compile(
    r"(?<!\w)(?:"
    + "|".join(re.escape(w) for w in sorted(GONE_KO, key=len, reverse=True))
    + r")(?=$|\W|["
    + _KO_FOLLOWERS
    + r"])"
)
_EN_FOLLOWER_ALT = "|".join(re.escape(w) for w in sorted(_EN_FOLLOWERS, key=len, reverse=True))
_GONE_EN_RE = re.compile(
    r"\b(?:"
    + "|".join(re.escape(w) for w in sorted(GONE_EN, key=len, reverse=True))
    + r")\b(?=$|[^\w\s]|\s+(?:"
    + _EN_FOLLOWER_ALT
    + r")\b)"
)
_RECOVERED_EN_RE = _en_pattern(RECOVERED_EN)
_NEAR_MISS_KO = tuple(p for p in NEAR_MISS if not p.isascii())
_NEAR_MISS_EN_RE = _en_pattern(tuple(p for p in NEAR_MISS if p.isascii()))

_EN_PRE_NEG = re.compile(r"(?:\b(?:not|no longer|never|presumed|nearly|almost)|n't)\s+$")
_KO_POST_NEG = re.compile(r"^[^.,;!?]{0,3}\s*(?:않|아니|뻔|척|줄\s*알)")
_KO_PRE_NEG = re.compile(r"(?:^|\s)안\s+$")


def _normalize(value: str | None) -> str:
    if not value:
        return ""
    return norm(unicodedata.normalize("NFC", value))


def is_gone_status(value: str | None) -> bool:
    """Whether a `has_status` value says a character is gone without recovery, negation, or near miss."""
    text = _normalize(value)
    if not text:
        return False
    if any(w in text for w in RECOVERED_KO) or _RECOVERED_EN_RE.search(text):
        return False
    if any(p in text for p in _NEAR_MISS_KO) or _NEAR_MISS_EN_RE.search(text):
        return False

    matched = False
    for m in _GONE_KO_RE.finditer(text):
        matched = True
        if _KO_POST_NEG.match(text[m.end():]) or _KO_PRE_NEG.search(text[:m.start()]):
            return False

    for m in _GONE_EN_RE.finditer(text):
        matched = True
        if _EN_PRE_NEG.search(text[:m.start()]):
            return False

    return matched


def is_gone_place(name: str | None) -> bool:
    """Whether a `located_in` place's whole normalized name is a non-place (e.g. 저승, the afterlife)."""
    text = _normalize(name)
    return bool(text) and text in NOT_PLACES
