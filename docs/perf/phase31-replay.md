# Phase 31 step 3: `packet-v12` replayed on the PHASE-28 gate (2026-10-05)

**Result: every replay bar of PHASE-31 Q7 (b) met, with 첫날 added to the history cue (owner, 2026-10-05).** As
first specified (without 첫날), S2's full-history median was 21 (bar 22) and one history question lost its answer.
Zero model calls; the live gate (Q6 c) is next, reduced to S1, S2 and S3 once each (owner).

**High risk:** recall semantics (what the packet carries); `packet-v11` unchanged and still the default.

## Method

Every probe of the 17 runs of the PHASE-28 live gate on `9947d2c` (`phase28-live-gate-9947d2c.md`) is compiled
again from its run's database with `audit.replay`: the facts, summaries and vectors as of the request. The gate's
harness deleted each probe message after asking, so a replay passes the probe as `query`; with the message gone, the
lexical route ranks the story without it, and about a third of the replays differ from the captured packet in an
excerpt or two (the trace each probe came from is the one whose `packet-v11` replay is closest to the captured
packet). Each case is therefore compared within the replay: `packet-v11`, `packet-v12` as specified, and
`packet-v12` with 첫날 as a history cue, three replays each, the majority deciding (the lexical route did not return
the same candidates on every replay of one request; reported separately). The query embedding is the gate's model
(`qwen3-embedding:8b`, the same digest) on the evaluation Ollama; vectors ran on every replay. Scored as the gate
scores (`tools/eval_rp.py` `score`, gold present and forbidden phrases placed, the captured window as the prompt).
S0main and S0s2 are the owner's real chats: aggregates only.

## Results

Cases passed per run (three runs each unless noted).

| Set | Bar (Q7 b) | Gate | `packet-v11` replay | `packet-v12` as specified | `packet-v12` with 첫날 | |
|---|---|---|---|---|---|---|
| S1, turn 240 | median ≥ 21/25 | 18, 19, 19 | 19, 20, 20 | 21, 22, 22 | 21, 22, 22 | met |
| S2, full history | median ≥ 22/25 | 19, 19, 19 | 20, 20, 20 | 21, 22, 21 | 22, 22, 22 | met with 첫날 |
| S2, default window | no worse than v11 − 1 | 20, 20, 19 | 21, 21, 20 | 22, 22, 20 | 22, 22, 21 | met |
| S3 | 6/6 | 5, 5, 5 | 5, 5, 5 | 6, 6, 6 | 6, 6, 6 | met |
| S1, turn 120 | no worse than v11 − 1 | 22, 21, 23 | 22, 21, 23 | 21, 20, 22 | 21, 20, 22 | met (−1) |
| S1, turns 30 and 60 | no worse than v11 − 1 | 25 each | 25 each | 25 each | 25 each | met |
| S5 branch and new chat | no worse than v11 − 1 | 6 each | 6 each | 6 each | 6 each | met |
| S4 (one run) | no worse than v11 − 1 | 3 | 3 | 3 | 3 | met |
| S4b | no worse than v11 − 1 | 3, 3, 3 | 3, 3, 3 | 3, 3, 3 | 3, 3, 3 | met |
| S0main, memory cases (default and all) | no worse than v11 − 1 | 38 each | 38, 37, 38 | = v11 | = v11 | met |
| S0s2 | no worse than v11 − 1 | 15 | 15 | 15 | 15 | met |

Forbidden phrases placed, per run: S1 turn 240 5 → 2 and S2 full history 5 → 2 (v11 replay → v12), S2 default
3 → 2, S1 turn 120 3 → 4; S0main unchanged (1). Total lower in every run. History-cue cases (S1 `early` and `past`,
S0main's): no case worse with 첫날; without it S2's `c240_20_early` ("…윤슬포 첫날 저녁에 먹은 게…") lost its
answer in two or three runs, its excerpt left out as stating the replaced residence.

**What changed, case by case** (every run unless noted): `s3_r4_book` (K43) passes, the excerpt anchoring on the
lending sentence; `c240_02_location` passes, the ended role `투숙객: 갈매기 여관 3호실` no longer printed for "지금";
`c240_08_state` passes, an excerpt of a replaced state left out. One loss: `c120_24_irrelevant` ("따뜻한 차 하나
추천해 줘"), a trap question, now places a forbidden phrase: the one-character word 차 moves its excerpt's anchor to
the sentence with 보리차 (Q3 as designed). S1 turn 240's 03, 05, 06, 19, 21 and 24 still fail (03 and 05 not
diagnosed here; 06, 19, 21 and 24 failed historically too).

## Not measured here

Generated answers (the gate scores packets); latency (a replay is not a timing test); a chat whose question about
now says 첫날 (it then gets `packet-v11`'s packet). The lexical route's run-to-run difference is a separate finding.

## Evidence

Owner-local: the replay script and per-case JSON (case names, scores, trace ids) in the session scratchpad and
`/home/grantkim725/nmos-eval/age24-v16-9947d2c/`; databases `nmos_age24_9947d2c_*` on the test Postgres, read only.
