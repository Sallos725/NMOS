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


def _label(key: str, metadata: dict[str, Any]) -> str:
    if key.startswith("card:"):
        return "card"
    if key in ("persona", "note"):
        return "persona" if key == "persona" else "author's note"
    comment = metadata.get("comment")
    return f'lorebook "{comment}"' if comment else "lorebook"


def _names(e: dict[str, Any]) -> set[str]:
    raw = [e.get("name"), *(e.get("names") or []), *(a.get("name") for a in e.get("aliases") or []),
           *(a.get("other") for a in e.get("aliases") or [])]
    return {n for n in (norm(x) for x in raw if x) if len(n) >= NAME_MIN}


def _named_in(name: str, hay: str) -> bool:
    """A normalized name in a normalized text: a Latin name as a whole word ("ren" is not in "current"); any other as
    written, since a Korean particle joins its name ("레나는")."""
    if not name.isascii():
        return name in hay
    return re.search(rf"(?<![a-z0-9]){re.escape(name)}(?![a-z0-9])", hay) is not None


def canon_input(entries: list[dict[str, Any]], entities: list[dict[str, Any]], facts: list[dict[str, Any]],
                story_text: str, excluded: frozenset[str] = frozenset()) -> tuple[list[dict[str, Any]], int]:
    """The setting's side (S3) from the manifest in force (`canon.manifest`): the card's story fields, the persona and
    the note without NMOS's block always; then the lorebook entries whose keys or text name an entity of the story's
    side (one with a story fact, or named in the scenes given), ranked by how many with a story fact they name, then how
    many in all, then how late the story stated a fact of one, then key. Each text has its name macros filled in (as
    the host fills them), at most ENTRY_CHARS of it, at most CANON_CHARS in all. Returns the texts given
    (`{key, label, text}`) and how many candidate entries did not fit. The persona and the entities the owner left out
    (PHASE-47) pick no entry."""
    by_key = {e["key"]: e for e in entries if e.get("content")}
    character = ((by_key.get("card:name") or {}).get("content") or "").strip() or None
    user = ((by_key.get("persona") or {}).get("metadata") or {}).get("name") or None

    def text_of(e: dict[str, Any]) -> str:
        text = strip_blocks(e["content"])[0] if e["key"] == "note" else e["content"]
        return named(text, character, user).strip()

    latest: dict[str, int] = {}  # entity id -> the newest turn of a story fact about it
    for f in facts:
        if f.get("canon") or f.get("turn") is None or f["turn"] < 0:
            continue
        for side in ("subject_entity", "object_entity"):
            ref = f.get(side)
            if isinstance(ref, dict) and ref.get("id"):
                latest[str(ref["id"])] = max(latest.get(str(ref["id"]), -1), f["turn"])
    told_text = norm(story_text)
    names = {str(e["id"]): ns for e in entities
             if not e.get("persona") and str(e["id"]) not in excluded and (ns := _names(e))}
    names = {i: ns for i, ns in names.items() if i in latest or any(_named_in(n, told_text) for n in ns)}
    given: list[dict[str, Any]] = []
    total = 0
    for key in ALWAYS:
        e = by_key.get(key)
        text = text_of(e)[:ENTRY_CHARS] if e else ""
        if text:
            given.append({"key": key, "label": _label(key, e.get("metadata") or {}), "text": text})
            total += len(text)
    ranked = []
    for e in entries:
        if not e["key"].startswith("lore:") or not e.get("content"):
            continue
        text = text_of(e)
        hay, keys = norm(text), {norm(k) for k in (e.get("metadata") or {}).get("keys") or []}
        hit = [i for i, ns in names.items() if any(n in keys or _named_in(n, hay) for n in ns)]
        if not hit:
            continue
        touched = [latest[i] for i in hit if i in latest]
        ranked.append(((-len(touched), -len(hit), -max(touched, default=-1), e["key"]), e, text[:ENTRY_CHARS]))
    left = 0
    for _, e, text in sorted(ranked, key=lambda r: r[0]):
        if total + len(text) > CANON_CHARS:
            left += 1
            continue
        given.append({"key": e["key"], "label": _label(e["key"], e.get("metadata") or {}), "text": text})
        total += len(text)
    return given, left


TURN = re.compile(r"\d+")


def _flat(text: Any) -> str:
    return " ".join(str(text or "").casefold().split())


def check(items: Any, given: list[dict[str, Any]], spans: list[tuple[int, int]],
          last_turn: int | None) -> list[dict[str, Any]]:
    """The items of a reply that hold (S4): a key given, a quote of at least QUOTE_MIN characters found in that text
    (whitespace and case aside), a "now", and turns each at most the head's and inside a span the story's side cited.
    The same key and quote twice is one item, the newer turns. Anything else is dropped."""
    texts = {g["key"]: _flat(g["text"]) for g in given}
    labels = {g["key"]: g["label"] for g in given}
    out: list[dict[str, Any]] = []
    seen: dict[tuple[str, str], int] = {}
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict):
            continue
        key, quote, now = str(it.get("key") or ""), str(it.get("quote") or "").strip(), str(it.get("now") or "").strip()
        q = _flat(quote)
        if key not in texts or len(q) < QUOTE_MIN or q not in texts[key] or not now:
            continue
        raw = it.get("turns") if isinstance(it.get("turns"), list) else [it.get("turns")]
        turns = sorted({int(m) for x in raw for m in TURN.findall(str(x))})
        if not turns or last_turn is None or any(t > last_turn or not any(a <= t <= b for a, b in spans) for t in turns):
            continue
        row = {"key": key, "label": labels[key], "quote": quote, "subject": str(it.get("subject") or "").strip(),
               "now": now, "turns": turns, "kind": it.get("kind") if it.get("kind") in KINDS else "other"}
        at = seen.get((key, q))
        if at is None:
            seen[(key, q)] = len(out)
            out.append(row)
        elif turns[-1] > out[at]["turns"][-1]:
            out[at] = row
    return out


def line(r: dict[str, Any]) -> str:
    """One line of the note (S7), in the chronicle's turn style."""
    a, b = r["turns"][0], r["turns"][-1]
    when = f"t{a}" if a == b else f"t{a}–{b}"
    head = f"{r['subject']} ({r['label']})" if r["subject"] else r["label"]
    return f'- {head}: the setting says "{r["quote"]}" → now {r["now"]} ({when})'
