# Memory map at 10,000 messages, and the trial install through it (PHASE-55 step 5)

Measured 2026-11-02 on the owner's host. No model is called.

## Render time

`tools/bench_map.py` against the test PostgreSQL 16 (:5436), one throwaway database per fixture, the app in-process
(`TestClient`: request parsing included, network excluded). Each page twice to warm up, then 20 times: p50 / p95 / max
in ms, and the HTML's size in KB (the `html` field for the panel's routes).

- **Fixtures** (`tools/bench_inspector.py`'s, see `inspector-timeline.md`): `base` is `scale.md`'s chat of 10,000
  messages with one `located_in` per turn (40 characters); `heavy` adds one character with one assertion on every turn
  across eight predicates, among them a relationship and a feeling toward the 40 others and 625 events.
- The run used the code before the review's last change to the split-name check (every pair compared instead of by
  name): an upper bound for that part. Other agents worked on the same host; run to run a page varies by about ±15 ms.

| Page | `base` p50 / p95 / max | KB | `heavy` p50 / p95 / max | KB |
|---|---|---:|---|---:|
| Hub, panel, old plugin | 284 / 312 / 317 | 1.2 | 403 / 467 / 477 | 1.2 |
| Hub, panel, `map=1` | 270 / 315 / 333 | 1.4 | 402 / 438 / 440 | 1.4 |
| Memory document, panel, old plugin | 203 / 237 / 240 | 2.3 | 348 / 360 / 385 | 17.8 |
| Memory document, panel, `map=1` | 202 / 239 / 239 | 2.4 | 338 / 365 / 372 | 17.9 |
| **Map, panel** | 113 / 145 / 150 | 16.6 | 242 / 260 / 260 | 88.4 |
| **Map, browser** | 115 / 151 / 168 | 31.9 | 242 / 262 / 283 | 105.1 |
| **Map, browser, `all=1`** | 121 / 157 / 169 | 36.7 | 255 / 279 / 279 | 111.1 |
| Map, panel, `focus` | 118 / 162 / 162 | 0.8 | 238 / 263 / 281 | 10.5 |
| Map, browser, `focus` | 115 / 149 / 158 | 8.1 | 235 / 259 / 260 | 29.6 |

Every map page is well under the one second of acceptance criterion 7, and faster than the hub and the memory
document, which read more besides the memory view (the attention queue, coverage, summaries). The flag adds nothing
measurable to the hub or the memory document. The heavy panel map's 88 KB are mostly its 200 event lines (the cap).

## The trial install through the map

The trial install's database (`nmos_p32_try`, 6113's), opened in a read-only transaction with the active extractor and
canon generations, the three longest chats. Numbers only.

| Chat | Messages / turns | Current facts | The setting's only | Story facts a turn | Ties: setting / story / changed | Maybe one person? |
|---|---|---:|---:|---:|---|---:|
| Longest | 153 / 77 | 1,077 | 80.3 % | 2.8 | 92 / 10 / 0 | 5 |
| Second | 121 / 61 | 737 | 77.2 % | 2.8 | 57 / 6 / 1 | 4 |
| Third | 99 / 50 | 618 | 72.0 % | 3.5 | 23 / 9 / 2 | 0 |

The longest chat gives the 2026-11-02 prototype's numbers ("about 80 %", "about 2.8 a turn", almost no story-made
relationship changes), once section 1 counts as the prototype did: every current fact, `knows` and events included, and
the story's current facts per turn. The spec's first draft left `knows` and events out (88.1 % on the same chat) and
counted the story's assertions per turn (6.2), so the spec was amended at this step. The prototype counted six split
characters; the map flags five pairs by the name rule (PHASE-54 was deployed to 6113 the same evening, and earlier
turns keep their extraction).

Event records on the longest chat: 96 story events, 87 naming someone else, 35 with a reason, none with an outcome
(the field is for a thread's end), 53 major and 43 minor.

## Screens

Synthetic data only (fictional names), Chromium at 1,100 and 390 px: no sideways scroll on any of the three forms
(browser page, one person's map, panel fragment); no text under 13 px. Under 700 px the whole drawing is hidden; one
person's map is scaled to the width (its neighbours on one ring), its labels at 15.6 px for four ties. With more than
about eleven ties the labels of that drawing fall under 13 px at 390 px; the lines below it carry the same content.
