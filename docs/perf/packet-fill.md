# A packet that fills its budget — what-if, and PocketRisu v1.13.0 numbers (2026-09-29)

Measured while comparing NMOS with another long-term memory plugin ("plugin B"; that comparison is kept outside the
repository). This page keeps what concerns NMOS alone: the packet's size against its budget (K33), a what-if that
scales recall with the budget, latency and first sight on PocketRisu v1.13.0, and two evaluation pitfalls.

Numbers only. The M0 datasets are the owner's chats (PHASE-11 Q1).

## Setup

- **Cases.** The owner's two M0 datasets:
  - the main chat: 73 turns, ≈918,000 characters; M0-28 and M0-12 at the request of turn 73, 40 cases, 21 of them
    needing memory, 16 forbidden phrases;
  - sample 2: 35 turns, ≈114,000 characters; the 15 cases on window B (the two isolation cases need other chats),
    13 needing memory, 4 forbidden phrases.

  Owner repairs (Phase 13) were not applied.
- **Extraction.** Two generations of each chat: the production `gemma4:31b-cloud` (`extract-v13`), and
  `deepseek-v4.1-flash` over every turn on copies of the test databases. Summaries of the same model are on.
- **Replay.** `audit.replay` of the cases' traces with the case's question, `packet-v8`, scored with
  `tools/eval_rp.py`'s `score`, on read-only connections.
- **Vectors on.** The chats' own `qwen3-embedding:8b` projection, the query embedded by the local Ollama, the model
  warmed first (see the first pitfall below).

## The packet ignores its budget (K33)

`packet-v8` compiles ≈1,800–2,900 tokens at any budget from 2,000 to 20,000. Recall's limits stop it first
(`RecallOptions`: 5 excerpts of at most 480 characters, 8 facts, 3 events, 3 threads). Main chat, deepseek:
30 passed at 2,000, 31 at every budget from 4,000 to 20,000, all at ≈2,200 tokens.

## What-if: scale recall with the budget

Two variants, replayed outside the repository with the limits overridden (`f` = budget / 2,000):

- **all grow:** excerpts `5f`, each up to `480f` characters (at most 2,400); facts `8f`; events `3f`; threads `3f`;
- **excerpts and facts:** excerpts as above; facts `8 × min(f, 2)`; events, threads, secrets, `<Cast>` and `<Story>`
  as today.

Passed / needing memory / forbidden placed (tokens):

| Chat, extraction | 2,000 today | 4,000 all | 8,000 all | 16,000 all |
|---|---|---|---|---|
| main, gemma4 | 32, 13/21, 0 (1,904) | 35, 16/21, 1 (3,133) | 36, 18/21, 2 (5,335) | 33, 17/21, 10 (9,415) |
| main, deepseek | 30, 11/21, 0 (1,910) | 32, 13/21, 2 (3,424) | 33, 14/21, 2 (5,865) | 32, 16/21, 8 (10,507) |
| sample 2, deepseek | 9, 8/13, 1 (1,755) | 12, 11/13, 1 (3,897) | 12, 11/13, 1 (6,656) | 12, 11/13, 1 (8,451) |
| sample 2, gemma4 | 10, 8/13, 0 (1,743) | 11, 9/13, 0 (2,654) | 11, 9/13, 0 (4,122) | 11, 9/13, 0 (5,696) |

| Chat, extraction | 4,000 excerpts+facts | 8,000 excerpts+facts | 16,000 excerpts+facts |
|---|---|---|---|
| main, gemma4 | 36, 17/21, 1 (2,919) | 36, 17/21, 1 (3,663) | 36, 17/21, 1 (5,079) |
| main, deepseek | 31, 12/21, 1 (3,202) | 31, 12/21, 1 (3,946) | 33, 14/21, 1 (5,362) |
| sample 2, deepseek | 12, 11/13, 1 (3,861) | 12, 11/13, 1 (5,916) | 12, 11/13, 1 (7,490) |
| sample 2, gemma4 | 11, 9/13, 0 (2,652) | 11, 9/13, 0 (4,120) | 11, 9/13, 0 (5,694) |

- **Growing everything places stale lines.** At 16,000 (main, gemma4) the 10 forbidden phrases stood in open threads
  (8 times), secrets (8), claims (3), facts (2) and one excerpt; a phrase can stand in more than one.
- **Growing excerpts and facts only keeps the gains without them.** Over the four runs at 4,000: +9 cases needing
  memory and +2 forbidden against today's 2,000. Flat from 4,000 to 16,000.
