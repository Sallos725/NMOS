"""A name as the story says it (PHASE-24, ADR 0058). Pure.

Korean calls a character written in full as a three-syllable name (백이안) by the given name alone (이안), and a story
written in English stores a Korean character under a romanized name (Hajin) that the user writes in Hangul (하진).
`aliases` gives, for one request, the other names a character goes by: its given name, and a Hangul word of the
message that spells its Latin name on a fixed key. They count wherever the message is matched against a character's
names (fact selection, threads, the scene's cast); nothing is stored, and entity resolution is unchanged (ADR 0012).
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any

from .entities import TITLES, norm

# One-syllable family names whose three-syllable full names Korean shortens to the given name (Q1).
FAMILY = frozenset("김이박최정강조윤장임한오서신권황안송류전홍고문양손배백허유남심노하곽성차주우구민진나지엄채원천방공현함변염여추"
                   "도소석선설")
# Two-syllable family names whose four-syllable full names Korean shortens to the given name (남궁세연 → 세연). Equal to
# `extraction.FAMILY_TWO` (pinned by a test; `extraction` imports this module, so it is not imported here).
FAMILY_TWO = frozenset({"남궁", "제갈", "선우", "독고", "황보", "사공", "서문", "동방", "망절", "어금"})
# The usual spellings of family names that are not their Revised Romanization alone (Q2).
SPELLINGS = {
    "이": ("lee", "yi", "rhee", "i"), "박": ("park", "bak"), "김": ("kim", "gim"), "최": ("choi", "choe"),
    "정": ("jung", "jeong", "chung"), "강": ("kang", "gang"), "조": ("cho", "jo"), "윤": ("yoon", "yun"),
    "장": ("jang", "chang"), "임": ("lim", "im"), "오": ("oh", "o"), "서": ("seo", "suh"), "신": ("shin", "sin"),
    "권": ("kwon", "gwon"), "안": ("ahn", "an"), "류": ("ryu", "yoo", "yu"), "유": ("yoo", "yu"),
    "전": ("jeon", "jun", "chun"), "고": ("ko", "go"), "문": ("moon", "mun"), "손": ("son", "sohn"),
    "백": ("baek", "paik"), "허": ("heo", "huh"), "심": ("shim", "sim"), "노": ("noh", "no", "roh"),
    "곽": ("kwak", "gwak"), "성": ("sung", "seong"), "주": ("joo", "ju"), "우": ("woo", "u"),
    "구": ("koo", "gu", "ku"), "나": ("na", "ra"), "엄": ("eom", "um"), "천": ("cheon", "chun"),
    "현": ("hyun", "hyeon"),
}
# Spelling variants folded together, in this order (Q2).
FOLDS = (("oo", "u"), ("ou", "u"), ("eo", "u"), ("wu", "u"), ("ee", "i"), ("ui", "i"), ("yi", "i"), ("wo", "u"),
         ("ae", "e"), ("ai", "e"), ("sh", "s"), ("ch", "j"), ("k", "g"), ("p", "b"), ("t", "d"), ("l", "r"),
         ("rr", "r"), ("eu", "u"))
KEY_MIN = 4  # a shorter key matches too much
# Revised Romanization, syllable by syllable (no sound change across syllables: names are spelled so).
_INITIAL = ("g", "kk", "n", "d", "tt", "r", "m", "b", "pp", "s", "ss", "", "j", "jj", "ch", "k", "t", "p", "h")
_MEDIAL = ("a", "ae", "ya", "yae", "eo", "e", "yeo", "ye", "o", "wa", "wae", "oe", "yo", "u", "wo", "we", "wi", "yu",
           "eu", "ui", "i")
_FINAL = ("", "k", "k", "k", "n", "n", "n", "t", "l", "k", "m", "l", "l", "l", "p", "l", "m", "p", "p", "t", "t", "ng",
          "t", "t", "k", "t", "p", "t")
HANGUL = re.compile(r"[가-힣]+")
_LATIN_NAME = re.compile(r"[a-z][a-z' -]*")


def given(name: str) -> str | None:
    """The given name of a normalized Hangul full name: three syllables with a common one-syllable family name
    (백이안 → 이안), four with a two-syllable one (남궁세연 → 세연), and either written with a space after the family
    name (백 이안 → 이안)."""
    family, _, rest = name.partition(" ")
    if rest:  # spaced: the family name, then a two-syllable given name
        if ((family in FAMILY or family in FAMILY_TWO) and len(rest) == 2 and HANGUL.fullmatch(rest)):
            return rest
        return None
    if not HANGUL.fullmatch(name):
        return None
    if len(name) == 3 and name[0] in FAMILY:
        return name[1:]
    if len(name) == 4 and name[:2] in FAMILY_TWO:
        return name[2:]
    return None


def romanized(word: str) -> str:
    """A Hangul word in Revised Romanization, syllable by syllable."""
    out = []
    for ch in word:
        o = ord(ch) - 0xAC00
        out.append(_INITIAL[o // 588] + _MEDIAL[(o % 588) // 28] + _FINAL[o % 28])
    return "".join(out)


def key(latin: str) -> str:
    """The spelling key: letters only, lower case, the usual variants folded together."""
    s = re.sub(r"[^a-z]", "", latin.lower())
    for a, b in FOLDS:
        s = s.replace(a, b)
    return s


def hangul_keys(word: str) -> frozenset[str]:
    """Every key a Hangul word of two to six syllables may be spelled as: as romanized, and with its family name's
    usual spellings when it has three or four syllables."""
    if not 2 <= len(word) <= 6 or not HANGUL.fullmatch(word):
        return frozenset()
    out = {key(romanized(word))}
    if 3 <= len(word) <= 4 and word[0] in SPELLINGS:
        rest = romanized(word[1:])
        out |= {key(s + rest) for s in SPELLINGS[word[0]]}
    return frozenset(out)


def latin_keys(name: str) -> frozenset[str]:
    """The keys of a normalized Latin name: the whole name, its first part that is not a title when it has two or more
    (a Western first name: Elena Vance → Elena, Sir Arthur Pendragon → Arthur), and its last part when it has two (a
    romanized Korean given name: Ryu Ha-jin → Ha-jin)."""
    if not _LATIN_NAME.fullmatch(name):
        return frozenset()
    parts = name.split()
    out = {key(name)} | ({key(parts[1])} if len(parts) == 2 else set())
    if len(parts) >= 2:
        first = next((p for p in parts[:-1] if p.rstrip(".") not in TITLES), None)
        if first:
            out.add(key(first))
    return frozenset(k for k in out if len(k) >= KEY_MIN)


LOOSE_MIN = 5  # a shorter loose key matches too much


def loose(k: str) -> str:
    """A spelling key with every run of vowels as one mark: the vowels English names leave to the ear (Daniel, 대니얼,
    다니엘 → `dvnvr`). Only for the persona's own names (`entities._persona_matcher`), never between two characters."""
    return re.sub(r"[aeiouwy]+", "v", k)


