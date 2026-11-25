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


def keywords(query: str, *, v21: bool = False) -> list[str]:
    """At most KEYWORDS_MAX words to look up on their own: stems first, longest first (ties keep the message's order),
    then the fallback forms if room is left. `v21`: `keywords_v21` (the default is `packet-v20`'s, unchanged)."""
    if v21:
        return keywords_v21(query)
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


# --- packet-v21 (the defaults above are packet-v20's and stay as they are: a change to them is a new policy) -------------
# A word loses at most one question ending, and only where the clause ends ("…뭐였지?", "민지야,"), then at most one
# particle: "윤하나가" stays "윤하나", "주머니에서" "주머니", and "강아지" in the middle of a question keeps its "지". A
# one-syllable particle comes off only where it fits the syllable before it ("스파이" has no 받침, so no "이" to drop).
_QUESTION_ENDINGS_V21 = tuple(sorted({
    "이었더라", "였더라", "이었지", "였었지", "였지", "었지", "았지", "했지", "더라", "던가", "었나", "았나", "했나",
    "이었어", "였어", "었어", "았어", "했어", "이에요", "예요", "에요", "이야", "이지", "인가", "인지", "일까",
    "니", "냐", "나", "까", "야", "지", "요",
}, key=len, reverse=True))
_PLURAL_STACKS = ("들에게서", "들한테서", "들에서는", "들에게는", "들에게", "들한테", "들에서", "들이랑",
                  "들처럼", "들까지", "들부터", "들보다", "들마다", "들은", "들이", "들을", "들의", "들에", "들도",
                  "들만", "들로", "들과", "들랑", "들")
_PARTICLES_V21 = tuple(sorted({
    "에게서", "한테서", "에서는", "에게는", "한테는", "으로는", "로는", "에서도", "에게", "한테", "에서", "으로",
    "이랑", "하고", "처럼", "까지", "부터", "보다", "마다", "밖에", "이나", "이며",
    "은", "는", "이", "가", "을", "를", "의", "에", "도", "만", "로", "와", "과", "랑", *_PLURAL_STACKS,
}, key=len, reverse=True))
# Particles that follow a noun and never a verb: the stem they leave is a noun, whatever it ends with ("서고에서").
_NOUN_PARTICLES_V21 = frozenset({
    "에게서", "한테서", "에서는", "에게는", "한테는", "으로는", "로는", "에서도", "에게", "한테", "에서", "으로", "이랑",
    "처럼", "까지", "부터", "보다", "마다", "를", "의", "와", "과", "랑", "로", *_PLURAL_STACKS,
})
# Which syllable a particle or ending may follow: True after a final consonant (받침), False after none; "로" also after ㄹ.
_AFTER_FINAL = {"이": True, "은": True, "을": True, "과": True, "으로": True, "으로는": True, "이랑": True, "이나": True,
                "이며": True, "이야": True, "이지": True, "이에요": True, "이었어": True, "이었지": True, "이었더라": True,
                "가": False, "는": False, "를": False, "와": False, "랑": False, "야": False, "예요": False,
                "로": False, "로는": False}
# Verb endings `packet-v21` adds: literary past tenses, connectives and adverbials ("들어섰다", "돌아왔다", "떨리며",
# "조용히", "자연스럽게") say what happened and give their place to a name or a noun.
_VERBISH_V21 = _VERBISH + ("였다", "갔다", "왔다", "봤다", "됐다", "졌다", "냈다", "쳤다", "렸다", "섰다", "났다", "셨다",
                           "웠다", "겼다", "꼈다", "으며", "며", "면서", "하게", "롭게", "스럽게", "히", "거나", "지만", "으나")
# Pronouns a story's narration is full of; they name nobody in particular.
STOP_WORDS_V21 = STOP_WORDS | frozenset({"그는", "그가", "그를", "그의", "그도", "그와", "그녀", "그들", "저는", "자기"})
_PAST = 20  # the 받침 ㅆ: a past tense ("갔지", "찾았", "무거웠다"), almost never the end of a noun


