# Inspector timeline render time at 10,000 messages (PHASE-32 step 4)

Measured 2026-10-09 on the owner's host with `tools/bench_inspector.py`, against the test PostgreSQL 16 (:5436), one
throwaway database per fixture and side. No model is called.

- **Before:** `origin/main` at `03b4133` (v0.3.0 with #267, #268, #269 and #271): no timeline, no status lanes.
- **After:** `fix/pre040-audit` at `9a303bd` (PHASE-32 steps 2–3 and PHASE-39). "After − before" is everything between
  the two commits, not the timeline alone. At most the timeline's own share is the gap, on the after side, between
  the browser page and the panel's old-plugin form of it, which has no timeline (and also no page shell, language
  switch or head-turn query).

## Method

- **Chat:** `docs/perf/scale.md`'s synthetic chat of 10,000 messages (`bench_scale.build_chat`: Korean prose of
  ≈1.5 kB per reply), synced through the plugin's routes, then one extraction generation over every turn
  (`bench_scale.add_generation`: one `located_in` per turn, 40 characters in turn), then `ANALYZE`.
- **Fixtures**, each in its own database:
  - `base`: the setup above. Every character has one fact with 125 history entries. Its place never changes (turn
    `k + 40j` always gets the same place), so a character's timeline is one lane with one bar.
  - `bar`: the same chat with a one-line status bar at the end of every reply (`☆ [Level: … | Gold: … | Items: …]`;
    level, gold and items change every 40, 3 and 5 turns), read by the block rule
    `{"id":"bar","kind":"block","role":"char","start":"☆ \\[","end":"\\]\\s*$","separator":"|"}`
    (`Settings(parsers_file=…)`). 15,000 state observations after; 5,000 before (main has no `separator` and reads the
    bar as one field).
  - `heavy` (beyond the named setup): `base` plus one more character with one assertion on every turn, eight
    predicates in turn (place, status, relationship and feeling toward the 40 others, traits, events, goals,
    identity): 746 facts with 4,999 history entries. Its page draws 83 lanes, 1,307 bars and 200 event dots (the
    cap).
- **Characters timed:** the one with the most facts and the median one (in `base` and `bar` all 40 are alike).
- **Timing:** the app in-process (`TestClient`: request parsing included, network excluded). Each page twice to warm
  up, then 20 times: p50 / p95 / max in ms. The size is the HTML in KB (for the panel routes, the `html` field of the
  JSON). Pages the code does not have (`part=…`, `timeline=lazy`, `status=lazy`, `span=recent` on main) are not timed
  on that side: FastAPI would ignore the unknown query and answer with the plain page.
- Host: 16 cores, load ≈1.5 from other services; other agents worked on the same host. Run to run, the same page
  varied by about ±15 ms (a repeat of `bar` on the after side agreed within that).

## Results

### `base` (the named setup)

| Page | Before p50 / p95 / max | After p50 / p95 / max | After − before (p50) | KB before → after |
|---|---|---|---:|---|
| Character page, browser, whole chat | 97 / 132 / 142 | 108 / 142 / 143 | +11 | 8.7 → 22.4 |
| Character page, browser, recent 25 turns | — | 110 / 150 / 156 | | 17.8 |
| Character page, browser, median character | 97 / 131 / 133 | 113 / 155 / 184 | +16 | 8.7 → 22.4 |
| Character panel, old plugin | 98 / 135 / 162 | 106 / 145 / 155 | +8 | 6.5 → 6.6 |
| Character panel, `timeline=lazy` | — | 106 / 151 / 151 | | 6.8 |
| Character panel, `part=timeline` (whole / recent) | — | 106 / 141 / 143 · 104 / 142 / 154 | | 5.1 · 1.0 |
| Conversation page, browser, whole chat | 329 / 353 / 382 | 335 / 357 / 359 | +6 | 1,015 → 1,181 |
| Conversation page, browser, recent 25 turns | — | 329 / 355 / 356 | | 1,175 |
| Conversation panel, old plugin | 322 / 347 / 354 | 322 / 361 / 363 | 0 | 1,013 → 1,154 |
| Conversation panel, `timeline=lazy&status=lazy` | — | 327 / 363 / 366 | | 1,155 |
| Conversation panel, `part=timeline` (whole / recent) | — | 112 / 153 / 154 · 111 / 143 / 143 | | 18.5 · 12.7 |

