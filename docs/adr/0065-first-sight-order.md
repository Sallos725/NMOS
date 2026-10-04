# 0065 — A chat seen for the first time is extracted in story order

Status: accepted, 2026-10-04 (`docs/phases/PHASE-30.md` Q1–Q4, approved by the owner; NMO-36 under AGE-24). Changes
the worker's order for every extractor generation; no prompt, generation key, stored row, setting or migration changes.

## Context

Every list an extraction is shown (KNOWN ENTITIES, OPEN PROMISES, OPEN SECRETS, OPEN THREADS, and under `extract-v16`
CURRENT ROLES and NAME PAIRS) is read from the turns before the target that the same generation has already extracted
(`extraction.earlier_assertions`). A generation's backfill was already claimed oldest first for this reason (PHASE-10,
ADR 0033). A chat's first sight was claimed newest first, with live turns, because nothing served those turns yet: so
every turn was extracted before every turn before it, and every list was empty. Measured on `extract-v16` (#251,
`docs/perf/extract-v16-q5c-s1.md`, S1 once): first connection roles 4/7 and names 1/3, against 7/7 and 3/3 in story
order. The newest turns are the ones the host prompt still carries, and their messages are embedded before any
extraction runs, so extracting them first served little.

## Decision

1. **A first sight's window is claimed oldest first** (Q1). `enqueue_after_apply` queues it at `FIRST_PRIORITY` (210:
   after live turns, 100, and canon facts, 150; before a generation's recent window, 250), in turn order; `claim` takes
   that priority, like `RECENT_PRIORITY` and later, in id order. The window is unchanged (the latest
   `NMOS_EXTRACT_BACKFILL` turns). 210, not 200: an embedding rebuild's recent window is 200 and keeps its order.
2. **A live turn waits behind its chat's first-sight window** (Q2). While the chat has an extract job of the same
   generation at `FIRST_PRIORITY` queued or running (`first_sight_pending`), a newly eligible turn is queued at
   `FIRST_PRIORITY` too, so it is claimed after every earlier turn; otherwise at `LIVE_PRIORITY` (100), newest first, as
   before. A dead job holds nothing; a job waiting for a retry holds the chat's later first-sight jobs in `claim` (added
   on the review of #260). A held turn holds the turns after it the same way, so the chat drains in order.
   Each turn is extracted once.
3. **Embedding keeps its priorities** (150 on a first sight, 50 live) and order; it no longer derives them from the
   extraction's.
4. **Concurrency is unchanged** (Q3): with two workers, a turn can be extracted while an earlier one is still running and
   miss what it establishes; a slow turn can leave several later turns without it. A generation's backfill has the same
   gap.

## Consequences

- A long chat connected for the first time gets every generation's lists from its first extraction on; `extract-v16`'s
  corrections apply to it. PHASE-28 Q2's limit is removed for the window.
- The facts of the window's newest turns arrive last; the total time to extract the window is unchanged.
- Fewer turns need a reveal check (ADR 0057 item 4): a turn is no longer extracted before the earlier turn that holds a
  secret.
- Turns before the window still move to the generation only through "extract all history" (D22), after the window, so
  the window's turns do not see them.
- Rejected: the newest K turns first and again at the end (a second call per turn, a discarded extraction, a K to
  tune); a second pass over the whole window (twice the cost); live turns first and re-extracted afterwards (the same
  costs).
