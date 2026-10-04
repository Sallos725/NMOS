# Fresh S1 on 6e4ca05, after the Codex review fixes (2026-10-04)

**Pass: 240/240 turns, names 3/3, role scenes 7/7, no wrong ending, no false join.** The owner-approved re-measurement
of the review-fix head `6e4ca05319014ae0801a888e834a6080d37b5078`, generation
`extract-409d69e00030e6052c6125fa4520d5db` (`extract-v15` unchanged). Same envelope, gold, review and stop rules as the
`9aa7c57` run (`extract-v16-9aa7c57-sequential.md`); a new restore of the preserved S1 baseline.

**High risk:** knowledge boundaries, identity and provenance, current/historical role state, extraction generations.

## First, a zero-call replay

The `9aa7c57` run's recorded replies (main and every confirmation) were passed through `6e4ca05`'s post-processing,
with each listed role carrying the knowledge scope its stored positive row has, as `role_hints` now does. Prompts are
unchanged by the fixes (the scope is not shown), so up to a first difference the inputs are the same. **0 of 240 turns
change; no confirmation the new code would ask was missing.** The replay was checked twice: the old code reproduces the
stored rows exactly (0), and a planted private scope on the turn-1 inn role changes exactly the turn-87 ending (1). S1's
five `limited` roles are not ended in that run, and no free ending was written under another name of a listed party.

## The fresh run

| Check | Result |
|---|---|
| 74 mentorship, 86 eve, 88 settling in, 99 promotion elsewhere, 144 shop closure | kept |
| 87 move, 233 resignation | ended after a confirmation yes |
| Names at 239 | 강무진/무진, 윤하람/하람, 백이안/이안 joined |
| Endings applied | 87, 134 (sponsorship cancelled), 159, 219, 233: each reviewed correct; none held |
| Doubts | one `planned` ending (158) answered no and dropped |
| Aliases | 16 rows; 8 newly joined, all correct; alias confirmations 2, both yes (1 `오 사장`, 160 `람이`); none held |

At turn 200 the main reply wrote no alias this time, so the run does not exercise that confirmation (the `9aa7c57` run
and the probe do). 248 calls (240 main, 8 confirmation), input 2,901,137, output 254,993, **$0.51 uncached**, 23 min
including 88 s of review; no technical error. Fresh read-only readback verified all 240 extractions; the Inspector lists
the automatic endings at 233 and 219, nothing held; no repair was run.

Evidence (owner-local): `/home/grantkim725/nmos-eval/pr251/2026-10-04/replay-6e4ca05/` (`replay.json` `b1ded3fb…`,
`replay-oldcode.json`, `replay-mutation.json`) and `sequential-6e4ca05/` (`PLAN.json` `4b284efb…`, final archive
`a9c85c4f…`, `fresh-readback-summary.json` `d5e315f8…`). Limits as before: one story, one run; first connection,
other stories and the live runs are not covered.
