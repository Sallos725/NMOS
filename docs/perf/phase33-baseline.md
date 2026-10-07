# Phase 33 step 2 — the baselines (2026-10-07)

Zero-call measurements on the v0.3.0 bench databases (`0ace76c`, `extract-v16`, `packet-v12`; the S0–S6 bench of
2026-10-05/06), before any Phase 33 change. Numbers only; the real chat's cases stay with the owner.

## The exact-quote set (Q10 b)

24 questions on the synthetic chat (`fixtures/quotes/s3-quotes.json`): 8 ask by turn number ("14턴에 … 뭐라고 했어?"), 8 by a
first cue ("처음 만난 날 …"), 8 by a speaker and words. Every quote is said in turns 1–58 and the request is the S3 set's
recorded request at turn 100 (32k context, about 22 turns in the prompt), so none is in the prompt: memory must bring it.
`tools/eval_rp.py --policy packet-v12`, the query embedded by the bench's embedder (local), three replays.

| Set | Passed (each of 3 replays) |
|---|---|
| by turn | 1 / 8 |
| by a first cue | 2 / 8 |
| by speaker and words | 1 / 8 |
| **all** | **4 / 24** |

The three replays agreed case by case. In all 24 the lexical route found the message that holds the quote; the excerpt
grew around the sentence that best matched the question's words (median 105 characters) and left the quote out. The bar
(PHASE-33 Q11) is 20 of 24 with the source turn and the words.

## The overuse baseline (Q8)

`tools/overuse_report.py` over every recorded request, in order. S1 is the live-play set (240 turns, 340 requests, echo
checked on the 240 with a reply); the S0 and S2 requests are probes, which have no reply to check echo against.

| Set | Requests | Repeat share | Streak p50 / p90 / max | Stale token share | Echo: new / repeated |
|---|---|---|---|---|---|
| S1 (live, 240 turns) | 340 | 0.614 | 1 / 3 / 35 | 0.381 | 0.246 / 0.106 |
| S3 (main chat) | 46 | 0.340 | 1 / 3 / 12 | 0.077 | 0.285 / 0.173 |
| S0 main (real chat, probes) | 81 | 0.607 | 1 / 3 / 80 | 0.316 | — |
| S2 (240 turns, probes) | 52 | 0.508 | 1 / 3 / 50 | 0.254 | — |

*Note (2026-10-07, Phase 34):* the bench's chat model is a stub that plays scripted replies (`mode: script`), so a
reply never depends on the packet: the echo columns measure how much of a line the script happens to reuse, not how a
model uses memory. The placement numbers (repeat share, streaks, stale tokens) do not depend on the replies and stand.
Echo before and after Phase 34 is measured on real replies (`docs/phases/PHASE-34.md` Q8 d).

In live play 61 % of a packet's lines were placed in the request before it too, and 38 % of its tokens went to lines
placed in each of the three requests before it; a repeated line was echoed by the reply less than half as often as a
new one (10.6 % against 24.6 %). Phase 34's overuse penalty is measured against these.

## The form of address used before (Q6)

The real-chat case that asks how one character first addressed another misses because the first form was never
extracted: none of the chat's 17 `addresses` facts holds it. An extraction cause, recorded as K44; no recall change in
this phase. Whether the quote route reaches the earliest lines that character said is measured in step 3.
