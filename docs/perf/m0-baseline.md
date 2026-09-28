# M0 — RP evaluation baseline (Phase 11 step 2)

The baseline before any Phase 11 change: `main` at `8c790b2` (Phase 10, the 2026-09-27 fixes), measured 2026-09-28.
Numbers only; the cases are the owner's chat and stay outside the repository (PHASE-11 Q1).

## Setup

- **Data.** A restored copy of the owner's production backup of 2026-09-28 in the test Postgres, read-only. Of its
  7 chats, one (73 turns) has recorded requests with a packet ledger (Phase 9); all 9 are at its last turns.
- **Cases.** 12 questions at the chat's last recorded request (turn 73), each a probe in place of the user's message
  (`tools/eval_rp.py`), with gold phrases the packet must hold and forbidden ones it must not. Drafted from the
  chat's extracted facts and confirmed by the owner (goals still open, a secret still kept, every other answer).
- **Compiled as `main` would today.** The current extractor generation's facts as of now (`--extractor`), `packet-v4`,
  the default budget of 800 tokens (`--budget`; the recorded requests carried 600), lexical recall only
  (`--no-vectors`: the embedding endpoint is not reachable from the evaluation; excerpts may differ with vectors).

```bash
cd apps/sidecar && uv run python ../../tools/eval_rp.py <cases> --db <restored copy> \
  --extractor <current generation> --policy packet-v4 --budget 800 --no-vectors
```

## Result

| Category | cases | passed | gold held | forbidden placed | mean tokens |
|---|---:|---:|---:|---:|---:|
| address | 2 | 0 | 2/2 | 2/2 | 782 |
| goal | 1 | 0 | 0/2 | 0/5 | 758 |
| irrelevant | 1 | 1 | — | 0/2 | 790 |
| past | 1 | 1 | 1/1 | — | 789 |
| promise | 1 | 1 | 1/1 | — | 734 |
| relationship | 2 | 2 | 2/2 | — | 786 |
| secret | 1 | 0 | 0/1 | — | 772 |
| state | 2 | 0 | 0/2 | — | 773 |
| why | 1 | 0 | 0/1 | — | 783 |
| **all** | **12** | **5** | **6/12** | **2/9** | **776** |

## What fails, and where Phase 11 addresses it

- **The persona's full name is a second character.** The chat names the persona both by the persona name and by a
  full name that ends with it; extraction uses both, and entity resolution (ADR 0023) joins only the exact
  persona name. Each pair then has two current speech levels (both address failures place the old one), and a
  promise made to "both" becomes two threads with equal text, so a resolution ties and closes neither (K23): the
  stale promises take room in every packet. The owner chose to join the names by hand in production (ADR 0025) and a
  resolver rule in step 3 (2026-09-28); this copy predates the join.
- **Goals never reach the packet.** No goal line was placed in any of the 12 packets, including the question about a
  character's goals; every goal ever stated stays "current" (115 across the owner's chats, PHASE-11 Evidence) and
  none outranks standing facts and threads. Steps 4–5.
- **Standing facts crowd out identity.** For "what does X do", speech levels and feelings of X (ranked first, ADR
  0026) filled the facts before X's occupation. Measured here; not in Phase 11's scope unless step 5's thread
  section changes the order.
- **A cause stated in a character's words is a claim.** The "why" answer is recorded in a feeling the character
  voiced, a claim (ADR 0013), which does not replace the narrated feeling and was not placed. Step 6 (`because`).
- **A secret a late turn marks is not placed** when the question does not share its words; the budget went to the
  stale promises above. Re-measured after step 3.

## After step 3 (ADR 0038)

