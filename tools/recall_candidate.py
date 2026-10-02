"""Evaluation-only vector passage focus; receives no benchmark labels or case identifiers."""
from __future__ import annotations

from typing import Any, Callable
from contextvars import ContextVar
from pathlib import Path
import re
from nmos_sidecar.facts import WHY

from nmos_sidecar import packet, retrieval

_QUERY: ContextVar[str] = ContextVar("recall_candidate_query", default="")
_ANSWER_SPANS: ContextVar[frozenset[str]] = ContextVar("recall_answer_spans", default=frozenset())
_CHAR_LIMIT: ContextVar[int] = ContextVar("recall_answer_limit", default=960)
DETAIL = re.compile(r"내용|\bcontents?\b", re.IGNORECASE)


def focus_candidates(rows: list[dict[str, Any]], min_sim: float, query: str = "",
                     max_chars: int = 960) -> list[dict[str, Any]]:
    words = retrieval.keywords(query)
    if WHY.search(query) and not DETAIL.search(query):
        # A cast name shared by most candidates is not evidence of the requested topic.
        words = [word for word in words if sum(word.casefold() in row['clean'].casefold()
                                              for row in rows) * 2 <= len(rows)]
    out = []
    for original in rows:
        row = dict(original)
        start, end = row.get('text_start'), row.get('text_end')
        if query:
            from recall_answer_spans import select_span
            selected = select_span(row['clean'], query, words, max_chars)
            if selected is not None:
                start, end = selected.start, selected.end
                row['answer_span_kind'] = selected.kind
        if (('answer_span_kind' in row or row.get('sim') is not None and row['sim'] >= min_sim)
                and isinstance(start, int) and isinstance(end, int) and 0 <= start < end <= len(row['clean'])):
            row['full_clean'] = row['clean']
            row['focus_span'] = {'start': start, 'end': end}
            row['clean'] = row['clean'][start:end]
            row['text_start'], row['text_end'] = 0, len(row['clean'])
        out.append(row)
    return out


def contextual_excerpt(content: str, query: str, words: list[str],
                       max_chars: int = packet.MAX_EXCERPT_CHARS) -> tuple[str, str]:
    """Keep the existing anchor but expand by character budget, not four sentence fragments.

    Dialogue is often split into tiny sentences. A four-sentence ceiling can omit the answer
    right after a question even when the allocated passage budget has hundreds of chars free.
    """
    max_chars = min(max_chars, 320)
    parts = packet.sentences(content) or [content.strip()]
    grams = packet._trigrams(query)
    best = max(range(len(parts)), key=lambda i: (
        sum(w.casefold() in parts[i].casefold() for w in words),
        len(packet._trigrams(parts[i]) & grams), -i))
    def framed(lo: int, hi: int, text: str) -> str:
        suffix = '…' if hi < len(parts) - 1 else ''
        if len(text) > max_chars:
            text, suffix = text[:max_chars - 1].rstrip(), '…'
        return ('…' if lo else '') + text + suffix
    short = framed(best, best, parts[best])
    lo = hi = best
    length, after = len(parts[best]), True
    while length <= max_chars:
        right = hi + 1 < len(parts) and length + 1 + len(parts[hi + 1]) <= max_chars
        left = lo > 0 and length + 1 + len(parts[lo - 1]) <= max_chars
        if not (left or right):
            break
        if right and (after or not left):
            hi += 1; length += 1 + len(parts[hi])
        else:
            lo -= 1; length += 1 + len(parts[lo])
        after = not after
    return framed(lo, hi, ' '.join(parts[lo:hi + 1])), short


def focused_excerpt(content: str, query: str, words: list[str],
                    max_chars: int = packet.MAX_EXCERPT_CHARS) -> tuple[str, str]:
    target = _QUERY.get()
    if content in _ANSWER_SPANS.get():
        _, short = packet.grown_excerpt(content, target, words, max_chars)
        return content, short
    if WHY.search(target) or DETAIL.search(target):
        return contextual_excerpt(content, ' '.join(words) if words else target, words, max_chars)
    return packet.grown_excerpt(content, ' '.join(words) if words else target, words, max_chars)


def install(original_gather: Callable[..., retrieval.Gathered], root: Path,
            answer_spans: bool = False) -> Callable[..., retrieval.Gathered]:
    original_fuse = retrieval.fuse
    def fuse(lexical: list[dict[str, Any]], vector: list[dict[str, Any]], threshold: float,
             min_sim: float, keyword: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        rows = focus_candidates(original_fuse(lexical, vector, threshold, min_sim, keyword), min_sim,
                                _QUERY.get() if answer_spans else '', _CHAR_LIMIT.get())
        _ANSWER_SPANS.set(frozenset(row['clean'] for row in rows if 'answer_span_kind' in row))
        return rows
    retrieval.fuse = fuse
    retrieval.grown_excerpt = focused_excerpt

    def gather(conn: Any, head: Any, query: str, previous_ai: str, in_context: set[str],
               options: retrieval.RecallOptions, *args: Any, **kwargs: Any) -> retrieval.Gathered:
        token = _QUERY.set(query)
        spans_token = _ANSWER_SPANS.set(frozenset())
        limit_token = _CHAR_LIMIT.set(options.excerpt_chars)
        try:
            return original_gather(conn, head, query, previous_ai, in_context, options, *args, **kwargs)
        finally:
            _QUERY.reset(token)
            _ANSWER_SPANS.reset(spans_token)
            _CHAR_LIMIT.reset(limit_token)
    return gather
