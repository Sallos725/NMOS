# Phase 29 probe: the alias confirmation on fixed inputs (2026-10-04)

**The bar is met: 60/60.** The alias confirmation alone (`ALIAS_CONFIRM_SYSTEM`, `alias_prompt` at `b447843`), 20
frozen inputs × 3 repeats, sequential, no retries, owner-approved. This measures the confirmation call, not the worker
path or a sequential run; the fresh S1 on the new generation is the next gate (PHASE-29 Measurement (c)).

**High risk:** identity and provenance, knowledge boundaries through an alias, extraction generations.

## Inputs

| Set | Inputs | Expected | Kept / held over 3 repeats | Bar |
|---|---:|---|---|---|
| Measured wrong aliases (S1 200 `윤하람 → 도도`, S1 237 `람이 → 도도`) | 2 | held | held 6/6 | 6/6 held: **met** |
| Measured correct free aliases (S1 1 `오봉순 → 오 사장`, 160 and 185 `윤하람 → 람이`) | 3 | kept | kept 9/9 | 9/9 kept: **met** |
| Authored negatives (a name called out in dialogue, a letter's greeting, a name in reported speech, a shop sign) | 4 | held | held 12/12 | 12/12 held: **met** |
| Authored positives (a self-introduction, "everyone calls him", a nickname answered to, a title with the surname) | 4 | kept | kept 12/12 | ≥ 11/12 kept: **met** |
| NAME PAIRS answers (S1 10, 18, 24, 33, 59, 133, 143), not asked under Q1 | 7 | kept | kept 21/21 | information only |

The measured inputs are rendered from the stored S1 runs through fresh read-only connections (`8fe66d1`, `c0b0a5b`;
turn 237 with the 4e76c70 run's stored KNOWN ENTITIES from `fixtures/model/phase28/2026-10-03-s1-confirmation-review/`),
each with NAME_A's names as that run's hints held them (turn 200: `윤하람 (also written: 하람, 람이)`). The authored
controls are synthetic scenes with invented names, written and hashed before any call.

## What the model said

Both measured wrong aliases are answered no in every repeat, with the passage that shows the address: turn 200
`"도도, 술 마셨지. 맥주 냄새 나."`, turn 237 `도도에게. 안녕, 도도!`. The four authored negatives likewise quote the
vocative, the greeting, the reported speech and the sign. Every yes quotes a TARGET passage containing NAME_B (the
contract); for the NAME PAIRS rows two quotes contain the alias only inside the full name (133 `항만청장`) or beside it
(18), so, as for role endings, the quote check filters a yes and does not prove it.

## Cost and time

60 calls; input 156,516 (cached 106,816), output 2,408; **$0.02287544** at $0.14 / $0.40 per million, uncached (the
approved estimate was about $0.037: the estimator over-counts Hangul). Median 598 ms, maximum 6,859 ms; maximum output
61 tokens of the 512 cap. No HTTP error, no unusable reply, every `finish_reason` `stop`. Elapsed 47 s.

## Evidence and limits

Owner-local: `/home/grantkim725/nmos-eval/pr251/2026-10-04/phase29-probe/` — `PLAN.json` (`0e2aca74…`), `inputs.json`
(`ee0d84df…`), `authored-controls.json` (`86a83e20…`), every request, HTTP body and grade under `results/`,
`summary.json` (`4c09ea7a…`), `build_inputs.py`, `run_probe.py`.

Two measured wrong inputs and three measured correct ones are small single samples; the authored controls offset that
only partly and were written by the implementer. The same model makes the first answer and the confirmation, so a
belief shared by both is not caught (PHASE-28's turn 227), and a wrong yes is not listed for the owner. Not verified:
the worker path on real replies, a fresh sequential S1 (names 3/3, roles 7/7), first connection, other languages.
