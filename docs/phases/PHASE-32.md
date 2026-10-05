# Phase 32 — Memory on a time axis: a character's facts as bars over turns in the Inspector

> **Status: authorized 2026-10-05 as an exception to R7; spec drafted, the proposed answers awaiting the owner.**
> Not a roadmap stage. The owner pulled it in before 1.0 by name (2026-10-05, an exception to R7 in
> `docs/ROADMAP-1.0.md`, as Phase 23 was). Tracked as AGE-39, which the owner had first set for after 1.0.
> The owner reviewed a mockup built on synthetic data, and the design below follows it.

## Why

The Inspector lists memory as tables: a character's standing facts, relationships, threads and events, each with its
history in a timeline column. Every value is there, but a long chat makes it hard to see what changed when, what is
current, and what was replaced. NMOS memory is time-indexed, so turns are its natural axis. Every current fact
already carries its full history with turns and outcomes (`facts.py`: `current`, `superseded`, `ended`,
`conflicting`), and canon facts sit before turn 0 (ADR 0047). The owner rejected a node-and-edge graph, which goes
messy as the cast grows, and a character-by-character matrix, which was hard to read, mostly empty and unusable on a
narrow screen.

## Decided (owner, 2026-10-05)

- **Only the browser Inspector**, the pages the sidecar serves at `/inspector/…`. The NMOS panel inside PocketRisu
  shows the same pages through the plugin's sanitizer, which keeps only `class`, `title` and `open` (with links) and
  drops `style`. That would break every bar's position, so the panel (`embed`) gets none of this phase. Supporting
  it is a later plugin change.
- **The sidecar only.** No plugin change or build, no migration, no new API, no model call. The packet, recall and
  extraction are untouched.
- The layout is one line per character over the turn axis, then the chosen character's tracks: their state, the
  relationships that go **from** them, their threads and their events.

## Scope

1. **The character page** (`/inspector/c/<conv>/e/<entity>`) gets a timeline section above its tables:
   - **State**: one lane per current fact of this character that has history or is a standing fact. Each history
     entry is a bar from its turn to the next entry's turn, or to the current turn while it is `current`. Superseded
     and ended entries are drawn outlined, the current one filled.
   - **Relationships from this character**: `relationship`, `role_toward` and `feels_toward` with this character as
     subject, one lane per object and predicate.
   - **Threads** this character opened or that are addressed to them: a bar from the opening turn to the closing
     turn, or to now while open.
   - **Events** this character takes part in: dots on one lane, sized by salience.
2. **The conversation page** (`/inspector/c/<conv>`) gets a cast strip. Each character gets one line with a tick at
   every turn where one of their facts starts or ends, plus their last change turn. The line links to that
   character's page. The characters in the current scene come first; the rest fold under a `<details>`.
