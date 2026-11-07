# Phase 55 — The memory map: where a chat's memory came from, who is tied to whom, and what happened when

Status: **approved**, 2026-11-02 (an owner request, not a roadmap stage, pulled in by name: "진행 부탁해"). The owner saw
a local prototype of this view on 2026-11-02 and wants it in the product. Q1–Q6 and Q8 as recommended; Q7 amended by the
owner: the caps stay the default and the browser page gets a "show all" link that draws the whole cast ("전체보기
버튼을 만들어서 전부 보여주는것도"). Linear: to be filed by the owner (AGE-39 is Phase 32's time axis and is done).

**Amendment 1 (2026-11-02, the owner: "앵간해선 RisuAI 내부, 즉 플러그인에서 바로 interactive graph를 보고 싶은데",
then "바로 진행해줘"): step 6, the drawing in the panel, interactive.** After the browser page was tried, the owner
wanted the graph inside the panel. Q3 stays (a) for the sanitizer: no SVG goes through it. Instead the sidecar sends the
drawing as data (`GET /v1/views/c/{id}/map/graph`: the same rings' positions, names, kinds, marks, the panel's words),
and the plugin draws it with SVG elements of its own (`graph.ts`), every name as text, never parsed as markup; it checks
every field against a fixed set or a number range and draws nothing on a mismatch. Pan with one finger, pinch or wheel
to zoom, names at a fixed 14 px on screen (shown once nodes are far enough apart, a picked person's ties always);
a tap picks a person and dims everything not tied to them, a second tap opens their own map (`?focus=`); "fit" and
"show all" buttons. No layout runs on the phone. `features.map_graph` gates it; without it, or on any error, the note
that sends the reader to the browser stays. Criterion 8 is amended to the measured growth (below). Q2's "no script"
holds for the browser page; the panel's drawing is the plugin's own code, not a script from the sidecar.

**Amendment 2 (2026-11-07, the owner's look, criterion 10: the whole drawing shows cut off; moving nodes by hand is a
wish, not a need, and stays out because the plugin stays light for an iPhone).** On the longest chat of the trial install
(126 nodes with "show all"), measured in Chromium with the real panel and page: the browser page drew at natural size
(2,599 px wide in a 788 px column, so only a corner showed), and in the panel at 390 px a tap on a node left 31 of 42
picks with a name cut by the edge (up to 117 px). Now: the page's drawing fits the column; past 1,400 units wide its
whole map keeps only the scene's cast and the persona as names, the others in their `<title>` and the lines below (one
person's map keeps every name); in both, a name by a side of the drawing runs inward and a drawn name stops at 24
characters; the panel's fit leaves 36 px whatever the scale. After it: no dot or name outside the drawing on the page,
0 of 42 picks cut at either width. WebKit could not be started on the host, so the owner's iPhone look stays open.

Not high risk (`AGENTS.md §14`) with the answers proposed below: no stored data, schema, extraction, packet, recall or
memory selection changes, and no new tag or attribute through the panel's sanitizer. **Q3 (b) would make step 4 high
risk** (the sanitizer, a security boundary), as PHASE-32 step 3 was.

## Why

On 2026-11-02 a local HTML page built only from the trial install's read APIs (`GET /v1/conversations/{id}/facts`,
`/entities` and `/threads` on the 6113 test sidecar, read-only, no model call) drew one chat as four parts: where its
current facts came from, a graph of who is tied to whom, the story's events by turn, and how much an event record
holds. It showed, on the trial install's longest chat (153 messages, 75 turns; counts only, the repository holds no
chat content):

1. **Most of the memory is the setting.** About 80 % of the current facts came from the lorebook (canon facts, ADR
   0047); the story itself added about 2.8 facts a turn.
2. **The story barely moves the relationships.** Almost every relationship edge was the setting's; story-made changes
   between characters were close to none.