On the after side, the browser character page took 2 ms (p50) more than the panel's old-plugin form without the
timeline, and the conversation page 13 ms more (upper bounds for the timeline: see above). A character page's
≈100 ms is the memory view built for every request (`memory_view` over 5,000 assertions), on both sides.

### `bar` (status lanes, PHASE-39)

| Page | Before p50 / p95 / max | After p50 / p95 / max | After − before (p50) | KB before → after |
|---|---|---|---:|---|
| Conversation page, browser, whole chat | 359 / 391 / 394 | 496 / 681 / 718 | +137 | 1,015 → 1,293 |
| Conversation page, browser, recent 25 turns | — | 476 / 495 / 497 | | 1,184 |
| Conversation panel, old plugin | 353 / 390 / 396 | 367 / 416 / 420 | +14 | 1,013 → 1,154 |
| Conversation panel, `timeline=lazy&status=lazy` | — | 470 / 505 / 516 | | 1,155 |
| Conversation panel, `part=status` (whole / recent) | — | 81 / 121 / 121 · 79 / 119 / 120 | | 68.5 · 3.8 |
| Character page, browser, whole chat | 96 / 136 / 145 | 107 / 144 / 145 | +11 | 8.7 → 22.4 |

The status lanes draw 3 keys and 360 bars (15 in the recent window). A repeat run gave 484 / 503 / 525 for the browser
page; the first run's p95 and max were noise. **The panel's `status=lazy` page costs ≈100 ms more than the old
plugin's** (470 vs 367; repeat 462 vs 366) although it holds only an empty section: `inspector_detail_html` builds the
whole status history (`state_history`) to count the changed keys for the section's header, then draws none of it.

### `heavy` (one character with 746 facts, beyond the named setup)

| Page | Before p50 / p95 / max | After p50 / p95 / max | After − before (p50) | KB before → after |
|---|---|---|---:|---|
| Character page, browser, whole chat | 204 / 238 / 246 | 250 / 298 / 309 | +46 | 314 → 787 |
| Character page, browser, recent 25 turns | — | 231 / 265 / 277 | | 439 |
| Character panel, old plugin | 220 / 236 / 256 | 235 / 258 / 266 | +15 | 312 → 379 |
| Character panel, `part=timeline` (whole / recent) | — | 224 / 271 / 272 · 211 / 259 / 272 | | 288 · 36.5 |
| Median character, browser, whole chat | 217 / 239 / 249 | 206 / 244 / 244 | −11 | 10.4 → 24.6 |
| Conversation page, browser, whole chat | 465 / 491 / 495 | 480 / 509 / 521 | +15 | 1,133 → 1,339 |
| Conversation panel, `part=timeline` (whole / recent) | — | 233 / 251 / 269 · 218 / 270 / 284 | | 23.9 · 13.5 |

The heavy character's browser page took 15 ms (p50) more than its old-plugin panel form on the after side; the page grew
from 379 to 787 KB.

## Acceptance criterion 7

**Passed.** The slowest character page at 10,000 messages took 184 ms (max of 20) in the named setup and 309 ms for
the heavy character, against the stop at one second. The timeline itself adds at most 2 ms (named setup) to 15 ms
(heavy) to a character page; most of a page's time is the memory view, which the pages before the timeline already built.

## What it does not measure

The browser's own layout and paint of the larger pages (787 KB for the heavy character), the iPhone panel, the host's
proxy and network, threads (`threads.py`), canon facts and embeddings (none in these fixtures), the owner's own chats,
and more than one extraction generation.
