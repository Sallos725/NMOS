# Phase 52 — The panel rebuilt: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the panel's three tabs and twenty-section Inspector page with a hub of blocks, memory as one
document, a person's sheet with a circle timeline, a plain-words "working" page, grouped settings and a chat list
(`docs/phases/PHASE-52.md`, D1–D9).

**Architecture:** Every content screen, the hub included, is a sidecar page: a new module `views.py` renders HTML
fragments from what the Inspector already reads, served under `/v1/views/…` (the panel) and `/views/…` (the browser).
The panel shows them with the machinery that shows Inspector pages today (`showInspector`, its back stack, link
interception, `enhance`, repair wiring), extended to the new paths. The sidecar also serves the one stylesheet for these
pages (`/v1/views/style`), which the panel injects once, so the component styles exist once. The plugin keeps the shell:
a header (back, title, refresh), the actions a block names (`data-act`: settings, backup, the author's note), and the
settings groups. Colours and type come from one tokens fixture both languages check.

**Tech stack:** Python 3.12 / FastAPI (sidecar, pytest on the compose Postgres :5436); TypeScript / Vitest / happy-dom
(plugin). Screenshots with the Playwright in `~/nmos-eval/three-bench/harness/node_modules` against the test install
(:6113, read only; synthetic names in anything committed).

---

## Amendment before Task 1 (2026-10-23, after reading the sanitizer)

- **Order:** a thin slice first — Task 2's stylesheet and helpers, `/v1/views/style` injected by the panel, the hub
  (Task 3) as one sidecar page with one link into an existing Inspector page and back, `features.views` gating, a
  390 px screenshot — then the tokens (Task 1) and the other screens on top.
- **Inside the sanitizer** (`safeFragment`: `DIV P H1 H2 SPAN B BR A TABLE… DETAILS SUMMARY`; attributes `class`,
  `title`, `open`, section ids, Inspector hrefs, `data-repair`, `data-l`/`data-w`, `data-span`, the mark texts): blocks
  are `<a href="/views/…">`; the plugin's actions are `<a data-act="notes|settings|backup">` (the one attribute added,
  values fixed, tested to drop anything else); no `ul`/`li`/`h3`/`button`/`input`/`svg`; the chat filter's input is
  created by the plugin at a `.v-filter` slot; the circle timeline is `div.v-mark` placed by `data-l` with the mark
  attributes `markDetail` reads.
- **CSS:** every rule of `views.STYLE` starts with `.nmos ` (a test); the browser pages wrap their body in
  `<div class="nmos">`; the panel injects the stylesheet only when it holds no `@import` and no `url(`, and its own
  screens (connection error, fallback) need none of it.

## File structure

| File | Change |
| --- | --- |
| `fixtures/unit/design-tokens-v1.json` | **new**: colours (from `palette.ts`), type scale (16/14/13, 20/17), spacing, radius |
| `apps/sidecar/src/nmos_sidecar/tokens.py` | **new**: the tokens as Python, checked against the fixture |
| `adapters/pocketrisu-plugin/src/palette.ts` | values checked against the fixture (a test), type scale exported |
| `apps/sidecar/src/nmos_sidecar/views.py` | **new**: `STYLE`, small HTML helpers, `hub`, `memory`, `person`, `working`, `chats` |
| `apps/sidecar/src/nmos_sidecar/timeline.py` | `circles(marks, slots)`: merge to at most 60 marks, size by importance |
| `apps/sidecar/src/nmos_sidecar/api.py` | `/v1/views/style`, `/v1/views/hub`, `/v1/views/c/{id}/memory`, `…/person/{e}`, `…/working`, `/v1/views/chats`; the same under `/views/…` as full pages; `features.views` in `/v1/health` |
| `apps/sidecar/src/nmos_sidecar/inspector.py` | type sizes up (details pages keep their content) |
| `apps/sidecar/tests/test_views.py` | **new** |
| `adapters/pocketrisu-plugin/src/inspector.ts` | `inspectorApiPath` and friends accept `/views/…` |
| `adapters/pocketrisu-plugin/src/ui.ts` | the shell: header, hub first, `data-act` actions, settings groups, the injected stylesheet, fallback without `features.views` |
| `adapters/pocketrisu-plugin/src/i18n.ts` | shell strings |
| `adapters/pocketrisu-plugin/test/views.test.ts` | **new** (path rules, shell, actions) |

