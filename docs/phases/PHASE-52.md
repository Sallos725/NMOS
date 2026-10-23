# Phase 52 — The panel, rebuilt: a hub, memory as a document, status in plain words

Status: **approved**, 2026-10-23 (AGE-92). In `0.5.0` by R8 (owner, 2026-10-23, AGE-90). An owner request, not a
roadmap stage. The design below (D1–D9) was decided with the owner in the design conversation of 2026-10-23, on
mockups; the implementation approach is A (owner, same day).

The owner, on the panel as it is: "It reads like XML. There is too much, it is hard to look at, everything is a list,
some of it folded and some open so I cannot find things, the default font is too small to see, and it looks like an
HTML page I wrote without JS or CSS."

Not high risk (`AGENTS.md §14`): no stored data, schema, extraction, packet or memory selection changes. The new read
endpoints read what the Inspector already reads.

## Why (read from the code and a capture of the test install, 2026-10-23)

1. **One page of more than twenty sections.** A chat's Inspector page (`inspector.detail`) runs "needs a look",
   people, status, processing, usage, threads, unmatched ends, relationships, summaries, canon, facts, items,
   entities, claims, non-actual, packets, repeats, searches, commits and messages, one after another; its table of
   contents is one run-on line of twenty links.
2. **Two audiences on one page.** What the story holds (who is where, who owes whom) sits beside what NMOS runs on
   (generation keys such as `extract-…`, model endpoints, commits, packet ledgers) with the same weight. The owner's
   design rules ("Dense, Not Cluttered": bad density makes every piece of information look equally important) name
   exactly this.
3. **Tables everywhere.** On a phone's width a table cell such as an unmatched end's reason breaks into one word per
   line.
4. **Small type and raw terms.** The panel's body is 13.5 px, its help text 12 px, labels 11.5 px (`ui.ts`); internal
   words (`resolved`, `canon`, coverage, generation) are shown as they are.
5. **The panel has three tabs** (Status, Inspector, Settings); what the owner opens it for most is to see whether the
   memory is right, whether NMOS is working, and settings and tools (owner, 2026-10-23); repairs are occasional.

## Design (decided with the owner, 2026-10-23)

D1. **The hub.** The panel opens on a hub of blocks, one per category, each a one-line summary that opens its screen:
- a **working** line across the top (quiet green when the last reply got its memory and nothing failed; amber or red
  with what and why otherwise);
- **memory** (the largest block; on a wide screen it previews the first two lines of "now");
- **needs a look** (only while there is something to look at);
- **the author's note** (Phase 50), **usage**, **settings**, **backup** (export and restore), **other chats**.

