"""The forensic path's quote route (PHASE-33 Q1–Q3, ADR 0067): a question about what someone said gets the words said,
verbatim, from the turn that said them.

No model call and no new search: the messages are the ones recall already found (whole-message trigram, keywords,
vectors), plus the turns a turn number names. Within them every quoted span is a candidate, scored by the question's
words in the quote and the narration around it, the message's rank, and the question's time anchor. The speaker is
named only when the narration around the quote names one character, or the message is the user's own; otherwise the
line carries none rather than a guess (Q2).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from .entities import norm
from .facts import FIRST_CUE, HISTORY_CUE
from .keywords import _HANGUL, _QUESTION_STARTS, _VERBISH, _WORD, _stems, MIN_HANGUL, MIN_LATIN, STOP_WORDS

# A question about what was said (Q1). The words are recorded here and reported per case by the measurement.
SPEECH_CUE = re.compile(
    r"말했|말한|말하던|말하더|라고\s?했|라고\s?한|라고\s?하|뭐라고|뭐라\s?했|했던\s?말|한\s?말|대사|한마디|"
    r"물었|물어봤|대답했|대답한|중얼거|외쳤|소리쳤|호통|속삭였|"
    r"\bsaid\b|\bsay\b|\bsays\b|\btold\b|\basked\b|\banswered\b|\bwords\b", re.IGNORECASE)
# A phrase the question quotes asks for the line that holds it.
QUERY_QUOTE = re.compile(r"[\"“'‘「『](.{2,80}?)[\"”'’」』]")
# A turn the question names (Q3): N턴, "turn N".
TURN_ANCHOR = re.compile(r"(\d{1,5})\s*턴|\bturn\s+(\d{1,5})\b", re.IGNORECASE)
# How it started, for quotes: FIRST_CUE and the first day or night (Q1, Q3).
FIRST_QUOTE = re.compile(FIRST_CUE.pattern + r"|첫\s?날|\bthe first (?:night|day|time)\b", re.IGNORECASE)

QUOTE = re.compile(r"[\"“「『]([^\"“”「」『』\n]{4,300})[\"”」』]")
_SENTENCE_END = re.compile(r"(?<=[.!?…。])\s+|\n+")
QUOTES_MAX = 2  # quote lines per packet (Q2)
QUOTE_CHARS = 600  # one quote line, with its narration (Q2)
TURN_SPAN = 2  # a named turn reads turns N−2…N+2 (Q3)
CANDIDATES = 12  # the found messages a quote is looked for in, best ranked first
SEARCHED = 30  # messages with quotes the route's own search adds, most of the question's words first
TIMEOUT_MS = 150  # the route's own search (Q4): abstains past it
_SUBJECT = "(?:이|가|은|는|께서|도)"
_SUBJECT_WORD = re.compile(r"([가-힣]+?)(?:께서|이|가|은|는)")
_HANGUL_WORD = re.compile(r"[가-힣]+")
_QUOTATIVE = re.compile(r"(?:하고|하며|하면서|라고|라며|이라고|하는|하자|했다|한다)(?![가-힣])")
# a verb of speaking after the quote: the subject before it said the words
_SPEAKING = re.compile(r"말했|말하|물었|묻|대답|답했|되물|외쳤|소리쳤|중얼|속삭|덧붙|호통|불렀|투덜|웅얼|내뱉|입을 열|"
                       r"말을 이|쏘아붙|받아쳤|타일렀|설명했|재촉했|혼잣말")
# words a question uses to ask about speech; they say nothing about which line
_SPEECH_WORDS = ("말했", "말한", "말하", "뭐라", "대답", "물었", "물어", "중얼", "외쳤", "소리쳤", "호통", "속삭", "대사", "한마디",
                 "했어", "했지", "했더", "했던", "said", "say", "says", "told", "asked", "answered", "words")
_ABOUT = ("대해", "대한", "관해", "관한")  # "…에 대해": what the question is about follows; the word itself says nothing
VERB_WEIGHT = 0.5  # a word that ends like a verb ("보고", "놀리면서") says what happened around the line, weakly


@dataclass(frozen=True)
class Quote:
    position: int
    turn: int | None
    revision_id: str
    speaker: str | None
    text: str  # the quote with the narration sentence around it
    words: str  # the quoted words alone
    score: float


# A question about what someone is called ("뭐라고 불러?") asks for the form of address now, which the facts hold; quotes
# would bring back every older form (the v0.3.0 bench replay, S1 turn 120). With a history cue ("처음에 뭐라고 불렀더라?")
# the older forms are what it asks for. The same words as `retrieval.CALLED`.
ADDRESS_CUE = re.compile(r"부르|불러|부름|호칭|\bcalls?\b|\bcalled\b", re.IGNORECASE)


def asks_for_words(query: str) -> bool:
    if ADDRESS_CUE.search(query) and not HISTORY_CUE.search(query):
        return False
    return bool(SPEECH_CUE.search(query) or QUERY_QUOTE.search(query))


def named_turn(query: str) -> int | None:
    m = TURN_ANCHOR.search(query)
    if not m:
        return None
    return int(m.group(1) or m.group(2))


def query_terms(query: str) -> dict[str, float]:
    """Every word of the question that can point at a line, with its weight: Korean stems (particles off) and Latin
    words; no question words, no stop words, no words about speaking; a verb-like word weighs VERB_WEIGHT."""
    out: dict[str, float] = {}
    for raw in _WORD.findall(query):
        word = raw.lower()
        if any(word.startswith(s) for s in _SPEECH_WORDS) or FIRST_QUOTE.fullmatch(word):
            continue
        if _HANGUL.match(word):
            if (word.startswith(_QUESTION_STARTS) or word.endswith("턴") or word.startswith(("처음", "첫"))
                    or word.startswith(_ABOUT)):
                continue
            stem, longer = _stems(word)
            if len(stem) >= MIN_HANGUL and stem not in STOP_WORDS:
                out.setdefault(stem, VERB_WEIGHT if word.endswith(_VERBISH + ("면서",)) else 1.0)
        elif word.isascii() and word.isalpha() and len(word) >= MIN_LATIN and word not in STOP_WORDS:
            out.setdefault(word, 1.0)
    return out


def query_words(query: str) -> list[str]:
    return list(query_terms(query))


def named(query: str, names: dict[str, str]) -> tuple[set[str], set[str]]:
    """The characters the question names: whose words it asks for (those it names as a subject, "이안이 … 도윤한테";
    every one named when none is a subject), and the others (to whom, about whom: words like any other)."""
    flat = norm(query)
    found = {display for key, display in names.items() if key and key in flat}
    subject = {display for key, display in names.items()
               if key and re.search(re.escape(key) + _SUBJECT + r"(?![가-힣])", flat)}
    return (subject, found - subject) if subject else (found, set())


def _sentences(text: str) -> list[tuple[int, int]]:
    """Sentence spans of a message, quotes kept whole (a quote's own full stops do not end its sentence)."""
    guarded = QUOTE.sub(lambda m: m.group(0).replace(".", "\x00").replace("!", "\x01").replace("?", "\x02")
                        .replace("…", "\x03"), text)
    spans, start = [], 0
    for m in _SENTENCE_END.finditer(guarded):
        if m.start() > start:
            spans.append((start, m.start()))
        start = m.end()
    if start < len(text):
        spans.append((start, len(text)))
    return spans


@dataclass(frozen=True)
class Spoken:
    words: str  # the quoted words
    line: str  # what is placed: the quote's sentence and the sentences around it, up to QUOTE_CHARS, verbatim
    near: str  # its own sentence and the next, without quoted words (weight 1)
    wide: str  # two sentences either side, without quoted words (weight 0.5)
    before: str  # its sentence's narration before the quote, from the sentence start or the quote before it
    after: str  # its sentence's narration after the quote, to the sentence end or the quote after it
    first: int  # the first and last sentence index the line covers
    last: int
    at: int  # the quote's own sentence


def quotes_in(text: str) -> list[Spoken]:
    """Every quote of a message with the text around it. The line grows from the quote's sentence outward, the next
    sentence first (where the speaker is usually named), alternating, while it fits QUOTE_CHARS: the reader gets the
    exchange the words were said in, verbatim."""
    spans = _sentences(text)
    out = []
    for m in QUOTE.finditer(text):
        i = next((n for n, (a, b) in enumerate(spans) if a <= m.start() < b), None)
        if i is None:
            continue
        lo = hi = i
        if spans[i][1] - spans[i][0] > QUOTE_CHARS:  # one long sentence: the quote and what is next to it
            a = max(spans[i][0], m.start() - (QUOTE_CHARS - (m.end() - m.start())) // 2)
            line = text[a:a + QUOTE_CHARS].strip()
        else:
            grow = True
            while grow:
                grow = False
                if hi + 1 < len(spans) and spans[hi + 1][1] - spans[lo][0] <= QUOTE_CHARS:
                    hi, grow = hi + 1, True
                if lo > 0 and spans[hi][1] - spans[lo - 1][0] <= QUOTE_CHARS:
                    lo, grow = lo - 1, True
            line = text[spans[lo][0]:spans[hi][1]].strip()
        near = text[spans[i][0]:spans[min(i + 1, len(spans) - 1)][1]]
        wide = text[spans[max(i - 2, 0)][0]:spans[min(i + 2, len(spans) - 1)][1]]
        before = re.split(QUOTE, text[spans[i][0]:m.start()])[-1]
        after = QUOTE.split(text[m.end():spans[i][1]], maxsplit=1)[0]
        out.append(Spoken(m.group(1), line, QUOTE.sub(" ", near), QUOTE.sub(" ", wide), before, after, lo, hi, i))
    return out


def _subject(word: str, names: dict[str, str]) -> str | None:
    """The character a subject-marked word names ("이안이", "곽은비가"), else None."""
    m = _SUBJECT_WORD.fullmatch(word)
    return names.get(norm(m.group(1))) if m else None


def _speaker(spoken: Spoken, names: dict[str, str], role: str | None, message_speaker: str | None) -> str | None:
    """Who said it (Q2), only where the quote's own sentence says so: the user's own message is the persona's;
    `X가 "…" 하고/라고 …` is X's, the subject nearest before the quote; `"…" X가 … 말했다` is X's, the first subject
    after it, with a verb of speaking in the clause. The nearest subject decides: one that is no known character
    (주인 할머니가, 수염 선원이) leaves the line unattributed rather than guessed. The sentences around are not read:
    the next is most often the listener's (추오월이 말없이 그를 보았다), so they named the wrong speaker."""
    if role == "user" and message_speaker:
        return message_speaker
    after = spoken.after.strip()
    if _QUOTATIVE.match(after):
        words = [w for w in _HANGUL_WORD.findall(spoken.before) if _SUBJECT_WORD.fullmatch(w)]
        return _subject(words[-1], names) if words else None
    clause = re.split(r"[,.!?…]|(?<=[가-힣])자\s|(?<=[가-힣])고\s", after, maxsplit=1)[0]
    words = [w for w in _HANGUL_WORD.findall(clause) if _SUBJECT_WORD.fullmatch(w)]
    if words and _SPEAKING.search(after):
        return _subject(words[0], names)
    return None


def pick(candidates: list[dict[str, Any]], query: str, names: dict[str, str], last_position: int | None,
         first: bool, rarity: dict[str, float] | None = None, met: int | None = None) -> list[Quote]:
    """The best quotes for the question among the messages recall found. `candidates` are message rows in recall's
    order (`clean`, `position`, `turn`, `id`, `role`, `name`); `names` maps a normalized character name to how the
    packet shows it; `rarity` weighs a word by how few of the chat's messages hold it (1 when unknown); `met` is the
    turn by which every character the question names had appeared, for a first cue."""
    terms = query_terms(query)
    wanted = [m.group(1) for m in QUERY_QUOTE.finditer(query)]
    turn = named_turn(query)
    first = first and turn is None  # a named turn says where; "첫째 장" is no first cue then
    asked, _ = named(query, names)  # whose words are asked for
    asked_keys = {norm(d) for d in asked} | {key for key, d in names.items() if d in asked}
    weights = {w: v * (rarity or {}).get(w, 1.0) for w, v in terms.items()
               if not any(w in k or k in w for k in asked_keys)}  # the speaker is scored as a speaker, below
    if weights and (top := max(weights.values())) > 0:  # the question's rarest word weighs 1
        weights = {w: v / top for w, v in weights.items()}
    scored: list[Quote] = []
    spans_of: dict[int, tuple[int, int, int]] = {}
    for rank, c in enumerate(candidates):
        for sp in quotes_in(c["clean"] or ""):
            in_quote, near, line = norm(sp.words), norm(sp.near), norm(sp.line)
            # a word in the quote counts twice, in its sentence or the next 1.5, anywhere in the line placed once
            hits = sum(v * (2 if w in in_quote else 1.5 if w in near else 1 if w in line else 0)
                       for w, v in weights.items())
            phrase = any(norm(p) in in_quote for p in wanted)
            speaker = _speaker(sp, names, c.get("role"), c.get("name"))
            if not hits and not phrase and not (turn is not None and c.get("turn") == turn):
                continue
            score = hits + (5 if phrase else 0) + 0.5 / (1 + rank)
            if asked:  # the words of the one asked about: said by them, or by nobody named with them in the narration
                if speaker:
                    score += 1.5 if speaker in asked else -1
                elif any(k in near for k in asked_keys):
                    score += 1.5
            if turn is not None and c.get("turn") is not None:
                score += 4 if c["turn"] == turn else 1 if abs(c["turn"] - turn) <= TURN_SPAN else -2
            if first and met is not None and c.get("turn") is not None:  # where they met (Q3)
                score += 3 if met <= c["turn"] <= met + TURN_SPAN else 0 if c["turn"] > met else -2
            elif first and last_position:  # earlier lines first: the earliest third of the chat leads (Q3)
                score += 1.5 * (1 - c["position"] / last_position) + (1 if c["position"] <= last_position / 3 else 0)
            q = Quote(position=c["position"], turn=c.get("turn"), revision_id=str(c["id"]), speaker=speaker,
                      text=sp.line, words=sp.words, score=round(score, 4))
            scored.append(q)
            spans_of[id(q)] = (sp.first, sp.last, sp.at)
    scored.sort(key=lambda q: (-q.score, q.position))
    out: list[Quote] = []
    for q in scored:
        a, b, at = spans_of[id(q)]
        if any(q.revision_id == o.revision_id and a <= spans_of[id(o)][1] and spans_of[id(o)][0] <= b for o in out):
            continue  # a line already placed shows this quote, or this line would show that one
        out.append(q)
        if len(out) == QUOTES_MAX:
            break
    return out


def character_names(entities: Iterable[dict[str, Any]]) -> dict[str, str]:
    """Normalized name → display name, for every character and each of its names of two characters or more."""
    out: dict[str, str] = {}
    for e in entities:
        if e.get("type") != "character":
            continue
        for n in [e.get("name"), *(e.get("names") or [])]:
            if n and len(norm(n)) >= 2:
                out.setdefault(norm(n), e.get("name") or n)
    return out