def aliases(entities: Iterable[Mapping[str, Any]], persona_names: Iterable[str], text: str,
            marked: Iterable[str] = ()) -> dict[str, frozenset[str]]:
    """{normalized name of a character: the other normalized names it goes by in this request} (Q1, Q2).

    `entities` are the resolution's (ADR 0012), `persona_names` every name the persona goes by, `text` the user's
    message and the previous reply, `marked` the names in knowledge marks (someone a secret is kept from may be named
    only there, ADR 0034): each one no entity goes by is a character of its own. A given name or a Hangul word counts
    for one character only, whichever rule gives it: not when it is another entity's name, when two characters would
    share it (a given name and a spelling included), or when it is the persona's given name. The persona gains none (its names are never a mention, ADR 0023)."""
    persona = {norm(n) for n in persona_names}
    entities = list(entities)
    held = {norm(n) for e in entities for n in e["names"]}
    for n in dict.fromkeys(norm(x) for x in marked if x):
        if n not in held and n not in persona:
            entities.append({"id": f"mark:{n}", "type": "character", "names": [n]})
            held.add(n)
    taken = persona | {g for n in persona if (g := given(n))} | held
    characters = [e for e in entities if e["type"] == "character" and not e.get("persona")]
    owners: dict[str, set[str]] = defaultdict(set)  # a variant → every character either rule gives it to
    for e in characters:
        for n in e["names"]:
            if g := given(norm(n)):
                owners[g].add(e["id"])
    spelled: dict[str, set[str]] = defaultdict(set)
    for e in characters:
        for n in e["names"]:
            for k in latin_keys(norm(n)):
                spelled[k].add(e["id"])
    if spelled:
        for run in HANGUL.findall(text):
            for size in (6, 5, 4, 3, 2):  # a particle may follow the name: the longest prefix that spells one decides
                word = run[:size]
                if len(word) < size:
                    continue
                ids = set().union(*(spelled.get(k, set()) for k in hangul_keys(word)))
                if ids:
                    owners[word] |= ids  # two characters for one word: neither, below
                    break
    extra: dict[str, set[str]] = defaultdict(set)
    for word, ids in owners.items():
        if len(ids) == 1 and word not in taken:
            extra[next(iter(ids))].add(word)
    return {norm(n): frozenset(extra[e["id"]]) for e in characters if extra.get(e["id"]) for n in e["names"]}


def widened(names: Iterable[str], extra: Mapping[str, frozenset[str]] | None) -> set[str]:
    """Normalized names and the other names they go by in this request."""
    out = {norm(n) for n in names if n}
    if extra:
        out |= {v for n in list(out) for v in extra.get(n, ())}
    return out
