# Phase 50 — Notes for the author's note: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On the owner's request, the sidecar writes three paste-ready sections for a chat's author's note (a
chronicle, what changed from the setting, address and standing), each between NMOS markers that canon never reads.

**Architecture:** A pure module `notes.py` builds the sections from what is already read: `facts.memory_view` (facts
with their `history`, threads, secrets) and `summaries.current` (scene summaries and the story so far). Only the
chronicle calls a model (the extraction model, one call, an in-process cache, a leak check at `LEAK_NEAR` and an
assembled fallback). `POST /v1/conversations/{id}/notes` returns the texts as JSON; the plugin panel shows them with a
Copy button. The marker is removed from the note before the canon hash (plugin) and before a canon read (sidecar).

**Tech Stack:** Python 3.12 / FastAPI / psycopg (sidecar, pytest against the compose Postgres on :5436);
TypeScript / Vitest (plugin).

Spec: `docs/phases/PHASE-50.md`. Paths as of `main` `6d593d4`.

---

## File structure

| File | What changes |
| --- | --- |
| `apps/sidecar/src/nmos_sidecar/notes.py` | **new**: markers (`strip_blocks`, `wrap`), the two fact sections, the chronicle (input, prompt, model call, check, fallback, cache), `Ask`, `make` |
| `apps/sidecar/src/nmos_sidecar/canonfacts.py` | `process`: a `note` text loses its marked blocks before it is read |
| `apps/sidecar/src/nmos_sidecar/api.py` | `POST /v1/conversations/{conv_id}/notes` |
| `apps/sidecar/src/nmos_sidecar/inspector.py` | the canon section says which NMOS blocks the note carries and how far they reach |
| `fixtures/unit/note-blocks-v1.json` | **new**: marker cases both languages check |
| `apps/sidecar/tests/test_notes.py` | **new**: unit + API tests |
| `adapters/pocketrisu-plugin/src/notes.ts` | **new**: `stripNoteBlocks` (the same regex) |
| `adapters/pocketrisu-plugin/src/canon.ts` | the note is added without its blocks, the blocks in its metadata |
| `adapters/pocketrisu-plugin/src/ui.ts`, `i18n.ts` | the button, the form, the result card with Copy |
| `adapters/pocketrisu-plugin/test/notes.test.ts` | **new** |
| `adapters/pocketrisu-plugin/dist/*` | rebuilt |
| `docs/phases/PHASE-50.md` | amendment (task 0) and evidence |

---

### Task 0: Spec amendment (what reading the code changed)

**Files:** Modify `docs/phases/PHASE-50.md`

- [ ] **Step 1:** Amend, with a dated note "Amendment 1 (2026-10-23, from the code, before step 2)":
  - S2: the **Open threads** part is rendered from the stored threads, not written by the model; the model writes
    Events and Now (JSON `{"events": "...", "now": "..."}`), told each thread's stored state and outcome. This replaces
    the thread-state check (a deterministic part cannot be wrong). Status-window values are left out of the input
    (the cast's `located_in`/`has_status` facts give "Now").
  - S6: the panel cannot run a page's scripts (it inserts the Inspector's HTML as a fragment, H15), so the panel itself
    shows the texts the API returns, each in a read-only box with Copy; there is no `/inspector/c/{id}/notes` page. The
    Inspector's canon section shows the note's NMOS blocks and how far they reach.
  - S7: no 409; a section with nothing to say comes back empty with its reason (`no_scenes`, `none`).
- [ ] **Step 2:** Commit `docs(phase-50): amendment 1 — open threads from the store, the panel shows the texts`.

---

### Task 1: Markers (`strip_blocks`, `wrap`) and the shared fixture

**Files:** Create `fixtures/unit/note-blocks-v1.json`, `apps/sidecar/src/nmos_sidecar/notes.py`,
`apps/sidecar/tests/test_notes.py`

- [ ] **Step 1: The fixture** (both languages read it):

```json
{
  "version": 1,
  "cases": [
    {"name": "no block", "note": "지금은 한겨울 밤이다.", "text": "지금은 한겨울 밤이다.", "blocks": []},
    {"name": "one block after the owner's text",
     "note": "지금은 한겨울 밤이다.\n\n[NMOS 연대기 · t0–87 · 2026-10-23]\n## 사건\n- 하나가 등대에 갔다.\n[/NMOS 연대기]\n",
     "text": "지금은 한겨울 밤이다.", "blocks": [{"kind": "chronicle", "turns": "0-87"}]},
    {"name": "two blocks, English, text between",
     "note": "[NMOS changed · t120 · 2026-10-23]\n- a\n[/NMOS changed]\nKeep this.\n[NMOS address · t120 · 2026-10-23]\n- b\n[/NMOS address]",
     "text": "Keep this.", "blocks": [{"kind": "changed", "turns": "120"}, {"kind": "address", "turns": "120"}]},
    {"name": "an unclosed marker stays", "note": "[NMOS 연대기 · t0–3 · 2026-10-23]\n열린 채로", "text": "[NMOS 연대기 · t0–3 · 2026-10-23]\n열린 채로", "blocks": []},
    {"name": "only a block", "note": "[NMOS 호칭·관계 · t5 · 2026-10-23]\n- x\n[/NMOS 호칭·관계]", "text": "", "blocks": [{"kind": "address", "turns": "5"}]}
  ]
}
```

- [ ] **Step 2: Failing test** in `tests/test_notes.py`:

```python
"""PHASE-50: notes for the author's note — markers, the fact sections, the chronicle, the API."""

from __future__ import annotations

import json
from pathlib import Path

from nmos_sidecar import notes

BLOCKS = Path(__file__).resolve().parents[3] / "fixtures/unit/note-blocks-v1.json"


def test_blocks_are_the_plugins():
    for case in json.loads(BLOCKS.read_text(encoding="utf-8"))["cases"]:
        assert notes.strip_blocks(case["note"]) == (case["text"], case["blocks"]), case["name"]


def test_a_note_without_a_block_comes_back_as_it_was():
    note = "  앞뒤 공백도\n\n\n그대로  "
    assert notes.strip_blocks(note) == (note, [])


def test_wrap_writes_what_strip_removes():
    text = notes.wrap("chronicle", "## 사건\n- 하나", "0-87", "ko", "2026-10-23")
    assert text.splitlines()[0] == "[NMOS 연대기 · t0–87 · 2026-10-23]" and text.endswith("[/NMOS 연대기]")
    assert notes.strip_blocks("메모\n\n" + text) == ("메모", [{"kind": "chronicle", "turns": "0-87"}])
    assert notes.wrap("address", "- x", "5", "en", "2026-10-23").splitlines()[0] == "[NMOS address · t5 · 2026-10-23]"
```