3. **Six characters were two entities each** (a full name of several Hangul words and its first word). This is the
   finding PHASE-54 (draft PR #325) corrects in extraction; on the map it was visible at a glance as pairs of nodes
   with the same edges.
4. **Events are thin.** Most event records had a subject and a sentence, few named who else took part, fewer said why,
   and none can say who did what to whom or which earlier event caused them (the schema has no field for either).

None of this is visible in the panel today. PHASE-52's memory document reads what is true now, line by line; its
"changed from the setting" section lists the story's departures but not how much of the memory the setting supplies.
PHASE-32's time axis shows one person's facts over turns. The Inspector's tables hold every row but no proportions.
The map answers a different question: **is this chat's memory being built from the story, and what shape is it in?**

**A reversal to name.** PHASE-32 (2026-10-05) records that the owner rejected a node-and-edge graph, "which goes
messy as the cast grows", and put "a graph" out of its scope. The prototype's graph is what the owner liked on
2026-11-02. This spec keeps the graph but carries the earlier objection into its design: a cap on nodes, the setting's
edges told apart from the story's, a one-person focus on a phone (Q5), and the same content as plain lines wherever
the graph cannot be read (Q3).

## Goal

One screen per chat, **the memory map**, rendered by the sidecar from the chat's memory as every request reads it
(`memory_view`, the read behind `/facts`, `/entities` and `/threads`), with four sections:

1. **Where the facts came from**: per kind of fact, how many are the setting's only, the story's over the setting's,
   the story's only, or corrected by the owner; and how many facts the story added per turn.
2. **Who is tied to whom**: characters, the groups they belong to and the places they are now, with the setting's
   edges and the story's told apart, and names that look like one person kept as two.
3. **What happened when**: the story's events in turn order, each with its subject, who else took part, its weight
   (salience) and its reason (`because`).
4. **How much an event record holds**: the share of events with participants, a reason and an outcome, and what an
   event record cannot hold at all.

Read-only: the map shows, it never joins, splits, corrects or closes. Each line that has a repair today links to the
place that offers it (a person's sheet, PHASE-20's join preview).

## Scope

### The data (step 2)

A pure module, `memorymap.py`, shapes the four sections from the dictionary `memory_view` already returns (`facts`
with `history`, `entities`, `excluded`, `threads`, `assertions`, `resolution`, `canon_facts`). No new query, column,
migration or model call; the HTTP read APIs are not called, the same in-process read is used.

- **Sources (section 1).** Every current fact (`view["facts"]`) falls in one bucket by its history's `canon` marks, the
  rule PHASE-32's design review set for "Only from the setting":
  - *setting only*: every history step is canon;
  - *story over the setting*: the current version is the story's and an earlier step is canon (the facts PHASE-52's
    "changed from the setting" lists, and the story's restatements of a canon value);
  - *story only*: no step is canon;
  - *corrected by you*: the current version is the owner's (`owner`), whatever came before.

  Counted per predicate, shown in the panel's words ("위치", "관계"…, PHASE-52's change words). Story facts per turn:
  the story's current facts (the two story buckets) over the chat's turns. **Amended at step 5 (2026-11-02):** the
  first draft left `knows` and `event` out of the counts and counted the story's assertions per turn; the prototype
  counted every current fact and the story's current facts, and the map now counts as the prototype did, so the
  owner sees the same numbers for the same chat (acceptance criterion 1).
- **The graph (section 2).** Nodes and edges by the answer to Q4; an entity the owner left out (`entity_exclude`,
  PHASE-47) is not drawn and is counted; the persona is drawn and marked as "you" (PHASE-32 Q9, ADR 0023 keeps the
  persona's names out of recall, not out of view). Suspected split names by the answer to Q5.
- **Events (section 3).** `event` facts of the story (canon events stay with the setting), by turn: subject,
  participants (names as the story writes them, the entity's name when resolved), salience, `because`, `outcome`.
- **Depth (section 4).** Over the story's events: how many name at least one participant, how many carry `because`,
  how many an `outcome`, and the salience split (major, minor, none). Fields the schema has no place for are a fixed,
  quiet note: a participant's part in the event (who did it, to whom), the place it happened, and a link to an earlier
  event that caused it (`because` is free text). Under details only: the same counts per extractor generation, since
  generations record participants and reasons differently (an identifier, so not on the screen itself, PHASE-52 D8).

### The screen (step 3)

`GET /v1/views/c/{id}/map` (`{"html": …}`, as the other screens) and the browser page `/views/c/{id}/map`, in
`views.py`, styled from the PHASE-52 tokens under `.nmos`. Sections in the order above; numbers first, then the
lines. Every section works as plain lines, in the panel's tags only (`div`, `p`, `h1`, `h2`, `span`, `b`, `br`, `a`,
`details`, `summary`). The browser page adds the graph drawing (Q2, Q3), the one place where the browser page carries
markup the panel's fragment does not (a deviation from `views.py`'s rule that they are the same fragments, stated in
its docstring when built).