Read side only (`resolve-v5`, one relationship history per pair, `packet-v5`), the same data, cases and extractor
generation; `--policy packet-v5`. Forbidden phrases count only as current: the earlier version a `packet-v5` line
names after "; before, turn N:" is past (the scorer's rule since this step; the baseline had no such lines).

| Category | cases | passed | gold held | forbidden placed | mean tokens |
|---|---:|---:|---:|---:|---:|
| address | 2 | 2 | 2/2 | 0/2 | 770 |
| goal | 1 | 0 | 0/2 | 0/5 | 787 |
| irrelevant | 1 | 1 | — | 0/2 | 758 |
| past | 1 | 1 | 1/1 | — | 774 |
| promise | 1 | 1 | 1/1 | — | 759 |
| relationship | 2 | 2 | 2/2 | — | 788 |
| secret | 1 | 0 | 0/1 | — | 769 |
| state | 2 | 0 | 0/2 | — | 776 |
| why | 1 | 0 | 0/1 | — | 787 |
| **all** | **12** | **7** | **6/12** | **0/9** | **775** |

No category is worse than the baseline. Under `packet-v4` with the new fold "past" fell to 0 of 1: the baseline's
pass came from the stale speech level, and the correct fold left no earlier version in the packet; `packet-v5` answers
it from the version the current one replaced. Goals, the secret, identity and the "why" case are for later steps.

## Expanded M0 (28 cases)

Twelve cases leave one or two per category, so one wording changes a category (see `docs/perf/extract-v13.md`). At the
owner's request (2026-09-28) the set grew to 28 at the same request (turn 73): 16 new questions, and gold that accepts
wordings of the same answer (for "how do they stand now": 좋아함, 역도 참, 설렘, 호감, 애정). The owner confirmed every
answer. The earlier numbers above are for the first 12 cases.

| Category | cases | `main` 075baf8, `packet-v4` | after step 3, `packet-v5` |
|---|---:|---:|---:|
| address | 5 | 2 | 4 |
| goal | 1 | 0 | 0 |
| irrelevant | 3 | 3 | 3 |
| past | 3 | 3 | 3 |
| promise | 3 | 2 | 2 |
| relationship | 4 | 3 | 3 |
| secret | 2 | 0 | 0 |
| state | 5 | 0 | 0 |
| why | 2 | 0 | 0 |
| **all** | **28** | **13** (forbidden placed as current 3/16) | **15** (1/16) |

The first run of step 3 on these cases had "past" at 2: `packet-v5` named only the version a standing fact replaced,
and "what did he call her at first" needs the earliest. `packet-v5` now names that too when it differs (ADR 0038).

## Scoring corrected: what the prompt already holds (step 6)

Every number above counts a gold answer only when the packet holds it. But memory leaves out what the request's prompt
already carries (D3, the recorded `in_context` window: 11 messages, the last five or six turns, for these requests), so
an answer there is not missing, and a case whose answers are all there does not test memory. `tools/eval_rp.py` now
counts a gold phrase found in those messages as held, says how many were, and reports the cases that need memory (a
gold phrase in no wording in the window) apart. Forbidden phrases still count in the packet only.

Of the 28 cases, 19 have every answer in the last turns; **9 need memory**.

| | cases passed (28) | needing memory, passed (9) | forbidden placed as current (16) |
|---|---:|---:|---:|
| `main` 075baf8, before Phase 11 (`packet-v4`, `extract-v12` facts) | 23 | 5 | 3 |
| step 3, 7c1e740 (`packet-v5`) | 25 | 7 | 1 |
| steps 4–5, 7709f23 (`packet-v5`, `extract-v13` re-extraction) | 26 | 7 | 0 |
| step 6 (`packet-v6`) | 26 | 7 | 0 |
| `packet-v7`, the new default (ADR 0041; same copy and facts as step 6) | 26 | 7 | 0 |

The two memory cases still failing are the goal case (an old open goal loses to newer ones, K23) and a "why" about a
status later statuses replaced (current facts do not reach it). Measuring memory needs cases whose answers lie outside
the prompt window; this chat's recorded requests are all at its last turns.

`packet-v7` renumbers the 16 excerpt lines of these 28 packets (their positions were 22 to 68 above the turns of their
messages) and changes nothing else in them.

## Phase 12 cases: answers outside the prompt window (Phase 12 step 2)

PHASE-12 Q8: 12 new cases at the same request (turn 73), each with every answer only in turns 0–66, outside the
request's prompt window (checked against its `in_context` messages). Drafted from the chat and confirmed by the owner
(2026-09-28, all 12 as drafted). They stay outside the repository with the others. Categories: an early event (6), why
something early was so (1), what has happened so far (2), and a character's lasting state (3).

The baseline is `main` after Phase 11: the copy whose longest chat was re-extracted with `extract-v13`, `packet-v6`,
budget 800 and lexical recall only, as above.

| Category | cases | passed on `main` (Phase 11) | gold phrases held |
|---|---:|---:|---:|
| early event | 6 | 1 | 1 of 6 |
| why | 1 | 0 | 0 of 1 |
| story so far | 2 | 0 | 0 of 5 |
| lasting state | 3 | 1 | 1 of 3 |
| **all** | **12** | **2** | **2 of 15** |

Every one needs memory. The two that pass have their answer in a fact line the question's words reach: two events
of the same gift, and a possession. The rest were said once, early, and no line the packet chooses carries them. The
packets used 737–789 of 800 tokens.
