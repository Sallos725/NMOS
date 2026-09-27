# 0040 — Stated causes in the packet, linked to the event they name

Status: accepted, 2026-09-28. Phase 11 step 6 (`docs/phases/PHASE-11.md`, Q4). Read side only: new default packet policy
`packet-v6`; no migration, no extractor change (`because` comes with `extract-v13`, ADR 0039).

## Context

`extract-v13` keeps the cause the story states on events, feelings, relationships, status and goals (`because`): on
the owner's chat re-extracted with it, 28 current facts and claims carry one (`docs/perf/extract-v13.md`). The packet
did not show it, so "why is she angry at him?" had no answer unless the excerpt search happened to find the sentence.
Q4 allows explicit links only: no inferred causality.

## Decision

1. **`packet-v6` (default):** `packet-v5` plus, on a fact or a claim with a stated cause, `; because: <the cause>`
   after the value (before the `before`/`first` of ADR 0038). A claim's cause is the speaker's.
2. **A why-question brings it.** Under `packet-v6` the cause's words count in a fact's relevance, and when the message
   asks why (왜, 어째서, 무슨 이유, why, how come) a fact or claim with a cause gains 1.0, about half a name mention.
   Without that, the standing facts of the same people (ADR 0026) took the slots first.
3. **Links, read time, for the Inspector.** A stated cause links to the earlier event it names when one clearly does:
   an event of the same subject or object (or with either as a participant), at most 5 turns back, whose value the cause
   repeats (trigram overlap 0.35 with the names of both left out, leading the next by 0.1). Nothing is stored and
   nothing is inferred: without a match the stated text stands alone. The Inspector shows the cause and, when linked,
   the event and its turn. The packet does not show links: a wrong one would tell the model a false turn.
4. **Resolutions** already link a thread's opening and end (ADR 0019, ADR 0039); the Inspector's thread table shows
   both.

## Consequences

- On the owner's chat, 2 of 28 causes link. Without the name rule a link joined a cause to a different event of the same
  people; without the 5-turn window a cause at turn 72 joined an invitation at turn 43. Both were wrong, so the rule is
  strict.
- M0 does not move with it: its "why" case that needs memory asks about a status that later statuses replaced, and
  current facts do not reach it (a history search would; Stage 7). The public memory evaluation has a case for it.
- `packet-v5` and earlier render and rank as before.
