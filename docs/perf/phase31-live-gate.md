# Phase 31 reduced live gates (`packet-v12`, 2026-10-05)

**Result: the second run (`ba12fcc`, Q1 amended) met every bar — S3 6/6, S2 full history 23 (bar 22), S1 turn 240 23
(bar 21).** The first run (`1d2e14e`) met S3 and missed S1 and S2 on three cases (below), which led to Q1's amendment
(`phase31-replay.md`). `packet-v12` is the default since (owner, 2026-10-05).

**High risk:** recall semantics (what the packet carries); `NMOS_PACKET_POLICY=packet-v11` keeps the previous packet.

## Second run: `ba12fcc` (Q1 amended, #265 merged)

Same lane as the first run below, at `ba12fcc` (PR #264 with `main` 3b3fe60 merged: the keyword lookup always starts
from the trigram index, #265). Cap 1,300 extraction calls; used 1,084, no HTTP error; every 30 minutes checked, no
quality stop. S3 16 min, S2 29 min, S1 91 min.

| Set | Bar | PHASE-28 gate (`packet-v11`) | First run | Second run | |
|---|---|---|---:|---:|---|
| S3 | 6/6 | 5, 5, 5 | 6 | 6 | met |
| S5 branch / new chat | keep | 6, 6 | 6, 6 | 6, 6 | met |
| S2, full history | 22/25 | 19, 19, 19 | 20 | 23 | met |
| S2, default window | — | 20, 20, 19 | 20 | 22 | |
| S1, turns 30 and 60 | keep | 25, 25 | 25, 25 | 25, 25 | met |
| S1, turn 120 | — | 22, 21, 23 | 21 | 23 | |
| S1, turn 240 | 21/25 | 18, 19, 19 | 20 | 23 | met |

Forbidden phrases placed: S1 turn 240 and S2 full history 1 of 41 each (the first run 4, the PHASE-28 gate 6), S1 turn
120 1 of 33. Failing: S1 turn 240 and S2 full history 19 and 24, which failed in every earlier lane; S1 turn 120 21
and 24. The replay of the first run's databases had predicted 23 and 23.

**Review.** No false join. Endings applied were the story's: the move (87, 88), the sponsorship (134; in the PHASE-28
gate it ended at 227), the colleague at the harbour office when 서도윤 is dismissed (135), the attic (159), the inn help
(219), the resignation (233, 234). Aliases were names and their parts, 오 사장, 청장 for 항만청장 and 저금통 → 작은 나무 상자.
One live extraction (S1 turn 105) was dead after five invalid-JSON replies from the model; its turn has no facts.

**The keyword route ran.** `too_broad` for 3 of 340 S1 requests, 3 of 52 S2 and 1 of 70 S3 (the first run 25, 52, 14).

## First run: `1d2e14e`

### Lane

`1d2e14e` (PR #264: `packet-v12` with 첫날 as a history cue; `extract-v16` the default), the PHASE-28 harness
(headless PocketRisu host, a stub generation model, `gemma4:31b-cloud` extraction through the evaluation Ollama)
with the pacing corrected (8 s between messages, not 20; a 15 s bound on the shown reply, not 180), the query
embedding `qwen3-embedding:8b` on the evaluation Ollama (the gate's model and digest; the host's Ollama untouched).
Reduced per AGENTS §7 item 6 (owner, 2026-10-05): S3 (with S5), S2 and S1, once each. Owner-approved cap 1,300
extraction calls; used 1,019, no HTTP error; checked every 30 minutes, no quality stop. Scores are packet coverage.

### Results

| Set | Bar | PHASE-28 gate (`9947d2c`, `packet-v11`) | This run (`packet-v12`) | |
|---|---|---|---:|---|
| S3 | 6/6 | 5, 5, 5 | 6 | met (K43) |
| S5 branch / new chat | keep | 6, 6 | 6, 6 | met |
| S2, full history | 22/25 | 19, 19, 19 | 20 | **miss** |
| S2, default window | — | 20, 20, 19 | 20 | |
| S1, turns 30 and 60 | keep | 25, 25 | 25, 25 | met |
| S1, turn 120 | — | 22, 21, 23 | 21 | |
| S1, turn 240 | 21/25 | 18, 19, 19 | 20 | **miss** |

Forbidden phrases placed: S1 turn 240 4 of 41 (gate 6), S2 full history 4 of 41 (gate 6), S1 turn 120 4 of 33.

**Failing cases.** S1 turn 240 and S2 full history: 03, 05, 06, 19 and 24. 02 (the ended role) passes in both, as
in the replay. 03, 05 and 06 each place one forbidden phrase from an older excerpt: "이 여관이 제 집이에요" (turn 17;
the old residence 갈매기 여관 shares no four-character span with it), "도윤 씨라고 불러 주는 대신" (turn 21) and the
turn-95 passage that drops '서 선생' (the pair's current address is in the prompt window, so no packet fact judges
it; the old value is mostly the frame "존댓말, '…'이라고 부름"). 19 and 24 failed in every earlier lane.

**Review.** No false join. Endings applied were the story's: the move (87), the attic (159), the inn help (219), the
resignation (233, 234), and the sponsorship at 227 (PHASE-28's 227 class, one pair, within the stop rule). Aliases were
names and their parts, 오 사장, 서정호's nickname and, in S2, 저금통 → 작은 나무 상자 (turn 71 says the box is her
저금통).

### The keyword route was mostly off live

The keyword route (ADR 0052) reported `too_broad` for 25 of 191 S1 requests, all 52 of S2's, and 14 of 70 of S3's, as
in the PHASE-28 gate (S1 55–59 of 340, S2 52 of 52). A separate session (the replay-determinism task, #265) traced it to
stale planner statistics: a reroll, an edit or a delete makes a new head commit (an append keeps the head, D4), which
the planner estimates at one row until autoanalyze, and the keyword query then reads the membership first and runs out
its time slice. The harness rerolls and deletes its probes, so the gate met this nearly always; whether the owner's
prod requests that reported `too_broad` did so for this reason or for the recheck cost of long messages is not
separated. A replay on a copy
whose statistics are current runs the route; this run's misses and the replay's are therefore not the same
condition, which may explain part of S2's gap (replay 22, live 20; not measured). That fix is outside Phase 31.

### Timing

S3 16 min, S2 28 min, S1 86 min (the probes' queue waits included), against the PHASE-28 gate's 27, 30 and about 250:
the corrected pacing cut S1 by about two thirds.

## Evidence

Owner-local: `/home/grantkim725/nmos-eval/p31-gate-ba12fcc/` and `/home/grantkim725/nmos-eval/p31-gate-1d2e14e/`
(`provenance.json`, `proxy.jsonl`, `run/<set>-1/`; databases `nmos_p31_ba12fcc_*` and `nmos_p31_1d2e14e_*` on the test
Postgres).
