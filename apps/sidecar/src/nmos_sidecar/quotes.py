"""The forensic path's quote route (PHASE-33 Q1–Q3, ADR 0067): a question about what someone said gets the words said,
verbatim, from the turn that said them.

No model call and no new search: the messages are the ones recall already found (whole-message trigram, keywords,
vectors), plus the turns a turn number names. Within them every quoted span is a candidate, scored by the question's
words in the quote and the narration around it, the message's rank, and the question's time anchor. The speaker is
named only when the narration around the quote names one character, or the message is the user's own; otherwise the
line carries none rather than a guess (Q2).

`v21=True` (one switch, threaded through `asks_for_words`, `pick`, `quotes_in`, `query_terms` and `_speaker`) is
`packet-v21`'s reading: a quote or a verb of speaking in the message asks for words only beside a question or a recall
cue outside the quoted words; single-quoted and two-character lines are quotes; English and the sentence before a
quote that stands alone can name the speaker. The defaults are `packet-v20`'s, unchanged (ADR 0027: traces replay).
"""

from __future__ import annotations

import re
import dataclasses
from dataclasses import dataclass
from typing import Any, Iterable

from .entities import norm
from .facts import FIRST_CUE, HISTORY_CUE
from .keywords import (_CLAUSE_END, _HANGUL, _QUESTION_STARTS, _VERBISH, _WORD, _stems, MIN_HANGUL, MIN_LATIN, STOP_WORDS,
                       STOP_WORDS_V21, stems_v21, verbish_v21)

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
# packet-v21: two characters are a line ("죽어", "아니."), and so are single-quoted words ('가지 마.', ‘…’), but not
# the apostrophes of English contractions and possessives ("don't think he's"): no letter or digit before the opening
# mark, none after the closing one.
QUOTE_V21 = re.compile(r"[\"“「『]([^\"“”「」『』\n]{2,300})[\"”」』]"
                       r"|(?<![0-9A-Za-z])['‘]([^'‘’\"“”\n]{2,300}?)['’](?![0-9A-Za-z])")
# The question-side quote of packet-v21, with the same guard against contractions.
QUERY_QUOTE_V21 = re.compile(r"[\"“「『](.{2,80}?)[\"”」』]"
                             r"|(?<![A-Za-z])['‘](?!s\b|t\b|re\b|ve\b|ll\b|d\b|m\b)(.{2,80}?)['’](?![A-Za-z])")
# Any quoted span of a message, however long, so the cues are read only outside the quoted words (packet-v21).
_QUOTED_SPAN_V21 = re.compile(r"[\"“「『][^\"“”「」『』]{0,2000}[\"”」』]"
                              r"|(?<![0-9A-Za-z])['‘][^'‘’\n]{0,600}['’](?![0-9A-Za-z])")
# A question or a recall cue outside the quoted words: only beside one does a quote or a verb of speaking ask for the
# words said (packet-v21).
RECALL_CUE_V21 = re.compile(
    r"[?？]|기억|언제|누가|누구|뭐였|무슨|찾아|맞지|맞나|그때|처음|더라|던가|했지|었지|았지|였지|했나|했니|했냐|는지|은지|"
    r"\bremember|\brecall|\bwhen did\b|\bwho said\b|\bwhat did\b|\bwhat was\b|\bdid\b.{0,60}\bsay\b",
    re.IGNORECASE)
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
# What the question says the words did: asked ("뭐라고 물었어?") takes a line that is a question; answered ("뭐라고
# 대답했어?") a line right after one that is.
ASKING = re.compile(r"물었|물어|묻[고는던]|질문|\basked\b", re.IGNORECASE)
ANSWERING = re.compile(r"대답|답했|답한|되받|\banswered\b|\breplied\b", re.IGNORECASE)
_QUESTION_END = re.compile(r"(?:\?|(?:냐|니|까|나요|가요|는가|던가|래요)[.!…]*)\s*$")
# packet-v21: English speech attribution ("…," said Elena / Elena whispered, "…" / "…," Elena said).
_SAY_EN = (r"(?:said|says|asked|asks|whispered|whispers|shouted|shouts|yelled|yells|replied|replies|answered|answers|"
           r"muttered|mutters|murmured|murmurs|cried|called|added|adds|snapped|growled|sighed|told|tells|began|"
           r"continued|insisted|demanded|breathed|hissed|exclaimed|admitted|warned|stammered)")
