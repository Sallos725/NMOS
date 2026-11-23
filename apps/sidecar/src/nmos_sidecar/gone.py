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

# Alive or returned in words outside the brief's recovered list ("살아 있음", "found after going missing", "back
# from the dead"). "발견되지" (not found) and "found dead" / "never found" / "not found" are no return.
ALIVE_KO: tuple[str, ...] = (
    "살아",
    "발견",
)

ALIVE_EN: tuple[str, ...] = (
    "living",
    "found",
    "back from",
)

NEAR_MISS: tuple[str, ...] = (
    "죽지 않",
    "죽을 뻔",
    "죽은 척",
    "죽은 줄 알았",
    "직전",
    "위기",
    "추정",
    "알려",
    "소문",
    "생각",
    "처리",
    "not dead",
    "nearly died",
    "presumed",
    "rumored",
    "rumoured",
    "believed",
    "thought",
    "reportedly",
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
# A negation, a near miss, or hearsay ("죽었다고", "사망했다는", "실종이라는") right after the word.
_KO_POST_NEG = re.compile(r"^[^.,;!?]{0,3}\s*(?:않|아니|뻔|척|줄\s*알|다고|다는|라고|라는)")
_KO_PRE_NEG = re.compile(r"(?:^|\s)안\s+$")

_ALIVE_KO_RE = re.compile(r"살아|발견(?!되지)")
_ALIVE_EN_RE = re.compile(r"\bliving\b|\bback from\b|(?<!not )(?<!never )\bfound\b(?!\s+dead)")

# Someone else's fate inside the subject's status: a noun with a subject or topic particle before the word
# ("동생이 실종됨", "아버지가 사망함"), or an English determiner before it ("her brother was killed").
_KO_OTHER_SUBJECT = re.compile(r"[가-힣](?:이|가|은|는|께서)(?=\s)")
_EN_OTHER_SUBJECT = re.compile(r"\b(?:her|his|their|my|your|our|its|the|a|an)\s+\w")
# The word modifies the noun after it ("실종된 동생", "사망한 아버지", "추방된 왕자"): not the subject's state, except
# a state noun ("사망한 상태", "실종된 지 3년").
_KO_MODIFIES_NOUN = re.compile(r"^(?:한|된|당한)\s+(?!상태|채|것|지(?:\s|$))\S")
# The word is the subject's own state only at the start of the value or right after a word that says how or when
# ("전투 중", "왕국에서", "병으로", "결국"; "is", "went", "still", "found"). After any other word it may be someone
# else's ("동생 실종", "아버지 사망", "brother killed", "left arm missing").
_KO_OWN = re.compile(r"(?:^|(?:에서|중|에|로|결국|끝내|이미|마침내)\s+)$")
_EN_OWN = re.compile(r"(?:^|\b(?:is|was|were|went|gone|got|still|been|now|reported|found)\s+)$")
# "전사" alone is also "warrior": it counts inflected ("전사함", "전사했다") or after "중" / "에서" ("전투 중 전사").
_JEONSA_DIED = re.compile(r"^(?:함|했|하|한)")
_JEONSA_CONTEXT = re.compile(r"(?:중|에서)\s+$")
# "떠남" counts as the whole status or with a for-good word ("영영 떠남"); "마을을 떠남", "잠시 떠남" do not.
_LEAVE_FOR_GOOD = re.compile(r"영영|영원히|다시는")


def _ko_counts(text: str, m: re.Match[str]) -> bool:
    before, after = text[:m.start()], text[m.end():]
    if _KO_OTHER_SUBJECT.search(before) or _KO_MODIFIES_NOUN.match(after):
        return False
    word = m.group(0)
    if word == "떠남":
        return bool(_LEAVE_FOR_GOOD.search(text)) or (not before and not re.search(r"\w", after))
    if not _KO_OWN.search(before):
        return False
    if word == "전사":
        return bool(_JEONSA_DIED.match(after) or _JEONSA_CONTEXT.search(before))
    return True


def _en_counts(text: str, m: re.Match[str]) -> bool:
    before = text[:m.start()]
    return not _EN_OTHER_SUBJECT.search(before) and bool(_EN_OWN.search(before))


def _normalize(value: str | None) -> str:
    if not value:
        return ""
    return norm(unicodedata.normalize("NFC", value))


def is_gone_status(value: str | None) -> bool:
    """Whether a `has_status` value plainly says the character itself is dead, missing or gone for good, now.

    Not when it also says recovered, alive or found, a negation, a near miss or hearsay; nor when the word is
    someone else's fate, a warrior, a missing object, or a leave that is not plainly for good."""
    text = _normalize(value)
    if not text:
        return False
    if any(w in text for w in RECOVERED_KO) or _RECOVERED_EN_RE.search(text):
        return False
    if _ALIVE_KO_RE.search(text) or _ALIVE_EN_RE.search(text):
        return False
    if any(p in text for p in _NEAR_MISS_KO) or _NEAR_MISS_EN_RE.search(text):
        return False

    matched = False
    for m in _GONE_KO_RE.finditer(text):
        if _KO_POST_NEG.match(text[m.end():]) or _KO_PRE_NEG.search(text[:m.start()]):
            return False
        matched = matched or _ko_counts(text, m)

    for m in _GONE_EN_RE.finditer(text):
        if _EN_PRE_NEG.search(text[:m.start()]):
            return False
        matched = matched or _en_counts(text, m)

    return matched


def is_gone_place(name: str | None) -> bool:
    """Whether a `located_in` place's whole normalized name is a non-place (e.g. 저승, the afterlife)."""
    text = _normalize(name)
    return bool(text) and text in NOT_PLACES
