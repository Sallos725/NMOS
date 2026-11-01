"""Diverged from the setting (PHASE-53): where the story left the card's and the lorebook's setting, for the author's
note. One model call compares the setting (the card, the persona and the note always; the lorebook entries that name
what the story is about) with the story (its current facts and scene summaries); every line it gives is checked against
the canon text it quotes and the turns it cites before the note says it.

Nothing is stored and no packet reads it: `notes.make` places it first in the note. It imports nothing from `notes`,
which hands it facts already filtered for secrets and Phase 50's `changed` lines as the fallback (S6).
"""

from __future__ import annotations

import hashlib
import re
import threading
from collections import OrderedDict
from collections.abc import Callable
from typing import Any

from .canonfacts import named
from .entities import norm
from .inspector import fact_line_text
from .llm import LLMError, metered
from .noteblocks import strip_blocks
from .summaries import content, held as summary_held, leaks

STORY_CHARS = 20_000  # the story's side (S2); facts take at most half
CANON_CHARS = 30_000  # the setting's side (S3)
ENTRY_CHARS = 4_000  # of one canon text
QUOTE_MIN = 12  # characters of a quote, normalized
NAME_MIN = 2  # a shorter name picks too many entries
ALWAYS = ("card:desc", "card:personality", "card:scenario", "card:greeting", "persona", "note")
KINDS = ("life", "position", "relationship", "world", "other")
HEAD = "## Diverged from the setting"
CACHE_MAX = 64
_CACHE: OrderedDict[str, dict[str, Any]] = OrderedDict()  # model-made parts only, by their whole input
_CACHE_LOCK = threading.Lock()  # requests run in the server's thread pool


def clear_cache() -> None:
    with _CACHE_LOCK:
        _CACHE.clear()


def _everyone(open_secrets: list[dict[str, Any]]) -> frozenset[str]:
    return frozenset(norm(n) for s in open_secrets for n in s["open"])


def story_input(facts: list[dict[str, Any]], told: dict[str, Any] | None, open_secrets: list[dict[str, Any]],
                told_secrets: bool) -> tuple[str, list[tuple[int, int]], int]:
    """The story's side (S2): its current facts, newest first, in at most half of STORY_CHARS; then the newest scene
    summaries that fit and the story so far for turns they leave out, in order. Returns the text, the turn spans it
    cites (a fact's turn, a summary's range) and how many summaries were held for a secret (`summaries.held`, as the
    chronicle holds them: the note is read in every scene)."""
    everyone = _everyone(open_secrets)
    lines, spans, size = ["STORY FACTS (newest first):"], [], 0
    for f in sorted((f for f in facts if not f.get("canon") and f.get("turn") is not None and f["turn"] >= 0),
                    key=lambda f: -f["position"]):
        line = f"- [t{f['turn']}] " + ("NOT " if f.get("polarity") == "negative" else "") + fact_line_text(f)
        if size + len(line) > STORY_CHARS // 2:
            break
        lines.append(line)
        spans.append((f["turn"], f["turn"]))
        size += len(line) + 1
    held, rows = 0, []
    for x in (told or {}).get("scenes") or []:
        row = x.get("summary")
        if row is None:
            continue
        if not told_secrets and summary_held(row, open_secrets, everyone):
            held += 1
        else:
            rows.append(row)
    newest: list[dict[str, Any]] = []
    for row in reversed(rows):
        if size + len(row["text"]) + 24 > STORY_CHARS:
            break
        newest.insert(0, row)
        size += len(row["text"]) + 24
    story = (told or {}).get("story")
    if story is not None and not told_secrets and summary_held(story, open_secrets, everyone):
        story, held = None, held + 1
    if story is not None and (not newest or newest[0]["first_turn"] > 0) and size + len(story["text"]) <= STORY_CHARS:
        newest.insert(0, story)
    lines += ["", "SCENES:"] + [f"[turns {r['first_turn']}–{r['last_turn']}] {r['text']}" for r in newest]
    spans += [(r["first_turn"], r["last_turn"]) for r in newest]
    return "\n".join(lines), spans, held
