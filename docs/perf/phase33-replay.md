# Phase 33 step 3 — `packet-v13` replayed (2026-10-07)

Zero model calls. The exact-quote set (Q10 b) and every probe of the v0.3.0 bench (Q10 c; `0ace76c`, `extract-v16`,
the S0–S6 runs of 2026-10-05/06, databases `nmos_b030_*`), each compiled again with `audit.replay` under `packet-v12`
and `packet-v13`, three replays each, the majority deciding; scored by `tools/eval_rp.py`. The query embedding is the
bench's model on the evaluation Ollama; vectors ran on every replay. Each probe's trace is the one its question made
in its run, matched in the order the probes were asked. S0main and S0s2 are the owner's real chats: aggregates only.

**Result: Q11 (b) and (c) met — 20 or 21 of 24 on the quote set (21 in four replays of six).** `packet-v12`'s compiled
output is unchanged.

## The exact-quote set (Q10 b)

| Set | `packet-v12` | `packet-v13` (6 replays) |
|---|---|---|
| by turn | 1 / 8 | 7 / 8 in each |
| by a first cue | 2 / 8 | 7 / 8 in four, 6 / 8 in two |
| by speaker and words | 1 / 8 | 7 / 8 in each |
| **all** | **4 / 24** | **21 / 24 in four, 20 / 24 in two** |

No forbidden phrase placed. Of the 48 quote lines placed, 4 carry a speaker and none is wrong (read by hand against
the source turns). Mean packet 3,900 tokens against 3,010 under `packet-v12` (two quote lines, about 1,050 tokens, in
the 4,000 budget). The misses: a named turn whose message is long, the answer in a part of it the question's words do
not reach; a first-cue question whose first visit spans two turns (the lines placed come from its first); one message
the candidates did not reach; and in two replays of six a first-cue line that loses a 0.001 tie recall's order decides.

The set reached 19 with the first rules; two rules took it to 20–21, each a reading of prose rather than of this set:
the sentence before a quote counts as near (narration before a line often sets its scene), and
the question's verb of speaking is matched to the line ("물었어" to a line that is a question, "대답했어" to the line
after one). The bench sets the forensic path runs on were replayed again three times with them: unchanged.

The first rule for the speaker read the next sentence too: it named a speaker on about 40 of 48 lines and the wrong
one on about 15 (the next sentence is most often the listener's: 추오월이 말없이 그를 보았다). Reading the sentence
before the quote (PHASE-33 Q2's proposal) named the listener as often. Both were dropped (ADR 0067).

## The v0.3.0 bench (Q10 c)

Cases passed, each of three replays.

| Set | Cases | Speech cue | `packet-v12` | `packet-v13` | Forbidden placed (v12 → v13) |
|---|---:|---:|---|---|---|
| S0main default | 40 | 1 | 34 | 34 | 3 → 3 |
| S0main all history | 40 | 1 | 34 | 34 | 3 → 3 |
| S0s2 default / all | 15 / 15 | 0 | 15 / 15 | 15 / 15 | 0 → 0 |
| S1 turn 30 / 60 | 25 / 25 | 1 / 0 | 25 / 25 | 25 / 25 | 0 → 0 |
| S1 turn 120 | 25 | 0 | 22 | 22 | 2 → 2 |
| S1 turn 240 | 25 | 0 | 23 | 23 | 1 → 1 |
| S2 default / all history | 25 / 25 | 0 | 22 / 23 | 22 / 23 | 2 / 1 → same |
| S3; S5 branch; S5 new chat | 6 each | 0 | 6 each | 6 each | 0 → 0 |
| S4 | 4 | 1 | 3 | 3, 2, 2 (see below) | 0 → 0 |
| S4b | 3 | 2 | 3 | 3 | 0 → 0 |
| S6 | 25 | 0 | 21 | 21 | 2 → 2 |
| first-cue probes (S0main, S0s2, S2, S6) | 1 each | 0 | 0, 1, 1, 1 | same | 0 → 0 |

Every set is equal case by case except S4, where one question with no speech cue ("…동물 이름이 뭐였지?") failed in
two `packet-v13` replays with the lexical route finding nothing: its 300 ms slice. The path to the lexical route is the
same code under both policies for a question without a cue; 30 further replays of the case (cold processes, one
process, `eval_rp` as run) passed under both. S6, the first-sight catch-up set, holds at 21 of 25; no S6 case was
compiled during a catch-up, so Q5 is not exercised by it (the reduced live run, Q10 d, is).

**The address questions.** As first built, a question about what someone is called ("뭐라고 불러?") took the forensic
path on its 뭐라고, and S1 turn 120 and S6 each lost two cases with three more forbidden phrases: quotes brought back
the older forms of address. Such a question no longer takes it unless it carries a history cue (ADR 0067 item 1).

**`packet-v12` unchanged.** All 314 bench probes compiled under `packet-v12` give the same packet text byte for byte
on `main` (`556dab6`) and on this branch, with the lexical and keyword slices lifted so the comparison is deterministic
(with them, `main` against itself differs on about 11 of S0main's long-chat probes).

## Latency at scale (Q10 e)

`tools/bench_forensic.py` (new): `/v1/retrieve` under `packet-v12` and `packet-v13` on `bench_scale.py`'s synthetic
chat, in-process, no embedder, one throwaway database per size; five questions with a speech cue (the forensic path
under `packet-v13`) and five without, six rounds. Every reply of that chat holds a quoted line many times: the worst
case for the quote route. Bar (Q4): forensic p95 at most 150 ms above normal p95 at 10,000 messages.

| Messages | Without a cue, v12 → v13 (p95) | With a cue, v12 → v13 (p95) | Forensic over normal | Quote route (p50 / p95) |
|---:|---|---|---:|---|
| 1,000 | 39.7 → 39.6 ms | 97 → 134 ms | +37 ms | 36 / 53 ms |
| 5,000 | 49.0 → 47.6 ms | 106 → 181 ms | +76 ms | 56 / 82 ms |
| 10,000 | 49.4 → 49.0 ms | 153 → 255 ms | **+102 ms** | 83 / 120 ms |

**Met.** A question without a cue costs nothing more. As first built the route's own search ran `ILIKE` over every
message, twice per word, carrying the text: 160 ms at 10,000 messages, past its 150 ms slice, so it timed out and
the forensic path cost +151 ms p95 for nothing (+162 at 5,000). It now marks which words each message holds with
`strpos` (Korean has no case; a Latin word is matched as written and capitalized), returns no text, and fetches the
text of the best 30 only: 38–54 ms at 10,000. The first-met lookup does the same. The quote set and the bench sets
the forensic path runs on were replayed again: unchanged (21 of 24 in three replays).
