# `extract-v14`: shorter context, synthetic examples, evidence in the turn (Phase 19)

`docs/phases/PHASE-19.md`. Numbers only: the owner's chats and the cases stay outside the repository.

## Step 2: offline measurements (2026-09-30, no model call)

### Setup

- **Evaluation copies** of Phase 18 (`docs/perf/lexical-recall.md`, "Setup"), read-only: the owner's two M0 chats
  (main, sample 2) with their `extract-v13` extractions by `deepseek-v4.1-flash` and `gemma4:31b-cloud`, and the
  synthetic 240-turn chat with `deepseek-v4.1-flash`.
- **The Q3 check as specified**: a valid row whose quote has at least 12 characters, and whose quote reaches less than
  `EVIDENCE_MIN` (0.7, `threads.similarity`) against its target turn's text, would be parked. The target turn's text is
  what the worker gave the model: the extraction's members' normalized text at the extraction's normalizer, joined by
  line breaks. Rows without a quote and shorter quotes are not checked.
- **Sampled turns**: the runs measured before the spec (its "Evidence behind Q1 and Q3"): today's prompt three times,
  the 1,000-character context three times, `gemma4:31b`, on 60 synthetic turns and 20 turns of the main M0 chat. The
  check is applied to their stored rows.
- **M0 v2 replays** as Phase 18's `extract-v13` baseline: `packet-v10`, 4,000 tokens, keyword route on, each run's
  own summaries, vectors on and off. Every case passed or failed as in Phase 18's runs (vectors on and off, all 16
  runs); one run (sample 2, `gemma`, vectors on) passed one case more on one of four later replays, so a single case
  there is within replay noise.

### How many valid rows the check would park

| Copy | model | extractions | valid rows | with a quote | quote < 12 | would be parked | share of valid rows |
|---|---|---:|---:|---:|---:|---:|---:|
| M0 main | deepseek | 73 | 456 | 456 | 24 | 6 | 1.3 % |
| M0 main | gemma | 73 | 422 | 422 | 20 | 22 | 5.2 % |
| M0 sample 2 | deepseek | 34 | 258 | 258 | 7 | 0 | 0.0 % |
| M0 sample 2 | gemma | 128 | 723 | 723 | 29 | 35 | 4.8 % |
| synthetic | deepseek | 240 | 1,258 | 1,258 | 18 | 3 | 0.2 % |
| **all** | **deepseek** | 347 | 1,972 | 1,972 | 49 | 9 | **0.5 %** |
| **all** | **gemma** | 201 | 1,145 | 1,145 | 49 | 57 | **5.0 %** |

Every valid row carries a quote. By `epistemic`: deepseek 9 of 1,893 `stated` and 0 of 79 `implied`; gemma 52 of
1,059 `stated` and 5 of 86 `implied`. By quote length, of the rows checked: 12–29 characters 5/644 (deepseek) and
32/468 (gemma), 30–59 characters 4/1,066 and 20/494, 60 or more 0/213 and 5/134.

By predicate (would be parked / valid; predicates with none parked in either model left out):

| Predicate | deepseek | gemma |
|---|---:|---:|
| `event` | 1 / 513 | 10 / 276 |
| `resolved` | 1 / 114 | 12 / 50 |
| `located_in` | 0 / 142 | 9 / 120 |
| `addresses` | 1 / 52 | 9 / 49 |
| `feels_toward` | 0 / 72 | 5 / 68 |
| `goal` | 0 / 164 | 4 / 139 |
| `knows` | 2 / 162 | 2 / 115 |
| `has_trait` | 1 / 71 | 2 / 26 |
| `has_status` | 1 / 61 | 1 / 61 |
| `possesses` | 0 / 113 | 1 / 83 |
| `identity` | 0 / 64 | 1 / 42 |
| `fulfilled` | 0 / 15 | 1 / 8 |
| `promised` | 1 / 68 | 0 / 24 |
| `relationship` | 1 / 40 | 0 / 13 |

Where the 66 quotes are: 55 are found (at the same 0.7) in one of the three context turns the model was shown, so the
row is stated there, not in its target turn; 11 are in none of the four turns. A `resolved` row whose quote comes from
an earlier turn closes a thread at the wrong turn; it is the predicate `gemma` most often misplaces (12 of 50).

