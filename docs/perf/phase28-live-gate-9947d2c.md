# PHASE-28 live gate on the focused `extract-v16` (`9947d2c`, 2026-10-04/05)

**Verdict: not passed.** Everything extraction decides passed: the real-chat memory cases 9/10 in every run (bar 8),
S4b 3/3 (recovered from `extract-v15`'s 2/3), no false join. Three sets missed their medians, each for a recall reason
that `extract-v15` (`e13dee7`) shows too: S1 at turn 240 (19, bar 21), S2 (19, bar 22) and S3 (5/6, bar 6/6, K43).
Phase 31 (draft) is the correction. The first attempt on `7b7cc14` was paused after S0main ×3 (7, 5, 8 of 10) and led to
the focused prompt (ADR 0064 item 5, `extract-v16-focus.md`).

**High risk:** extraction generations, current/historical role state, identity, recall semantics.

## Lane

`9947d2c` (`extract-v16` the default, generation `extract-c3a2394e…`; `packet-v11`; first sight oldest first), the
e13dee7 harness (headless PocketRisu host, a stub generation model, `gemma4:31b-cloud` extraction through the eval
Ollama, `qwen3-embedding:8b` on the host's Ollama), 17 runs: S0main ×3, S0s2, S4, S3 ×3 (with S5), S4b ×3, S2 ×3,
S1 ×3. Owner-approved: a dedicated cap of 5,000 extraction calls (used 4,014, no HTTP error); every run checked every
30 minutes, with a pause on a quality stop (none fired). Scores are packet coverage (gold phrases present, forbidden
phrases absent), not generated answers. S0main and S0s2 are the owner's real chats: aggregates only.

## Results

| Set | Bar | Historical lane | `e13dee7` | `9947d2c` runs | Median | |
|---|---|---|---:|---|---:|---|
| S0main, all (memory cases) | ≥ 8/10 every run | 6/10 | 8, 10, 8 | 9, 9, 9 (38/40 each) | 9 | pass |
| S0s2 | keep | 15/15 | 15/15 | 15/15 | 15 | pass |
| S4 | keep | 3/4 | 4/4 | 3/4 | 3 | pass (= historical) |
| S4b | median 3/3 | 3/3 | 2/3 | 3, 3, 3 | 3 | pass |
| S5 branch / new chat | keep | 6/6, 6/6 | 6/6, 6/6 | 6/6 ×3, 6/6 ×3 | 6 | pass |
| S3 | median 6/6 | 6/6 | 5/6 | 5, 5, 5 | 5 | **miss** (K43) |
| S2, full history | median 22/25 | 22 | 20 | 19, 19, 19 | 19 | **miss** |
| S1, turn 120 | — | 22 | 23 | 22, 21, 23 | 22 | |
| S1, turn 240 | median 21/25 | 21 | 19 | 18, 19, 19 | 19 | **miss** |

S1 turns 30 and 60: 25/25 in every run and lane. Forbidden phrases placed: S1 turn 240 and S2 6 of 41 per run
(historical 2); S0main 1 of 21 per run.

**Failing cases.** S1 turn 240 and S2 fail the same six in every run: 02 and 03 (current residence), 05 and 06 (form
of address), 19 (a past reason) and 24 (an irrelevant question); S1 run 1 also missed 21 once. The historical lane
passed 02, 03 and 05; it failed 06, 19, 21 and 24 too. In the packets: 03 and 05 (and 06) carry an older excerpt with
the replaced value; 02 prints the ended role `서도윤 role toward 오봉순: 투숙객: 갈매기 여관 3호실에 묵음` (negated, a correct
`extract-v16` ending) on a question about now. S3's one miss is `s3_r4_book` in every run (K43; stage diagnosis in
`k43-offline-diagnosis.md`).

## Review of endings and aliases (every run)

No false join. Applied endings were the story's: the move (87), the attic (159), the inn help (219), the resignation
(233, 234), and the real chats' endings (S0main one, S0s2 one pair), each reviewed against its turn. The sponsorship cancelled at
134 ended at 227 instead in each S1 run (PHASE-28's 227 class; one per run, within the stop rule's one). Aliases served
were names and their parts, 오 사장, a revealed `?이모`, a cat's name, and 서정호's nickname 미친 해도쟁이 (the story calls it
his nickname); one S2 run stored 도윤 → 젊은 양반 (a form of address, joining no one).

## Timing

A run of S1 takes about 4 h 10 min: about 90 min is the harness's fixed 20 s pause after each message and about 95 min
the ~190 s it waits when it misses a reply after a reroll; NMOS's own work is about 0.6 s a turn. Recorded for the next
gate (lower the pause, fix the reroll wait).

## Evidence

Owner-local: `/home/grantkim725/nmos-eval/age24-v16-9947d2c/` (`provenance.json`, `proxy.jsonl`, `run/<set>-<n>/`
with every request, packet text, rows and `result.json`; databases `nmos_age24_9947d2c_*` on the test Postgres; the
first attempt in `age24-v16-7b7cc14/`).