- [ ] **Step 3:** Run `cd apps/sidecar && uv run pytest tests/test_notes.py -q` → FAIL (`nmos_sidecar.notes` missing).
- [ ] **Step 4: Implement** the head of `notes.py`:

```python
"""Notes for the author's note (PHASE-50): sections the owner pastes into a chat's author's note, made on request.

Three kinds: the chronicle (the story's events, how they went and ended, from the scene summaries and the threads; one
model call, with an assembled fallback), what changed from the setting (canon values a story fact now supersedes) and
address and standing (each pair's relationship, role, feeling and form of address). Each is written between two marker
lines. The author's note is canon (ADR 0045), so the canon never reads a marked block: the plugin removes them before
the hash, and `canonfacts.process` again before a read (an older plugin sends them whole).
"""

from __future__ import annotations

import re
from typing import Any

KINDS = ("chronicle", "changed", "address")
LABELS = {"chronicle": ("연대기", "chronicle"), "changed": ("설정 변경점", "changed"), "address": ("호칭·관계", "address")}
_BY_LABEL = {label: kind for kind, pair in LABELS.items() for label in pair}
_LABEL = "|".join(re.escape(label) for label in _BY_LABEL)
# `[NMOS <label> · t<first>[–<last>] · <date>]` … `[/NMOS <label>]`, the closing label the opening one.
BLOCK = re.compile(r"\[NMOS (" + _LABEL + r")(?: · t(\d+)(?:–(\d+))?)?(?: · [^\]\n]*)?\]\n?[\s\S]*?\[/NMOS \1\]\n?")


def strip_blocks(text: str) -> tuple[str, list[dict[str, str]]]:
    """The note without NMOS's blocks, and each block's kind and turns ("0-87", "120"). A note without one comes back
    exactly as it was; an unclosed marker is not a block."""
    blocks = [{"kind": _BY_LABEL[m[1]], "turns": m[2] + (f"-{m[3]}" if m[3] else "") if m[2] else ""}
              for m in BLOCK.finditer(text)]
    if not blocks:
        return text, []
    rest = re.sub(r"\n{3,}", "\n\n", BLOCK.sub("\n\n", text)).strip()
    return rest, blocks


def wrap(kind: str, body: str, turns: str, lang: str, today: str) -> str:
    """A section between its markers (`turns`: "0-87" or "120")."""
    label = LABELS[kind][lang == "en"]
    return f"[NMOS {label} · t{turns.replace('-', '–')} · {today}]\n{body.strip()}\n[/NMOS {label}]"
```

- [ ] **Step 5:** Run the test → PASS.
- [ ] **Step 6:** Commit `feat(notes): NMOS note blocks — strip and wrap, a fixture both sides check (PHASE-50)`.

---

### Task 2: Canon never reads a marked block (sidecar guard)

**Files:** Modify `apps/sidecar/src/nmos_sidecar/canonfacts.py` (`process`, the line `text = named(...)`);
Test `apps/sidecar/tests/test_notes.py`

- [ ] **Step 1: Failing test** (an older plugin sends the note whole):

```python
import psycopg
from psycopg.rows import dict_row

from conftest import make_client
from test_canon_facts import Model, canon_texts, drain, story
from test_canon import push
from test_generations import LLM
from test_sidecar_integration import sync

NOTE = "Hana is in the harbor town.\n\n[NMOS 연대기 · t0–1 · 2026-10-23]\nHana is a smuggler.\n[/NMOS 연대기]"


def test_canon_does_not_read_a_marked_block(migrated):
    chat, model = story(), Model()
    with make_client(migrated, **LLM) as c:
        sync(c, chat)
        push(c, chat, {**canon_texts(), "note": (NOTE, {})})
        drain(migrated, model)
    note = next(u for u in model.canon_calls() if "author's note" in u)
    assert "Hana is in the harbor town." in note and "smuggler" not in note and "NMOS" not in note
```