- **Section 1** as a short list: one line per predicate, its four counts as a quiet stacked bar of positioned `div`s
  (widths as `data-w`, as the timeline's) and the numbers in text beside it; the overall share and the story's facts
  per turn on top.
- **Section 2** in the panel: one line per character, most edges first, with their ties (`관계: …`, `역할: …`,
  `감정: …`) each marked "story", "setting" or "changed from the setting"; then groups and places; then "maybe one
  person?" lines (Q5), each linking to the person's sheet whose details offer the join with its preview (PHASE-20).
  In the browser, the graph drawing above the same lines (Q3).
- **Section 3** as PHASE-52 D4 amendment 2 draws a person's changes, for the whole chat: the overview bar (30 spans,
  at most five rings), then the lines (turn, ring for `major` or dot, subject — text, the participants muted, "because
  …" on a second muted line). Lines fold by span of turns, the latest span open. No third timeline renderer: the bar
  and line helpers of `views.py` / `timeline.circles` are reused.
- **Section 4** as four numbers with their share and the fixed note.

### The panel (step 4)

- The hub gets a **memory map** block, drawn only when the plugin's hub request says it can open the map (a query
  flag, as PHASE-32's timeline flag), so an older plugin's hub is byte-identical to today's.
- `inspector.ts` accepts `/v1/views/c/{id}/map` and its `focus` query as a view path (one more alternative in the
  existing pattern; no new tag or attribute).
- `/v1/health` reports `features.map`; a new plugin with an older sidecar does not draw the block.
- The memory document's foot gets a quiet "memory map" link beside "all facts" and "needs a look".

## Out of scope

- Any change to what memory holds, extraction, the packet, recall, settings or workers.
- New event fields (a participant's part, the event's place, a causal link). Section 4 only names their absence;
  adding them is an extractor generation and its own phase (`docs/STATUS.md`, "Queued for the next extractor
  generation": nothing queued today).
- Joining or splitting from the map. The map links to the existing join preview (PHASE-20); it never acts.
- A charting or graph library, an external script, a web font, a CDN.
- SVG, `img` or `style` through the panel's sanitizer, unless the owner chooses Q3 (b).
- A light theme (PHASE-52, dark only).
- Editing the PHASE-32 time axis or PHASE-52's person sheet; the map links to them.

## Questions and proposed answers

| # | Question | Proposed answer | Alternatives |
|---|---|---|---|
| Q1 | Where does the map live? | **Its own screen, opened from a hub block "memory map" and a link at the foot of the memory document;** the browser page at `/views/c/{id}/map` shows the same (PHASE-52 D9). The memory document reads what is true now; the map is an overview of how it was built, with no identifiers, so it is not a details page either. | (b) A section of the memory document (it is already the longest screen). (c) The Inspector's details (identifier pages; the owner would not find it). |
| Q2 | How is the graph laid out? | **On the server, in Python, by the sidecar's own code, deterministically: concentric rings.** The scene's cast in the middle ring, the other characters by number of ties on the next, groups and places on the outer ring; positions from the order, so the same memory always draws the same map and a new turn moves little. Drawn as inline SVG in the browser page: circles, lines, text, no script. About a hundred lines, no dependency. | (b) A force layout written in Python (fixed seed and iterations): tighter clusters, but nodes move between turns. (c) A vendored JavaScript graph library: a new runtime dependency (`AGENTS.md §8`), a script in the page, and of no use in the panel. |
| Q3 | The graph in the panel? | **(a) Not drawn: the panel shows section 2 as lines** (each character's ties, story/setting marked), with a link that opens the browser page where the sidecar is reachable. No sanitizer change; the iPhone's panel stays light (`nmos-plugin-stays-light`, PHASE-32's page-weight rule). | (b) A strict SVG subset through the sanitizer (`svg`, `circle`, `line`, `text`, numeric attributes only), or the server's SVG shown as an image the plugin fetches with its token: the graph on the phone too, but a sanitizer change, **high risk**, a later step after (a) is tried. |
| Q4 | Which facts are edges? | **Character to character: one edge per pair** carrying `relationship`, `role_toward` and `feels_toward` in both directions (its detail lists each with its direction); `addresses` only in the edge's detail (speech level, too common to draw). **Character to group:** `member_of`. **Character to place:** the current `located_in` only. Not edges: `owes` and `promised` (threads, in the memory document), events (sharing an event would tie almost everyone), `knows` (never drawn). An edge is "setting" when every step of all its facts is canon, "changed from the setting" when a story value replaced a canon one, "story" otherwise. | (b) Events shared as edges (weighted by count). (c) `addresses` as its own edge. |
| Q5 | How are suspected split names flagged? | **A "maybe one person?" line, and a dashed line in the drawing, between two character entities when one's name is a part of the other's by `extraction.name_parts`** (with PHASE-54's Hangul words once merged; the map reuses that helper, never a second rule), **or when one name's words are the first words of the other's.** Never for a pair the owner split (`Resolution.splits`), an entity left out, or the persona with anyone. Each links to the person's sheet; nothing is joined. | (b) Also two entities with the same ties to the same people (catches renamings, more false alarms). (c) No flag; leave it to PHASE-54. |
| Q6 | The phone? | **The panel is lines (Q3). In the browser at under 700 px the whole graph is hidden and the lines show; each character line links to `?focus=<entity>`, which draws that person and their direct ties only** (fits 390 px, server-rendered, no script, like PHASE-32's `?span=`). The default focus is none: lines first. | (b) The whole graph scaled to the width (unreadable past a dozen nodes). (c) The focus view by default on the scene's lead. |
| Q7 | Caps on a large cast? | **At most 24 characters (the scene's cast and the persona always, then by ties and mentions), 8 groups and 8 places in the drawing;** the lines list everyone, by three and "N more" (PHASE-52 D2). Section 3 folds by span; at most 200 event lines rendered, the rest counted. What is left out is counted ("+N"). **Owner (2026-11-02): these caps by default, and a "show all" link beside the "+N" (`?all=1`, server-rendered like `?focus`, no script) draws every character, group and place; hidden under 700 px with the rest of the drawing.** | (b) No cap in the drawing. (c) 12 characters. |
| Q8 | When? | **Build now on `main`, try it on the test install (6131/6113), ship it in the next release:** `0.6.0` if PHASE-54 makes one before `1.0.0` (owner, 2026-11-02, PHASE-54 Q5), else `1.1.0`. It is rendering only, not a heavy change (a packet policy, an extractor generation, a migration), so it does not restart the quiet weeks by itself; `1.0.0` stays `0.5.0`'s build (R8) unless a `0.6.0` is made. Until 1.0 a new phase needs the owner to pull it in by name (R7). | (b) Approve now, build after `1.0.0` is tagged, ship in `1.1.0` (AGE-39's original timing). (c) Into `1.0.0` itself: a new build, an R8 amendment. |

## Steps

1. **This spec**, with the owner's answers (2026-11-02).
2. **The data**: `memorymap.py`, pure, from `memory_view`'s dictionary; `tests/test_memorymap.py` on synthetic
   views: each bucket of section 1 (setting only, story over setting, story only, owner), story facts per turn,
   every edge kind and its setting/story/changed mark, a pair's two directions on one edge, `addresses` in the detail
   only, excluded entities counted and not drawn, the persona marked, the split flag (a part, the first words, an
   owner split not flagged, the persona never), events by turn with participants and reasons, the depth counts.
3. **The screen**: `views.map` and the two routes, the layout of Q2 as a pure function (positions from a list of
   nodes; tested for determinism and for no two nodes on one spot), the browser page's SVG, `?focus`. Tests: the
   panel fragment uses only the sanitizer's tags and attributes (checked against the plugin's list, as PHASE-52's
   tests do), chat text escaped everywhere (names and values with markup), caps and their counts, empty states (a
   chat with no extraction yet, no canon, no events), Korean and English.
4. **The panel**: the hub flag and block, the view path in `inspector.ts`, `features.map`, the memory document's
   link. Plugin tests: an old hub request gets today's bytes; the map path and `focus` pass, other paths do not;
   gzipped size recorded.
5. **Check**: render times at 10,000 messages (`docs/perf/scale.md`'s setup) recorded in `docs/perf/memory-map.md`;
   the trial install's chats read through the map, numbers only, and compared with the prototype's counts of
   2026-11-02 (the same chat should give the same shares); screenshots at 390 px and 1,100 px on synthetic data only;
   the owner's look on an iPhone and a desktop.
6. **The drawing in the panel** (amendment 1): `views.map_graph` and its route, `graph.ts` and its loading in
   `ui.ts`; tests: the data's shape and caps (sidecar), a spoiled field refused, names as text, fit and zoom
   arithmetic, a tap picks, a second tap opens, a drag is not a tap, the note stays without the feature (plugin).

## Acceptance criteria

1. Every number on the map equals a count over `memory_view`'s result for the same head (tests on synthetic views),
   and on the trial install's longest chat the shares of section 1 match the 2026-11-02 prototype's within the facts
   added since (step 5).
2. Every edge corresponds to at least one current fact of a Q4 predicate, with the setting/story/changed mark its
   history gives (tests).
3. A "maybe one person?" flag appears only by Q5's rule, never for an owner split, a left-out entity or the persona
   (tests).
4. The panel fragment holds only the sanitizer's tags and attributes, no table, no identifier (generation key,
   commit, endpoint) outside details, body text 16 px and nothing under 13 px (PHASE-52 D8), and every value escaped
   (tests).
5. Without the plugin's flag the hub is byte-identical to today's (test); an older plugin is unaffected, a newer
   plugin with an older sidecar draws no map block.
6. At 390 px neither the panel screen nor the browser page scrolls sideways (the whole graph hidden, the lines and the
   focus view shown).
7. The map at 10,000 messages renders in under one second; slower stops step 5 for the owner (PHASE-32 criterion 7).
8. The plugin's gzipped build grows by at most 2 % (one block flag and one path; 69,576 bytes at PHASE-52).
   **Amended (amendment 1):** with step 6's drawing, at most 5 %; measured 70,344 → 73,780 bytes (+4.88 %, `gzip -9`
   against `main` at `446d5fb`, with amendment 2).
9. No test outside the map, the views, the hub flag and the plugin's view path changes; the packet, recall and
   extraction tests pass unchanged.
10. The owner's look on an iPhone and a desktop.

## Stop conditions

- A section needs data `memory_view` does not hold (a new query, column or migration).
- The graph needs a library, an external script, or SVG, `img` or `style` through the sanitizer (unless Q3 (b) is
  chosen, which is its own high-risk step).
- The map is slower than one second at 10,000 messages.
- The owner's look finds the graph unreadable at the trial install's cast size: the drawing is dropped and the lines
  stay (the earlier rejection in PHASE-32 stands for that case).

## Risk

Not high risk under `AGENTS.md §14` with Q3 (a): read-only rendering over the view every request already reads, no
memory selection, no stored data. The plugin's view-path pattern is part of the sanitizer; adding one fixed path keeps
its rules (no tag, attribute or free `style`), and the step 4 review checks exactly that. Q3 (b) would be **high risk**
(security boundary) and is a separate, later step.
