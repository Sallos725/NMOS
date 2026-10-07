# Phase 34 step 2 — labels recorded, the sequential baseline (2026-10-07)

`packet-v14` at step 2 labels every ledger line (PHASE-34 Q1) and places what `packet-v13` places. Measured with
`tools/replay_sequence.py` (new, Q8 b): the S1 live run of the v0.3.0 bench (`nmos_b030_s1_1`, 240 turns; synthetic
chat) compiled again request by request in the order the requests were made, under each policy, zero model calls,
vectors on (the bench's embedder on the evaluation Ollama). 241 of its 340 recorded requests replay; the 99 skipped
are the bench's probes, whose messages the harness deleted after asking.

| Policy | Requests | Repeat share | Streak p50 / p90 / max | Stale token share | Mean tokens placed |
|---|---:|---:|---|---:|---:|
| `packet-v13` | 241 | 0.522 | 1 / 3 / 16 | 0.214 | 2,105 |
| `packet-v14` (step 2) | 241 | 0.522 | 1 / 3 / 16 | 0.213 | 2,106 |

The two place the same lines (the 0.001 is the vector route's run-to-run noise). The recorded run measured 0.614 and
0.381 over all 340 requests (`docs/perf/phase33-baseline.md`); the replay leaves the probes out and compiles every
packet again, so the replay's own `packet-v13` row is the reference for Phase 34 (Q9).

## By label (`packet-v14`)

| Label | Placed lines | Placed tokens | Of the repeated lines | Of the stale tokens |
|---|---:|---:|---:|---:|
| required | 0.571 | 0.547 | 0.638 | 0.439 |
| supportive | 0.429 | 0.453 | 0.362 | 0.561 |
| risky | 0 | 0 | 0 | 0 |

Most repetition is required lines (the state, the cast, what the question names), which a packet should repeat while
they hold; the supportive lines are fewer but hold most of the stale tokens (excerpts and Story are long). The rest
(Q3) acts on supportive lines only, and only from the fourth request in a row: removing every repeated supportive line
would lower the whole packet's repeat share by at most 36 %, and the first two repeats of a line stay. Q9's bar on the
whole packet's repeat share (a quarter lower) is therefore out of reach by construction; the stale token share's (a
third lower) is not. **For the owner:** measure Q9 (b) on supportive lines (their repeat share and stale token share),
which is what §49 asks about, and keep the whole-packet numbers as a report.