3. A lane, thread or event links to its row in the tables below it (`#a-<fact id>`; history entries carry no id of
   their own, so every bar of a lane links to its fact's row), and the row is highlighted with `:target`. The rows get
   that `id` outside `embed` only. Each bar's `title` gives its value, turn span and outcome. **No JavaScript.**
4. Two time windows, chosen with a query parameter that keeps the token and language: the whole chat (the default)
   and the last 50 turns.
5. The strings are Korean and English through the Inspector's existing `_t`. The page's own tokens work in light and
   dark, and the layout works at phone width.

## Out of scope

- The panel (`embed`) and every plugin change.
- A graph, a matrix or any other layout. Any JavaScript, charting library or web font: the Inspector runs on a LAN
  sidecar with system fonts.
- Editing from the timeline. Repairs stay in the panel and the existing actions.
- New queries, columns or a migration. The timeline uses only what `view` already holds. If a lane needs more, stop
  and ask.
- A change to what the packet holds, to recall, extraction, workers or settings.

## Questions and proposed answers

| # | Question | Proposed answer | Alternatives |
|---|---|---|---|
| Q1 | Where does it appear? | **Above the tables of the character page, and as a cast strip on the conversation page.** The character page is already the one-person view. | A separate `/timeline` page. |
| Q2 | The panel (`embed`)? | **Not drawn.** The embed output stays byte-identical to today's. | Emit a list fallback for the panel. |
| Q3 | Interaction without JavaScript? | **A lane links to its fact's table row (`#a-<fact id>`) with a `:target` highlight; every bar has a `title`.** | A small inline script for a detail column (the mockup had one). |
| Q4 | Which state lanes? | **Every current fact of the character from `facts.py`'s fold**, one lane per fact (its history is the lane), ordered as the facts table orders them. A fact whose every entry is closed shows as an outlined lane up to its end. | Only standing predicates. |
| Q5 | Which relationships? | **Only those going from this character** (subject = character): `relationship`, `role_toward`, `feels_toward`. Relationships toward the character stay in the existing Pairs table. | Both directions. |
| Q6 | How is the cast strip ordered, and what folds? | **The current scene's cast first (`scene.py`), then every other character under "N more" in a `<details>`**, each line linking to its character page. | Every character open, by mention count. |
| Q7 | Time windows? | **The whole chat, and the last 50 turns** (`?span=recent`). | Any range from the query. |
| Q8 | Caps on a large chat? | **At most 40 lanes per section, 200 event dots and 120 ticks per cast line.** What is left out is counted ("+N in the table below"). | No caps. |
| Q9 | The persona? | **Drawn on the persona's own character page like any character.** On the conversation page it is not a cast line, since the persona is never in the cast (ADR 0023). | Leave the persona out. |
| Q10 | Canon facts and owner repairs? | **A canon entry's bar starts at turn 0 and is marked as from the setting (history entries carry `canon`). A current version that is the owner's (the fact's `owner`) is marked as such. Earlier versions carry no owner mark in `view`, so they get none.** | Add the owner mark to history entries (a `facts.py` change, out of scope). |

## Steps

1. This spec, with the owner's answers.
2. **Implementation** (one PR): `inspector.py` (timeline and cast strip), strings, styles, and tests in
   `tests/test_inspector.py`. The tests cover:
   - bars from synthetic history (spans, outcomes, canon at 0, the owner's current version);
   - the caps and their counts;
   - links and anchors;
   - escaping;
   - `embed` unchanged;
   - the persona page;
   - empty states;
   - the recent window.

   No other module changes behavior.
3. **Measurement and check**: the character and conversation pages timed before and after on the 10,000-message
   scale fixture (`docs/perf/scale.md`'s setup), recorded in `docs/perf/inspector-timeline.md`. The owner looks at
   it in the browser on their own instance, in light and dark and at phone width. The repository records only
   numbers and synthetic screenshots, never chat content.

## Acceptance criteria

1. On the character page, every bar and dot corresponds to one history entry, thread or event in the tables below
   it, with the same turns and outcome, and links to the row of its fact, thread or event (tests).
2. The conversation page has the cast strip with the current scene first and the rest folded (tests).
3. The `embed` output of both pages is byte-identical to before (test).
4. No change outside the Inspector's rendering. The packet, recall and extraction tests pass unchanged, and no
   JavaScript is emitted.
5. Every value reaches the page through the Inspector's escaping (test with markup in names and values).
6. At 400 px wide the page does not scroll sideways: labels go above their tracks.
7. The added render time at 10,000 messages is measured and recorded. A character page slower than one second
   stops step 3 for the owner.
8. The owner's look in the browser.

## Stop conditions

- A lane needs data that `view` does not hold (a new query, column or migration).
- Any part needs JavaScript, a library or a plugin change.
- A test outside the Inspector changes.

## Risk

Not high risk under `AGENTS.md` §14. The change is read-only rendering on the Inspector's existing view, with no
stored data, no memory selection and no security boundary. The `embed` byte-identity test keeps the panel exactly
as it is.