_NAME_EN = r"([A-Z][\w'-]*(?:\s+[A-Z][\w'-]*)?)"
_EN_AFTER_SAY_NAME = re.compile(r"^\s*,?\s*" + _SAY_EN + r"\s+" + _NAME_EN)
_EN_AFTER_NAME_SAY = re.compile(r"^\s*,?\s*" + _NAME_EN + r"\s+(?:\w+ly\s+)?" + _SAY_EN + r"\b")
_EN_BEFORE = re.compile(_NAME_EN + r"\s+(?:\w+ly\s+)?" + _SAY_EN + r"(?:\s+\w+ly)?(?:\s+(?:to|at)\s+\w+)?\s*[,:]?\s*$")
_EN_SENTENCE_SUBJECT = re.compile(r"^\s*" + _NAME_EN + r"\s+[a-z]")
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


def asks_for_words(query: str, *, v21: bool = False) -> bool:
    """Whether the message asks for the words someone said (Q1). `v21`: a verb of speaking or a quoted phrase asks only
    beside a question or a recall cue, both read outside the quoted words (`RECALL_CUE_V21`): narration with dialogue
    (`고개를 끄덕이며 말했다. "알겠어, 내일 광장에서 보자."`, `"어디 가?" 그가 물었다.`) and English contractions
    ("I don't think he's right") ask for nothing."""
    if ADDRESS_CUE.search(query) and not HISTORY_CUE.search(query):
        return False
    if not v21:
        return bool(SPEECH_CUE.search(query) or QUERY_QUOTE.search(query))
    outside = _QUOTED_SPAN_V21.sub(" ", query)
    if not RECALL_CUE_V21.search(outside):
        return False
    return bool(SPEECH_CUE.search(outside) or QUERY_QUOTE_V21.search(query))


def named_turn(query: str) -> int | None:
    m = TURN_ANCHOR.search(query)
    if not m:
        return None
    return int(m.group(1) or m.group(2))


def query_terms(query: str, *, v21: bool = False) -> dict[str, float]:
    """Every word of the question that can point at a line, with its weight: Korean stems (particles off) and Latin
    words; no question words, no stop words, no words about speaking; a verb-like word weighs VERB_WEIGHT. `v21`:
    `keywords.stems_v21`, `verbish_v21` and `STOP_WORDS_V21`."""
    if v21:
        return _query_terms_v21(query)
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


