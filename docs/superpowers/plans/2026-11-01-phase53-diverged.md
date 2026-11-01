# Phase 53 — Diverged from the setting: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The author's note's first part lists where the story left the card's and the lorebook's setting, found by one
model call and checked line by line against the canon text it quotes and the turns it cites (`docs/phases/PHASE-53.md`).

**Architecture:** A new sidecar module `divergence.py` builds both sides of the input (story: current story facts and
scene summaries; setting: card, persona, note and the lorebook entries that name the story's entities), calls the
extraction model once (one retry), checks every item deterministically, and falls back to Phase 50's `changed` lines.
`notes.make` places it first in the one NMOS block; the endpoint passes the manifest in force. The plugin only renames
the toggle and changes the defaults.

**Tech Stack:** Python 3 / FastAPI / psycopg (sidecar, `uv run pytest`, Postgres on 127.0.0.1:5436), TypeScript /
vitest / esbuild (PocketRisu plugin).

**Branch / worktree:** `docs/phase53-diverged-from-setting` in `/home/grantkim725/data/docker/risuaiNode/NMOS-p53`.
Guard every git command with a branch check (`nmos-worktree-safety`):
`[ "$(git -C /home/grantkim725/data/docker/risuaiNode/NMOS-p53 branch --show-current)" = docs/phase53-diverged-from-setting ]`.

**Public repository:** synthetic names only (Hana, Kaito, Ren, Mira, Taku); no owner chat text anywhere.

---

## File structure

- Create `apps/sidecar/src/nmos_sidecar/divergence.py` — the part: inputs, prompt, check, call, cache, lines. Imports
  nothing from `notes` (notes imports it), so it receives facts already filtered for secrets and the fallback lines.
- Create `apps/sidecar/tests/test_divergence.py` — pure tests of the module with a stub model.
- Modify `apps/sidecar/src/nmos_sidecar/notes.py` — `KINDS`, `HEADER`, `Ask.of`, `make(..., canon=...)`.
- Modify `apps/sidecar/tests/test_notes.py` — header text, `Ask` order, one endpoint test for the new part.
- Modify `apps/sidecar/src/nmos_sidecar/api.py:1130-1151` — the endpoint reads the manifest and summaries for the part.
- Modify `adapters/pocketrisu-plugin/src/ui.ts:1315-1345`, `src/i18n.ts:170-200` — the toggle, defaults, texts.
- Modify `adapters/pocketrisu-plugin/test/dom.test.ts:545-560`, `test/views.test.ts:148-151` — the new boxes.
- Rebuild `adapters/pocketrisu-plugin/dist/nmos-pocketrisu.js` (committed build).
- Modify `docs/phases/PHASE-53.md` — the line format, step evidence.

---

### Task 1: The story's side of the input

**Files:**
- Create: `apps/sidecar/src/nmos_sidecar/divergence.py`
- Test: `apps/sidecar/tests/test_divergence.py`

- [ ] **Step 1: Write the failing tests**

```python
"""PHASE-53: diverged from the setting — the inputs, the check, the call, the fallback."""

from __future__ import annotations

from nmos_sidecar import divergence


def fact(subject, predicate, *, obj=None, value=None, turn=5, eid=None, canon=None, polarity="positive", **kw):
    """A current fact as `memory_view` makes it (the fields this part reads)."""
    return {"subject": subject, "predicate": predicate, "object": obj, "value": value, "turn": turn,
            "position": turn, "polarity": polarity, "canon": canon,
            "subject_entity": {"id": eid or f"e-{subject}", "name": subject}, "history": [], **kw}


def scene(first, last, text, told=()):
    return {"window": None, "summary": {"id": f"s{first}", "first_turn": first, "last_turn": last, "text": text,
                                        "coverage": {"secrets": list(told)}}}


def told(*scenes, story=None):
    return {"scenes": list(scenes), "story": story}


def test_the_story_side_holds_story_facts_newest_first_then_the_scenes_in_order():
    facts = [fact("Ren", "has_status", value="arrested", turn=42),
             fact("Ren", "located_in", obj="capital prison", turn=44),
             fact("Ren", "identity", value="captain", turn=-1, canon="card:desc")]  # canon: not the story's
    text, spans, held = divergence.story_input(
        facts, told(scene(0, 7, "Ren leads the guard."), scene(40, 47, "Ren is taken away in chains.")), [], False)
    assert text.index("[t44] Ren located in capital prison") < text.index("[t42] Ren has status: arrested")
    assert "captain" not in text
    assert text.index("[turns 0–7] Ren leads the guard.") < text.index("[turns 40–47] Ren is taken away")
    assert (42, 42) in spans and (44, 44) in spans and (40, 47) in spans and held == 0


def test_a_denial_says_not():
    text, _, _ = divergence.story_input([fact("Ren", "member_of", obj="Royal Guard", polarity="negative")],
                                        None, [], False)
    assert "[t5] NOT Ren member of Royal Guard" in text


def test_the_story_side_keeps_to_its_cap_and_leaves_held_scenes_out():
    secret = {"open": ["Kaito"], "holders": ["Hana"], "text": "Hana identity: smuggler", "turn": 2, "position": 2}
    long = [scene(8 * i, 8 * i + 7, "x" * 3000, told=("smuggler",)) for i in range(10)]
    leaky = scene(80, 87, "Hana is a smuggler, Kaito must never know.")
    text, spans, held = divergence.story_input([], told(*long, leaky), [secret], False)
    assert len(text) <= divergence.STORY_CHARS + 200 and held == 1 and "smuggler" not in text
    assert (72, 79) in spans and (0, 7) not in spans  # the newest that fit
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd /home/grantkim725/data/docker/risuaiNode/NMOS-p53/apps/sidecar && uv run pytest tests/test_divergence.py -q`
Expected: FAIL — `ImportError: cannot import name 'divergence'`.

- [ ] **Step 3: Write the module's head and `story_input`**

```python
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
```

- [ ] **Step 4: Run the tests**

Run: `cd /home/grantkim725/data/docker/risuaiNode/NMOS-p53/apps/sidecar && uv run pytest tests/test_divergence.py -q`
Expected: 3 passed. If `fact_line_text` words a predicate differently ("has status: arrested"), fix the test's
expected strings to what `inspector.fact_line_text` prints, not the function.

- [ ] **Step 5: Commit**

```bash
W=/home/grantkim725/data/docker/risuaiNode/NMOS-p53
[ "$(git -C $W branch --show-current)" = docs/phase53-diverged-from-setting ] && git -C $W add apps/sidecar/src/nmos_sidecar/divergence.py apps/sidecar/tests/test_divergence.py && git -C $W commit -m "feat(sidecar): the story's side of the divergence input (PHASE-53 S2)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 2: The setting's side of the input

**Files:**
- Modify: `apps/sidecar/src/nmos_sidecar/divergence.py`
- Test: `apps/sidecar/tests/test_divergence.py`

- [ ] **Step 1: Write the failing tests**

```python
def entry(key, text, **metadata):
    """A manifest entry as `canon.manifest` gives it."""
    return {"key": key, "hash": "h", "metadata": metadata, "content": text, "revision_id": None}


ENTITIES = [{"id": "e-Ren", "type": "character", "name": "Ren", "names": ["Ren", "Captain Ren"],
             "aliases": [{"name": "Ren", "other": "레나"}], "persona": False},
            {"id": "e-Mira", "type": "character", "name": "Mira", "names": ["Mira"], "aliases": [], "persona": False},
            {"id": "e-Taku", "type": "character", "name": "Taku", "names": ["Taku"], "aliases": [], "persona": True}]
MANIFEST = [entry("card:name", "Hana"), entry("card:desc", "{{char}} serves under Captain Ren."),
            entry("persona", "{{user}} is a traveler.", name="Taku"),
            entry("note", "Keep it slow.\n[NMOS note · t3 · 2026-10-23]\nold\n[/NMOS note]"),
            entry("lore:guard", "The Royal Guard answers to its captain.", keys=["Ren", "guard"], comment="Royal Guard"),
            entry("lore:bakery", "Mira bakes at dawn.", keys=["Mira"], comment="Bakery"),
            entry("lore:sea", "The current is cold.", keys=["sea"], comment="Sea")]  # "ren" inside a word: no


def test_the_setting_side_always_holds_the_card_persona_and_note_and_ranks_the_lorebook():
    facts = [fact("Ren", "has_status", value="arrested", turn=42)]
    given, left = divergence.canon_input(MANIFEST, ENTITIES, facts, "Mira watched them go.")
    keys = [g["key"] for g in given]
    assert keys[:3] == ["card:desc", "persona", "note"]
    assert keys[3:] == ["lore:guard", "lore:bakery"] and left == 0  # Ren has a story fact; Mira is only named
    assert given[0]["text"] == "Hana serves under Captain Ren." and given[1]["text"] == "Taku is a traveler."
    assert given[2]["text"] == "Keep it slow." and given[3]["label"] == 'lorebook "Royal Guard"'
    assert given[0]["label"] == "card" and given[1]["label"] == "persona" and given[2]["label"] == "author's note"


def test_an_alias_picks_an_entry_and_the_persona_picks_none():
    manifest = [entry("lore:jail", "레나는 감옥에 있다.", keys=["감옥"], comment="Jail"),  # a particle on the name
                entry("lore:taku", "Taku is the user.", keys=["Taku"], comment="Taku")]
    given, _ = divergence.canon_input(manifest, ENTITIES, [fact("Ren", "has_status", value="arrested")], "")
    assert [g["key"] for g in given] == ["lore:jail"]


def test_the_setting_side_keeps_to_its_caps():
    manifest = [entry("card:desc", "d" * 9000)] + [
        entry(f"lore:{i:02d}", f"Ren {i} " + "y" * 6000, keys=["Ren"]) for i in range(10)]
    given, left = divergence.canon_input(manifest, ENTITIES, [fact("Ren", "has_status", value="arrested")], "")
    assert all(len(g["text"]) <= divergence.ENTRY_CHARS for g in given)
    assert sum(len(g["text"]) for g in given) <= divergence.CANON_CHARS and left == 4
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd /home/grantkim725/data/docker/risuaiNode/NMOS-p53/apps/sidecar && uv run pytest tests/test_divergence.py -q -k "setting_side or alias"`
Expected: FAIL — `AttributeError: module 'nmos_sidecar.divergence' has no attribute 'canon_input'`.

- [ ] **Step 3: Write `canon_input`**

```python
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
```

- [ ] **Step 4: Run the tests**

Run: `cd /home/grantkim725/data/docker/risuaiNode/NMOS-p53/apps/sidecar && uv run pytest tests/test_divergence.py -q`
Expected: 6 passed. In the caps test the card takes 4,000 and six entries of 4,000 fit (28,000), so 4 are left out.

- [ ] **Step 5: Commit**

```bash
W=/home/grantkim725/data/docker/risuaiNode/NMOS-p53
[ "$(git -C $W branch --show-current)" = docs/phase53-diverged-from-setting ] && git -C $W commit -am "feat(sidecar): the setting's side of the divergence input, lorebook entries by name (PHASE-53 S3)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 3: The check and the line

**Files:**
- Modify: `apps/sidecar/src/nmos_sidecar/divergence.py`
- Test: `apps/sidecar/tests/test_divergence.py`

- [ ] **Step 1: Write the failing tests**

```python
GIVEN = [{"key": "card:desc", "label": "card", "text": "Hana serves under Captain Ren of the Royal Guard."},
         {"key": "lore:guard", "label": 'lorebook "Royal Guard"', "text": "The Royal Guard answers to Captain Ren."}]
SPANS = [(42, 42), (40, 47)]


def item(**kw):
    return {"key": "lore:guard", "quote": "answers to Captain Ren", "subject": "Ren", "now": "arrested",
            "turns": [42], "kind": "life", **kw}


def test_the_check_keeps_an_item_that_quotes_its_text_and_cites_the_story():
    rows = divergence.check([item(quote="ANSWERS  to captain ren", turns=["t42", "44"])], GIVEN, SPANS, 50)
    assert rows == [{"key": "lore:guard", "label": 'lorebook "Royal Guard"', "quote": "ANSWERS  to captain ren",
                     "subject": "Ren", "now": "arrested", "turns": [42, 44], "kind": "life"}]


def test_the_check_drops_what_it_cannot_find():
    bad = [item(key="lore:moon"),                      # not a text given
           item(quote="answers to Captain Mira"),      # not in the text
           item(quote="Captain Ren"),                  # too short to be a quote
           item(turns=[60]),                           # after the head
           item(turns=[30]),                           # not a turn the story gave
           item(turns=[]), item(now=""), "nonsense"]
    assert divergence.check(bad, GIVEN, SPANS, 50) == []
    assert divergence.check("nonsense", GIVEN, SPANS, 50) == []


def test_the_same_quote_twice_is_one_line_with_the_newer_turns_and_an_unknown_kind_is_other():
    rows = divergence.check([item(turns=[42]), item(turns=[45], kind="poem")], GIVEN, SPANS, 50)
    assert len(rows) == 1 and rows[0]["turns"] == [45] and rows[0]["kind"] == "other"


def test_a_line_names_its_text_and_turns():
    assert divergence.line({**item(), "label": 'lorebook "Royal Guard"', "turns": [42, 44],
                            "now": "arrested and held in the capital prison"}) == (
        '- Ren (lorebook "Royal Guard"): the setting says "answers to Captain Ren" → now arrested and held in the'
        ' capital prison (t42–44)')
    assert divergence.line({**item(), "label": "card", "subject": "", "turns": [42]}).startswith(
        '- card: the setting says "answers to Captain Ren" → now arrested (t42)')
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd /home/grantkim725/data/docker/risuaiNode/NMOS-p53/apps/sidecar && uv run pytest tests/test_divergence.py -q -k "check or line"`
Expected: FAIL — `AttributeError: ... has no attribute 'check'`.

- [ ] **Step 3: Write `check` and `line`**

```python
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
```

- [ ] **Step 4: Run the tests**

Run: `cd /home/grantkim725/data/docker/risuaiNode/NMOS-p53/apps/sidecar && uv run pytest tests/test_divergence.py -q`
Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
W=/home/grantkim725/data/docker/risuaiNode/NMOS-p53
[ "$(git -C $W branch --show-current)" = docs/phase53-diverged-from-setting ] && git -C $W commit -am "feat(sidecar): check each divergence against its quoted canon text and cited turns (PHASE-53 S4)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 4: The call, its retry, secrets, the fallback and the cache

**Files:**
- Modify: `apps/sidecar/src/nmos_sidecar/divergence.py`
- Test: `apps/sidecar/tests/test_divergence.py`

- [ ] **Step 1: Write the failing tests**

```python
from nmos_sidecar.llm import LLMError


class Writer:
    """A stand-in model: its replies in order (an exception is raised), the prompts it saw."""

    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []

    def __call__(self, system, user):
        self.calls.append((system, user))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply, "{}"


FACTS = [fact("Ren", "has_status", value="arrested", turn=42)]
TOLD = told(scene(40, 47, "Ren is taken away in chains."))
GOOD = {"diverged": [{"key": "lore:guard", "quote": "The Royal Guard answers to its captain", "subject": "Ren",
                      "now": "arrested", "turns": [42], "kind": "life"}]}
FALLBACK = ["- Ren — status: was free → now arrested (t42)"]


def run(model, *, secrets=(), told_secrets=False, fallback=FALLBACK, manifest=MANIFEST):
    return divergence.diverged(manifest, ENTITIES, FACTS, TOLD, list(secrets), 47, model, told_secrets, fallback)


def test_the_model_finds_it_and_the_part_says_it():
    divergence.clear_cache()
    w = Writer(GOOD)
    out = run(w)
    assert out["made"] == "model" and out["lines"] == 1 and out["dropped"] == 0 and out["entries"] == 1  # Mira unnamed
    assert out["body"] == ('## Diverged from the setting\n- Ren (lorebook "Royal Guard"): the setting says "The Royal'
                           ' Guard answers to its captain" → now arrested (t42)')
    system, user = w.calls[0]
    assert "SETTING" in user and "[key: lore:guard · lorebook \"Royal Guard\"]" in user and "[t42]" in user


def test_nothing_changed_is_an_answer():
    divergence.clear_cache()
    out = run(Writer({"diverged": []}))
    assert out["made"] == "model" and out["body"] == "" and out["reason"] == "none"


def test_a_broken_reply_is_asked_again_then_the_fallback():
    divergence.clear_cache()
    w = Writer(LLMError("bad json"), {"diverged": "nope"})
    out = run(w)
    assert len(w.calls) == 2 and out["made"] == "facts"
    assert out["body"] == "## Diverged from the setting\n- Ren — status: was free → now arrested (t42)"


def test_a_reply_with_nothing_that_holds_is_asked_again_with_why():
    divergence.clear_cache()
    bad = {"diverged": [{**GOOD["diverged"][0], "quote": "The Royal Guard answers to the queen"}]}
    w = Writer(bad, GOOD)
    out = run(w)
    assert out["made"] == "model" and "copy each quote exactly" in w.calls[1][1]


def test_a_reply_that_tells_a_kept_secret_is_asked_again_then_the_fallback():
    divergence.clear_cache()
    secret = {"open": ["Kaito"], "holders": ["Ren"], "text": "Ren identity: royal guard traitor", "turn": 41,
              "position": 41}
    leak = {"diverged": [{**GOOD["diverged"][0], "now": "arrested as the royal guard traitor"}]}
    w = Writer(leak, leak)
    out = run(w, secrets=[secret])
    assert len(w.calls) == 2 and "TOLD THESE SECRETS" in w.calls[1][1] and out["made"] == "facts"
    assert "OPEN SECRETS" in w.calls[0][1]


def test_no_model_no_setting_or_no_story_is_the_fallback_without_a_call():
    divergence.clear_cache()
    assert run(None)["made"] == "facts"
    w = Writer(GOOD)
    assert run(w, manifest=[])["made"] == "facts" and not w.calls
    empty = run(None, fallback=[])
    assert empty["body"] == "" and empty["reason"] == "none"


def test_asked_twice_with_nothing_changed_the_model_answers_once_and_a_failure_is_not_remembered():
    divergence.clear_cache()
    w = Writer(GOOD)
    first, again = run(w), run(w)
    assert len(w.calls) == 1 and not first["cached"] and again["cached"]
    divergence.clear_cache()
    f = Writer(LLMError("down"), LLMError("down"), GOOD)
    assert run(f)["made"] == "facts" and run(f)["made"] == "model"
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd /home/grantkim725/data/docker/risuaiNode/NMOS-p53/apps/sidecar && uv run pytest tests/test_divergence.py -q`
Expected: the 7 new tests FAIL — `AttributeError: ... has no attribute 'diverged'`.

- [ ] **Step 3: Write the prompt and `diverged`**

```python
PROMPT = """You compare the SETTING of a role-play chat (its character card, persona, author's note and lorebook
entries, all written before the story began) with the STORY so far (facts stored from it, each with its turn, and scene
summaries with their turns). List every place where the story has left the setting: something a SETTING text states
that no longer holds now. That includes a character's life and freedom (dead, arrested, missing, gravely wounded,
exiled), a position or allegiance (dismissed, promoted, deserted, changed sides), a relationship turned around, and the
world and its places (a city destroyed, a ruler fallen, an item gone).

For each, give:
- "key": the key of the SETTING text, exactly as given;
- "quote": the words of that text that no longer hold, copied exactly from it;
- "subject": who or what it is about, named as the input names it;
- "now": how things stand in the story now, in English, one short clause;
- "turns": the turns of the STORY items that show it, as numbers;
- "kind": one of "life", "position", "relationship", "world", "other".
Only what the input says. A story detail the setting does not contradict is not a divergence, and neither is something
the setting leaves out. Keep names, titles, places and quoted words exactly as the input writes them.
{secrets}
Answer with JSON only: {{"diverged": [...]}}, an empty list when nothing the setting states has changed."""
SECRETS_KEPT = """
If OPEN SECRETS are listed, never write a secret's content, not even in other words or as a hint: the note is read in
every scene, in front of the characters it is kept from.
"""
SECRETS_TOLD = """
SECRETS are listed: you may write them, each marked with who does not know it, like "(secret: Kaito does not know)".
"""
NOTHING_HELD = ("\n\nNONE OF YOUR LAST ITEMS COULD BE USED: copy each quote exactly from its SETTING text, and cite only"
                " turns the STORY gives.")


def _user(given: list[dict[str, Any]], story: str, open_secrets: list[dict[str, Any]], told_secrets: bool) -> str:
    lines = []
    if open_secrets:
        lines += ["SECRETS:" if told_secrets else "OPEN SECRETS (never write their content):"]
        lines += [f"- {', '.join(s['holders'])} keep from {', '.join(s['open'])}: {content(s)}" for s in open_secrets]
        lines += [""]
    lines += ["SETTING:"]
    for g in given:
        lines += [f"[key: {g['key']} · {g['label']}]", g["text"], ""]
    return "\n".join(lines + ["STORY:", story])


def diverged(entries: list[dict[str, Any]], entities: list[dict[str, Any]], facts: list[dict[str, Any]],
             told: dict[str, Any] | None, open_secrets: list[dict[str, Any]], last_turn: int | None,
             model: Callable[..., tuple[Any, ...]] | None, told_secrets: bool, fallback: list[str],
             excluded: frozenset[str] = frozenset()) -> dict[str, Any]:
    """The part's Markdown and how it was made (S4–S6). `facts` are already filtered for secrets by the caller, and
    `fallback` is Phase 50's `changed` lines. One call, asked again once when its reply is not JSON with a list, when
    no item it named holds, or (secrets off) when its lines tell a kept secret at LEAK_NEAR; then the fallback. A model
    answer, an empty one included, is cached by its whole input; a fallback is not, so a failed call is tried again."""
    story, spans, held = story_input(facts, told, open_secrets, told_secrets)
    given, left = canon_input(entries, entities, facts, story, excluded)
    base = {"turns": str(last_turn or 0), "held": held, "entries": sum(g["key"].startswith("lore:") for g in given),
            "left_out": left, "cached": False, "dropped": 0}

    def facts_part() -> dict[str, Any]:
        return {**base, "made": "facts", "lines": len(fallback), "reason": "" if fallback else "none",
                "body": f"{HEAD}\n" + "\n".join(fallback) if fallback else ""}

    if model is None or not given or not spans:
        return facts_part()
    system = PROMPT.format(secrets=SECRETS_TOLD if told_secrets else (SECRETS_KEPT if open_secrets else ""))
    user = _user(given, story, open_secrets, told_secrets)
    which = getattr(getattr(model, "__self__", None), "model", "")
    key = hashlib.sha256(f"{told_secrets}|{which}|{system}|{user}".encode()).hexdigest()
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
        if hit is not None:
            _CACHE.move_to_end(key)
            return {**hit, "cached": True}
    everyone = _everyone(open_secrets)
    ask = user
    for _ in range(2):
        try:
            parsed, _, _ = metered(model, system, ask)
        except LLMError:
            continue
        items = parsed.get("diverged") if isinstance(parsed, dict) else None
        if not isinstance(items, list):
            continue
        rows = check(items, given, spans, last_turn)
        if items and not rows:
            ask = user + NOTHING_HELD
            continue
        lines = [line(r) for r in rows]
        told_now = [] if told_secrets else leaks("\n".join(lines), open_secrets, everyone)
        if told_now:
            ask = user + "\n\nYOUR LAST ANSWER TOLD THESE SECRETS; write it again without them:\n" + "\n".join(
                f"- {content(s)}" for s in told_now)
            continue
        out = {**base, "made": "model", "lines": len(lines), "reason": "" if lines else "none",
               "dropped": len(items) - len(rows), "body": f"{HEAD}\n" + "\n".join(lines) if lines else ""}
        with _CACHE_LOCK:
            _CACHE[key] = out
            while len(_CACHE) > CACHE_MAX:
                _CACHE.popitem(last=False)
        return out
    return facts_part()
```

- [ ] **Step 4: Run the tests**

Run: `cd /home/grantkim725/data/docker/risuaiNode/NMOS-p53/apps/sidecar && uv run pytest tests/test_divergence.py -q`
Expected: 17 passed. If the secret test does not trip `leaks` (its trigram bar), make the leaked `now` repeat the
secret's content more closely (`"royal guard traitor"` word for word) rather than loosening the code: the test is that a
held reply is asked again, then falls back.

- [ ] **Step 5: Commit**

```bash
W=/home/grantkim725/data/docker/risuaiNode/NMOS-p53
[ "$(git -C $W branch --show-current)" = docs/phase53-diverged-from-setting ] && git -C $W commit -am "feat(sidecar): one checked model call for what diverged from the setting, Phase 50's lines as the fallback (PHASE-53 S4-S6)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 5: The note places it first

**Files:**
- Modify: `apps/sidecar/src/nmos_sidecar/notes.py:24-46`, `:291-342`
- Test: `apps/sidecar/tests/test_notes.py:267-290`

- [ ] **Step 1: Update the tests first**

In `test_ask_refuses_what_it_does_not_know_and_keeps_the_notes_order`, add after the existing assert:

```python
    assert notes.Ask.of({"sections": ["address", "diverged", "changed"]}).sections == ("diverged", "address")
```

In `test_the_note_is_one_block_of_the_parts_that_have_something_to_say`, the header gains a line: replace the
expected header lines with

```python
                           "# Story memory (NMOS, as of turn 12)\n"
                           "What the story has established so far. The latest messages take precedence over it.\n"
                           "The character card and lorebook were written before the story began: where they disagree"
                           " with this note, this note is true now.\n\n"
```

and add a new test below it:

```python
def test_diverged_comes_first_and_falls_back_to_what_changed():
    notes.clear_cache()
    hist = [canon_entry("Hana", "located_in", obj="harbor town")]
    view = {"facts": [fact("Hana", "located_in", obj="old mill", turn=7, history=hist)], "threads": [], "secrets": [],
            "entities": []}
    out = notes.make(notes.Ask.of({"sections": ["address", "diverged"]}), view, told(), 12, None, "2026-11-01",
                     canon=[])
    assert [s["kind"] for s in out["sections"]] == ["diverged", "address"]
    assert out["sections"][0]["made"] == "facts" and out["sections"][0]["lines"] == 1
    assert "## Diverged from the setting\n- Hana — location: was harbor town → now old mill (t7)" in out["text"]
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd /home/grantkim725/data/docker/risuaiNode/NMOS-p53/apps/sidecar && uv run pytest tests/test_notes.py -q -k "ask_refuses or one_block or diverged_comes"`
Expected: FAIL (3) — `ValueError: sections must be some of chronicle, changed, address` and the header mismatch.

- [ ] **Step 3: Change `notes.py`**

Imports (with the other `from .` lines):

```python
from . import divergence
```

Replace `KINDS` and `HEADER`:

```python
KINDS = ("diverged", "chronicle", "changed", "address")  # the parts the owner can pick, in the note's order
```

```python
HEADER = ("# Story memory (NMOS, as of turn {turn})\n"
          "What the story has established so far. The latest messages take precedence over it.\n"
          "The character card and lorebook were written before the story began: where they disagree with this note,"
          " this note is true now.")
```

`clear_cache` also clears the part's cache:

```python
def clear_cache() -> None:
    with _CACHE_LOCK:
        _CACHE.clear()
    divergence.clear_cache()
```

In `Ask.of`, after `sections = tuple(dict.fromkeys(body.get("sections") or ()))` and its check, drop `changed` when
`diverged` is asked (its fallback is the same lines; an older plugin still asks for `changed` alone):

```python
        if "diverged" in sections:
            sections = tuple(s for s in sections if s != "changed")
```

In `make`, add the `canon` parameter and the part (before the `chronicle` branch):

```python
def make(ask: Ask, view: dict[str, Any], told: dict[str, Any] | None, last_turn: int | None,
         model: Callable[..., tuple[Any, ...]] | None, today: str,
         canon: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """The note: one block holding every part asked for that has something to say, and what each part was made of.
    `canon` is the manifest in force with its texts (`canon.manifest`), which only the diverged part reads."""
    facts = view.get("facts") or []
    parts: list[str] = []
    info = []
    for kind in ask.sections:
        if kind == "diverged":
            d = divergence.diverged(canon or [], view.get("entities") or [],
                                    [f for f in facts if ask.secrets or not kept(f)], told,
                                    [s for s in view.get("secrets") or [] if s.get("open")], last_turn,
                                    model if ask.model else None, ask.secrets, changed_lines(facts, ask.secrets),
                                    frozenset(view.get("excluded") or ()))
            body = d["body"]
            info.append({"kind": kind, **{k: d[k] for k in ("made", "cached", "held", "reason", "turns", "lines",
                                                            "entries", "left_out", "dropped")}, "chars": len(body)})
        elif kind == "chronicle":
```

(the rest of the loop is unchanged; the old `if kind == "chronicle":` becomes `elif`).

Update the module docstring's first paragraph to name the new first part: "…and holds up to four parts the owner picks:
what diverged from the setting (PHASE-53: one checked model call, Phase 50's changed lines as its fallback), the
chronicle…".

- [ ] **Step 4: Run the notes and divergence tests**

Run: `cd /home/grantkim725/data/docker/risuaiNode/NMOS-p53/apps/sidecar && uv run pytest tests/test_notes.py tests/test_divergence.py -q`
Expected: all pass. Any other test of the old header text (`git grep -n "take precedence over it" apps/sidecar/tests`)
gets the third line too.

- [ ] **Step 5: Commit**

```bash
W=/home/grantkim725/data/docker/risuaiNode/NMOS-p53
[ "$(git -C $W branch --show-current)" = docs/phase53-diverged-from-setting ] && git -C $W commit -am "feat(sidecar): the note's first part is what diverged from the setting; the header says the setting is older (PHASE-53 S1, S7)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 6: The endpoint reads the manifest

**Files:**
- Modify: `apps/sidecar/src/nmos_sidecar/api.py:1130-1151`
- Test: `apps/sidecar/tests/test_notes.py` (after `test_the_endpoint_lists_what_the_story_changed_of_the_card`)

- [ ] **Step 1: Write the failing endpoint test**

```python
def test_the_endpoint_compares_the_setting_with_the_story(migrated, monkeypatch):
    import re

    asked: list[str] = []

    class Fake:
        def __init__(self, *args, **kwargs):
            pass

        def complete_metered(self, system, user):
            asked.append(user)
            turn = int(re.search(r"\[t(\d+)\] Hana located in old mill", user)[1])
            return {"diverged": [{"key": "card:desc", "quote": "Hana is in the harbor town", "subject": "Hana",
                                  "now": "in the old mill", "turns": [turn], "kind": "world"}]}, "{}", None

    monkeypatch.setattr(notes, "ChatModel", Fake)
    notes.clear_cache()
    chat, model = story(), Model()
    with make_client(migrated, **LLM) as c:
        sync(c, chat)
        push(c, chat, canon_texts())
        drain(migrated, model)
        cid = canon_view(migrated, chat)["conversation"]
        out = c.post(f"/v1/conversations/{cid}/notes", json={"sections": ["diverged"]}).json()
    assert len(asked) == 1 and "[key: card:desc · card]\nHana is a lighthouse keeper." in asked[0]
    assert "lore:mira" not in asked[0]  # Mira is in no story fact or scene
    part = out["sections"][0]
    assert part["kind"] == "diverged" and part["made"] == "model" and part["lines"] == 1
    assert '- Hana (card): the setting says "Hana is in the harbor town" → now in the old mill (t' in out["text"]
```

- [ ] **Step 2: Run it to see it fail**

Run: `cd /home/grantkim725/data/docker/risuaiNode/NMOS-p53/apps/sidecar && uv run pytest tests/test_notes.py -q -k compares_the_setting`
Expected: FAIL — the part is made as `facts` (no model, no manifest passed). Needs Postgres on :5436; with it down the test
is skipped, so check `docker ps | grep 5436` first.

- [ ] **Step 3: Change the endpoint**

In `author_notes`, replace from `key = rt.get("active_summarizer")` to `out = notes.make(...)`:

```python
            key = rt.get("active_summarizer")
            calls = {"chronicle", "diverged"} & set(ask.sections)  # the parts that read summaries and call a model
            told = summaries.current(conn, conv_id, head, key) if key and calls else None
            manifest = canon.manifest(conn, conv_id) if "diverged" in ask.sections else None
        model = notes.model_for(rt["settings"]) if ask.model and calls else None
        out = notes.make(ask, view, told, last, model, date.today().isoformat(), canon=manifest)
```

and the docstring's last sentence: "Only the chronicle and what diverged from the setting call a model, after the
database connection is back."

- [ ] **Step 4: Run the notes tests**

Run: `cd /home/grantkim725/data/docker/risuaiNode/NMOS-p53/apps/sidecar && NMOS_TEST_REQUIRE_DB=1 uv run pytest tests/test_notes.py tests/test_divergence.py -q`
Expected: all pass. If the canon facts' story turn of "Hana is in the old mill." differs, the regex in `Fake` finds
it; if the card text in the prompt differs (macro filled), match the test's string to `canonfacts.named` output.

- [ ] **Step 5: Run the whole sidecar suite**

Run: `cd /home/grantkim725/data/docker/risuaiNode/NMOS-p53/apps/sidecar && NMOS_TEST_REQUIRE_DB=1 uv run pytest -q -x -p no:cacheprovider`
Expected: all pass (about 1,600 tests; it takes a few minutes, run in the background).

- [ ] **Step 6: Commit**

```bash
W=/home/grantkim725/data/docker/risuaiNode/NMOS-p53
[ "$(git -C $W branch --show-current)" = docs/phase53-diverged-from-setting ] && git -C $W commit -am "feat(sidecar): the notes endpoint gives the part the manifest in force (PHASE-53 S3)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 7: The plugin's toggle and texts

**Files:**
- Modify: `adapters/pocketrisu-plugin/src/ui.ts:1315-1345`, `src/i18n.ts:170-200`
- Test: `adapters/pocketrisu-plugin/test/dom.test.ts:545-560`, `test/views.test.ts:148-151`

- [ ] **Step 1: Update the tests first**

`views.test.ts` line 150:

```ts
      .toEqual(['diverged', 'chronicle', 'address']);
```

`dom.test.ts`, in `makes one note for the author's note…`:

```ts
    expect(boxes.map((b) => [b.value, b.checked])).toEqual([['diverged', true], ['chronicle', false], ['address', false]]);
    boxes[2]!.click(); // and "address"
    button('Make').click();
    await settle();
    expect(posts(calls).at(-1)).toEqual(['POST', `/v1/conversations/${id}/notes`,
      { sections: ['diverged', 'address'], chars: 3000, secrets: false }]);
```

and in its stub reply (line ~506) replace the `changed` part with
`{ kind: 'diverged', made: 'model', cached: false, held: 0, reason: '', entries: 3, left_out: 1 }`, then expect

```ts
    expect(panel().textContent).toContain('diverged from the setting: written by the model');
    expect(panel().textContent).toContain('3 lorebook entries compared, 1 left out for length');
```

(keep the chronicle and address expectations).

- [ ] **Step 2: Run them to see them fail**

Run: `cd /home/grantkim725/data/docker/risuaiNode/NMOS-p53/adapters/pocketrisu-plugin && npx vitest run test/dom.test.ts test/views.test.ts`
Expected: FAIL — the boxes are `chronicle, changed, address`, all checked.

- [ ] **Step 3: Change `i18n.ts` and `ui.ts`**

`i18n.ts`, next to the other `notes.part.*` keys:

```ts
  'notes.part.diverged': ['설정과 달라진 것', 'diverged from the setting'],
```

next to `notes.chronicle`:

```ts
  'notes.diverged': ['설정과 달라진 것: 카드·로어북과 지금 이야기가 어긋난 곳 (모델 1회 호출)', 'Diverged from the setting: where the story no longer fits the card or lorebook (one model call)'],
  'notes.entries': ['로어북 {n}개 항목과 비교, {m}개는 길이 상한으로 제외', '{n} lorebook entries compared, {m} left out for length'],
```

and `notes.sub` gains one sentence at its end, Korean then English:
`' 설정과 달라진 것과 연대기는 만들 때마다 모델을 한 번씩 부릅니다.'` /
`' Diverged from the setting and the chronicle each call the model once when made.'`

`ui.ts`, `buildNotes`: `pick` takes whether it starts checked, and the parts change:

```ts
    const pick = (key: StringKey, kind: string, on: boolean) => {
      const box = el('input', { type: 'checkbox', value: kind });
      box.checked = on;
      return { box, row: el('div', { class: 'check' }, box, el('span', { text: L(key) })) };
    };
    // PHASE-53: what diverged from the setting first and on; the chronicle and address stay, off by default.
    const kinds = [pick('notes.diverged', 'diverged', true), pick('notes.chronicle', 'chronicle', false),
      pick('notes.address', 'address', false)];
```

the request's timeout covers two parts that call a model, each with a retry:

```ts
          { sections, chars: Number(length.value), secrets: secrets.checked }, 600_000); // two calls, each with a retry
```

`NotePart` gains the part's counts:

```ts
  interface NotePart { kind: string; made: string; cached: boolean; held: number; reason: string; stale?: number; entries?: number; left_out?: number }
```

and `noteResult`'s `how`, before `return L('notes.part_made', …)`:

```ts
      if (p.kind === 'diverged' && p.entries !== undefined) bits.push(L('notes.entries', { n: p.entries, m: p.left_out ?? 0 }));
```

- [ ] **Step 4: Run the plugin's checks and build**

Run: `cd /home/grantkim725/data/docker/risuaiNode/NMOS-p53/adapters/pocketrisu-plugin && npm test && npm run typecheck && npm run build`
Expected: all tests pass, no type errors, `dist/nmos-pocketrisu.js` rebuilt. `notes.changed` is no longer shown by
the form; if a test reports an unused string key, delete it (keep `notes.part.changed`: an older sidecar's reply or a
request for `changed` alone still names it). Do not change the plugin's `//@version`
(`nmos-plugin-channels-hold`: bumped only at releases). If `node_modules` is missing in the worktree, run `npm ci`
there; never symlink the main checkout's (`nmos-phase9-branch`).

- [ ] **Step 5: Commit**

```bash
W=/home/grantkim725/data/docker/risuaiNode/NMOS-p53
[ "$(git -C $W branch --show-current)" = docs/phase53-diverged-from-setting ] && git -C $W add -A adapters/pocketrisu-plugin && git -C $W commit -m "feat(plugin): diverged from the setting first and on, chronicle and address off (PHASE-53 S1)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 8: Review, spec evidence, PR

- [ ] **Step 1: Peer review** — invoke the project `peer-review` skill on the diff against `origin/main`. High risk
  (AGENTS §14: canon/provenance, secrets, a model claim in every prompt). Fix what it finds, re-run the touched tests.
- [ ] **Step 2: Spec** — in `docs/phases/PHASE-53.md`: the S7 example line becomes the chronicle's turn style
  (`(t42–44)`); add `## Steps 2–4 evidence (date)` with the files, the test counts, the plugin build hash, the review's
  fixes. Commit `docs(phase53): steps 2-4 evidence`.
- [ ] **Step 3: Push and open the PR** (ask the owner first): title `Phase 53: the author's note says where the story
  left the setting`, body with "Part of" no Linear key unless the owner gives one, **High risk** marked, the test
  evidence, and the attribution line. Read Copilot's review when it comes (`nmos-read-copilot-reviews`); one
  `gh pr checks` for CI (`nmos-pr-bind-unavailable`).

### Task 9: Measurement (Q2, zero cost) and the trials

Outside the repository, in `~/nmos-eval/phase53/`. Never the production database (`nmos-prod-db-hands-off`), never a
paid endpoint (`nmos-api-spend`).

- [ ] **Step 1: Copies** — restore each test install chat database into a throwaway DB on test PG :5436
  (`createdb -h 127.0.0.1 -p 5436 nmos_p53_<n>` + `pg_restore`), and before any sidecar runs against a copy rewrite its
  `app_config` llm/embed rows to the local eval Ollama (`restored-copy-app-config`); check the first POST goes to
  127.0.0.1:11500.
- [ ] **Step 2: Zero-call check** — a script that, per chat copy, calls `divergence.story_input` and
  `divergence.canon_input` on the head's view and manifest and prints only counts: facts and scenes given, lorebook
  candidates, entries given, left out, total characters. Report the owner-named divergences' entries as in or out by
  role, not text.
- [ ] **Step 3: Local model** — run the sidecar on a copy against eval Ollama :11500 and make the note per chat; keep
  each reply, the dropped count and the lines; the owner reads the lines.
- [ ] **Step 4: Test install** — after the owner's go, the build on 6131/6113 (backup first, as Phase 50 did); the
  owner pastes and tries it.
- [ ] **Step 5: Second trial** — the same build on the install the owner uses, only when the owner says; no read of
  that database by the agent; the owner reports.
