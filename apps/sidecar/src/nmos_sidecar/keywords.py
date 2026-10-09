"""The words of a user message that name something (PHASE-18 Q1, ADR 0052).

Lexical recall scores a whole message against each head message (D15, ADR 0004). A natural question dilutes that
score with its own words ("…이름이 뭐였더라?"), so the message that answers it often stays under the bar. The keyword
route (retrieval) looks each of these words up on its own. Deterministic, no dependency: Korean particles and question
endings come off a word's end from fixed lists; a word that would shrink under two syllables keeps its form (민지, 사과),
and a one-syllable ending that may belong to a name keeps the word beside its stem (서도윤이 → 서도윤이, 서도윤).
"""

from __future__ import annotations

import re

KEYWORDS_MAX = 4  # per request, longest first (PHASE-18 Q1)
MIN_HANGUL, MIN_LATIN = 2, 3

# Endings that close a question or a remark, then particles; longest first so "에서는" goes before "는".
_SUFFIXES = sorted({
    # question and sentence endings
    "이었더라", "였더라", "이었지", "였었지", "였지", "었지", "았지", "했지", "더라", "던가", "었나", "았나", "했나",
    "이었어", "였어", "었어", "았어", "했어", "이에요", "예요", "에요", "이야", "이지", "인가", "인지", "일까",
    "니", "냐", "나", "까", "야", "지", "요",
    # particles (and their common stacks)
    "에게서", "한테서", "에서는", "에게는", "한테는", "으로는", "로는", "에서도", "에게", "한테", "에서", "으로",
    "이랑", "하고", "처럼", "까지", "부터", "보다", "마다", "밖에", "이나", "이며",
    "은", "는", "이", "가", "을", "를", "의", "에", "도", "만", "로", "와", "과", "랑",
}, key=len, reverse=True)

STOP_WORDS = frozenset({
    "뭐", "뭐야", "뭐지", "무엇", "무슨", "어떤", "어디", "누구", "누가", "언제", "왜", "어떻게", "얼마", "몇",
    "지금", "요즘", "그때", "아까", "혹시", "정말", "진짜", "그냥", "그리고", "그래서", "근데", "그럼", "그런데",
    "이거", "그거", "저거", "이것", "그것", "저것", "이제", "다시", "우리", "제가", "내가", "네가", "너는", "나는",
    "있어", "있지", "없어", "했던", "하는", "하고", "알아", "기억", "기억나", "이야기", "얘기", "거기", "여기", "저기",
    "사이", "상태", "어때", "어땠", "했었", "있었", "뭐였",
    "the", "and", "what", "who", "where", "when", "why", "how", "was", "were", "did", "does", "is", "are", "you",
    "that", "this", "with", "about", "now",
})

# A word starting with an interrogative is the question itself ("뭐였더라", "어디야", "누구랑").
_QUESTION_STARTS = ("뭐", "무엇", "무슨", "어디", "어느", "누구", "누가", "언제", "왜", "어떻", "어땠", "얼마", "몇")

# A word that ends like a verb or an adjective ("먹었어", "끝나고", "팔아서", "받으라고") says what happened, not what
# it happened to: it is looked up only when fewer than KEYWORDS_MAX names and nouns were found.
_VERBISH = ("었어", "았어", "였어", "했어", "었지", "았지", "했지", "었다", "았다", "했다", "었던", "았던", "했던",
            "어서", "아서", "해서", "라고", "다고", "는데", "니까", "으면", "려고", "하고", "고", "면", "던", "을", "는")

_WORD = re.compile(r"[0-9A-Za-z가-힣]+")
_HANGUL = re.compile(r"^[가-힣]+$")


def _stems(word: str) -> tuple[str, list[str]]:
    """The word's stem after at most two endings or particles ("…이었지", then "…에게"), and the longer forms kept
    only as a fallback: a one-syllable suffix may be the end of a name. A stem under two syllables is not a stem."""
    fallback: list[str] = []
    current = word
    for _ in range(2):
        # the longest suffix that still leaves a stem of two syllables ("사이야": not "이야", but "야")
        suffix = next((s for s in _SUFFIXES if current.endswith(s) and len(current) - len(s) >= MIN_HANGUL), None)
        if suffix is None:
            break
        stem = current[: -len(suffix)]
        if len(suffix) == 1:
            fallback.insert(0, current)
        current = stem
    return current, fallback


def keywords(query: str) -> list[str]:
    """At most KEYWORDS_MAX words to look up on their own: stems first, longest first (ties keep the message's order),
    then the fallback forms if room is left."""
    primary: list[str] = []
    fallback: list[str] = []
    for raw in _WORD.findall(query):
        word = raw.lower()
        if _HANGUL.match(word):
            if word.startswith(_QUESTION_STARTS):
                continue
            stem, longer = _stems(word)
            if len(stem) >= MIN_HANGUL and stem not in STOP_WORDS:
                (fallback if stem.endswith(_VERBISH) else primary).append(stem)
                fallback.extend(longer)
        elif word.isascii() and word.isalpha() and len(word) >= MIN_LATIN and word not in STOP_WORDS:
            primary.append(word)
        # numbers and mixed tokens: the whole-message route still sees them
    primary = list(dict.fromkeys(primary))
    order = {w: i for i, w in enumerate(primary)}
    chosen = sorted(primary, key=lambda w: (-len(w), order[w]))[:KEYWORDS_MAX]
    for w in dict.fromkeys(fallback):
        if len(chosen) >= KEYWORDS_MAX:
            break
        if w not in chosen:
            chosen.append(w)
    return chosen


# Source-side suffixes are particles only, not question/verb endings. The exact
# word boundary is checked after an indexed candidate prefilter (PHASE-41).
_SOURCE_PARTICLES = (
    "에게서", "한테서", "에서는", "에게는", "한테는", "으로는", "로는", "에서도",
    "에게", "한테", "에서", "으로", "이랑", "하고", "처럼", "까지", "부터", "보다", "마다", "밖에", "이나", "이며",
    "은", "는", "이", "가", "을", "를", "의", "에", "도", "만", "로", "와", "과", "랑",
)


def particle_lookup(word: str) -> tuple[list[str], str] | None:
    """Cheap index guards and the exact PostgreSQL word/particle boundary check.

    The coarse trigram branch also covers every other word boundary. These two
    LIKE guards avoid repeatedly scoring long messages at common start/space
    occurrences; neither their prefix matches nor the coarse score admits a row.
    """
    if len(word) < MIN_HANGUL or not _HANGUL.fullmatch(word):
        return None
    return ([word + "%", "% " + word + "%"],
            r"\m" + word + "(" + "|".join(_SOURCE_PARTICLES) + r")\M")
