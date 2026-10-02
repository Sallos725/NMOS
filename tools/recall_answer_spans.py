"""Experimental contiguous answer spans inside sources already accepted by retrieval.

Only the question and source text are inputs. No gold, case identity or entity-specific rules.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from nmos_sidecar.facts import WHY

DETAIL = re.compile(r"내용|\bcontents?\b", re.I)
ENUMERATOR = re.compile(
    r"(?:^|[\n\"“‘'])[\s*_]*"
    r"(?:[1-9][0-9]?[.)]|[①-⑳]|(?:하나|둘|셋|넷|다섯|여섯|일곱|여덟|아홉|열)(?:\s*반)?[.．])",
    re.M,
)
CAUSE = re.compile(r"때문|탓|인해|덕분|니까|그래서|그 결과|원인|문제|\bbecause\b|\bdue to\b|\btherefore\b|\bcaus\w*", re.I)


@dataclass(frozen=True)
class AnswerSpan:
    start: int
    end: int
    kind: str


def lines(content: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in re.finditer(r"[^\n]+", content) if m.group().strip()]


def enumerated_span(content: str, words: list[str], limit: int) -> AnswerSpan | None:
    markers = list(ENUMERATOR.finditer(content))
    blocks: list[list[re.Match[str]]] = []
    for marker in markers:
        if not blocks or marker.end() - blocks[-1][0].start() > limit:
            blocks.append([])
        blocks[-1].append(marker)
    candidates = []
    for block in blocks:
        if len(block) < 3:
            continue
        first, last = block[0].start(), block[-1].end()
        end = content.find('\n', last)
        end = len(content) if end < 0 else end
        start = content.rfind('\n', 0, first) + 1
        # A nearby title/description links the list to the requested document.
        before = content[max(0, first - 300):first].casefold()
        support = sum(word.casefold() in before for word in words)
        if support < 2 or end - start > limit:
            continue
        candidates.append((support, len(block), -start, AnswerSpan(start, end, 'enumerated')))
    return max(candidates, key=lambda x: x[:3])[-1] if candidates else None


def causal_span(content: str, words: list[str], limit: int) -> AnswerSpan | None:
    limit = min(limit, 640)
    segments = lines(content)
    candidates = []
    for index, (start, _) in enumerate(segments):
        for _, end in segments[index:]:
            if end - start > limit:
                break
            text = content[start:end]
            markers = {m.group().casefold() for m in CAUSE.finditer(text)}
            if len(markers) < 3:
                continue
            support = sum(word.casefold() in text.casefold() for word in words)
            if support:
                candidates.append((len(markers), support, end - start, -start, AnswerSpan(start, end, 'causal')))
    return max(candidates, key=lambda x: x[:4])[-1] if candidates else None


ENCLOSURE = re.compile(r"(?:뭐|무엇|어떤|어디).{0,30}(?:담|넣|보관|포장)")
PACKING_ACTIONS = ("담", "넣", "보관", "포장")


def enclosure_span(content: str, query: str, words: list[str], limit: int) -> AnswerSpan | None:
    actions = [stem for stem in PACKING_ACTIONS if re.search(r"(?<![가-힣])" + stem, query)]
    segments = lines(content)
    candidates = []
    limit = min(limit, 480)
    for index, (start, end) in enumerate(segments):
        sentence = content[start:end]
        if not any(re.search(r"(?<![가-힣])" + stem, sentence) for stem in actions):
            continue
        # The following paragraph often names who puts the object into the described container.
        if index + 1 < len(segments) and segments[index + 1][1] - start <= limit:
            end = segments[index + 1][1]
        if end - start > limit:
            continue
        support = sum(word.casefold() in content[start:end].casefold() for word in words)
        if support:
            candidates.append((support, -start, AnswerSpan(start, end, 'enclosure')))
    return max(candidates, key=lambda x: x[:2])[-1] if candidates else None


def select_span(content: str, query: str, words: list[str], limit: int) -> AnswerSpan | None:
    if limit < 24 or not words:
        return None
    if DETAIL.search(query):
        return enumerated_span(content, words, limit)
    if WHY.search(query):
        return causal_span(content, words, limit)
    if ENCLOSURE.search(query):
        return enclosure_span(content, query, words, limit)
    return None