- [ ] **Step 2:** Run → FAIL (`smuggler` in the note's prompt).
- [ ] **Step 3: Implement** in `canonfacts.process`, right after `text = named(...)`:

```python
    if src["key"] == "note":  # NMOS's own blocks are not canon (PHASE-50 S5): an older plugin sends them whole
        text = notes.strip_blocks(text)[0]
```

and `from . import generations, normtext, notes` in the imports.

- [ ] **Step 4:** Run `uv run pytest tests/test_notes.py tests/test_canon_facts.py -q` → PASS.
- [ ] **Step 5:** Commit `fix(canon): the author's note is read without NMOS's blocks (PHASE-50 S5)`.

---

### Task 3: The two fact sections

**Files:** Modify `notes.py`; Test `tests/test_notes.py`

- [ ] **Step 1: Failing tests** (synthetic facts shaped as `memory_view` makes them):

```python
def fact(subject, predicate, *, obj=None, value=None, turn=5, history=(), knowledge=None, hidden_from=None, **kw):
    return {"subject": subject, "predicate": predicate, "object": obj, "value": value, "turn": turn, "position": turn,
            "polarity": "positive", "history": list(history), "knowledge": knowledge, "hidden_from": hidden_from,
            "claims": [], **kw}


def canon_entry(subject, predicate, *, obj=None, value=None, outcome="superseded"):
    return {"subject": subject, "predicate": predicate, "object": obj, "value": value, "polarity": "positive",
            "turn": -1, "position": -1, "outcome": outcome, "canon": "card:desc"}


def test_changed_lists_a_canon_value_the_story_replaced_and_nothing_else():
    moved = fact("Hana", "located_in", obj="old mill", turn=1,
                 history=[canon_entry("Hana", "located_in", obj="harbor town"), {"outcome": "current"}])
    same = fact("Hana", "relationship", obj="Kaito", value="sister", turn=-1, canon="card:desc")
    trait = fact("Hana", "has_trait", value="stubborn", history=[canon_entry("Hana", "has_trait", value="shy")])
    lines = notes.changed_lines([moved, same, trait], "ko")
    assert lines == ["- Hana 위치: 설정 harbor town → 지금 old mill (t1)"]


def test_changed_leaves_out_what_is_kept_from_someone_unless_asked():
    who = fact("Hana", "identity", value="smuggler", knowledge="limited", hidden_from=["Kaito"],
               history=[canon_entry("Hana", "identity", value="lighthouse keeper")])
    assert notes.changed_lines([who], "ko") == []
    assert notes.changed_lines([who], "ko", secrets=True) == [
        "- Hana 정체: 설정 lighthouse keeper → 지금 smuggler (t5) (비밀: Kaito는 모름)"]


def test_an_items_holder_is_a_change_of_who_holds_it():
    held = fact("Kaito", "possesses", obj="map", history=[canon_entry("Hana", "possesses", obj="map")])
    assert notes.changed_lines([held], "en") == ["- map held by: setting Hana → now Kaito (t5)"]


def test_address_gives_one_line_per_pair():
    rel = fact("Hana", "relationship", obj="Kaito", value="childhood friend")
    calls = fact("Kaito", "addresses", obj="Hana", value="누나")
    feels = fact("Hana", "feels_toward", obj="Kaito", value="trust", knowledge="limited", hidden_from=["Kaito"])
    assert notes.address_lines([rel, calls, feels], "ko") == [
        "- Hana ↔ Kaito: 관계 childhood friend · Kaito→Hana 호칭 \"누나\""]
```

- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3: Implement** in `notes.py`:

```python
from .facts import HOLDER_PER_ITEM, symmetric
from .inspector import _named, pairs
from .predicates import REGISTRY

PAIRS_MAX = 30  # address lines at most
# A canon value a story fact can replace: single-valued predicates and an item's holder (PHASE-50 S3). A multi-valued
# one accumulates, so NMOS cannot tell a change from an addition there.
CHANGEABLE = frozenset(p for p, d in REGISTRY.items() if d.cardinality == "single") | HOLDER_PER_ITEM
WORDS = {
    "ko": {"located_in": "위치", "has_status": "상태", "identity": "정체", "relationship": "관계", "role_toward": "역할",
           "feels_toward": "감정", "addresses": "호칭", "possesses": "소지자", "destroyed": "소멸",
           "setting": "설정", "now": "지금", "not": "아님", "secret": "비밀: {who}는 모름", "fixed": "직접 고침"},
    "en": {"located_in": "location", "has_status": "status", "identity": "identity", "relationship": "relationship",
           "role_toward": "role", "feels_toward": "feeling", "addresses": "calls", "possesses": "held by",
           "destroyed": "destroyed", "setting": "setting", "now": "now", "not": "not",
           "secret": "secret: {who} does not know", "fixed": "fixed by the owner"},
}


def _w(lang: str, key: str) -> str:
    return WORDS["en" if lang == "en" else "ko"].get(key, key.replace("_", " "))


def kept(f: dict[str, Any]) -> bool:
    """Kept from someone: the note reaches every scene, so any limited fact counts (PHASE-50 S4)."""
    return f.get("knowledge") == "limited" or bool(f.get("hidden_from"))


def _secret_mark(f: dict[str, Any], lang: str) -> str:
    who = ", ".join(f.get("hidden_from") or []) or "?"
    return f" ({_w(lang, 'secret').format(who=who)})"


def _said(e: dict[str, Any], lang: str) -> str:
    """What a statement says in its slot: an item's holder, else its value or object."""
    said = e.get("subject") if e["predicate"] in HOLDER_PER_ITEM else (e.get("value") or e.get("object") or "")
    return f"{_w(lang, 'not')} {said}" if e.get("polarity") == "negative" else str(said)


def _head(f: dict[str, Any], lang: str) -> str:
    if f["predicate"] in HOLDER_PER_ITEM:
        return f"{f.get('object')} {_w(lang, f['predicate'])}"
    if f["predicate"] in ("relationship", "role_toward", "feels_toward", "addresses") and f.get("object"):
        return f"{_named(f, 'subject')} → {_named(f, 'object')} {_w(lang, f['predicate'])}"
    return f"{_named(f, 'subject')} {_w(lang, f['predicate'])}"


def changed_lines(facts: list[dict[str, Any]], lang: str, secrets: bool = False) -> list[str]:
    """Each canon value a current story fact replaced or ended (its history's canon entry), newest first."""
    out: list[str] = []
    seen: set[tuple] = set()
    for f in facts:
        if f.get("canon") or f["predicate"] not in CHANGEABLE or (kept(f) and not secrets):
            continue
        for h in f.get("history") or ():
            if not h.get("canon") or h.get("outcome") not in ("superseded", "ended") or (kept(h) and not secrets):
                continue
            old, new = _said(h, lang), _said(f, lang)
            key = (f["predicate"], h.get("subject"), h.get("object"), old, new)
            if old == new or key in seen:
                continue
            seen.add(key)
            line = (f"- {_head(f, lang)}: {_w(lang, 'setting')} {old} → {_w(lang, 'now')} {new} (t{f.get('turn')})")
            if f.get("repair"):
                line += f" ({_w(lang, 'fixed')})"
            out.append(line + (_secret_mark(f, lang) if kept(f) else ""))
    return out


def address_lines(facts: list[dict[str, Any]], lang: str, secrets: bool = False) -> list[str]:
    """One line per pair (`inspector.pairs`): relationship, then each direction's role, feeling and form of address."""
    shown = [f for f in facts if secrets or not kept(f)]
    out = []
    for p in pairs(shown)[:PAIRS_MAX]:
        bits = []
        for f in p["relationship"]:
            who = "" if symmetric(f.get("value")) and len(p["relationship"]) == 1 else \
                f"{_named(f, 'subject')}→{_named(f, 'object')} "
            bits.append(f"{who}{_w(lang, 'relationship')} {f.get('value')}")
        for k, pred in (("role", "role_toward"), ("feels", "feels_toward"), ("speech", "addresses")):
            for f in p[k]:
                value = f'"{f.get("value")}"' if pred == "addresses" else f.get("value")
                bits.append(f"{_named(f, 'subject')}→{_named(f, 'object')} {_w(lang, pred)} {value}"
                            + (_secret_mark(f, lang) if kept(f) else ""))
        if bits:
            out.append(f"- {' ↔ '.join(sorted(p['names'].values()))}: " + " · ".join(bits))
    return out
```

- [ ] **Step 4:** Run → PASS. If `symmetric("childhood friend")` is False, the expected line in the address test
  becomes `Hana→Kaito 관계 childhood friend`: fix the test's expectation to what `facts.symmetric` says, not the code.
- [ ] **Step 5:** Commit `feat(notes): what changed from the setting, address and standing (PHASE-50 S3)`.

---

### Task 4: The chronicle

**Files:** Modify `notes.py`; Test `tests/test_notes.py`

- [ ] **Step 1: Failing tests**:

```python
def scene(first, last, text, sid=None):
    return {"window": type("W", (), {"first_turn": first, "last_turn": last})(),
            "summary": {"id": sid or f"s{first}", "first_turn": first, "last_turn": last, "text": text}}


def told(*scenes_, story=None):
    return {"scenes": list(scenes_), "story": story}


THREADS = [
    {"kind": "promise", "by": "Hana", "to": "Kaito", "text": "meet at the lighthouse", "turn": 3, "status": "open",
     "closed_by": None, "knowledge": None, "hidden_from": None},
    {"kind": "goal", "by": "Hana", "to": None, "text": "find the bell", "turn": 1, "status": "achieved",
     "closed_by": {"turn": 9}, "knowledge": None, "hidden_from": None},
]
SECRET = {"open": ["Kaito"], "holders": ["Hana"], "text": "Hana identity: smuggler", "turn": 2, "position": 2}


def test_assembled_without_a_model_open_threads_from_the_store():
    out = notes.chronicle(told(scene(0, 7, "Hana went to the mill."), scene(8, 15, "Hana found the bell.")),
                          THREADS, [], [], 3000, "ko", model=None)
    assert out["made"] == "assembled" and out["turns"] == "0-15"
    assert "## 열린 일\n- Hana → Kaito: meet at the lighthouse (약속, t3부터)" in out["body"]
    assert "Hana: find the bell → achieved (t9)" in out["body"] and "Hana found the bell." in out["body"]


def test_a_scene_that_tells_a_kept_secret_is_left_out():
    out = notes.chronicle(told(scene(0, 7, "Hana is a smuggler, she told no one.")), [], [], [SECRET], 3000, "ko",
                          model=None)
    assert "smuggler" not in out["body"] and out["held"] == 1


class Writer:
    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []

    def __call__(self, system, user):
        self.calls.append(user)
        return self.replies.pop(0), "{}"


def test_the_model_writes_events_and_now_the_store_writes_open_threads():
    w = Writer({"events": "- Hana went to the mill (t0–7).", "now": "- Hana is at the mill."})
    out = notes.chronicle(told(scene(0, 7, "Hana went to the mill.")), THREADS, [], [], 3000, "ko", model=w)
    assert out["made"] == "model" and len(w.calls) == 1
    assert out["body"].startswith("## 사건\n- Hana went to the mill (t0–7).\n\n## 지금\n- Hana is at the mill.")
    assert out["body"].endswith("## 열린 일\n- Hana → Kaito: meet at the lighthouse (약속, t3부터)")
    assert "find the bell" in w.calls[0] and "achieved" in w.calls[0]


def test_a_reply_that_tells_a_secret_is_asked_again_then_assembled():
    bad = {"events": "- Hana is a smuggler.", "now": ""}
    w = Writer(bad, bad)
    out = notes.chronicle(told(scene(0, 7, "Hana walked.")), [], [], [SECRET], 3000, "ko", model=w)
    assert len(w.calls) == 2 and "smuggler" in w.calls[1]  # the retry names what it told
    assert out["made"] == "assembled" and "smuggler" not in out["body"]


def test_asked_twice_with_nothing_changed_the_model_answers_once():
    notes.clear_cache()
    w = Writer({"events": "- e", "now": "- n"})
    args = (told(scene(0, 7, "Hana walked.")), [], [], [], 3000, "ko")
    first, second = notes.chronicle(*args, model=w), notes.chronicle(*args, model=w)
    assert len(w.calls) == 1 and second["body"] == first["body"] and second["cached"] and not first["cached"]
```

- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3: Implement** in `notes.py`:

```python
import hashlib
from collections import OrderedDict
from collections.abc import Callable

from .llm import LLMError, metered
from .summaries import LEAK_NEAR, content, leaks
from .threads import KINDS as THREAD_KINDS  # noqa: F401  (kinds are named in THREAD_WORDS)

INPUT_CHARS = 40_000  # scene summaries the chronicle reads at most (PHASE-50 Q2 (a)): the newest
NOW_MAX = 30  # "now" facts in the input
CACHE_MAX = 64
_CACHE: OrderedDict[str, dict[str, Any]] = OrderedDict()
NOW_PREDICATES = frozenset({"located_in", "has_status"})
THREAD_WORDS = {"ko": {"promise": "약속", "goal": "목표", "question": "질문", "threat": "위협", "debt": "빚",
                       "since": "t{t}부터", "events": "사건", "now": "지금", "open": "열린 일"},
                "en": {"promise": "promise", "goal": "goal", "question": "question", "threat": "threat", "debt": "debt",
                       "since": "since t{t}", "events": "Events", "now": "Now", "open": "Open threads"}}

CHRONICLE_PROMPT = """You write a chronicle of a role-play chat, for its author's note: the user pastes it so that the
model writing the story keeps what happened in mind. You get SCENES (summaries in order, each with its turns), maybe
the STORY SO FAR (it covers turns before the first scene given), THREADS (promises, goals, questions, threats and
debts, each with its state and, when it ended, its outcome) and NOW (where characters are and how they are).

Write two parts in the language of the chat:
- "events": the events in order, one line each starting with "- ": how it began, how it went, and how it ended or that
  it is still open, with its turns like (t12–20). A thread is told in the state THREADS gives it: never call an open one
  ended, never give an ended one another outcome.
- "now": where things stand, one line each starting with "- ".
Together at most {chars} characters. Only what the input says: no guesses, no judgments, no out-of-character notes.

If OPEN SECRETS are listed, never write a secret's content, not even in other words or as a hint, and leave out the
object or act it is about: the note is read in every scene, in front of the characters it is kept from.{told}

Answer with JSON only: {{"events": "...", "now": "..."}}"""
SECRETS_TOLD = """
If SECRETS are listed, you may write them, each marked with who does not know it: "(○○ does not know)" in the
language of the chat."""


def clear_cache() -> None:
    _CACHE.clear()


def _tw(lang: str, key: str) -> str:
    return THREAD_WORDS["en" if lang == "en" else "ko"].get(key, key)


def _cut_lines(text: str, cap: int) -> str:
    """At most `cap` characters, at a line end when one is in the last third."""
    text = text.strip()
    if len(text) <= cap:
        return text
    head = text[:cap]
    end = head.rfind("\n")
    return head[:end].rstrip() if end >= cap * 2 // 3 else head.rstrip()


def _thread_line(t: dict[str, Any], lang: str) -> str:
    who = f"{t['by']} → {t['to']}" if t.get("to") else str(t["by"])
    if t["status"] == "open":
        return f"- {who}: {t['text']} ({_tw(lang, t['kind'])}, {_tw(lang, 'since').format(t=t.get('turn'))})"
    closed = (t.get("closed_by") or {}).get("turn")
    return f"- {who}: {t['text']} → {t['status']}" + (f" (t{closed})" if closed is not None else "")


def _input(scenes: list[dict[str, Any]], story: dict[str, Any] | None, threads: list[dict[str, Any]],
           now: list[dict[str, Any]], secrets: list[dict[str, Any]], told_secrets: bool) -> str:
    lines: list[str] = []
    if secrets:
        head = "SECRETS:" if told_secrets else "OPEN SECRETS (never write their content):"
        lines += [head] + [f"- {', '.join(s['holders'])} keep from {', '.join(s['open'])}: {content(s)}"
                           for s in secrets] + [""]
    if story is not None:
        lines += [f"STORY SO FAR (turns {story['first_turn']}–{story['last_turn']}): {story['text']}", ""]
    lines += ["SCENES:"] + [f"[turns {s['first_turn']}–{s['last_turn']}] {s['text']}" for s in scenes] + [""]
    lines += ["THREADS:"] + [_thread_line(t, "en") for t in threads] + [""]
    lines += ["NOW:"] + [f"- {f['subject']} {f['predicate'].replace('_', ' ')} {f.get('object') or f.get('value')}"
                         for f in now]
    return "\n".join(lines)


def chronicle(told: dict[str, Any] | None, threads: list[dict[str, Any]], facts: list[dict[str, Any]],
              secrets: list[dict[str, Any]], chars: int, lang: str, model: Callable[..., tuple[Any, ...]] | None,
              told_secrets: bool = False) -> dict[str, Any]:
    """The chronicle's body (without markers): Events and Now from the model, or assembled; Open threads from the
    store. Secrets off: lines kept from someone are left out of the input, scene summaries and replies that repeat a
    secret at LEAK_NEAR are held (the note is read in every scene)."""
    open_secrets = [s for s in secrets if s.get("open")]
    everyone = frozenset(n for s in open_secrets for n in s["open"])
    held = 0
    scenes: list[dict[str, Any]] = []
    for x in (told or {}).get("scenes") or []:
        row = x.get("summary")
        if row is None:
            continue
        if not told_secrets and leaks(row["text"], open_secrets, everyone):
            held += 1
            continue
        scenes.append(row)
    story = (told or {}).get("story")
    if story is not None and not told_secrets and leaks(story["text"], open_secrets, everyone):
        story, held = None, held + 1
    if not scenes:
        return {"body": "", "turns": "", "made": "none", "cached": False, "held": held, "reason": "no_scenes"}
    newest: list[dict[str, Any]] = []
    size = 0
    for row in reversed(scenes):
        size += len(row["text"]) + 20
        if size > INPUT_CHARS and newest:
            break
        newest.insert(0, row)
    story = story if story is not None and newest[0]["first_turn"] > 0 else None
    shown = [t for t in threads if told_secrets or not kept(t)]
    now = [f for f in facts if f["predicate"] in NOW_PREDICATES and not f.get("canon")
           and (told_secrets or not kept(f))][:NOW_MAX]
    turns = f"{(story or newest[0])['first_turn']}-{newest[-1]['last_turn']}"
    opened = [_thread_line(t, lang) for t in shown if t["status"] == "open"]
    tail = f"\n\n## {_tw(lang, 'open')}\n" + "\n".join(opened) if opened else ""
    budget = max(500, chars - len(tail))
    user = _input(newest, story, shown, now, open_secrets, told_secrets)
    key = hashlib.sha256(f"{lang}|{chars}|{told_secrets}|{model is not None}|{user}".encode()).hexdigest()
    if (hit := _CACHE.get(key)) is not None:
        _CACHE.move_to_end(key)
        return {**hit, "cached": True}

    def assembled() -> str:
        events = [f"- (t{r['first_turn']}–{r['last_turn']}) {r['text']}" for r in newest]
        if story is not None:
            events.insert(0, f"- (t{story['first_turn']}–{story['last_turn']}) {story['text']}")
        events += [_thread_line(t, lang) for t in shown if t["status"] != "open"]
        nows = [f"- {_head(f, lang)}: {_said(f, lang)}" for f in now]
        body = f"## {_tw(lang, 'events')}\n" + "\n".join(events)
        if nows:
            body += f"\n\n## {_tw(lang, 'now')}\n" + "\n".join(nows)
        return _cut_lines(body, budget)

    made, body = "assembled", ""
    if model is not None:
        system = CHRONICLE_PROMPT.format(chars=budget, told=SECRETS_TOLD if told_secrets else "")
        ask = user
        for _ in range(2):
            try:
                parsed, _, _ = metered(model, system, ask)
            except LLMError:
                break
            events, nows = str(parsed.get("events") or "").strip(), str(parsed.get("now") or "").strip()
            text = f"## {_tw(lang, 'events')}\n{events}" + (f"\n\n## {_tw(lang, 'now')}\n{nows}" if nows else "")
            told_now = [] if told_secrets else leaks(events + "\n" + nows, open_secrets, everyone)
            if events and not told_now:
                made, body = "model", _cut_lines(text, budget)
                break
            ask = user + "\n\nYOUR LAST ANSWER TOLD THESE SECRETS; write it again without them:\n" + "\n".join(
                f"- {content(s)}" for s in told_now)
    if not body:
        body = assembled()
    out = {"body": body + tail, "turns": turns, "made": made, "cached": False, "held": held, "reason": ""}
    _CACHE[key] = out
    while len(_CACHE) > CACHE_MAX:
        _CACHE.popitem(last=False)
    return out
```

  Note: the test helpers pass `facts=[]`; the assembled test's ended-thread line is `- Hana: find the bell → achieved (t9)`.
- [ ] **Step 4:** Run → PASS. Fix the code, not the tests, unless a test contradicts the spec.
- [ ] **Step 5:** Commit `feat(notes): the chronicle — one call, open threads from the store, held secrets, a cache (PHASE-50 S2, S4)`.

---

### Task 5: `Ask`, `make` and the endpoint

**Files:** Modify `notes.py`, `api.py`; Test `tests/test_notes.py`

- [ ] **Step 1: Failing tests**:

```python
import pytest

from nmos_sidecar import notes as notes_mod
from test_canon_facts import view as canon_view


def test_ask_refuses_what_it_does_not_know():
    for bad in ({"sections": []}, {"sections": ["poem"]}, {"sections": ["changed"], "chars": 100}):
        with pytest.raises(ValueError):
            notes.Ask.of(bad)
    assert notes.Ask.of({"sections": ["changed"]}) == notes.Ask(("changed",), 3000, False, True, "ko")


def test_the_endpoint_lists_what_the_story_changed_of_the_card(migrated):
    chat, model = story(), Model()
    with make_client(migrated, **LLM) as c:
        sync(c, chat)
        push(c, chat, canon_texts())
        drain(migrated, model)
        cid = canon_view(migrated, chat)["conversation"]
        r = c.post(f"/v1/conversations/{cid}/notes", json={"sections": ["changed", "address"], "lang": "en"})
        assert r.status_code == 200, r.text
        got = {s["kind"]: s for s in r.json()["sections"]}
    changed = got["changed"]["text"]
    assert changed.startswith("[NMOS changed · t") and changed.endswith("[/NMOS changed]")
    assert "Hana location: setting harbor town → now old mill" in changed
    assert "lighthouse keeper → now smuggler" in changed
    assert "sister" not in changed  # the story did not change it
    assert "Hana ↔ Kaito" in got["address"]["text"] and got["changed"]["made"] == "facts"


def test_the_endpoint_says_no_and_not_found(migrated):
    with make_client(migrated) as c:
        assert c.post("/v1/conversations/00000000-0000-0000-0000-000000000000/notes",
                      json={"sections": ["changed"]}).status_code == 404
        assert c.post("/v1/conversations/00000000-0000-0000-0000-000000000000/notes",
                      json={"sections": ["poem"]}).status_code == 422
```

- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3: Implement** in `notes.py`:

```python
from dataclasses import dataclass

from .config import Settings
from .llm import ChatModel


@dataclass(frozen=True)
class Ask:
    sections: tuple[str, ...]
    chars: int
    secrets: bool
    model: bool
    lang: str

    @classmethod
    def of(cls, body: dict[str, Any]) -> "Ask":
        sections = tuple(dict.fromkeys(body.get("sections") or ()))
        if not sections or any(s not in KINDS for s in sections):
            raise ValueError(f"sections must be some of {', '.join(KINDS)}")
        chars = int(body.get("chars", 3000))
        if chars not in (3000, 6000):
            raise ValueError("chars must be 3000 or 6000")
        return cls(sections, chars, bool(body.get("secrets", False)), bool(body.get("model", True)),
                   "en" if body.get("lang") == "en" else "ko")


def model_for(settings: Settings) -> Callable[..., tuple[Any, ...]] | None:
    """The extraction model (PHASE-50 Q3), or None when none is configured."""
    if not (settings.llm_url and settings.llm_model):
        return None
    return ChatModel(settings.llm_url, settings.llm_model, settings.llm_api_key, settings.llm_timeout_s,
                     settings.llm_json_mode).complete_metered


def make(ask: Ask, view: dict[str, Any], told: dict[str, Any] | None, last_turn: int | None,
         model: Callable[..., tuple[Any, ...]] | None, today: str) -> dict[str, Any]:
    """Every section asked for, each wrapped between its markers (empty when it has nothing to say)."""
    out = []
    for kind in ask.sections:
        if kind == "chronicle":
            c = chronicle(told, view.get("threads") or [], view.get("facts") or [], view.get("secrets") or [],
                          ask.chars, ask.lang, model if ask.model else None, ask.secrets)
            body, turns, made, cached, held, reason = (c["body"], c["turns"], c["made"], c["cached"], c["held"],
                                                       c["reason"])
        else:
            make_lines = changed_lines if kind == "changed" else address_lines
            lines = make_lines(view.get("facts") or [], ask.lang, ask.secrets)
            body, turns, made, cached, held = "\n".join(lines), str(last_turn or 0), "facts", False, 0
            reason = "" if lines else "none"
        out.append({"kind": kind, "text": wrap(kind, body, turns, ask.lang, today) if body else "",
                    "turns": turns, "made": made, "cached": cached, "held": held, "reason": reason,
                    "chars": len(body)})
    return {"sections": out, "last_turn": last_turn}
```

  In `api.py`, beside the other per-chat actions (after `retry-failed`), with `from . import notes` and
  `from datetime import date` added to the imports:

```python
    @app.post("/v1/conversations/{conv_id}/notes", dependencies=[Depends(auth)])
    def author_notes(conv_id: UUID, body: dict[str, Any], request: Request):
        """Sections for the chat's author's note (PHASE-50): made on request, returned for the owner to paste; nothing
        is stored and no packet reads them. Only the chronicle calls a model, outside any database connection."""
        try:
            ask = notes.Ask.of(body)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
        with request.app.state.pool.connection() as conn:
            conv = readmodel.conversation(conn, conv_id)
            if conv is None or conv["head_commit_id"] is None:
                raise HTTPException(status_code=404, detail="conversation not found")
            head = conv["head_commit_id"]
            view = view_of(conn, head)
            last = head_turn(conn, head)
            key = rt.get("active_summarizer")
            told = summaries.current(conn, conv_id, head, key) if key and "chronicle" in ask.sections else None
        model = notes.model_for(rt["settings"]) if ask.model and "chronicle" in ask.sections else None
        out = notes.make(ask, view, told, last, model, date.today().isoformat())
        log.info("author notes conversation=%s sections=%s made=%s", conv_id, ",".join(ask.sections),
                 ",".join(s["made"] for s in out["sections"]))
        return out
```

- [ ] **Step 4:** Run `uv run pytest tests/test_notes.py -q` → PASS. If the canon scenario's address pair is told
  `Hana → Kaito` (the relationship test value is "sister", which may not be symmetric), keep the assertion on the pair
  name only (`"Hana ↔ Kaito"`), as written.
- [ ] **Step 5:** Commit `feat(api): POST /v1/conversations/{id}/notes (PHASE-50 S7)`.

---

### Task 6: The Inspector says what the note carries

**Files:** Modify `inspector.py` (the canon part of `detail`); Test `tests/test_notes.py`

- [ ] **Step 1: Failing test**:

```python
from nmos_sidecar import inspector


def test_the_canon_section_says_how_far_the_notes_blocks_reach():
    rows = [{"key": "note", "hash": "h", "metadata": {"nmos_blocks": [{"kind": "chronicle", "turns": "0-87"}]}}]
    line = inspector.note_blocks(rows, 120, "ko")
    assert "연대기 t0–87" in line and "t120" in line
    assert inspector.note_blocks([{"key": "note", "hash": "h", "metadata": {}}], 120, "ko") == ""
```

- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3: Implement** in `inspector.py` (strings in the `STRINGS` table as `cn.blocks`:
  `("작가 노트의 NMOS 정리: {blocks} · 지금 t{now}", "NMOS sections in the author's note: {blocks} · now t{now}")`):

```python
def note_blocks(rows: list[dict[str, Any]], now: int | None, lang: str) -> str:
    """Which NMOS sections the author's note carries and how far each reaches (PHASE-50 S6), from the note's manifest
    metadata; empty without them."""
    from .notes import LABELS  # notes imports this module

    note = next((r for r in rows if r.get("key") == "note"), None)
    blocks = ((note or {}).get("metadata") or {}).get("nmos_blocks") or []
    if not blocks:
        return ""
    said = " · ".join(f"{LABELS.get(b.get('kind'), (b.get('kind'),) * 2)[lang == 'en']} t{str(b.get('turns')).replace('-', '–')}"
                      for b in blocks)
    return f"<p class=\"muted\">{_v(_t(lang, 'cn.blocks').format(blocks=said, now=now))}</p>"
```

  and in `detail`, append `+ note_blocks(canon_rows, last_turn, lang)` to the canon part's HTML.
- [ ] **Step 4:** Run → PASS; run `uv run pytest tests/test_inspector.py -q` → PASS.
- [ ] **Step 5:** Commit `feat(inspector): the note's NMOS sections and how far they reach (PHASE-50 S6)`.

---

### Task 7: The plugin removes the blocks before the hash

**Files:** Create `adapters/pocketrisu-plugin/src/notes.ts`, `test/notes.test.ts`; Modify `src/canon.ts`

- [ ] **Step 1: Failing test** `test/notes.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { stripNoteBlocks } from '../src/notes';
import { canonTexts } from '../src/canon';
import type { HostChat } from '../src/types';

const doc = JSON.parse(readFileSync(new URL('../../../fixtures/unit/note-blocks-v1.json', import.meta.url), 'utf8'));

describe('NMOS note blocks (PHASE-50 S5)', () => {
  it('are removed as the sidecar removes them (fixtures/unit/note-blocks-v1.json)', () => {
    for (const c of doc.cases) expect(stripNoteBlocks(c.note), c.name).toEqual({ text: c.text, blocks: c.blocks });
  });
  it('leave the note out of canon without them, and name them in its metadata', () => {
    const chat: HostChat = { id: 'c', note: doc.cases[1].note, message: [] };
    const note = canonTexts(null, chat, [], null).find((t) => t.key === 'note')!;
    expect(note.text).toBe('지금은 한겨울 밤이다.');
    expect(note.metadata).toEqual({ nmos_blocks: [{ kind: 'chronicle', turns: '0-87' }] });
    const plain = canonTexts(null, { ...chat, note: '그냥 메모' }, [], null).find((t) => t.key === 'note')!;
    expect(plain.metadata).toEqual({});
    const only = canonTexts(null, { ...chat, note: doc.cases[4].note }, [], null);
    expect(only.find((t) => t.key === 'note')).toBeUndefined();
  });
});
```

- [ ] **Step 2:** `cd adapters/pocketrisu-plugin && npx vitest run test/notes.test.ts` → FAIL.
- [ ] **Step 3: Implement** `src/notes.ts`:

```ts
// NMOS's sections in the author's note (PHASE-50 S5): never canon. The sidecar's `notes.strip_blocks` is the same
// (fixtures/unit/note-blocks-v1.json).
const LABELS: Record<string, string> = {
  '연대기': 'chronicle', chronicle: 'chronicle', '설정 변경점': 'changed', changed: 'changed',
  '호칭·관계': 'address', address: 'address',
};
const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const LABEL = Object.keys(LABELS).map(escape).join('|');
const BLOCK = new RegExp(`\\[NMOS (${LABEL})(?: · t(\\d+)(?:–(\\d+))?)?(?: · [^\\]\\n]*)?\\]\\n?[\\s\\S]*?\\[/NMOS \\1\\]\\n?`, 'g');

export interface NoteBlock { kind: string; turns: string }

export function stripNoteBlocks(text: string): { text: string; blocks: NoteBlock[] } {
  const blocks: NoteBlock[] = [];
  for (const m of text.matchAll(BLOCK)) {
    blocks.push({ kind: LABELS[m[1]!]!, turns: m[2] ? m[2] + (m[3] ? `-${m[3]}` : '') : '' });
  }
  if (!blocks.length) return { text, blocks };
  return { text: text.replace(BLOCK, '\n\n').replace(/\n{3,}/g, '\n\n').trim(), blocks };
}
```

  In `canon.ts`, replace `add('note', chat.note);` with:

