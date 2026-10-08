# Phase 32 — Memory on a time axis: a character's facts as bars over turns in the Inspector

> **Status: approved 2026-10-05 (every proposed answer, with Q2, Q3 and Q7 as the owner amended them below).**
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

- **The browser Inspector first, then the panel.** Step 2 draws the timeline in the pages the sidecar serves at
  `/inspector/…`. Step 3 brings it to the NMOS panel inside PocketRisu, which the owner wants too: iPhone users read
  the Inspector only there.
  - The panel shows the same pages through the plugin's sanitizer. That sanitizer keeps only `class`, `title`,
    `open`, inspector links and section ids, and drops `style`.
  - Step 3 therefore needs a plugin change: bar positions pass through as numbers only, the panel gets the
    timeline's styles, and a tap shows a bar's detail, since a phone has no hover.
  - The sidecar sends the timeline to the panel only when the plugin says it can show it, so an older plugin's panel
    stays exactly as it is.
- **No file to install.** The browser page carries a short inline script for the detail column. Every bar is also a
  plain link, so the page works without the script. In the panel, the plugin's own code handles taps. A user only
  updates the sidecar and the plugin as usual.
- No migration, no new endpoint, no model call. The packet, recall and extraction are untouched.
- **Where a bar ends** (owner, 2026-10-05, option A, after the PR review). `facts.version_key` keeps one history for a
  pair's relationship (both directions) and for an item (every holder and place), so the next entry is not always
  where one ended.
  - `facts.py` records, on each closed history entry, the turn of the statement that closed it (`closed_turn`). The
    fold already knows that statement.
  - A lane draws only its own character's entries.
  - The field is for display only: what the fold chooses and every recall path are unchanged.
- The layout is one line per character over the turn axis, then the chosen character's tracks: their state, the
  relationships that go **from** them, their threads and their events.

## Scope

1. **The character page** (`/inspector/c/<conv>/e/<entity>`) gets a timeline section above its tables:
   - **State**: one lane per current fact of this character. Each of the character's own history entries is a bar
     from its turn to the turn before the statement that closed it (`closed_turn`), or to the current turn while it
     is `current`. Superseded and ended entries are drawn outlined, the current one filled.
   - **Relationships from this character**: `relationship`, `role_toward`, `feels_toward` and `addresses` with this
     character as subject, one lane per object and predicate.
   - **Threads** this character opened or that are addressed to them: a bar from the opening turn to the closing
     turn, or to now while open.
   - **Events** this character takes part in: dots on one lane, sized by salience.
2. **The conversation page** (`/inspector/c/<conv>`) gets a cast strip. Each character gets one line with a tick at
   every turn where one of their facts starts or ends, plus their last change turn. The line links to that
   character's page. The characters in the current scene come first; the rest fold under a `<details>`.
3. A lane, thread or event links to its row in the tables below it (`#a-<fact id>`). History entries carry no id
   of their own, so every bar of a lane links to its fact's row, and the row is highlighted with `:target`. The rows
   get that `id` outside `embed` only.
   - Each bar's `title` gives its value, turn span and outcome.
   - In the browser, a short inline script shows the clicked bar's detail in a side column: value, span, outcome,
     the lane's history, and the owner and canon marks.
   - **Page weight** (owner, 2026-10-06, for the iPhone, whose Safari reloads a tab under memory pressure). Only the
     detail of the bar selected at load is rendered. The script builds any other detail from the clicked bar's data
     attributes, as text and never as markup, and a lane's history is that lane's own bars.
     - A first build pre-rendered a hidden detail for every bar, each with its lane's whole history, so it grew with
       the square of a lane's versions.
     - On the 240-turn gate copy, the largest character page went from 396 KB (the timeline 261 KB, 2,170 hidden
       history lines) to 229 KB (94 KB).
     - At phone width the timeline is 822 of the page's 5,698 elements.
4. Two time windows, chosen with a query parameter that keeps the token and language: the whole chat (the default)
   and the last 25 turns (owner, 2026-10-05).
5. The strings are Korean and English through the Inspector's existing `_t`. The page's own tokens work in light and
   dark, and the layout works at phone width.

## Out of scope

- A graph, a matrix or any other layout.
- A charting library, an external script or a web font: the Inspector runs on a LAN sidecar with system fonts. The
  only script is the browser page's inline one.
- Editing from the timeline. Repairs stay in the panel and the existing actions.
- New queries, columns or a migration. The timeline uses only what `view` already holds. If a lane needs more, stop
  and ask.
- A change to what the packet holds, to recall, extraction, workers or settings.

## Questions and proposed answers