def verbish_v21(stem: str) -> bool:
    """Whether a `packet-v21` stem reads like a verb or an adjective: a `_VERBISH_V21` ending, or a past tense's ㅆ in
    its last two syllables."""
    return stem.endswith(_VERBISH_V21) or any(_final_consonant(c) == _PAST for c in stem[-2:])


# A token with a digit and a letter names something ("302호", "12월", "500골드", "B2"); so does a number of three digits
# or more. One or two bare digits do not.
_ALNUM_V21 = re.compile(r"(?=.*\d)(?=.*[a-z가-힣])[0-9a-z가-힣]+|\d{3,}")
_CLAUSE_END = re.compile(r"\s*(?:$|[?？!！.,…~])")


def _final_consonant(syllable: str) -> int | None:
    """The 받침 index of a Hangul syllable (0: none), None for anything else."""
    code = ord(syllable) - 0xAC00
    return code % 28 if 0 <= code < 11172 else None


def _fits(stem: str, suffix: str) -> bool:
    """Whether a particle or ending may follow the stem's last syllable."""
    need = _AFTER_FINAL.get(suffix)
    final = _final_consonant(stem[-1]) if stem else None
    if need is None or final is None:
        return True
    if suffix in ("로", "로는"):
        return final in (0, 8)  # none, or ㄹ
    return bool(final) == need


def _strip(word: str, suffixes: tuple[str, ...], least: int = MIN_HANGUL) -> str | None:
    """The longest suffix the word ends with that leaves a stem of `least` syllables and fits it, else None."""
    return next((s for s in suffixes if word.endswith(s) and len(word) - len(s) >= least and _fits(word[:-len(s)], s)),
                None)


def stems_v21(word: str, *, final: bool = True) -> tuple[str, list[str], bool]:
    """`packet-v21`'s stem: at most one question ending (only where the clause ends, `final`), then at most one particle.
    Returns the stem, the longer forms kept as a fallback (a one-syllable suffix may end a name), and whether a
    noun-only particle came off (the stem is then a noun, whatever it ends with)."""
    fallback: list[str] = []
    current = word
    if final and (ending := _strip(current, _QUESTION_ENDINGS_V21)):
        if len(ending) == 1:
            fallback.insert(0, current)
        current = current[:-len(ending)]
    noun = False
    if particle := _strip(current, _PARTICLES_V21):
        if len(particle) == 1:
            fallback.insert(0, current)
        current = current[:-len(particle)]
        noun = particle in _NOUN_PARTICLES_V21
    return current, fallback, noun


def _alnum_v21(word: str) -> str | None:
    """A token with a digit, its particle off ("302호에서" → "302호"), when it names something; else None."""
    if not _ALNUM_V21.fullmatch(word):
        return None
    if _HANGUL.match(word[-1]) and (particle := _strip(word, _PARTICLES_V21, least=2)):
        rest = word[:-len(particle)]
        if _ALNUM_V21.fullmatch(rest):
            return rest
    return word


def keywords_v21(query: str) -> list[str]:
    """`packet-v21`'s keywords: `keywords` with `stems_v21`, `verbish_v21`, `STOP_WORDS_V21` and the tokens with digits
    kept."""
    primary: list[str] = []
    fallback: list[str] = []
    for m in _WORD.finditer(query):
        word = m.group(0).lower()
        if _HANGUL.match(word):
            if word.startswith(_QUESTION_STARTS):
                continue
            stem, longer, noun = stems_v21(word, final=bool(_CLAUSE_END.match(query, m.end())))
            if len(stem) >= MIN_HANGUL and stem not in STOP_WORDS_V21:
                (fallback if not noun and verbish_v21(stem) else primary).append(stem)
                fallback.extend(longer)
        elif word.isascii() and word.isalpha() and len(word) >= MIN_LATIN and word not in STOP_WORDS_V21:
            primary.append(word)
        elif (named := _alnum_v21(word)) is not None:
            primary.append(named)
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
# A word of n syllables shares n of its n + 1 trigrams with the same word plus a particle, so a word of four or more
# syllables reaches the 0.8 fuzzy threshold there and its legacy lookup already finds every exact particle hit
# (PHASE-41 amendment 2, measured on the live copy and the gate databases); only two or three syllables need one.
PARTICLE_MAX = 3
_SOURCE_PARTICLES = (
    "에게서", "한테서", "에서는", "에게는", "한테는", "으로는", "로는", "에서도",
    "에게", "한테", "에서", "으로", "이랑", "하고", "처럼", "까지", "부터", "보다", "마다", "밖에", "이나", "이며",
    "은", "는", "이", "가", "을", "를", "의", "에", "도", "만", "로", "와", "과", "랑",
)
# `packet-v21`: the plural and its stacks first ("들에게서" before "들"), then the particles above.
_SOURCE_PARTICLES_V21 = _PLURAL_STACKS + _SOURCE_PARTICLES