```ts
  if (typeof chat.note === 'string') { // NMOS's own sections are not canon; the metadata names them (PHASE-50 S5)
    const note = stripNoteBlocks(chat.note);
    add('note', note.text, note.blocks.length ? { nmos_blocks: note.blocks } : {});
  }
```

  and `import { stripNoteBlocks } from './notes';`.
- [ ] **Step 4:** `npm test && npm run typecheck` → PASS (the existing canon tests unchanged).
- [ ] **Step 5:** Commit `feat(plugin): the author's note is canon without NMOS's sections (PHASE-50 S5)`.

---

### Task 8: The panel — button, form, result with Copy

**Files:** Modify `adapters/pocketrisu-plugin/src/ui.ts`, `src/i18n.ts`; Test `test/notes.test.ts` (copy fallback)

- [ ] **Step 1: i18n strings** in `STRINGS` (Korean first):

```ts
  // notes for the author's note (PHASE-50)
  'notes.open': ['작가의 노트용 정리', 'For the author\'s note'],
  'notes.sub': ['작가의 노트에 붙여넣을 정리를 만듭니다. 노트는 매 요청에 함께 가므로 붙여넣은 길이만큼 매 턴 토큰이 듭니다. NMOS 표시([NMOS …])째로 붙여넣어야 기억이 그 부분을 설정으로 읽지 않습니다.',
    'Makes sections to paste into the author\'s note. The note goes with every request, so what you paste is paid every turn. Paste them with their [NMOS …] lines, so memory does not read them as the setting.'],
  'notes.chronicle': ['연대기 (모델 1회 호출)', 'Chronicle (one model call)'],
  'notes.changed': ['설정 변경점', 'Changed from the setting'],
  'notes.address': ['호칭·관계', 'Address and standing'],
  'notes.length': ['연대기 길이', 'Chronicle length'],
  'notes.short': ['짧게 (3,000자)', 'Short (3,000 characters)'],
  'notes.long': ['길게 (6,000자)', 'Long (6,000 characters)'],
  'notes.secrets': ['비밀 포함 (누가 모르는지 표시)', 'Include secrets (marked with who does not know)'],
  'notes.secrets_warn': ['작가의 노트는 모든 장면에 들어갑니다. 비밀을 넣으면 모르는 캐릭터 앞에서 모델이 흘릴 수 있어요.',
    'The author\'s note reaches every scene. With secrets in it, the model can let one slip in front of a character it is kept from.'],
  'notes.make': ['만들기', 'Make'],
  'notes.copy': ['복사', 'Copy'],
  'notes.copied': ['복사했습니다.', 'Copied.'],
  'notes.copy_hint': ['자동 복사가 막혀 있어서 내용을 선택해 두었습니다. 길게 눌러 복사하세요.', 'Copying is blocked here, so the text is selected: copy it by hand.'],
  'notes.made_model': ['모델이 씀', 'written by the model'],
  'notes.made_assembled': ['모델 없이 조립', 'assembled without a model'],
  'notes.made_facts': ['기억에서 바로', 'straight from memory'],
  'notes.cached': ['(이전과 같음, 호출 없음)', '(unchanged, no call)'],
  'notes.held': ['비밀 때문에 뺀 요약 {n}개', '{n} summaries left out for secrets'],
  'notes.none': ['적을 것이 없습니다.', 'Nothing to write.'],
  'notes.no_scenes': ['아직 장면 요약이 없습니다 (8턴마다 하나, 4턴 뒤에 만들어집니다).', 'No scene summary yet (one per 8 turns, made 4 turns later).'],
  'notes.pick': ['하나 이상 고르세요.', 'Pick at least one.'],
```