- **Consistent with the position paper.** Room given to raw words pays; room given to open business costs
  (`docs/proposals/ACCOUNTABLE-MEMORY.md` §2).
- **gemma4 extraction beats deepseek flash for NMOS** on the main chat at every budget.

Phase 15 (`docs/phases/PHASE-15.md`, approved 2026-09-29).

## PocketRisu v1.13.0 (5,000 messages, stubs)

The synthetic chat of `docs/perf/scale.md`, stub models, click → model request, one untimed warm-up and five sends:

| Condition | Median (range) |
|---|---:|
| NMOS off | 3.09 s (3.06–3.10) |
| NMOS on, no facts or vectors | 4.13 s (4.07–4.17) |
| NMOS on, 7,500 facts and 5,123 vectors | 3.99 s (3.94–4.09) |

NMOS adds ≈0.9–1.0 s per warm generation (its `request done` total 0.8–1.1 s: sync ≈0.35–0.65 s, retrieve ≈0.25–0.45 s).
The first sync of this chat took 7.4 s. Stub extraction of the whole chat took 269 s (2,559 extractions, 5,123
embeddings, two workers). With `deepseek-v4.1-flash`, the main chat's 73 turns (≈12,000 characters a turn) took
≈31 min: one worker, a second from the 11th minute, ≈40 s a call.

Two host facts for anyone testing on v1.13.0: the chat-model request leaves from the browser, while NMOS's requests
(V3 `nativeFetch`) go through the PocketRisu server, so the sidecar must be reachable from the server.

## Pitfalls found

- **A replay silently drops vectors** when the trace's recorded embedding projection is not the one the evaluation
  embeds with (`audit.replay` notes "vectors of the trace's projection unavailable: lexical only"). The first numbers
  of this run were lexical-only for that reason (main 28/40, sample 2 6/15; deepseek, 2,000). Check the notes of every
  replayed case (Phase 15 Q6).
- **`qwen3-embedding:8b` loads cold in ≈18 s** on the local Ollama; warm, a query embeds in ≈50 ms. The request path
  gives the query embedding 300 ms and falls back to lexical recall (PHASE-3), so a request after the model was
  unloaded recalls without vectors (K34). How often that happens in production was not measured.

## The `packet-v8` baseline with vectors (Phase 15 step 2)

