# Owner repair — measurements (Phase 13, Stage 6 part 1)

Phase 13 (`docs/phases/PHASE-13.md`) lets the owner repair memory: close or reopen a thread, retract or correct a
fact, mark a secret found out, split two names. This file records what it is measured against. Numbers only: what
the chat says stays outside the repository (the owner's lists and the scripts that use them are with the M0 cases).

## The owner's lists (step 2, 2026-09-28)

The restored copy of the owner's backup (PHASE-11 Q1; read-only), its longest chat (74 turns, 147 messages), as
`extract-v13` read it. NMOS drafted a decision for every open thread and every secret still kept from someone, with
the turns that suggest it; the owner confirmed the draft as it was.

| | Open or kept now | The owner's decision |
|---|---:|---|
| Threads (37 goals, 10 questions, 12 promises) | 59 | 50 ended in the story (closed at the turn that ends them), 9 still under way |
| Secrets (of 19; 5 already ended) | 14 | 6 found out by the character they were kept from, 2 never kept (the character was only away), 6 still kept |

- Of the 50 ended threads, one is the "end matching no open thread" of that chat that has a thread to match (the
  closing turn named the thread's counterpart as its maker); the other 8 unmatched ends have no open thread.
- The 9 still under way are daily or repeated plans, plans for later the same day, a secret still being kept and a
  wish not yet met.

## Baseline on `main` (step 2, 54f896a)

`packet-v8`, budget 2,000, no vectors, the chat's recorded requests with the M0 cases' messages (40 cases:
`docs/perf/m0-baseline.md`, `docs/perf/summaries.md`).

| | `main` |
|---|---:|
| M0, 28 cases (need memory) | 26 (7 of 9) |
| M0, 12 cases outside the prompt window | 5 |
| Secret gate: scenes with no forbidden word in `<Story>` | 6 of 6 |
| Secret gate: scenes with `<Story>` at all | 0 of 6 |
| Packets carrying a thread the owner closed | 40 of 40 |
| Lines of threads the owner closed, in all 40 packets | 113 (16 distinct threads) |
| Lines of threads the owner kept open, in all 40 packets | 64 |

Every packet carries at least one thread the story ended long before; the step's measure is that none does once the
owner's repairs are applied. `<Story>` is held in all six gate scenes: with the stricter check in front of a character
a secret is kept from (ADR 0042 amendment 3), secrets the story already told still hold it; marking them found out
should let it back where no secret remains, with no forbidden word.

## With the owner's repairs (step 6, 2026-09-28)

Code: `main` after step 5 (6759cd5) and this step's changes. Each restored copy was copied again (`CREATE DATABASE …
TEMPLATE`), migrated to 0024, and the owner's decisions were made as repairs the way the panel makes them
(`repairs.plan`, then an `owner_repair` row). No worker ran and no model was called; replays as in step 2 (`packet-v8`,
budget 2,000, no vectors unless stated).

### The longest chat (the owner's lists of step 2)

58 repairs: 50 threads closed at the turn and with the outcome the owner chose, 8 secrets marked found out (6 found
out, 2 never kept). None was refused, and all 59 threads and 19 secrets then read as the owner decided.

| | `main`, no repairs | with the owner's repairs |
|---|---:|---:|
| Packets carrying a thread the owner closed | 40 of 40 | **0 of 40** |
| Lines of threads the owner closed | 113 | **0** |
| Lines of threads the owner kept open | 64 | 145 |
| M0, 28 cases (need memory) | 26 (7 of 9) | **27 (8 of 9)**: the goal case passes |
| M0, 12 cases outside the prompt window | 5 (gold held 7 of 15) | 5 (8 of 15) |
| Secret gate: scenes with `<Story>` | 0 of 6 | **6 of 6** |
| Secret gate: scenes with a forbidden word in `<Story>` | 0 of 6 | 0 of 6 (1 of 6 by the Phase 12 cases) |

- No M0 category is worse; the budget the closed threads used goes to the threads still under way.
- The secret gate: in one scene the story now names a plan of a child character, which a parent character it was kept
  from found out, by the owner's list, 52 turns before the scene. The Phase 12 case listed the words of that plan and of
  a second plan still kept together; the second plan's words are not in `<Story>`. The owner chose to judge the gate by
  their list: a case can now group its words by secret, and `tools/eval_secret_gate.py` reports the words of a secret
  the character has found out by the scene apart, as told, not forbidden.

### A second chat (sample 2, `docs/perf/m0-sample2.md`)

NMOS drafted the decisions for its 11 open threads and its one secret from the chat, and the owner confirmed the
draft as it was: 9 threads ended in the story (one threat ended by the character it threatened, which the story's
end did not match, K23), 2 are not over, and the secret is none (every character of that world has what it names).
10 repairs, none refused.

| | `main`, no repairs | with the owner's repairs |
|---|---:|---:|
| Packets carrying a thread the owner closed | 15 of 17 | **0 of 17** |
| Lines of threads the owner closed | 45 | **0** |
| M0, 17 cases, with vectors (need memory) | 12 (8 of 13) | 12 (8 of 13), the same cases |
| M0, 17 cases, lexical only | 8 (4 of 13) | 8 (4 of 13), the same cases |

### Latency (`tools/bench_story.py`, 10,000 messages)

Retrieve p50, the median of five rounds, each round running Phase 12 `main` (60965dd), this branch without repairs and
this branch with 100 live repairs in turn, pinned to two cores. The repairs are the costliest kind: a found out for each
of the six secrets and 94 retractions and corrections of facts (`BENCH_REPAIRS=100`).

| | retrieve p50, ms | against Phase 12 `main` |
|---|---:|---:|
| Phase 12 `main` | 117.6 | |
| Phase 13, no repairs | 119.3 | +1.7 |
| Phase 13, 100 repairs | 124.6 | **+7.0** |

The criterion (+5 ms with 100 live repairs) is missed by 2 ms; the owner accepted it (2026-09-28). With the owner's
own mix (50 thread closes, 8 secrets found out) on the longest chat, a memory read took 12.3 → 14.2 ms (+1.7 to +2.4,
three rounds).

- A first run gave +66 ms: every fact repair searched all of the head's assertions, and every retraction recomputed
  the version key of every fact. Fact repairs now look only at the rows of their turns, the result is built in one
  pass, and a retraction finds the restored version through the facts' version-key index.
- A read now fetches its conversation, the repairs in force and its last turn in one query, as Phase 12 fetched the
  conversation alone; the turn positions a later-turn correction needs are read only when there is one.
- What remains is the fact repairs' own work (about 2 ms for 94 of them over 5,000 facts) and reading the repairs.

### Upgrade and real host

- `tests/test_upgrade.py`: every recorded release and `main` fixture upgrades through migration 0024, and the owner
  closes a promise on the upgraded chat and takes the repair back.
- Real-host smoke (an isolated PocketRisu from `ghcr.io/pocketrisu/pocketrisu:latest`, a stub chat model, a stub
  extraction model, this branch's sidecar and worker, plugin build `b1f7a1a81fe0`): a goal set in play reached
  `<Cast>` in the next request; closed in the panel's Inspector with the outcome "abandoned", it was in neither `<Cast>`
  nor `<Threads>` of the next request; after undo in the Repairs section it was back in the one after. The Inspector
  showed the close controls (a box, the outcomes of the thread's kind, the button) on open threads, reopen on closed
  ones, "Needs attention" with a promise not restated for more than 30 turns, and the repair as taken back.


## Across a new generation (2026-10-01, ADR 0044 amendment 2)

Stage 6's criterion "every repair survives a rebuild and a new extractor generation", on real data. Production was
re-extracted with `extract-v14` (the owner, 2026-10-01) and restored as a copy on the test PostgreSQL; the owner's 68
repairs of step 6 (made on the `extract-v13` copies) were copied in with their stored targets and read as the panel
reads them. No worker, no model call; counts only (scripts in `~/nmos-eval/stage6-v14-repairs/`). The reference for
"the same item" is a v14 item of the same head whose quote shares a run of 12 characters or more with the v13 item's.

| | Longest chat (58) | Sample 2 (10) | Together |
|---|---:|---:|---:|
| Found again, by text only (before the amendment) | 23 | 6 | 29 |
| Found again, text then quote (the amendment) | 34 | 6 | **40** |
| Not found, though v14 has an item with the same quote | 0 | 0 | 0 |
| Not found: v14 has no item of that head with that quote | 24 | 4 | 28 |

- Of the 29 found by text before, 28 are the item the quotes name; one is found by its text in a turn where the two
  generations quote different sentences.
- Candidate rules on the 59 thread repairs (31 with a v14 thread of the same quote): the text match found 21 of those
  31; adding "the only item of that turn, kind and maker" found 29 but paired 15 threads with no quote in common;
  the quote alone found 31 with none paired otherwise. The amendment keeps the text match first, then the quote.
- Of the 28 not found, 19 have no item of that maker at the repair's turn (v14 did not state the thread or secret
  there, or at all), and 9 have one that quotes another sentence of the turn; they are listed as matching nothing.
- A memory read of the longest chat with its 58 repairs (24 matching nothing, so compared by quote on every read)
  takes 13.5–14.5 ms against 12.6–12.7 without the quote (medians of 31, three rounds); the head is checked before
  the quote, and a stored quote's runs of 12 characters are cached.
