# Phase 30 — A chat seen for the first time is extracted in story order

> **Status: approved 2026-10-04 (the owner: as proposed), current as a correction phase (AGENTS §7 item 5); step 2 in
> review (#260).** NMO-36 under AGE-24; a correction found by measurement, not roadmap Stage 7 or 8. It changes the
> worker's order for every extractor generation, `extract-v15` included, and no prompt, generation key or stored row
> (ADR 0065, D74).

## Questions and proposed answers

| # | Question | Proposed answer | Alternatives considered |
|---|---|---|---|
| Q1 | In what order is a chat seen for the first time extracted? | **Oldest turn first, within the window a first sight already queues** (the latest `NMOS_EXTRACT_BACKFILL` turns, default 100; the window does not change). Every turn's hints then come from the turns before it that this generation has already extracted, as in a generation's backfill (ADR 0014, PHASE-10). The first-sight jobs keep a lane of their own: before a generation's recent window (250) and after canon facts (150) and live turns (100), as today, but claimed in id order instead of newest first (a value of its own: a generation's embedding rebuild also uses 200). First-sight embedding keeps its priority and order (recall uses vectors directly, and an embedding needs no other row). | **(나) of NMO-36:** the newest K turns first, the rest oldest first, then the K turns again over the hints the rest gave. The K turns are the ones the host prompt still carries, so extracting them first adds little; they cost a second call each, and their first extraction has to be discarded and replaced (PHASE-22's re-extraction path, reveal checks) and has a K to tune. **(다):** keep newest first, then re-extract the whole window once (about twice the cost of a first connection). Keep newest first and document the limit (NMO-36 (가); the v16 corrections do not apply to a long chat connected for the first time). |
| Q2 | What happens to live turns that arrive while the first-sight work is still pending? | **They queue behind it, in the same lane.** While the chat has a first-sight extract job of the active generation queued or running, a newly eligible turn of that chat takes the first-sight lane instead of the live one, so it is extracted after every earlier turn, with their hints. A dead job does not hold anything (it is neither queued nor running), so a failed turn cannot hold the chat back; a job waiting for a retry does, and the chat's later first-sight jobs wait for it too (`claim`; *added 2026-10-04 on Copilot's review of #260*). Once the first-sight jobs are done, live turns run at once again. Each turn is extracted once, as today. | Live turns first, then re-extract those turns once the first-sight work is done (what the chat discussion first proposed; a second call per such turn and a discarded live extraction, the same costs as (나)). Live turns first, never redone (they keep the empty or partial hints this phase removes). |
| Q3 | Does the worker's concurrency change? | **No.** With `NMOS_WORKER_CONCURRENCY` (default 2), a turn can be extracted while an earlier one is still running, and miss what that one establishes: while one worker is held on a slow turn, the other can take several turns after it, so the gap is not bounded to one turn. A generation's backfill has the same gap today. Measured (Q6 (c)), not changed. | One worker per chat during a first sight (about twice as slow for a long chat, and a new claim rule). |
| Q4 | What else does the order touch? | **Nothing stored, keyed or prompted.** Every generation keeps its key; nothing re-extracts; no migration; `extract-v15`'s and `extract-v16`'s prompts unchanged. Behavior that changes for every generation: a first connection's hints (KNOWN ENTITIES, OPEN PROMISES, OPEN SECRETS, OPEN THREADS, and under `extract-v16` CURRENT ROLES and NAME PAIRS) are no longer empty, and the facts of the newest turns of the window arrive last instead of first. Scene summaries (300 and later) still wait for extraction's live and recent work. Reveal checks (ADR 0057 item 4): fewer turns need one, since a turn is no longer extracted before the earlier turn holding a secret. Request path: unchanged (it only enqueues). | — |
| Q5 | What about the request served before the window is extracted? | **Accepted, and measured:** the newest turns' facts arrive last. The host prompt still carries those turns, and their messages are embedded first (first-sight embedding, 150), so recall over them works before any extraction. The time until the window is extracted is the same total as today; the report gives it, and when the newest turn's facts were written. | Newest K first (Q1's (나)). |
| Q6 | How is it measured? | **Deterministic cases in CI, then one first connection of S1 on `extract-v16`** (below, "Measurement"), each paid run after an owner-approved estimate, every result reported. | — |
| Q7 | Where does it land? | **Its own PR off `main` (#260, with this spec)**, independent of #251: the order is not part of `extract-v16`. The paid measurement needs `extract-v16`, now on `main` (#251 merged 2026-10-04), so it runs on #260's head. | Inside #251 (it already carries Phases 28 and 29, and this changes every generation, not v16 alone). |
| Q8 | What is not in this phase? | The first-sight window (`NMOS_EXTRACT_BACKFILL`): turns before it are still extracted only by "extract all history" (D22), after the window, so the window's turns do not see them; a role set up before the window stays invisible to it. Embedding order. A generation's backfill, which already runs oldest first. Any prompt, hint, reconciliation or resolver change. A default switch to `extract-v16` or a release. | — |

## Goal

NMOS extracts a chat it sees for the first time newest turn first (`extraction.claim`: live and first-sight work runs
newest first, because nothing serves those turns yet). Every hint an extraction is shown is read from the turns before
it that the same generation has already extracted (`earlier_assertions`), so newest first leaves each turn's hints
empty: at the moment a turn is extracted, no turn before it has been. `extract-v16`'s corrections live entirely in those
hints (CURRENT ROLES to end a role as listed, NAME PAIRS and KNOWN ENTITIES to join a name said two ways), so none of
them applies to a long chat connected for the first time. PHASE-28 Q2 recorded this as a limit; Q5 (c) measured it.

The reason given for newest first is weak for a first connection. The newest turns are the ones the host prompt still
carries, and their messages are embedded before any extraction runs; long-term memory matters for the turns that have
left the prompt, which newest first extracts last.

## Baseline

`docs/perf/extract-v16-q5c-s1.md` (#251, at `cc1f6e9`, generation `extract-b88669ca…`), S1 of the synthetic story, one
worker, all 240 turns queued:

| Lane | Order | Role scenes | Names at 239 | False join | Cost |
|---|---|---:|---:|---:|---:|
| First connection | newest first | **4/7** (87 move and 233 resignation not ended; 99 had no role before the scene) | **1/3** (강무진/무진, 윤하람/하람 apart) | 0 | $0.47 uncached, 18.6 min |
| Backfill (sequential S1, `9aa7c57`) | oldest first | 7/7 | 3/3 | 0 | about $0.51 |

Every first-connection extraction was shown no CURRENT ROLES, no NAME PAIRS and no known characters. The endings came
only as free negative roles in other words, which ADR 0013's value match does not close (233: `항해사: 청새치호에서 일함`
beside the listed `항해사로 고용됨`). A persona alias `도윤 → 정호` (turn 129, not confirmed: the persona's, PHASE-29 Q1)
left 도윤 ambiguous. The fresh sequential S1 on #251's review-fix generation (`6e4ca05`, report `6d85610`) passed 7/7 and 3/3 as well.

## In scope

1. The first-sight order (Q1) and the live-turn hold (Q2) in `extraction.enqueue_after_apply` and `extraction.claim`,
   with their docstrings and the priority comments that name the lanes (`canonfacts.PRIORITY`).
2. ADR 0065 and D74 recording the order, and notes on PHASE-28 Q2's and ADR 0064's limit.
3. Deterministic cases (below), and a pin that every generation key and the extraction prompts are unchanged.
4. The measurement (Q6) and the decision it supports.

## Out of scope

Q8, and: a migration, a new setting, a new job kind, a change to the worker's concurrency, any change to a generation's
backfill or to "extract all history".

## Measurement

**(a) Zero-call.** Deterministic tests (the sidecar's job tests, test Postgres):

- a first sight's extract jobs are claimed oldest turn first; its embed jobs as before;
- a live turn of another chat, or of this chat once its first-sight jobs are done, is claimed before them, newest first;
- a live turn of a chat with a first-sight job queued or running is claimed after that chat's first-sight jobs, and a
  dead first-sight job holds nothing;
- a generation's recent window and history, canon facts, reveal checks and summaries keep their priorities and order;
- every generation key and both extraction prompts unchanged.

**(b) One first connection of S1 on `extract-v16`, one worker**, with Q5 (c)'s first-connection envelope and grading
(`first-s1-cc1f6e9/`: S1 synced at once into a fresh database, all 240 turns, main `max_tokens` 8,192, one 64-call
ceiling for confirmations, input stop 4.2M, no retry; prefix reads before and after each declared scene, the names at
the end, every alias and negative role reviewed). The only change is the order. Estimate: 240 main calls plus
confirmations, about **$0.50 (약 700원)**, about 20 minutes. Bar, fixed before the run: role scenes 7/7, names 3/3 at
239, no false join, no technical error; report the newest turn's extraction time and the total.

**(c) Optional, the owner's choice: the same with two workers** (the product default), about **$0.50 (약 700원)**,
about 10 minutes: what the concurrency gap (Q3) costs on S1. Not gating unless it misses a scene that (b) passes; then it
is a stop condition.

**Result of (b), 2026-10-04:** passed on `1388ea2` (generation `extract-409d69e0…`): role scenes 7/7, names 3/3, no
false join, no technical error; 252 calls, $0.51 uncached, 15.4 min; the turns taken 0, 1, 2, … 239
(`docs/perf/phase30-first-s1.md`). Outside the declared scenes, the sponsorship cancelled at 134 was recorded as a broken
promise and ended only at 227 (PHASE-28's 227 class; the sequential S1 on the same generation ended it at 134).

No `extract-v15` run is proposed: its prompt is unchanged and its hints can only gain content. One is possible at about
the same cost if the owner wants the change checked under the default generation.

## Acceptance criteria

- [x] **Keys and prompts unchanged**: every generation key and both extraction prompts as before (full sidecar suite,
  1,098 passed).
- [x] **Deterministic** (a): every case above (`tests/test_first_sight_order.py`; the K29 recovery tests now start from a
  chat first imported before Phase 30, and a first import matches the reveal at once).
- [x] **First connection** (b): role scenes 7/7, names 3/3, no false join (2026-10-04, `1388ea2`, $0.51;
  `docs/perf/phase30-first-s1.md`; one wrong timing outside the declared scenes, the 227 class).
- [ ] (c) reported if the owner runs it (not run).
- [ ] Diff-scoped self-review naming the guarantees at risk; STATUS, ADR 0065, D74, the PHASE-28 Q2 and
  ADR 0064 notes and NMO-36 updated.

## Steps

1. This document, approved (2026-10-04); AGENTS §1/§2 and STATUS name Phase 30.
2. Implementation, ADR 0065, D74 and deterministic cases (`tests/test_first_sight_order.py`) on the same PR, #260
   (Q7). #251 merged first (2026-10-04); its pin of the old order in `test_extract_v16.py` now expects the ending
   (`test_a_first_connection_lists_the_role_before_the_turn_that_ends_it`).
3. The measurement (b), and (c) if chosen, after the estimate is approved, on #260's head.
4. The decision: merged as the order for every generation, or withdrawn (NMO-36 (가): the limit documented).

## Stop conditions

Stop and ask the owner when: (b) misses its bar; (c) misses a scene (b) passes; a false join on any run; a generation
key, an extraction prompt or the request path changes; a migration, new setting or runtime dependency would be needed;
a held live turn could wait on anything other than its chat's queued or running first-sight jobs; a paid run would exceed
its approved estimate.

**Known risk.** S1 is one development story. The order fixes the input `extract-v16` was designed for; it does not
make the model's answers right. The window bounds the gain: a long chat whose roles were set up before its latest 100
turns still starts with them unknown (Q8).

**High risk (AGENTS §14):** extraction order and generations, current versus historical role state, identity and
provenance through the names the hints carry.