| # | Question | Proposed answer | Alternatives |
|---|---|---|---|
| Q1 | Where does it appear? | **Above the tables of the character page, and as a cast strip on the conversation page.** The character page is already the one-person view. | A separate `/timeline` page. |
| Q2 | The panel (`embed`)? | **Amended by the owner: drawn too, in step 3.** It is drawn only when the plugin asks for it (a query flag a new plugin sends). Without the flag the embed output stays byte-identical to today's. The plugin passes bar positions only as numbers. | Not drawn (the first proposal). |
| Q3 | How does a bar show its detail? | **Amended by the owner: as in the mockup, a detail column.** In the browser a short inline script shows it; with no script the bar is a link to its fact's row (`#a-<fact id>`, `:target`). In the panel the plugin shows the detail on a tap. | Links only, no script (the first proposal). |
| Q4 | Which state lanes? | **Every current fact with this character as subject from `facts.py`'s fold**, one lane per fact (its history is the lane), the most recently changed first. Left out: events (their own lane), relationships (Q5) and `knows` (the page's "What they know" table already lists it). | Only standing predicates. |
| Q5 | Which relationships? | **Only those going from this character** (subject = character): `relationship`, `role_toward`, `feels_toward` and `addresses` (speech level). Relationships toward the character stay in the existing Pairs table. | Both directions. |
| Q6 | How is the cast strip ordered, and what folds? | **The current scene's cast first (`scene.py`), then every other character under "N more" in a `<details>`**, each line linking to its character page. | Every character open, by mention count. |
| Q7 | Time windows? | **Amended by the owner: the whole chat, and the last 25 turns** (`?span=recent`). | The last 50 turns (the first proposal); any range from the query. |
| Q8 | Caps on a large chat? | **At most 40 lanes per section, 200 event dots and 120 ticks per cast line.** What is left out is counted ("+N in the table below"). | No caps. |
| Q9 | The persona? | **Drawn on the persona's own character page like any character. Amended by the owner (2026-10-06, after trying it): the persona is also the first cast line, marked as "you".** ADR 0023 keeps the persona's names out of recall, not out of view. | No cast line for the persona (the first proposal). |
| Q10 | Canon facts and owner repairs? | **A canon entry's bar starts at turn 0 and is marked as from the setting (history entries carry `canon`). A current version that is the owner's (the fact's `owner`) is marked as such. Earlier versions carry no owner mark in `view`, so they get none.** | Add the owner mark to history entries (a `facts.py` change, out of scope). |

## After the owner's first try (2026-10-06)

The owner used step 3 in a test instance and found it thinner and busier than the mockup, and missing the persona's
line. The changes, all in rendering:
- **Sizes as in the mockup.** Bars are 22 px on a 26 px track, with rounded bars, group titles, the last change turn at
  the end of a cast line, and a larger value in the detail.
- **A restated value is not a change.** A span that continues the one before it with the same value is one bar. A held
  item restated each turn had drawn a dozen slivers.
- **What did not change folds away.** A lane with one span that is still current goes under a closed "Unchanged facts
  (N)" or "Unchanged relationships (N)". In the recent window, so does a lane whose span began before the window.
- **Two values current at once** (two identities) share one history, and each lane draws only its own current value.
- **A held item's lane is named by the item**, for example "소지: 청동 나침반".
- **The persona's line** (Q9 amended).
- **An early chat folds nothing.** A section of 8 lanes or fewer shows them all, since nothing has changed yet.
- **Events of one turn step aside** instead of covering each other.
- **Tapping a selected mark again closes its detail.**
- **Each group (facts, relationships, threads, events) folds from its title.** The relationships group starts closed,
  because a large cast makes it the longest. The first detail is never chosen from a lane out of sight.

## After the owner's design review (2026-10-07)

The owner reviewed #266 against their trial chat, where a lorebook in another language supplied most of the facts:
- **Quieter lanes.** A lane's name carries its value; bars carry no text, are thinner (6 px minimum), and a one-turn
  bar is drawn above its neighbours. Events are thin ticks, their height by salience. A value from the setting is drawn
  muted.
- **What only the setting gave folds apart.** Lanes, item timelines, rows of the current-facts table and relationship
  pairs whose every step came from the setting (lorebook, card; ADR 0047) fold under their own line ("Only from the
  setting: N") below the story's own. An owner-corrected canon fact stays up.
- **Names as the story writes them.** The fact tables and pair directions show a subject or object by its entity's
  name (the story's spelling, which the resolver already joined to the lorebook's), the written spelling in the
  tooltip, never the persona placeholder. Values stay as written.
- **Threads start closed**, their open and closed counts in the title.
- **On a phone the detail rises as a sheet** from the bottom, after a tap, with a close button; lane names sit beside
  the track; the axis keeps the first, last and every other mark away from "now".

The setting fold and the names apply to the tables of every page, the panel's included: they are how the tables read,
not the timeline. Criterion 3 is amended accordingly.

## Steps

1. This spec, with the owner's answers (approved 2026-10-05).
2. **Implementation**: `timeline.py` (the rendering), wired into `inspector.py` (strings, styles, row anchors) and
   the two Inspector routes (`span`), with tests in `tests/test_inspector_timeline.py`. The tests cover:
   - bars from synthetic history (spans, outcomes, canon at 0, the owner's current version);
   - the caps and their counts;
   - links and anchors;
   - escaping;
   - `embed` unchanged;
   - the persona page;
   - empty states;
   - the recent window.

   No other module changes behavior.
3. **The panel** (one PR, **high risk** under `AGENTS.md` §14: it touches the panel's sanitizer, a security
   boundary). The changes:
   - the plugin asks for the timeline with a query flag;
   - the sanitizer keeps a bar's position only as numbers (a strict pattern, no free `style`);
   - the panel stylesheet gets the timeline from `palette.ts`;
   - a tap shows a bar's detail under its lane;
   - the panel asks for the timeline only when its section is opened, so a chat page in PocketRisu never holds it
     unasked (the iPhone, as above).

   **Implemented** on `claude/phase32-panel`.
   - The sidecar answers `timeline=lazy` with a closed section (`<div class="tl-lazy">`) on a character's or a chat's
     page, and `part=timeline` (with `span`) with the timeline alone in the panel's form: only the tags the panel
     keeps, positions as `data-l` / `data-w`, a mark's text in `data-v` / `data-s` / `data-o` / `data-k` / `data-p`
     (cut to 300 characters), the window as `data-span`, and no `style`, script or link but the Inspector's own.
   - The plugin's `keepAttribute` passes `data-l` / `data-w` only as a number from 0 to 100, `data-span` only as `''` or
     `recent`, and a mark's text only up to 400 characters. `placeMarks` sets the position from the number,
     `markDetail` builds a tapped mark's detail with `textContent`, and the one click listener the panel already had
     answers taps and window switches.
   - Tests: an old plugin's request gets `main`'s bytes (checked byte for byte), and the panel's form passes the
     sanitizer's rules. The plugin tests cover:
     - nothing asked before the section opens;
     - one fetch however often the section opens and closes;
     - one detail however often marks are tapped;
     - the window switch;
     - a mark's markup kept as text.

   Tests:
   - an old plugin's request gets today's bytes;
   - markup that tries to pass anything but numbers is dropped;
   - narrow layout.

   The change ships in a new plugin build.
4. **Measurement and check**: the character and conversation pages timed before and after on the 10,000-message
   scale fixture (`docs/perf/scale.md`'s setup), recorded in `docs/perf/inspector-timeline.md`. The owner looks at
   it in the browser on their own instance, in light and dark and at phone width. The repository records only
   numbers and synthetic screenshots, never chat content.

## Acceptance criteria

1. On the character page, every bar and dot corresponds to one history entry, thread or event in the tables below
   it, with the same turns and outcome, and links to the row of its fact, thread or event (tests).
2. The conversation page has the cast strip with the current scene first and the rest folded (tests).
3. Without the plugin's flag, the `embed` output of both pages holds no timeline and is byte-identical to before
   (test), but for the setting fold and the names of the design review (2026-10-07; their own `<details>` and text,
   which the sanitizer already keeps). With the flag, the panel shows the timeline, and the sanitizer passes only
   numeric positions (plugin tests).
4. No change outside the Inspector's rendering, its two routes' query parameters, the plugin's Inspector view and
   `facts.py`'s display-only `closed_turn` on history entries. The packet, recall and extraction tests pass
   unchanged. The browser page's only script is its inline detail
   script, and the panel runs none from the sidecar.
5. Every value reaches the page through the Inspector's escaping (test with markup in names and values).
6. At 400 px wide the page does not scroll sideways: labels go above their tracks.
7. The added render time at 10,000 messages is measured and recorded. A character page slower than one second
   stops step 4 for the owner.
8. The owner's look in the browser and in the panel, including on the iPhone.

## Stop conditions

- A lane needs data that `view` does not hold (a new query, column or migration).
- Any part needs an external script or library, or a change to the plugin beyond its Inspector view and sanitizer.
- A test outside the Inspector changes (the fold's `closed_turn` adds a field; it changes no outcome).

## Risk

Step 2 is not high risk under `AGENTS.md` §14. It is read-only rendering on the Inspector's existing view, with no
stored data, no memory selection and no security boundary.

Step 3 is **high risk**, because it changes what the panel's sanitizer lets through, which is a security boundary.
It stays narrow: numbers only, behind a flag, with no timeline reaching an old plugin.
