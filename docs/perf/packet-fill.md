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
itself says so (`vectors`: on, off, or the fallback's reason). `packet-v8` at 2,000 tokens on the same copies:

| Chat, extraction | Passed | Needing memory | Forbidden placed | Mean tokens | With vectors |
|---|---:|---:|---:|---:|---:|
| main, gemma4 `extract-v13` | 32/40 | 13/21 | 0 | 1,904 | 40/40 |
| main, deepseek-v4.1-flash | 30/40 | 11/21 | 0 | 1,910 | 40/40 |
| sample 2, deepseek-v4.1-flash | 9/15 | 8/13 | 1 | 1,755 | 15/15 |
| sample 2, gemma4 `extract-v13` | 10/15 | 8/13 | 0 | 1,743 | 15/15 |

These are the what-if's baselines to the case, now with every case confirmed to have run with vectors. Without
`--projection`, the same copies ran without vectors in every case (the settings of a copy name no embedder), and the
tool said so and exited with status 2.