On a phone, two columns; on a wide screen, three. Blocks are the one place the panel uses containers: each is an
independent unit (the design rules' "Typography Before Containers").

D2. **Memory, as one document** (owner's choice B), sections in this order: **now** (each character in the scene:
where and how), **open threads** (Phase 50 amendment 3's rule: not said again for 30 turns stays out, counted),
**people** (each pair: relationship, roles, feelings, forms of address), **so far** (the story so far, then the scenes),
**secrets** (the owner's view: what is kept from whom), **changed from the setting**. At the foot, quietly: all facts,
needs a look. No tables: one line per item, with a small muted line under it for kind and turns. A list shows its first
three items and "N more". A row of chips at the top jumps to a section on a phone; on a wide screen the same entries
are a small table of contents on the left. Repairs appear only when a line is tapped (a small menu: correct, lock,
close), not as buttons on every line.

D3. **A person's sheet** (owner's choice A, opened from any name): now, relationships, promises and goals, what they
know and do not know, and the timeline.

D4. **The timeline, in circles** (owner, 2026-10-23). A large ring marks a major event (`salience` `major`) or a change
of relationship; a small dot, any other change. When a lane would hold more marks than its width allows, neighbouring
turns merge into one mark: the chat's turns are cut into 30 equal spans and a span's changes are one mark, so a lane
holds at most 30 marks, over 3 % of its width apart (a phone too), at 76 turns or at 1,000. A merged mark is drawn
larger, and its card says how many ("t30–32 · ×3"): a "×N" label beside every mark overlapped on a phone's width.
At most five rings a lane: the spans with the most major events or relationship changes. On the test install 41 of a
lead's 72 events were "major", and a lane of rings marks nothing. Tapping a
mark opens its card under the lane. The timeline is still drawn only when its section is opened (PHASE-32 step 3, the
iPhone's memory).

D5. **Working, in plain words.** First, whether this reply got its memory (how long it took, how many lines and
characters), with "the memory just sent" shown as readable lines, not the packet's XML. Then processing (fact
extraction, search embeddings, scene summaries, reading the setting: done of due, failed, waiting, with "Retry
failed"), then usage (this chat, today: calls, estimated cost). Everything else (generation keys, models and
endpoints, commits, packet ledgers, searches, messages) is behind **details**, which keeps today's Inspector sections,
restyled.

D6. **Settings, in groups**: connection; models; how memory works (budget, summaries, canon); **this chat** (memory on
or off for this chat, the memory mode, and Phase 48's "AI replies only" when it lands); status windows; display
(language, the progress display); advanced (rules JSON, rebuild, delete). Each group opens its own page.

D7. **Other chats**: a searchable list (name, character, turns, last active, failures marked), each opening that
chat's hub. It replaces the Inspector's first page.

D8. **The look.** Dark only (owner, 2026-10-23), from `palette.ts`. Type: body 16 px, secondary 14 px, captions 13 px,
headings 20 and 17 px, two weights. The system's Korean fonts (no web font: the plugin stays light); monospace only for
identifiers under details, never for Korean. The accent marks action, selection and status only. Lists are lines and
dividers, not boxes.

D9. **The browser Inspector** (`/inspector`) shows the same screens as the panel.

## Approach (owner, 2026-10-23: A)

- **The sidecar renders content** (memory, person, working, details, other chats) as HTML fragments, as the Inspector
  does now; **the plugin draws the shell** (hub, navigation and back, settings forms, buttons, the author's note form)
  and wires actions by event delegation (`ui.ts`, as repairs and timelines are wired today).
- **New read endpoints** beside the Inspector's: `GET /v1/views/hub?conversation=<id>` (JSON: the working line, counts,
  the "now" preview, needs-a-look count, usage today), `GET /v1/views/c/{id}/memory`, `…/person/{entity}`,
  `…/working`, and `GET /v1/views/chats`. The existing `/v1/inspector/…` pages stay, restyled, as **details**.
- **One set of design tokens**: `fixtures/unit/design-tokens-v1.json` (colours, type scale, spacing), that the
  plugin's `palette.ts` and the sidecar's stylesheet are checked against in both languages' tests, as the other shared
  fixtures are.
- **The panel's sanitizer stays the boundary** (`inspector.ts` `safeFragment`: a fixed set of tags and attributes;
  no `button`, `input`, `svg` or `style`). The new pages stay inside it: blocks are links, a plugin action is the one
  added attribute `data-act` with a fixed set of values, the chat filter's input is the plugin's, and the circle timeline
  is positioned `div`s (`data-l`) as today's timeline is. The views stylesheet scopes every rule under `.nmos`, and the
  panel refuses one holding `@import` or `url(`.
- **Compatibility.** `/v1/health` reports `features.views`. A new plugin with an older sidecar falls back to today's
  Inspector screens; an older plugin with a newer sidecar keeps working with the restyled Inspector pages.
- **Budget.** The plugin build is 262,839 bytes (66,986 gzipped) on `8717e3f0b575`; this phase may add at most 20 % to
  the gzipped size.

## Out of scope

- A light theme (owner, 2026-10-23: dark only).
- The chat-screen progress display (`hud.ts`): only its type size follows D8.
- Changing what memory holds or sends: the screens show what is there.

## Steps

1. **Spec** (this file).
2. **Tokens and base styles**: the tokens fixture, the palette from it, the type scale, the line, section, chip, block
   and sheet styles in both places.
3. **The hub and the shell**: `GET /v1/views/hub`, the hub screen, navigation with a back stack, replacing the three
   tabs; the Phase 50 note form moves under its block.
4. **Memory and person**: the document, the person sheet, the circle timeline with merging, the tap menu for repairs.
5. **Working**: this reply, the memory just sent in readable lines, processing and retry, usage, details.
6. **Settings** in groups, with **this chat**; **other chats**; the browser Inspector on the same screens.
7. **Check**: screenshots at 390 px and 1,100 px on the test install's copy (synthetic names in anything committed),
   the owner's check on an iPhone and a desktop, every action of today's panel reachable (a list in the evidence).

## Steps 2–7 evidence (2026-10-23)

Built on PR #316 (stacked on #315), plan `docs/superpowers/plans/2026-10-23-phase52-panel-overhaul.md`, a thin slice
first (stylesheet, hub, a link and Back) as amended after reading the sanitizer.

- **Sidecar** (`views.py`, `tokens.py`, `timeline.circles`, `api.py`): `/v1/views/style`, `/v1/views/hub`,
  `/v1/views/c/{id}/memory`, `…/person/{entity}`, `…/working`, `/v1/views/chats`, each also a browser page under
  `/views/…`; `features.views`. `tests/test_views.py`: 26 tests (tokens against the fixture, every rule under `.nmos`, the
  hub's blocks and states, the memory document's order, folds, links and repair markers, the person's sheet and its
  circles, rings at most five, working in words with retry, the chat list, chat text escaped on every screen, every endpoint). The whole sidecar suite:
  1,621 passed before the last two fixes; the touched files' tests after them.
- **Plugin** (`ui.ts`, `inspector.ts`, `i18n.ts`): the hub first with a sidecar that has the screens, the stylesheet
  injected once (refused with `@import`/`url(`), `/views` paths, `data-act` limited to notes, settings, backup and
  retry, a tapped line's repair, the chat filter, the tab bar gone, settings in seven groups with "this chat" gathering
  its tools, the type scale (nothing under 13 px). `test/views.test.ts`: 15 tests; all 264 plugin tests pass. Gzipped
  build 69,576 bytes against 66,986 (+3.9 %; the budget is +20 %).
- **On the test install** (6131/6113, test-only) since 2026-10-23 22:36 KST, `trial-phase52-a3071ab`; the database
  fingerprint is identical before and after each deploy. The biggest chat (153 messages): hub 99 ms, memory 69 ms
  (59 KB), working 101 ms, a person 61 ms, chats 4 ms; today's Inspector chat page 165 ms and 551 KB.
- **What the test install's data changed** (screenshots at 390 px, not committed): the scene's cast named one person
  twice (one line per entity now); a lead's lane was all rings, since 41 of their 72 events were "major" (at most five
  rings now, and a relationship ring only where it replaced another); merged-count labels overlapped on a phone (a
  merged mark is larger, its count in its card); a person's relationships showed a bare name when the feelings ran the
  other way (both directions now); the memory just sent carried English predicate names (the panel's words now). Two
  names of one character that NMOS keeps as two entities still show twice: that is the memory's, fixed by a join.
- **The owner's first look** (2026-10-23, desktop and iPhone): the hub's grid left holes at two and three columns
  (blocks now grow to fill their row, so every row ends flush whatever their number); a close's preselected ending
  ("이룸") read like a name and a goal was offered "paid" (a close is now "How did it end?" with one button per
  ending of the thread's kind: a goal achieved, abandoned or failed; a question answered or abandoned; a threat
  averted or failed; a debt paid or abandoned; a promise kept or broken; the repair accepts what it did).
- **Where today's actions went:** Status tab → settings, connection (sidecar, plugin file, this chat on/off); Inspector
  list → other chats; a chat's page → memory (now, threads, people, so far, secrets, changed) and details (everything
  else, unchanged); Retry failed → working; Extract all history, Rebuild, Export this chat, Delete → settings, this
  chat; memory mode, this chat's status windows → settings, this chat; author's note → its hub block; closing a thread →
  tap its line in memory; the other repairs (correct, lock, retract, secrets, aliases, undo) → details, as before;
  joins and splits → a person's details; every settings card → its group.
- **Left for the owner:** re-import the plugin (`~/nmos-eval/p32-try/nmos-pocketrisu.js`, build `398d4d71256e`) on
  6131 and check on an iPhone and a desktop.

## Acceptance criteria

- Body text 16 px; no text under 13 px outside details.
- The memory screen holds no table and no identifier (generation key, commit, endpoint); they appear only under details.
- The hub is one request; memory, person and working are one request each.
- A timeline lane never draws more than 30 marks, none over another (test).
- Every action today's panel offers is reachable in the new one (the evidence lists them, old place → new place).
- The plugin's gzipped size grows by at most 20 %.
- The owner's check on an iPhone and a desktop.