## Conventions for every task

- Write the failing test first, see it fail, implement, see it pass, commit (`feat(phase-52): …`, attribution line).
- Sidecar text is Korean and English through `views.T` (the Inspector's `_t` pattern); the panel passes `lang`.
- No table in `views.py` output; names link to their person's sheet (`/views/c/{id}/person/{entity}`); every list
  shows three items, the rest under one `<details class="v-more">` ("N more").
- Escape every value (`inspector._v`); no inline script in fragments (the panel runs none).

---

### Task 1: Tokens

- [ ] Fixture `design-tokens-v1.json`: `color` (every `PALETTE` key and value), `type` (`body` 16, `secondary` 14,
  `caption` 13, `h1` 20, `h2` 17, `weights` [400, 600]), `space` (4, 8, 12, 16, 24, 32), `radius` (6, 12).
- [ ] `tokens.py`: `TOKENS` dict; `css_vars()` → `--c-*`, `--t-*`, `--s-*`, `--r-*` declarations.
- [ ] Tests: Python `TOKENS == fixture`; TS `PALETTE` equals `fixture.color` (key names camelCase ↔ kebab handled).
- [ ] Commit.

### Task 2: The views stylesheet and helpers

- [ ] `views.STYLE` (one string): page, headings, `.v-sec` (section title with count), `.v-line` + `.v-meta`,
  `.v-name` (link), `.v-chips` (jump row; on ≥ 900 px a left column), `.v-more`, `.v-blocks` (grid: 2 columns, 3 at
  ≥ 700 px), `.v-block` (+ `.ok`/`.warn`/`.err` left rule), `.v-tl` (timeline), sizes from tokens, no monospace except
  `.v-id`.
- [ ] Helpers: `section(id, title, count, body)`, `line(main, meta)`, `more(items, n=3)`, `name_link(conv, entity, name)`,
  `full_page(title, body, lang)` (for `/views/…` in a browser: `<style>` + body).
- [ ] `GET /v1/views/style` → `{"css": STYLE}`; `features.views: true` in `/v1/health`.
- [ ] Tests: `more` shows three and folds the rest; no `<table` in any helper output; health reports the feature.
- [ ] Commit.

### Task 3: The hub

- [ ] `views.hub(data, lang)`; data from one function `hub_data(conn, conv, settings, state)`:
  - working: `ok` when the chat's newest trace placed memory and nothing failed, `warn` when jobs failed or the
    newest request went without memory, `err` when the sidecar's model setting is missing; the plugin passes what only
    it knows as query parameters (`off=1` this chat is off, `all_off=1` the global switch, `build=<plugin build>`).
  - memory: characters in the scene (the newest trace's `scene_cast`), open threads (not stale), changed-from-setting
    count; on a wide screen the first two "now" lines.
  - needs a look: `inspector._attention` row count (block only when > 0).
  - usage today: `usage.py` totals for this chat since local midnight.
  - other chats: the number of conversations.
- [ ] Blocks are `<a href="/views/c/{id}/memory">` (and working, chats) or `<button data-act="notes|settings|backup">`.
- [ ] `GET /v1/views/hub?chat=<host_chat_ref>&lang=&off=&all_off=` → `{"html", "conversation"}`; without a known
  chat the hub shows the chats block and settings only.
- [ ] Tests: synthetic chat (SimChat) → blocks present in order, needs-a-look absent at 0, `data-act` values, links.
- [ ] Commit.

### Task 4: Memory, one document

- [ ] `views.memory(conv, view, told, last_turn, lang)`: sections now, open threads (Phase 50's `stale` rule, stale
  count line), people (`inspector.pairs`, addressed forms quoted), so far (story, then scenes newest first under
  "N more"), secrets (`view["secrets"]`: content, holders, kept from), changed (`notes.changed_lines` turned into lines);
  foot: all facts → `/inspector/c/{id}#facts`, needs a look → `/inspector/c/{id}#attention`.
- [ ] Each thread and fact line carries the same `span.rp[data-repair]` marker the Inspector uses today, so the panel's
  existing repair controls attach (shown on tap, D2).
- [ ] `GET /v1/views/c/{id}/memory` (+ browser `/views/c/{id}/memory`).
- [ ] Tests: section order; no `<table`, no generation key or commit id in the output; stale thread counted not shown;
  a name is a person link; repair markers present.
- [ ] Commit.

### Task 5: The person's sheet and the circle timeline

- [ ] `timeline.circles(marks, slots=60)`: marks `(turn, major)`; when more than `slots`, merge neighbours into
  buckets of equal turn span; a bucket is major if any member is; returns `(turn_from, turn_to, count, major)`.
- [ ] `views.person(conv, entity_id, view, now, lang)`: now (place, condition), relationships (pairs with this
  entity), promises and goals (threads by or to them), knows / does not know (secrets they hold, are kept from),
  timeline as SVG circles (major = ring r 9, else dot r 4; "×N" label under a merged mark), each mark a `data-v`
  element the panel's `showMark` already opens.
- [ ] Tests: 1,000 marks → ≤ 60; a merged bucket keeps "major"; sheet sections; links back to memory.
- [ ] Commit.

### Task 6: Working

- [ ] `views.working(conv, trace, cov, usage, lang)`: this reply (placed or not, ms, lines, characters, from the
  newest trace), "the memory just sent" as readable lines from the trace's ledger (`audit.audit`: each placed line's
  text, its section in words), processing in words with done/due, failed and waiting (and the `has-failed` marker the
  panel's Retry button keys on), usage (this chat, today and in all), details → `/inspector/c/{id}`.
- [ ] Tests: no XML tag text (`<Fact`, `<Thread`) in output; the failed marker when a job is dead.
- [ ] Commit.

### Task 7: Other chats

- [ ] `views.chats(conversations, lang)`: one line each (name, character, turns, last active relative, failed count
  in warn colour), `<input class="v-filter">` the panel wires to filter lines by text; the browser page filters with a
  small script.
- [ ] Tests: lines, failure marking.
- [ ] Commit.

### Task 8: The panel shell

- [ ] `inspector.ts`: `/views/…` hrefs map to `/v1/views/…`; conversation and entity extraction for the new paths.
- [ ] `ui.ts`: header with back and title replaces the tab bar; the panel opens on the hub (`GET /v1/views/hub`); the
  stylesheet from `/v1/views/style` is injected once per open; `data-act` handlers (notes → the Phase 50 form as a
  page; settings → the settings view; backup → the export/restore card); the old Status view becomes the
  "connection" page under settings and the screen shown when the sidecar cannot be reached; without
  `features.views` the panel opens today's Inspector as before.
- [ ] Repair controls, timelines and the chat filter wired by the existing delegation.
- [ ] Tests (happy-dom): hub loads first; a block link navigates; back returns; `data-act` opens settings; fallback
  without the feature; the chat filter hides non-matching lines.
- [ ] Commit; rebuild `dist`.

### Task 9: Settings in groups

- [ ] The settings view becomes a list of groups (connection, models, memory, this chat, status windows, display,
  advanced); each opens its existing card(s) as a page with back. "This chat" gathers the chat switch (`chatCard`), the
  memory mode (`modeCard`) and, later, Phase 48's switch; rebuild and delete move to advanced.
- [ ] Tests: every existing settings control is reachable under a group (a list in the test).
- [ ] Commit; rebuild `dist`.

### Task 10: Details restyled, browser pages, check

- [ ] Inspector pages: body 16 px, captions 13 px, headings from tokens; they are "details".
- [ ] `/views/…` full pages for the browser; `/inspector` index links to `/views/chats`.
- [ ] Screenshots at 390 px and 1,100 px of hub, memory, person, working, chats on a synthetic chat (committed) and
  on the test install's copy (not committed); the action map (old place → new place) in the phase file; gzipped size
  against the budget; full suites; peer-review; deploy to 6113 for the owner's iPhone and desktop check.
