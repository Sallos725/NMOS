# Phase 31 reduced live gate on `1d2e14e` (`packet-v12`, 2026-10-05)

**Result: S3 met (6/6); S1 turn 240 (20, bar 21) and S2 full history (20, bar 22) missed, each one run.** Both misses
are the same three cases in S1 and S2 (`c240_03_location`, `c240_05_address`, `c240_06_address`): an older excerpt of
a replaced value that the specified Q1 does not tell by reused spans. The owner approved Q1's amendment (marks, and
the facts the question names) on these cases; it is measured by replay (`phase31-replay.md`, "Q1 amended").

**High risk:** recall semantics; `packet-v11` unchanged and still the default.

## Lane

`1d2e14e` (PR #264: `packet-v12` with 첫날 as a history cue; `extract-v16` the default), the PHASE-28 harness
(headless PocketRisu host, a stub generation model, `gemma4:31b-cloud` extraction through the evaluation Ollama)
with the pacing corrected (8 s between messages, not 20; a 15 s bound on the shown reply, not 180), the query
embedding `qwen3-embedding:8b` on the evaluation Ollama (the gate's model and digest; the host's Ollama untouched).
Reduced per AGENTS §7 item 6 (owner, 2026-10-05): S3 (with S5), S2 and S1, once each. Owner-approved cap 1,300
extraction calls; used 1,019, no HTTP error; checked every 30 minutes, no quality stop. Scores are packet coverage.

## Results

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

## The keyword route was mostly off live

The keyword route (ADR 0052) reported `too_broad` for 25 of 191 S1 requests, all 52 of S2's, and 14 of 70 of S3's, as
in the PHASE-28 gate (S1 55–59 of 340, S2 52 of 52). A separate session (the replay-determinism task, #265) traced it to
stale planner statistics: a reroll, an edit or a delete makes a new head commit (an append keeps the head, D4), which
the planner estimates at one row until autoanalyze, and the keyword query then reads the membership first and runs out
its time slice. The harness rerolls and deletes its probes, so the gate met this nearly always; whether the owner's
prod requests that reported `too_broad` did so for this reason or for the recheck cost of long messages is not
separated. A replay on a copy
whose statistics are current runs the route; this run's misses and the replay's are therefore not the same
condition, which may explain part of S2's gap (replay 22, live 20; not measured). That fix is outside Phase 31.

## Timing

S3 16 min, S2 28 min, S1 86 min (the probes' queue waits included), against the PHASE-28 gate's 27, 30 and about 250:
the corrected pacing cut S1 by about two thirds.

## Evidence

Owner-local: `/home/grantkim725/nmos-eval/p31-gate-1d2e14e/` (`provenance.json`, `proxy.jsonl`, `run/<set>-1/`;
databases `nmos_p31_1d2e14e_*` on the test Postgres).
