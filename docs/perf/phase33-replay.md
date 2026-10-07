# Phase 33 step 3 — `packet-v13` replayed (2026-10-07)

Zero model calls. The exact-quote set (Q10 b) and every probe of the v0.3.0 bench (Q10 c; `0ace76c`, `extract-v16`,
the S0–S6 runs of 2026-10-05/06, databases `nmos_b030_*`), each compiled again with `audit.replay` under `packet-v12`
and `packet-v13`, three replays each, the majority deciding; scored by `tools/eval_rp.py`. The query embedding is the
bench's model on the evaluation Ollama; vectors ran on every replay. Each probe's trace is the one its question made
in its run, matched in the order the probes were asked. S0main and S0s2 are the owner's real chats: aggregates only.

**Result: Q11 (c) met; Q11 (b) not met — 19 of 24, the bar is 20.** `packet-v12`'s compiled output is unchanged.

## The exact-quote set (Q10 b)

| Set | `packet-v12` | `packet-v13` (each of 3 replays) |
|---|---|---|
| by turn | 1 / 8 | 6 / 8 |
| by a first cue | 2 / 8 | 7 / 8 |
| by speaker and words | 1 / 8 | 6 / 8 |
| **all** | **4 / 24** | **19 / 24** |

No forbidden phrase placed. Of the 48 quote lines placed, 3 carry a speaker and none is wrong (read by hand against
the source turns). Mean packet 3,900 tokens against 3,010 under `packet-v12` (two quote lines, about 1,050 tokens, in
the 4,000 budget). The five misses: two named turns whose message is long, the answer in a part of it the question's
words do not reach (the two placed lines come from the same message); a first-cue answer two turns after the turn the
two characters met; a near tie with another line of the same speaker; one message the candidates did not reach.

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
