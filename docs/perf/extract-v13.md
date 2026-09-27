# `extract-v13` — open business (Phase 11 steps 4–5, ADR 0039)

Measured 2026-09-28. Goals, questions, threats and debts open threads; `resolved` ends one with an outcome; `because`
keeps a cause the story states.

## Real-model tier (synthetic scenes)

`tools/eval_v13_model.py`, 14 Korean scenes written for this evaluation, 3 runs each, both models through the local
Ollama, 2 workers, no errors. Raw prompts, replies and checks: `fixtures/model/v13/`. Prompt fingerprint
`a0de52e41b72df2c` (the final prompt).

| Category | Scene | `gemma4:31b-cloud` | `deepseek-v4.1-flash` |
|---|---|---:|---:|
| opens | a lasting goal | 3/3 | 3/3 |
| opens | a question or mystery | 2/3 | 3/3 |
| opens | a threat made | 3/3 | 3/3 |
| opens | money borrowed | 3/3 | 3/3 |
| wish | a craving is not a goal | 3/3 | 3/3 |
| wish | the next step is not a goal | 3/3 | 3/3 |
| resolve | a goal achieved | 3/3 | 3/3 |
| resolve | a question answered | 3/3 | 3/3 |
| resolve | a threat averted | 3/3 | 3/3 |
| resolve | a debt paid | 3/3 | 3/3 |
| control | a goal worked on stays open | 3/3 | 3/3 |
| control | a debt mentioned stays open | 3/3 | 3/3 |
| cause | a stated cause is kept | 3/3 | 3/3 |
| cause | no cause is invented | 3/3 | 3/3 |
| **all** | | **41/42** | **42/42** |

The one miss: `gemma4` recorded "who rang the bell" as a goal to find out, not a question; it is an open thread
either way. A first prompt without examples had `gemma4` record a craving ("달달한 게 먹고 싶다") as a goal 3 of 3
times and the next step of a chore 2 of 3; the prompt now names both as not goals, and "wanting to find something out"
as a question. Every scene was run again with the final prompt (the table).

## The owner's chat (M0 copy re-extracted)

The restored backup (PHASE-11 Q1), with `extract-v13` activated on a second copy and the owner's model re-extracting
the M0 chat's 73 turns through the local Ollama (no errors). Counts only.

| | before (`extract-v12`) | `extract-v13` |
|---|---|---|
| goal assertions in the chat | 93 | 49 goals, 9 questions (restatements and cravings fewer) |
| goals as threads | none (facts, never ended) | 48 goal threads: **11 achieved**, 37 open |
| other threads | 8 promises open, 2 kept | promises unchanged; 1 question answered, 8 open |
| endings matching no open thread | — | 6 |
| facts with a stated cause | — | 66 |
| goal lines in M0's 12 packets | 0 | goals reach the packets as threads |

Two faults found here and fixed before this record: the model gives a `resolved` its owner as `object`, and closes a
goal with `fulfilled`; both matched nothing (11 unmatched). `resolved` now matches by owner and text only, and a
`fulfilled` that matches no promise ends the owner's goal (ADR 0039).

**M0 on the first 12 cases: 5 of 12, as the baseline.** Goals reached the packet but not the owner's two open ones
(newer goals rank first), and the relationship cases fell 2 → 0 because the new extraction words the current feeling
differently ("설렘과 긍정적인 감정" where the gold phrase was "좋아함"). That met a PHASE-11 stop condition. The owner
chose (2026-09-28) to fix it before merging: gold that accepts wordings of the same answer, and more cases.

**What changed before this record.** OPEN THREADS lists what the target turn is about first: a thread can only be
ended while it is listed, and the list had held only the newest threads of the characters named, so an old goal the
story came back to was never listed again. The copy was re-extracted with it (73 turns, no errors): 48 goal threads,
9 achieved; 10 questions, 1 answered and 1 given up; 9 endings match nothing.

**M0 on the 28 owner-confirmed cases** (`docs/perf/m0-baseline.md`):

| Category | cases | `main` (before Phase 11) | step 3 | `extract-v13` |
|---|---:|---:|---:|---:|
| address | 5 | 2 | 4 | 4 |
| goal | 1 | 0 | 0 | 0 |
| irrelevant | 3 | 3 | 3 | 3 |
| past | 3 | 3 | 3 | 3 |
| promise | 3 | 2 | 2 | 2 (forbidden 0, was 1) |
| relationship | 4 | 3 | 3 | 3 |
| secret | 2 | 0 | 0 | 0 |
| state | 5 | 0 | 0 | 2 |
| why | 2 | 0 | 0 | 0 |
| **all** | **28** | **13** | **15** | **17** |

No category is worse than the baseline. The goal case still fails: the owner's two open goals were stated once and
never mentioned again, and newer goals outrank them for three thread slots; 37 goals stay open without a turn saying
they ended (K23). The "why" cases wait for step 6, which reads `because`.