def _query_terms_v21(query: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for m in _WORD.finditer(query):
        word = m.group(0).lower()
        if any(word.startswith(s) for s in _SPEECH_WORDS) or FIRST_QUOTE.fullmatch(word):
            continue
        if _HANGUL.match(word):
            if (word.startswith(_QUESTION_STARTS) or word.endswith("턴") or word.startswith(("처음", "첫"))
                    or word.startswith(_ABOUT)):
                continue
            stem, _, noun = stems_v21(word, final=bool(_CLAUSE_END.match(query, m.end())))
            if len(stem) >= MIN_HANGUL and stem not in STOP_WORDS_V21:
                verb = not noun and (verbish_v21(stem) or verbish_v21(word))
                out.setdefault(stem, VERB_WEIGHT if verb else 1.0)
        elif word.isascii() and word.isalpha() and len(word) >= MIN_LATIN and word not in STOP_WORDS_V21:
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


def _sentences(text: str, quote: re.Pattern[str] = QUOTE) -> list[tuple[int, int]]:
    """Sentence spans of a message, quotes kept whole (a quote's own full stops do not end its sentence)."""
    guarded = quote.sub(lambda m: m.group(0).replace(".", "\x00").replace("!", "\x01").replace("?", "\x02")
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
    near: str  # its own sentence and the ones either side, without quoted words
    wide: str  # two sentences either side, without quoted words (weight 0.5)
    before: str  # its sentence's narration before the quote, from the sentence start or the quote before it
    after: str  # its sentence's narration after the quote, to the sentence end or the quote after it
    first: int  # the first and last sentence index the line covers
    last: int
    at: int  # the quote's own sentence
    after_question: bool = False  # the quote before it in the message is a question
    prev: str = ""  # packet-v21: the sentence before the quote's own, verbatim ("" before the first, and under v20)


def quotes_in(text: str, *, v21: bool = False) -> list[Spoken]:
    """Every quote of a message with the text around it. The line grows from the quote's sentence outward, the next
    sentence first (where the speaker is usually named), alternating, while it fits QUOTE_CHARS: the reader gets the
    exchange the words were said in, verbatim. `v21`: QUOTE_V21's quotes, and each carries the sentence before its own
    (`prev`). The default is also the extraction's finder (`extraction.target_quotes`): unchanged."""
    quote = QUOTE_V21 if v21 else QUOTE
    spans = _sentences(text, quote)
    out = []
    asked = False  # whether the quote before is a question
    for m in quote.finditer(text):
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
        near = text[spans[max(i - 1, 0)][0]:spans[min(i + 1, len(spans) - 1)][1]]
        wide = text[spans[max(i - 2, 0)][0]:spans[min(i + 2, len(spans) - 1)][1]]
        if not v21:
            before = re.split(QUOTE, text[spans[i][0]:m.start()])[-1]
            after = QUOTE.split(text[m.end():spans[i][1]], maxsplit=1)[0]
            out.append(Spoken(m.group(1), line, QUOTE.sub(" ", near), QUOTE.sub(" ", wide), before, after, lo, hi, i,
                              asked))
            asked = is_question(m.group(1))
            continue
        words = _words(m)
        before = _between(quote, text[spans[i][0]:m.start()])[-1]
        after = _between(quote, text[m.end():spans[i][1]])[0]
        prev = text[spans[i - 1][0]:spans[i - 1][1]] if i > 0 else ""
        out.append(Spoken(words, line, quote.sub(" ", near), quote.sub(" ", wide), before, after, lo, hi, i, asked,
                          prev))
        asked = is_question(words)
    return out


def _words(m: re.Match[str]) -> str:
    """The quoted words of a match: the v21 patterns hold them in one of two groups."""
    return next(g for g in m.groups() if g is not None)


def _between(quote: re.Pattern[str], text: str) -> list[str]:
    """The pieces of `text` between its quotes, in order (one piece when it holds none). Not `re.split`: that would
    interleave the v21 patterns' two groups."""
    pieces, start = [], 0
    for m in quote.finditer(text):
        pieces.append(text[start:m.start()])
        start = m.end()
    pieces.append(text[start:])
    return pieces


def is_question(words: str) -> bool:
    return bool(_QUESTION_END.search(words.strip()))


def _subject(word: str, names: dict[str, str]) -> str | None:
    """The character a subject-marked word names ("이안이", "곽은비가"), else None."""
    m = _SUBJECT_WORD.fullmatch(word)
    return names.get(norm(m.group(1))) if m else None


def _speaker(spoken: Spoken, names: dict[str, str], role: str | None, message_speaker: str | None, *,
             v21: bool = False) -> str | None:
    """Who said it (Q2), only where the quote's own sentence says so: the user's own message is the persona's;
    `X가 "…" 하고/라고 …` is X's, the subject nearest before the quote; `"…" X가 … 말했다` is X's, the first subject
    after it, with a verb of speaking in the clause. The nearest subject decides: one that is no known character
    (주인 할머니가, 수염 선원이) leaves the line unattributed rather than guessed. The sentences around are not read:
    the next is most often the listener's (추오월이 말없이 그를 보았다), so they named the wrong speaker."""
    if role == "user" and message_speaker:
        return message_speaker
    if v21:
        return _speaker_v21(spoken, names)
    after = spoken.after.strip()
    if _QUOTATIVE.match(after):
        words = [w for w in _HANGUL_WORD.findall(spoken.before) if _SUBJECT_WORD.fullmatch(w)]
        return _subject(words[-1], names) if words else None
    clause = re.split(r"[,.!?…]|(?<=[가-힣])자\s|(?<=[가-힣])고\s", after, maxsplit=1)[0]
    words = [w for w in _HANGUL_WORD.findall(clause) if _SUBJECT_WORD.fullmatch(w)]
    # the verb in the subject's own clause, and that subject alone: two subjects left in the span (다가오며, 다가오는데 …)
    # cannot say whose verb it is, so the line names nobody (a review, and its follow-up)
    if len(words) == 1 and _SPEAKING.search(clause):
        return _subject(words[0], names)
    return None


def _en_name(name: str, names: dict[str, str]) -> str | None:
    """The known character an English name names ("Elena", "Elena Park"; its first word, then its last, when the whole
    is unknown: "Then Elena said")."""
    parts = name.split()
    return names.get(norm(name)) or names.get(norm(parts[0])) or names.get(norm(parts[-1]))


def _speaker_v21(spoken: Spoken, names: dict[str, str]) -> str | None:
    """packet-v21's attribution, after the user's own message. Korean as v20 reads it, except that the clause after the
    quote may hold other subjects that name no character ("도윤이 목소리가 떨리며 말했다": 도윤) so long as its first
    subject is the one character in it; then English ("…," said Elena / Elena whispered, "…"); then, for a quote alone
    in its sentence, the one character the sentence before names ("이안이 돌아보았다.\n"가지 마.""), unless that
    sentence holds a quote of its own (an exchange: likely the other one's turn)."""
    after = spoken.after.strip()
    if _QUOTATIVE.match(after):
        words = [w for w in _HANGUL_WORD.findall(spoken.before) if _SUBJECT_WORD.fullmatch(w)]
        return _subject(words[-1], names) if words else None
    clause = re.split(r"[,.!?…]|(?<=[가-힣])자\s|(?<=[가-힣])고\s", after, maxsplit=1)[0]
    words = [w for w in _HANGUL_WORD.findall(clause) if _SUBJECT_WORD.fullmatch(w)]
    if words and _SPEAKING.search(clause):
        who = {s for w in words if (s := _subject(w, names))}
        first = _subject(words[0], names)
        return first if first and who == {first} else None
    m = _EN_AFTER_SAY_NAME.match(spoken.after) or _EN_AFTER_NAME_SAY.match(spoken.after) or _EN_BEFORE.search(
        spoken.before)
    if m is not None:
        return _en_name(m.group(1), names)
    if re.search(r"\w", spoken.before) or re.search(r"\w", spoken.after) or not spoken.prev.strip():
        return None
    if QUOTE_V21.search(spoken.prev):
        return None
    who = {s for w in _HANGUL_WORD.findall(spoken.prev) if _SUBJECT_WORD.fullmatch(w) and (s := _subject(w, names))}
    if (m := _EN_SENTENCE_SUBJECT.match(spoken.prev)) and (s := _en_name(m.group(1), names)):
        who.add(s)
    return next(iter(who)) if len(who) == 1 else None


def pick(candidates: list[dict[str, Any]], query: str, names: dict[str, str], last_position: int | None,
         first: bool, rarity: dict[str, float] | None = None, met: int | None = None,
         known: dict[str, str] | None = None, *, v21: bool = False) -> list[Quote]:
    """The best quotes for the question among the messages recall found. `candidates` are message rows in recall's
    order (`clean`, `position`, `turn`, `id`, `role`, `name`); `names` maps a normalized character name to how the
    packet shows it; `rarity` weighs a word by how few of the chat's messages hold it (1 when unknown); `met` is the
    turn by which every character the question names had appeared, for a first cue; `known` maps normalized quoted
    words to the speaker an extraction named for them (PHASE-45 S3), read only where the text names nobody. `v21`:
    packet-v21's terms, quotes and speakers (the module docstring)."""
    terms = query_terms(query, v21=v21)
    wanted = [_words(m) for m in (QUERY_QUOTE_V21 if v21 else QUERY_QUOTE).finditer(query)]
    turn = named_turn(query)
    first = first and turn is None  # a named turn says where; "첫째 장" is no first cue then
    asked, _ = named(query, names)  # whose words are asked for
    asking, answering = bool(ASKING.search(query)), bool(ANSWERING.search(query))
    asked_keys = {norm(d) for d in asked} | {key for key, d in names.items() if d in asked}
    weights = {w: v * (rarity or {}).get(w, 1.0) for w, v in terms.items()
               if not any(w in k or k in w for k in asked_keys)}  # the speaker is scored as a speaker, below
    if weights and (top := max(weights.values())) > 0:  # the question's rarest word weighs 1
        weights = {w: v / top for w, v in weights.items()}
    scored: list[Quote] = []
    spans_of: dict[int, tuple[int, int, int]] = {}
    lines_of: dict[str, list[tuple[str, str | None]]] = {}  # each message's quotes and their speakers (PHASE-45 S4)
    for rank, c in enumerate(candidates):
        for sp in quotes_in(c["clean"] or "", v21=v21):
            in_quote, near, line = norm(sp.words), norm(sp.near), norm(sp.line)
            # a word in the quote counts twice, in its sentence or the next 1.5, anywhere in the line placed once
            hits = sum(v * (2 if w in in_quote else 1.5 if w in near else 1 if w in line else 0)
                       for w, v in weights.items())
            phrase = any(norm(p) in in_quote for p in wanted)
            speaker = _speaker(sp, names, c.get("role"), c.get("name"), v21=v21)
            if speaker is None and known and (said := known.get(norm(sp.words))):  # who the extraction says (S3)
                speaker = names.get(norm(said), said)
            if known:
                lines_of.setdefault(str(c["id"]), []).append((sp.words, speaker))
            if not hits and not phrase and not (turn is not None and c.get("turn") == turn):
                continue
            score = hits + (5 if phrase else 0) + 0.5 / (1 + rank)
            if asking and is_question(sp.words) or answering and sp.after_question:
                score += 1
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
    gathered: set[tuple[str, str]] = set()  # (message, words) a speaker's line already shows
    for q in scored:
        a, b, at = spans_of[id(q)]
        if (q.revision_id, q.words) in gathered:
            continue
        if any(q.revision_id == o.revision_id and a <= spans_of[id(o)][1] and spans_of[id(o)][0] <= b for o in out):
            continue  # a line already placed shows this quote, or this line would show that one
        if known and asked and q.speaker in asked and lines_of.get(q.revision_id):
            # PHASE-45 S4: the asked speaker's other lines of this message follow their line, so they do not crowd
            # each other out of the two places
            placed, shown = speaker_line(q, lines_of[q.revision_id])
            spans_of[id(placed)] = spans_of[id(q)]
            q = placed
            gathered.update((q.revision_id, w) for w in shown)
        out.append(q)
        if len(out) == QUOTES_MAX:
            break
    return out


def speaker_line(q: Quote, lines: list[tuple[str, str | None]]) -> tuple[Quote, list[str]]:
    """`q`'s line as placed, then its speaker's other quoted lines of the message that the line does not show, the
    nearest first, within QUOTE_CHARS more (PHASE-45 S4): nothing the line showed is cut. Returns the line and the
    words it shows."""
    own = [w for w, who in lines if who == q.speaker]
    if q.words not in own:
        return q, [q.words]
    i = own.index(q.words)
    shown = [w for w in own if norm(w) in norm(q.text)]
    extra: list[str] = []
    size = 0
    for j in sorted(range(len(own)), key=lambda j: (abs(j - i), j)):
        w = own[j]
        if w in shown or w in extra:
            continue
        if size + len(w) + 6 > QUOTE_CHARS:
            break
        extra.append(w)
        size += len(w) + 6
    if not extra:
        return q, shown or [q.words]
    extra.sort(key=own.index)
    return (dataclasses.replace(q, text=q.text + f" … {q.speaker}: " + " … ".join(f'"{w}"' for w in extra)),
            shown + extra)


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