### Parked rows in the packets of passed cases

| Run | vectors | passed | passed cases holding a parked row | distinct rows | passed without the parked rows | needing memory: passed | … without them |
|---|---|---:|---:|---:|---:|---:|---:|
| M0 main, deepseek | on | 29/40 | 1 | 1 | 29 | 13 | 13 |
| M0 main, deepseek | off | 28/40 | 1 | 1 | 28 | 11 | 11 |
| M0 main, gemma | on | 32/40 | 28 | 5 | 31 | 16 | 15 |
| M0 main, gemma | off | 31/40 | 27 | 5 | 30 | 14 | 13 |
| M0 sample 2, deepseek | on / off | 11/15, 11/15 | 0 | 0 | unchanged | 8, 8 | unchanged |
| M0 sample 2, gemma | on / off | 8/15, 7/15 | 0 | 0 | unchanged | 5, 4 | unchanged |
| synthetic 30–240 | on / off | as Phase 18 | 0 | 0 | — | — | — |

"Without the parked rows" replays each case with those rows left out of the facts read, as `extract-v14` would leave
them `pending`; forbidden phrases placed are unchanged in every run. The six rows placed (deepseek: one `knows`, shown
as a claim; gemma: two `event`, one `addresses`, one `knows`, one `identity`, 41 fact and 19 claim lines) answer no
case: every case holding one passes as well without it. One gemma case of the main chat fails without the parked
rows, on and off, and holds none of them: a parked `resolved` row, quoting a context turn, had closed a goal thread,
and without it the thread is shown in the words of a later turn, which the case's gold phrase does not match.
That case's result, with and without the rows, was the same on four replays, vectors on and off.

The spec asked that none of the rows the check would park be a fact line placed in a passed case's packet. Measured,
six rows are, and none of them answers its case; the owner decided on 2026-09-30 to keep Q3 as specified and to judge
it by its effect instead: **leaving the parked rows out lowers the cases passed by at most one per run**. It does: 0
for deepseek, 1 for gemma on the main chat (vectors on and off), 0 elsewhere.

### Sampled turns: the check and repeated pairs

| Run | valid rows | quote < 12 | would be parked | share | `addresses` + `relationship` rows kept | new pair | changed value | repeats the pair's current value |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| today 1 | 374 | 9 | 9 | 2.4 % | 23 | 17 | 3 | 3 |
| today 2 | 372 | 6 | 8 | 2.2 % | 24 | 17 | 4 | 3 |
| today 3 | 374 | 9 | 6 | 1.6 % | 23 | 17 | 3 | 3 |
| context 1,000 1 | 404 | 12 | 2 | 0.5 % | 32 | 21 | 9 | 2 |
| context 1,000 2 | 414 | 13 | 3 | 0.7 % | 31 | 21 | 7 | 3 |
| context 1,000 3 | 408 | 12 | 5 | 1.2 % | 31 | 22 | 6 | 3 |

With the 12-character floor, the check parks 0.5–1.2 % of the shorter context's valid rows (1.6–2.4 % of today's; the
main chat's turns 1.0–4.6 % and 1.7–3.6 %). Today's prompt parks five `resolved` rows over three runs, the shorter
context none. A pair's current value is the copy's own generation's latest valid row for that pair before the turn
(pairs as the read side keys them, by name); rows the check would park are left out. The shorter context extracts
more `addresses` and `relationship` rows, and they are new pairs or changed values: repeats of the current value are
8 of 94 (8.5 %) against 9 of 70 (12.9 %) today.

### Step 2 criteria

- [x] The check parks at most 10 % of valid rows: 0.5 % (deepseek) and 5.0 % (gemma) of the copies' `extract-v13`
      rows; at most 4.6 % in any sampled run.
- [x] Amended by the owner (2026-09-30), in place of "no parked row is a fact line placed in a passed case's packet":
      leaving the parked rows out lowers the cases passed by at most one per run (measured 0 and 1).
- [x] The shorter context's `addresses` and `relationship` rows repeat the pair's current value no more often than
      today's (8.5 % against 12.9 %).
