"""Evaluation-only vector passage focus; receives no benchmark labels or case identifiers."""
from __future__ import annotations

from typing import Any, Callable
from contextvars import ContextVar
from pathlib import Path
import re
from nmos_sidecar.facts import WHY

from nmos_sidecar import packet, retrieval

_QUERY: ContextVar[str] = ContextVar("recall_candidate_query", default="")
DETAIL = re.compile(r"내용|\bcontents?\b", re.IGNORECASE)


def focus_candidates(rows: list[dict[str, Any]], min_sim: float) -> list[dict[str, Any]]:
    out = []
    for original in rows:
        row = dict(original)
        start, end = row.get('text_start'), row.get('text_end')
        if (row.get('sim') is not None and row['sim'] >= min_sim and isinstance(start, int)
                and isinstance(end, int) and 0 <= start < end <= len(row['clean'])):
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
    if WHY.search(target) or DETAIL.search(target):
        return contextual_excerpt(content, ' '.join(words) if words else target, words, max_chars)
    return packet.grown_excerpt(content, ' '.join(words) if words else target, words, max_chars)


def install(original_gather: Callable[..., retrieval.Gathered], root: Path) -> Callable[..., retrieval.Gathered]:
    original_fuse = retrieval.fuse
    def fuse(lexical: list[dict[str, Any]], vector: list[dict[str, Any]], threshold: float,
             min_sim: float, keyword: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        return focus_candidates(original_fuse(lexical, vector, threshold, min_sim, keyword), min_sim)
    retrieval.fuse = fuse
    retrieval.grown_excerpt = focused_excerpt

    def gather(conn: Any, head: Any, query: str, previous_ai: str, in_context: set[str],
               options: retrieval.RecallOptions, *args: Any, **kwargs: Any) -> retrieval.Gathered:
        token = _QUERY.set(query)
        try:
            return original_gather(conn, head, query, previous_ai, in_context, options, *args, **kwargs)
        finally:
            _QUERY.reset(token)
    return gather
