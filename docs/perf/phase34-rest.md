# Phase 34 step 3 — the rest and the threshold, replayed (2026-10-07)

`packet-v14` (ADR 0068): labels (Q1), a supportive line placed in each of the last `rest_after` requests and echoed by
none of their replies left out for two requests (Q2, Q3 as amended), the activation threshold for supportive excerpts
(Q4). Zero model calls; the query embedding on the evaluation Ollama; three replays each.

## Overuse, S1 replayed request by request (Q8 b)

`tools/replay_sequence.py` on the S1 live run of the v0.3.0 bench (`nmos_b030_s1_1`, 241 replayable requests), each
request reading the packets replayed before it. "Supportive" is every supportive line (the story-so-far summary is
required since the Q1 amendment).

| `packet-v14` | Whole: repeat share | Whole: stale token share | Supportive: repeat share | Supportive: stale token share | Supportive lines new to the packet | Lines left out resting |
|---|---:|---:|---:|---:|---:|---:|
| without the rest | 0.524 | 0.214 | 0.315 | 0.063 | 0.685 | 0 |
| `rest_after` 3 | 0.509 | 0.200 | 0.273 (−13 %) | 0.018 (−71 %) | 0.728 | 267 |
| **`rest_after` 2 (default)** | **0.498** | **0.196** | **0.242 (−23 %)** | **0.016 (−75 %)** | **0.758** | **519** |

Three replays agreed within 0.003. **Q9 (b) met** with the default: supportive repeats at least a fifth lower, their
stale tokens at least a third lower, the whole packet not higher; a resting line's slot went to lines new to the
packet (their share rose from 0.685 to 0.758).

How it got there, on the same replay: a tired line moved behind the others (the first Q3) was placed anyway whenever the
budget had room, nearly always on S1 (supportive repeats −6 %); the story-so-far summary held 70 % of the supportive
stale tokens (required now); waking a fact the previous reply named left almost nothing resting (the reply names the
main characters nearly always). A question about the past, and an excerpt the question's own words found, keep every
line: without the two, the bench lost a question about an old detail (S6 `c120_20_early`).

## The bench and the quote set (Q8 c)

| | `packet-v13` | `packet-v14` (`rest_after` 2) |
|---|---|---|
| The v0.3.0 bench, every probe of S0–S6 (sum over 20 sets, per replay) | 286, 285, 285 | 286, 286, 286 |
| Forbidden phrases placed (per replay) | 14, 14, 14 | 14, 14, 14 |
| The quote set | 20–21 / 24 | 21, 20, 20 / 24 |

Every set equal case by case but S4's `s4_del_pet`, which `packet-v13` missed in two replays on its lexical route's
time slice (`docs/perf/phase33-replay.md`). **Q9 (c) met.**

S0main and S0s2 are the owner's real chats: aggregates only. Latency (Q8 e) and the live run (Q8 d) are step 5.
