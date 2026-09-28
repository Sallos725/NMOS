# 0041 — Scene summaries and the story so far, a `summarize` projection

Status: accepted, 2026-09-28. Phase 12 step 3 (`docs/phases/PHASE-12.md`, Q1, Q2, Q6, Q7). New projection kind
`summarize` (generation `summarize-v1`); migration 0023 (`summary`). Off by default until step 5 puts summaries in the
packet; nothing reaches a packet yet.

## Context

The packet carries facts, threads and excerpts that match the message. On the owner's longest chat the prompt's own
messages hold the last 5–6 of 74 turns, and of 12 owner-confirmed questions whose answers lie outside them, the packet
answers 2 (`docs/perf/m0-baseline.md`, Phase 12 cases). What was said once, early, and is not a current fact comes back
only when the question shares its words. The original design keeps summaries as derived, rebuildable layers above raw
text (§36–37); the owner chose scenes of 8 turns and a story so far (PHASE-12 Q1, Q2).

## Decision

1. **Scenes are fixed windows of 8 turns** of the head, turns as ADR 0008 counts them: 0–7, 8–15, …. A window is due
   when it is complete and 4 more turns have a reply (`LAG`): the last turns are the ones still rerolled and edited.
2. **A scene summary is keyed by its window's member revisions in order.** An edit, delete, swipe or disable inside
   the window gives it another key, so the summary stops being current at once, before the next packet (invariant 7),
   and the window is queued again. A delete or insert that renumbers turns moves every later window, which is redone.
   Summaries of the old keys stay stored and serve again if the head shows those windows again (a swipe back).
3. **The story so far is one summary of the current scene summaries**, keyed by their ids in order and made once
   every due window has one. A story stays current while every scene it was made from is current, so it keeps
   serving while the newest window waits; an edit in any of its scenes stops it until it is redone.
4. **Its own projection generation** (D20): kind `summarize`, the extraction model and endpoint (Q6), the prompt
   fingerprint, the normalizer, the window, the lag and the per-message cap (6,000 characters, as extraction's target
   turn). Changing any of them makes a new generation; rows of another generation are never read.
5. **Rows and jobs.** `summary` stores the level (scene, story), the key, the members (revisions, or scene
   summaries: provenance, invariant 10), the turn range, the text (capped at 1,200 and 2,400 characters), the model's
   reply and what it saw. Raw text is never replaced (invariant 1). Jobs run in the worker like extraction: a reply
   without a `summary` text fails the job and is retried (as G3); a job whose window the head no longer shows ends
   obsolete. Priorities: a window made due in play after extraction's live and recent work; a generation's backfill of
   every chat after extraction's history, oldest window first (Q7).
6. **Scheduling.** An append looks only at the newest due window; any other commit, and a generation's activation,
   look at every window. After a scene is written the story is queued when every due window has a summary.
7. **Off by default** (`NMOS_SUMMARIES=0`, and a `summaries` setting the plugin can change). Turning it off makes
   queued jobs obsolete. Step 5 turns it on by default, after the owner is told the backfill's size (Q7).
8. The Inspector's chat page shows the story so far and each due window with its state (current, waiting, held back)
   and text. Deleting a chat deletes its summaries (ADR 0009); a per-chat rebuild of facts leaves them.

## Consequences

- Cost: each turn is read once more, in windows of about 25,000 characters on the owner's chats (extraction reads
  each turn with its 3 context turns). The story is redone once per 8 turns and on every change to a scene.
- An edit near the start of a long chat redoes one window and the story; a delete there redoes every later window.
- `summarize-v1` has no secrets rule yet: step 4 adds OPEN SECRETS to the prompt and the check on the output, and
  `held_back` is written then. Nothing uses summaries in a packet before step 5.