`tools/eval_rp.py` now searches a named projection (`--projection`, the copies' full `qwen3-embedding:8b` projection
here), warms the embedder before the first case, gives each replay's query 5,000 ms, and reports per case whether
vector search ran; with vectors asked for, a case without them makes it exit with status 2 (Phase 15 Q6). The replay
itself says so (`vectors`: on, off, or the fallback's reason), and searches a named projection as it is now, with its
model's query prefix (the rest of the request as of its time). `packet-v8` at 2,000 tokens on the same copies:

| Chat, extraction | Passed | Needing memory | Forbidden placed | Mean tokens | With vectors |
|---|---:|---:|---:|---:|---:|
| main, gemma4 `extract-v13` | 32/40 | 13/21 | 0 | 1,904 | 40/40 |
| main, deepseek-v4.1-flash | 30/40 | 11/21 | 0 | 1,910 | 40/40 |
| sample 2, deepseek-v4.1-flash | 9/15 | 8/13 | 1 | 1,755 | 15/15 |
| sample 2, gemma4 `extract-v13` | 10/15 | 8/13 | 0 | 1,743 | 15/15 |

These are the what-if's baselines to the case, now with every case confirmed to have run with vectors. Without
`--projection`, the same copies ran without vectors in every case (the settings of a copy name no embedder), and the
tool said so and exited with status 2.

## Evaluation of `packet-v9` (Phase 15 step 5)

### M0, with vectors, `packet-v9` at 4,000 against `packet-v8` at 2,000

The same copies, cases, generations and projection as the baseline above (`tools/eval_rp.py --projection`; every case
ran with vectors).

| Chat, extraction | `packet-v8` at 2,000 | `packet-v9` at 4,000 | Needing memory | Forbidden placed | Mean tokens |
|---|---|---|---:|---:|---|
| main, gemma4 | 32/40, 13/21 | 34/40, 15/21 | +2 | 0 → 1 | 1,904 → 2,767 |
| main, deepseek | 30/40, 11/21 | 30/40, 11/21 | +0 | 0 → 1 | 1,910 → 2,933 |
| sample 2, deepseek | 9/15, 8/13 | 12/15, 11/13 | +3 | 1 → 1 | 1,755 → 3,811 |
| sample 2, gemma4 | 10/15, 8/13 | 11/15, 9/13 | +1 | 0 → 0 | 1,743 → 2,648 |
| **Total** | | | **+6** | **+2** | |

Against the criteria (PHASE-15): cases needing memory +6 (at least +6); forbidden phrases +2 (at most +2), both an
excerpt, none from a thread or a secret; no category worse by more than one case. The two new forbidden phrases are the
same old excerpt on the longest chat under both extractions: an early message in the speech level two characters used
before they changed it, which the case forbids as current. It cost that case (address, one per extraction). Over the
four runs the cases gained are early scenes (+4), the cast (+3) and state (+1); address lost 2.

The what-if gave +9. The difference is the Codex finding of step 3: the added fact slots go only to facts kept from no
one, where the what-if grew every fact.

### The owner's recorded requests

Every recorded request of the two copies that still replays (13 and 25; 10 are on a chat edited since), as of its own
time, with vectors of the full projection (`~/nmos-eval/phase15-fill/traces_v9.py`, outside the repository).

| | Longest chat's copy | Sample 2's copy |
|---|---:|---:|
| Lines only `packet-v9` places (both at 4,000) | 26 facts, 22 claims, 20 excerpts | 26 facts, 22 claims, 6 excerpts |
| … of them secrets, private lines or threads | **0** | **0** |
| Mean excerpts placed (`packet-v8` → `packet-v9`, both at 4,000) | 2.0 → 3.5 | 0.4 → 0.6 |
| Mean facts and claims placed | 12.0 → 15.7 | 7.1 → 9.0 |
| Mean private lines, threads | 2.3, 1.4 → the same | 1.4, 0.9 → the same |
| Lines the next reply echoed, placed at 4,000 (`packet-v9`) | 4 of 4 | 3 of 4 |

The lines the replies echoed had all been cut for the budget when recorded (the plugin's default was then 600), so the
larger packet crowds out none of them; it places 7 of the 8. Against each request's own recorded budget instead of
4,000, `packet-v9` at 4,000 also places private lines and threads the small packets had no room for (30 and 18): that is
the larger budget, not the policy, and a budget the user raised under `packet-v8` placed them too.

### Latency (`tools/bench_story.py`, 10,000 messages)

Retrieve p50, the median of five rounds, each round running `packet-v8` at 2,000, `packet-v9` at 4,000 and `packet-v9`
at 8,000 in turn, pinned to two cores. The largest recall (`BENCH_RECALL=wide`): every message has a vector near the
query's, and each request asks for a place's scenes, so recall offers more than any budget takes.

| | retrieve p50, ms | against `packet-v8` at 2,000 | excerpts placed | packet tokens |
|---|---:|---:|---:|---:|
| `packet-v8`, 2,000 | 315.1 | | 5 | 645 |
| `packet-v9`, 4,000 | 310.4 | −4.7 (criterion +10) | 10 | 1,056 |
| `packet-v9`, 8,000 | 312.2 | −2.9 (criterion +25) | 20 | 1,276 |

The rounds spread by ±15 ms; the policy adds nothing measurable. The absolute time is high because this question makes
lexical recall run to its 300 ms timeout in every configuration (the default bench, whose questions do not, is
≈120 ms): ranking every fact once, 15 more excerpts and a larger packet cost less than the spread.

### Real host

An isolated PocketRisu v1.13.0 with stub models (2026-09-29), the plugin of steps 3 and 4. Each check passed:

- **The new default applies.** A freshly installed plugin with no budget set shows 4,000 in the panel, and requests
  carry 4,000 (`packet-v9`, `fill` 2.0). 99999 typed in the panel is stored as 8,000.
- **The packet grows to it.** With a short-window preset and 34 synthetic logbook entries, the same kind of question
  at 2,000, 4,000 and 8,000 got 3, 7 and 19 excerpts and 8, 16 and 16 facts; token estimates 1,916, 3,868 and 7,940,
  each within its budget. Excerpts were bounded by the budget, not their limits (5, 10, 20); 31–40 candidates.
  Excerpts of 623 and 619 characters (over `packet-v8`'s 480) came into the 8,000 packet from long entries.
- **The budget advice is inside the range.** At 300 tokens with about 100 facts, 7 lines were cut and the Status tab
  offered 1,200 (above 300, at most 8,000); the button set it.
- **Recall without vectors is shown** (step 4). An embedding stub delayed by 1 s gave `vectors: fallback` and the
  Status tab's notice; the next request with vectors cleared it.

It found one display bug, fixed in this step: after saving a budget above 8,000, the field kept showing what was
typed although 8,000 was stored.