# PostgreSQL's locale-dependent word boundaries exclude CJK letters on macOS,
# unlike its patched pg_trgm. Supplement POSIX alnum/underscore with Unicode 15
# assigned letters, letter numbers and decimal digits in these East Asian blocks:
# Han (including supplementary extensions), Hangul/Jamo, kana, Bopomofo, Yi,
# Tangut, Khitan, Nushu, and compatibility/halfwidth/fullwidth forms. These are
# assigned-character ranges, not whole blocks: punctuation/emoji remain boundaries.
# Other scripts retain the database locale's existing alnum classification.
_CJK_WORD_RANGES = (
    "\u1100-\u11ff\u3005-\u3007\u3021-\u3029\u3031-\u3035\u3038-\u303c"
    "\u3041-\u3096\u309d-\u309f\u30a1-\u30fa\u30fc-\u30ff\u3105-\u312f"
    "\u3131-\u318e\u31a0-\u31bf\u31f0-\u31ff\u3400-\u4dbf\u4e00-\ua48c"
    "\ua960-\ua97c\uac00-\ud7a3\ud7b0-\ud7c6\ud7cb-\ud7fb\uf900-\ufa6d"
    "\ufa70-\ufad9\uff10-\uff19\uff21-\uff3a\uff41-\uff5a\uff66-\uffbe"
    "\uffc2-\uffc7\uffca-\uffcf\uffd2-\uffd7\uffda-\uffdc\U00016fe0-\U00016fe1"
    "\U00016fe3\U00017000-\U000187f7\U00018800-\U00018cd5\U00018d00-\U00018d08\U0001aff0-\U0001aff3"
    "\U0001aff5-\U0001affb\U0001affd-\U0001affe\U0001b000-\U0001b122\U0001b132\U0001b150-\U0001b152"
    "\U0001b155\U0001b164-\U0001b167\U0001b170-\U0001b2fb\U00020000-\U0002a6df\U0002a700-\U0002b739"
    "\U0002b740-\U0002b81d\U0002b820-\U0002cea1\U0002ceb0-\U0002ebe0\U0002f800-\U0002fa1d\U00030000-\U0003134a"
    "\U00031350-\U000323af"
)
_NON_WORD = "[^[:alnum:]_" + _CJK_WORD_RANGES + "]"


def particle_lookup(word: str, *, v21: bool = False) -> tuple[list[str], str] | None:
    """Cheap index guards and the exact PostgreSQL word/particle boundary check.

    The coarse trigram branch also covers every other word boundary. These two
    LIKE guards avoid repeatedly scoring long messages at common start/space
    occurrences; neither their prefix matches nor the coarse score admits a row.
    `v21` also accepts the plural "들" and its particle stacks ("열쇠들을").
    """
    if not MIN_HANGUL <= len(word) <= PARTICLE_MAX or not _HANGUL.fullmatch(word):
        return None
    particles = _SOURCE_PARTICLES_V21 if v21 else _SOURCE_PARTICLES
    return ([word + "%", "% " + word + "%"],
            "(^|" + _NON_WORD + ")" + word + "(" + "|".join(particles) + ")($|" + _NON_WORD + ")")
