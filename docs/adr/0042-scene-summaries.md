# 0042 — Scene summaries and the story so far, a `summarize` projection

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
7. **Off by default** (`NMOS_SUMMARIES=0`, and a `summaries` setting through the settings API, which the settings
   response reports under `extraction`; the panel's switch comes with the step that turns summaries on). Turning it off
   makes queued jobs obsolete. Step 5 turns it on by default, after the owner is told the backfill's size (Q7).
8. The Inspector's chat page shows the story so far and each due window with its state (current, waiting)
   and text. Deleting a chat deletes its summaries (ADR 0009); a per-chat rebuild of facts leaves them. Whether a
   summary may be used is decided when it is read, not stored: the secrets it must not repeat can be extracted after
   it was written.

## Consequences

- Cost: each turn is read once more, in windows of about 25,000 characters on the owner's chats (extraction reads
  each turn with its 3 context turns). The story is redone once per 8 turns and on every change to a scene.
- An edit near the start of a long chat redoes one window and the story; a delete there redoes every later window.
- Nothing uses summaries in a packet before step 5.

## Amendment 1 — secrets (Phase 12 step 4, PHASE-12 Q3)

`summarize-v2`. The scene prompt lists the secrets stated by the window's last turn that are still kept from someone
(OPEN SECRETS, at most 12, newest first): never write their content or the object or act they are about, at most say
that the holders keep something. When a summary is read, `leaks` compares each secret still kept from someone with
it: trigram containment of the secret's content, the names of its holders and of those kept from left out of both,
at 0.7 or more marks the summary held (the Inspector shows it; step 5 keeps it out of packets). Secrets are read from
the head at that time, so a secret extracted after the summary was written counts too. The check catches a copied
secret (0.76 on the real-model tier), not a reworded one (about 0.3): the prompt is the guard, the check a backstop.
Real-model tier: `gemma4` 21/24, `deepseek` 24/24, neither wrote a secret's content (`docs/perf/summaries.md`).

## Amendment 2 — secrets stated after a summary (Phase 12 step 5)

`summarize-v3`. On the owner's chat a kiss at turns 61–63 was stated to be kept from a character only at turns 64 and
68, after the summaries of its window were written. The story so far then said it in other words, in the scene where
that character asks what happened.

- Each summary's prompt now lists the secrets stated up to 8 turns (`NEAR`) after its window, and records which it
  listed. The story's prompt lists them too.
- When a summary is read, a secret it should have listed and did not (`unlisted`) holds it, as a repeated one does.
- After each extraction the worker queues again every summary that such a secret now holds, and the story. A summary
  written again replaces the old one (the old row is discarded, kept for audit).

The same story then read "…신체적 접촉을 통해 애정을 확인했습니다" (`docs/perf/summaries.md`). A reworded secret can
still pass (K30).

## Amendment 3 — a stricter check in front of the character a secret is kept from (the secret gate, 2026-09-28)

The owner required a secret gate before summaries reach a packet (review of Phase 12). On the owner's restored chat
the `gemma4` story told Blanc "블랑의 수업에 몰래 잠입하는 작전", the plan the memory still holds as kept from her
(0.34, below the 0.7 bar). The owner chose a stricter bar only where it matters:
- when a character a secret is kept from is in the scene, a summary is held at 0.3 (`LEAK_NEAR`) instead of 0.7;
- elsewhere the bar stays 0.7.

On the owner's chat every one of the three main characters has a secret kept from her, so the story is held in most
of its scenes (all six gate scenes with the `gemma4` summaries). The gate passes 6 of 6 under both models' summaries
(`docs/perf/summaries.md`). The Inspector shows the general check (0.7), since it has no scene.