- [ ] **Step 2: Copy helper with a test** — add to `src/notes.ts`:

```ts
/** Copy a box's text; where the frame refuses the clipboard (iPhone Safari), select it for the reader. */
export async function copyText(box: HTMLTextAreaElement, clipboard: Pick<Clipboard, 'writeText'> | undefined): Promise<boolean> {
  try {
    if (!clipboard) throw new Error('no clipboard');
    await clipboard.writeText(box.value);
    return true;
  } catch {
    box.focus();
    box.select();
    box.setSelectionRange(0, box.value.length);
    return false;
  }
}
```

  test (Vitest's jsdom environment, as `dom.test.ts` uses — copy its header pragma):

```ts
  it('copies, and selects the text where the clipboard is refused', async () => {
    const box = document.createElement('textarea');
    box.value = '[NMOS 연대기 · t0–1 · 2026-10-23]\n- a\n[/NMOS 연대기]';
    document.body.append(box);
    let copied = '';
    expect(await copyText(box, { writeText: async (t: string) => { copied = t; } })).toBe(true);
    expect(copied).toBe(box.value);
    expect(await copyText(box, { writeText: async () => { throw new Error('denied'); } })).toBe(false);
    expect(box.selectionEnd - box.selectionStart).toBe(box.value.length);
  });
```

- [ ] **Step 3: The panel** in `ui.ts`, beside the other per-chat actions (they show on a conversation page only):
  - `const notesButton = el('button', { text: L('notes.open') });` added to the actions' `btns` row after
    `exportButton`; `const notesCard = el('div', { class: 'card', style: 'display:none' });` added to
    `inspectorView.append(...)` right after `actionMsg`.
  - `notesButton` toggles `notesCard` (built on first open, rebuilt when `actionConversation` changes — clear it in
    `showInspector` where `actionConversation` is reassigned: `notesCard.replaceChildren(); notesCard.style.display = 'none';`).
  - The form: three checkboxes (`notes.chronicle` checked, `notes.changed` checked, `notes.address` checked), a
    `select` (`notes.short` = 3000, `notes.long` = 6000), the `notes.secrets` checkbox with `notes.secrets_warn` shown
    while it is checked, the `notes.make` button and a `msg` line; the `notes.sub` text above.
  - Make: `POST /v1/conversations/${conversation}/notes` with `{ sections, chars, secrets, lang }`, timeout 180_000
    (one model call); while it runs the button is disabled and `msg` says `act.working`.
  - The result, per section: an `h2` with the section's label, a `sub` line (`notes.made_*`, `notes.cached` when cached,
    `notes.held` when `held > 0`, its `chars`), a `textarea` (`readonly`, `rows: 10`, full width) with `text`, and a
    `notes.copy` button calling `copyText(box, navigator.clipboard)`, then `say(msg, copied ? 'notes.copied' :
    'notes.copy_hint')`. An empty `text` shows `notes.no_scenes` or `notes.none` by `reason`.
  - Use the existing `el`, `say`, `L`, `errorText` helpers; no new styles beyond `style: 'width:100%'` on the box.
