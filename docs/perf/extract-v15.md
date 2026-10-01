# `extract-v15`: a role between two people (Phase 25)

`docs/phases/PHASE-25.md` (Q6), ADR 0059. Numbers only: the owner's chats and the cases stay outside the repository.

## Step 3: paid evaluation from the implementation branch (2026-10-01)

### Setup

- **Model**: `gemma4:31b` through the provider's API, two workers (one for (a)), the code of the step-2 branch.
- **(a) The AGE-27 evidence turns**: the three turns of the main M0 chat whose ledger states the tenancy, on the
  main evaluation copy with the hints of its `gemma` `extract-v13` generation, three runs. The turns are those of
  the `extract-v14` check recorded on AGE-27; every quote that check found in its turns is in the turns chosen (15/15).
- **(b) Sampled turns**: exactly the turns of Phase 19's stored `extract-v14` runs (`docs/perf/extract-v14.md`,
  step 4), named by their per-turn files (`tools/eval_extract_sample.py run --turns-from`): the synthetic chat's 91
  ledger turns and the main copy's 20 sampled turns (found across every chat of the copy, as Phase 19's tool did:
  `--every-chat`), with the same hints generations, three runs. Every quote the stored runs found in their turns is in
  the turns chosen (synthetic 467/467; main 106/106, 105/105, 101/101). The baseline is the stored runs: no new
  `extract-v14` spend. Scored as in Phase 19 (the synthetic ledger, persona given); `relationship` and `role_toward`
  rows are counted apart. The main copy's sample is indicative (its turns mix two chats, as in Phase 19).
- **(c) Re-extracted M0 chats**: copies of Phase 19's evaluation copies (`extract-v13` and `extract-v14` rows of
  `gemma`), migrated to 0028, the main chat (73 turns) and sample 2 (34 turns) re-extracted with `extract-v15` through
  the job queue. M0 v2 at `packet-v10`, 4,000 tokens, keyword route on, vectors off and on, each copy's own summaries,
  with today's code for both keys: the copies' `extract-v14` generation (baseline) and `extract-v15`.

### (a) The AGE-27 evidence turns

| run | turns with a `role_toward` row | the tenancy for the AGE-27 pair | also `located_in` |
|---:|---:|:---:|:---:|
| 1 | 1 of 3 | yes | no |
| 2 | 1 of 3 | yes | yes |
| 3 | 1 of 3 | yes | yes |

The turn that quoted the tenancy but stored a place under `extract-v14` now gives the role in every run, valid,
with the subject's side as value; the other two turns hold feelings and events, as before.

### (b) Sampled turns

| copy | label | run | valid rows | not in the turn | share | ledger facts: any row | valid, checked | `addresses` | `relationship` | `role_toward` | input tokens (sum) | output (median) |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| synthetic | v14 | 1 | 471 | 2 | 0.4 % | 116/167 | 113/167 | 20 | 16 | 0 | 764k | 1141 |
| synthetic | v14 | 2 | 459 | 4 | 0.9 % | 120/167 | 117/167 | 20 | 13 | 0 | 764k | 1150 |
| synthetic | v14 | 3 | 462 | 2 | 0.4 % | 117/167 | 115/167 | 21 | 14 | 0 | 764k | 1114 |
| synthetic | v15 | 1 | 476 | 5 | 1.1 % | 121/167 | 116/167 | 20 | 13 | 14 | 791k | 1178 |
| synthetic | v15 | 2 | 484 | 7 | 1.4 % | 115/167 | 114/167 | 20 | 13 | 19 | 791k | 1221 |
| synthetic | v15 | 3 | 491 | 5 | 1.0 % | 119/167 | 118/167 | 21 | 13 | 17 | 791k | 1242 |
| main (indicative) | v14 | 1 | 112 | 3 | 2.7 % | — | — | 5 | 2 | 0 | 163k | 1272 |
| main (indicative) | v14 | 2 | 104 | 1 | 1.0 % | — | — | 4 | 2 | 0 | 163k | 1162 |
| main (indicative) | v14 | 3 | 110 | 4 | 3.6 % | — | — | 4 | 1 | 0 | 163k | 1126 |
| main (indicative) | v15 | 1 | 107 | 6 | 5.6 % | — | — | 4 | 1 | 1 | 169k | 1206 |
| main (indicative) | v15 | 2 | 118 | 3 | 2.5 % | — | — | 5 | 1 | 2 | 169k | 1344 |
| main (indicative) | v15 | 3 | 107 | 4 | 3.7 % | — | — | 4 | 1 | 1 | 169k | 1304 |

Where the `relationship` rows went (synthetic chat, read row by row): the values `extract-v14` stored as a
relationship that are roles — a sponsor and client, a shipmate the turn hires as navigator — now come as
`role_toward`, with their other direction (employer) where the turn states it. One personal tie was lost: a turn that
states both an old friendship and a teacher's role gave the role only in all three runs. Every other relationship of
`extract-v14` is there, and one turn now gives both directions of a couple. Among 50 `role_toward` rows: one value in
English ("tenant: …", the description's own example word), one denial stored as a positive value ("not an
assistant"), and a few loose roles (a helper, one who puts pressure on an official).

### (c) Re-extracted M0 chats

| chat | vectors | `extract-v14`: passed | needing memory | forbidden placed | `extract-v15`: passed | needing memory | forbidden placed |
|---|---|---:|---:|---:|---:|---:|---:|
| main | off | 30/40 | 13/23 | 0 | 31/40 | 14/23 | 0 |
| main | on | 31/40 | 15/23 | 1 | 32/40 | 16/23 | 1 |
| sample 2 | off | 7/15 | 4/12 | 0 | 7/15 | 4/12 | 0 |
| sample 2 | on | 8/15 | 5/12 | 0 | 8/15 | 5/12 | 0 |

On the main chat the AGE-27 case passes with vectors off and on (it failed both ways before): its packet holds the
role as a fact. Three other cases fail and four pass that did not, the same with vectors off and on: one
re-extraction's variance (the cases are about a form of address, an item, a cause, open goals and promises, and the
story so far; none is about a role). Sample 2 is unchanged case by case.

### Cost

| part | calls | input tokens | output tokens |
|---|---:|---:|---:|
| (a) | 9 | 77k | 9k |
| (b) | 333 | 2,878k | 413k |
| (c) | 107 | 941k | 150k |
| **total** | **449** | **3.90M** | **0.57M** |

The spec's estimate was about 450 calls, 3.8M input and 0.4M output tokens: input within 3 %, output 43 % above it
(the estimate took too little output per call; `extract-v14` already wrote about 1.1k tokens a call). The run had
finished when this was counted; the stop condition on cost was reported to the owner.

### Criteria (PHASE-25)

| criterion | result |
|---|---|
| (a) a `role_toward` row with the tenancy for the AGE-27 pair in at least two of three runs | **met**: 3 of 3 |
| (b) ledger facts found among valid rows, mean not below `extract-v14`'s lowest run (113) | **met**: 116 (116, 114, 118) |
| (b) `relationship` rows not fewer than `extract-v14`'s lowest run | **met, at the bar**: synthetic 13 each (lowest 13), main 1 each (lowest 1) |
| (b) the evidence check parks at most 10 % of valid rows | **met**: 1.0–5.6 % |
| (b) input tokens within 5 % of `extract-v14`'s | **met**: +3.5 % synthetic, +3.7 % main |
| (c) cases passed and needing memory not lower by more than one per run | **met**: main +1 each, sample 2 equal |
| (c) forbidden phrases placed not higher in total | **met**: 1 and 1 |
| (c) the AGE-27 case passes with vectors off | **met** |