- [ ] **Step 4:** `npm test && npm run typecheck && npm run build` → PASS; `git status` shows the rebuilt `dist/`.
- [ ] **Step 5:** Commit `feat(panel): make and copy the author's-note sections (PHASE-50 S1)` (with `dist/`).

---

### Task 9: Whole suite, docs, review

- [ ] **Step 1:** `cd apps/sidecar && NMOS_TEST_REQUIRE_DB=1 uv run pytest -q` → all pass (report the count).
  `cd adapters/pocketrisu-plugin && npm test && npm run typecheck && npm run build` → pass; `git diff --stat dist`
  matches the build.
- [ ] **Step 2:** `CHANGELOG.md` "Unreleased": one entry for Phase 50 (the three sections, the marker, the endpoint,
  the canon guard). `docs/phases/PHASE-50.md`: step 2–4 evidence (test names and counts).
- [ ] **Step 3:** `peer-review` skill (scoped self-review of the diff; **high risk**: canon/provenance, secrets).
  Check explicitly: a note without blocks hashes and reads byte-identically (fixture case 1 + Task 7 test); a block
  never reaches a canon prompt (Task 2); secrets off leaves no limited fact and no leaking summary (Tasks 3–4).
- [ ] **Step 4:** Push; update PR #315 (title `feat(phase-50): …`, body: the steps, high risk and the guarantees,
  "Part of AGE-88"); read Copilot's review once it lands and fix confirmed findings.

### Task 10: The test install (6131/6113)

- [ ] **Step 1:** Tell the owner before redeploying 6113 (memory: say so first). Back up: `pg_dump` of
  `nmos_p32_try` and the save dir's plugin file to `~/nmos-eval/p32-try/backup-20261023-<hhmm>-phase50`.
- [ ] **Step 2:** Build a local image `nmos-sidecar:trial-phase50-<sha>` from the branch; redeploy
  `nmos-p32-sidecar`/`nmos-p32-worker` with it (the previous containers kept stopped as `*-prev-candidate-6d3f2f7`);
  `/v1/health` version and `plugin.expected` read back.
- [ ] **Step 3:** Copy the plugin build to `~/nmos-eval/p32-try/nmos-pocketrisu.js` for the owner to re-import.
- [ ] **Step 4:** Q5's zero-call checks on 6113's copy: the note entry hash of every chat unchanged after the redeploy
  (no blocks in any note yet); `changed`/`address` made for each chat, each line checked against the memory view.
  The chronicle's paid call only after the owner approves its estimate.
